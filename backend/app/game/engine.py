from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai import context_builder, intent_parser, memory_manager, narrator, narrative_validator
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import ActionIntentType, CharacterStatus, DiscoveryStatus, EventType
from app.core.logging import get_logger
from app.db.models.character import Character
from app.db.models.location import CharacterLocationDiscovery, Location
from app.db.models.quest import QuestObjective
from app.game import game_state
from app.game.combat import service as combat_service
from app.game.npcs import service as npcs_service
from app.game.progression import service as progression_service
from app.game.quests import service as quests_service
from app.game.relationships import service as relationship_service
from app.game.time import clock
from app.game.travel import service as travel_service
from app.services.event_log import log_event
from app.services.story_log import get_recent_story_log
from app.simulation import world_simulation
from app.game.perception import service as perception_service

logger = get_logger("game")


class CharacterDeadError(Exception):
    pass


class WorldNotStartedError(Exception):
    pass


@dataclass
class ActionResult:
    narrative: str
    narrator_unavailable: bool
    mechanical_summary: str
    intent_type: str
    warnings: list[str] = field(default_factory=list)


def resolve_action(db: Session, llm_service: LLMService, campaign_id: str, character_id: str, text: str) -> ActionResult:
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise ValueError(f"Personagem desconhecido nesta campanha: {character_id}")
    if character.status == CharacterStatus.DEAD:
        raise CharacterDeadError("Este personagem morreu. A morte é permanente — nenhuma ação é mais possível.")
    if character.region_id is None or character.location_id is None:
        raise WorldNotStartedError("Inicie o mundo antes de realizar uma ação.")

    state = game_state.build_game_state(db, campaign_id, character_id)
    active_npc = npcs_service.get_active_interlocutor(
        db, campaign_id, character_id, character.location_id
    )
    context = context_builder.build_context(
        db, state, active_npc.id if active_npc else None, player_input=text
    )

    intent = intent_parser.parse(llm_service, text, context)
    logger.info("resolved intent=%s target=%r for character=%s", intent.type, intent.target, character_id)

    mechanical_summary, minutes = _apply_intent(db, campaign_id, character, intent, state)

    if minutes > 0:
        clock.advance_world_time(db, campaign_id, minutes)
        world_simulation.tick(db, campaign_id, minutes)

    db.flush()

    fresh_state = game_state.build_game_state(db, campaign_id, character_id)
    recent_entries = get_recent_story_log(db, campaign_id, character_id)
    active_npc = npcs_service.get_active_interlocutor(
        db, campaign_id, character_id, character.location_id
    )
    fresh_context = context_builder.build_context(
        db, fresh_state, active_npc.id if active_npc else None, player_input=text
    )
    recent_history = context_builder.build_recent_history(recent_entries)
    canonical_facts = context_builder.build_canonical_facts(fresh_state)

    narrator_unavailable = False
    try:
        narrative_text = narrator.narrate(
            llm_service,
            mechanical_summary,
            fresh_context,
            player_input=text,
            recent_history=recent_history,
        )
    except LLMServiceError:
        narrative_text = mechanical_summary
        narrator_unavailable = True

    validation = narrative_validator.validate(narrative_text, canonical_facts)

    is_dialogue = active_npc is not None and (
        intent.type == ActionIntentType.TALK or _looks_like_dialogue(text)
    )
    story_event = log_event(
        db,
        campaign_id,
        EventType.STORY_EXCHANGE,
        actor_type="character",
        actor_id=character.id,
        payload={
            "player_text": text,
            "narrative": validation.text,
            "narrator_unavailable": narrator_unavailable,
        },
        importance=2 if is_dialogue else 1,
    )
    if is_dialogue and active_npc is not None:
        relationship_service.record_npc_interaction(
            db, campaign_id, character.id, active_npc.id
        )
        memory_manager.remember_dialogue(
            db,
            story_event,
            character,
            active_npc,
            text,
            validation.text,
            importance=3 if intent.type == ActionIntentType.TALK else 2,
        )

    db.commit()

    return ActionResult(
        narrative=validation.text,
        narrator_unavailable=narrator_unavailable,
        mechanical_summary=mechanical_summary,
        intent_type=intent.type.value,
        warnings=validation.warnings,
    )


def _looks_like_dialogue(text: str) -> bool:
    stripped = text.strip()
    return bool(
        stripped.startswith(("—", "-", '"', "'"))
        or "?" in stripped
        or "—" in stripped
    )


def _apply_intent(db: Session, campaign_id: str, character: Character, intent: Intent, state) -> tuple[str, int]:
    if intent.type == ActionIntentType.MOVE:
        return _handle_move(db, campaign_id, character, intent)
    if intent.type == ActionIntentType.TALK:
        return _handle_talk(db, campaign_id, character, intent, state)
    if intent.type == ActionIntentType.EXAMINE:
        return _handle_examine(
            db,
            campaign_id,
            character,
            intent,
        )
    if intent.type == ActionIntentType.REST:
        return _handle_rest(db, campaign_id, character)
    if intent.type == ActionIntentType.WAIT:
        return f"{character.name} espera, deixando o tempo passar.", 15
    if intent.type == ActionIntentType.SKILL_CHECK:
        return _handle_skill_check(db, campaign_id, character, intent)

    return f"{character.name} tenta: \"{intent.raw_text}\". Nenhum sistema mecânico específico se aplica ainda.", 1


def _handle_move(db: Session, campaign_id: str, character: Character, intent: Intent) -> tuple[str, int]:
    if not intent.target:
        return "Nenhum destino claro foi indicado.", 0

    destination = (
        db.query(Location)
        .join(
            CharacterLocationDiscovery,
            CharacterLocationDiscovery.location_id == Location.id,
        )
        .filter(
            CharacterLocationDiscovery.character_id == character.id,
            CharacterLocationDiscovery.status.in_(
                (
                    DiscoveryStatus.DISCOVERED.value,
                    DiscoveryStatus.VISITED.value,
                    DiscoveryStatus.MAPPED.value,
                )
            ),
            Location.region_id == character.region_id,
            Location.name.ilike(f"%{intent.target}%"),
        )
        .first()
    )
    if destination is None:
        return f"Nenhum lugar conhecido correspondente a '{intent.target}' pode ser alcançado a partir daqui.", 0

    try:
        minutes = travel_service.move_character(db, campaign_id, character, destination.id)
    except travel_service.TravelError as exc:
        return str(exc), 0

    return f"{character.name} viaja até {destination.name}.", minutes


def _handle_talk(db: Session, campaign_id: str, character: Character, intent: Intent, state) -> tuple[str, int]:
    npc = None
    if intent.target:
        target_lower = intent.target.lower()
        npc = next((n for n in state.nearby_npcs if target_lower in n.name.lower()), None)
    elif len(state.nearby_npcs) == 1:
        npc = state.nearby_npcs[0]

    if npc is None:
        return "Não há ninguém correspondente a essa descrição aqui para conversar.", 0

    npcs_service.meet_npc(db, campaign_id, character.id, npc.id)
    _auto_complete_talk_objectives(db, campaign_id, character, npc)

    return f"{character.name} conversa com {npc.name} ({npc.role}).", 10


def _auto_complete_talk_objectives(db: Session, campaign_id: str, character: Character, npc) -> None:
    """MVP shortcut: talking to an NPC named in an active quest objective completes it.
    A richer dialogue/objective-trigger system is future work."""
    for _cq, quest in _active_quests_for(db, character.id):
        objectives = db.query(QuestObjective).filter(QuestObjective.quest_id == quest.id).all()
        for objective in objectives:
            if npc.name in objective.description:
                quests_service.complete_objective(db, campaign_id, character.id, objective.id)


def _active_quests_for(db: Session, character_id: str):
    from app.core.enums import QuestStatus
    from app.db.models.quest import CharacterQuest, Quest

    links = (
        db.query(CharacterQuest)
        .filter(CharacterQuest.character_id == character_id, CharacterQuest.status == QuestStatus.ACTIVE)
        .all()
    )
    active = []
    for link in links:
        quest = db.get(Quest, link.quest_id)
        if quest is not None:
            active.append((link, quest))
    return active


def _handle_rest(db: Session, campaign_id: str, character: Character) -> tuple[str, int]:
    character.stamina_current = min(character.stamina_max, character.stamina_current + 10)
    character.hp_current = min(character.hp_max, character.hp_current + 5)
    log_event(db, campaign_id, EventType.PLAYER_RESTED, actor_type="character", actor_id=character.id)
    return f"{character.name} descansa, recuperando um pouco de stamina e vida.", 60


def _handle_skill_check(db: Session, campaign_id: str, character: Character, intent: Intent) -> tuple[str, int]:
    skill_name = intent.target or "Atletismo"
    result = combat_service.resolve_skill_check(db, character.id, skill_name)

    log_event(
        db,
        campaign_id,
        EventType.ACTION_CHECK_RESULT,
        actor_type="character",
        actor_id=character.id,
        payload={
            "skill": skill_name,
            "roll": result.roll.raw,
            "modifier": result.roll.modifier,
            "total": result.roll.total,
            "dc": result.dc,
            "success": result.success,
        },
    )

    if result.success:
        levels_gained = progression_service.add_xp(character, 5)
        log_event(
            db,
            campaign_id,
            EventType.PLAYER_GAINED_XP,
            actor_type="character",
            actor_id=character.id,
            payload={"amount": 5, "current_xp": character.xp},
        )
        if levels_gained:
            log_event(
                db, campaign_id, EventType.PLAYER_LEVELED_UP, actor_type="character",
                actor_id=character.id, payload={"new_level": character.level},
            )

    outcome = "tem sucesso" if result.success else "falha"
    critical = " (rolagem crítica)" if result.critical else ""
    summary = (
        f"{character.name} tenta uma ação baseada em {skill_name} e {outcome}{critical} "
        f"(rolou {result.roll.raw}+{result.roll.modifier}={result.roll.total} contra CD {result.dc}). "
        "Isto é uma checagem mecânica única, não uma resolução completa de combate."
    )
    return summary, 5

def _handle_examine(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
) -> tuple[str, int]:
    result = perception_service.observe_surroundings(
        db,
        character,
    )

    lines = [
        f"{character.name} observa os arredores de {result.location_name}.",
    ]

    if result.features:
        lines.append(
            "Elementos perceptíveis: "
            + "; ".join(result.features)
        )

    if result.routes:
        lines.append(
            "Rotas perceptíveis: "
            + "; ".join(result.routes)
        )

    if not result.features and not result.routes:
        lines.append(
            "Nenhum elemento adicional registrado pelo backend é perceptível."
        )

    return " ".join(lines), 2