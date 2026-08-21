from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.ai import context_builder, intent_parser, memory_manager, narrator, narrative_validator
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import (
    ActionIntentType,
    CharacterStatus,
    CombatActorType,
    DiscoveryStatus,
    EventType,
    KnowerType,
    KnowledgeCertainty,
    TravelIncidentKind,
)
from app.core.logging import get_logger
from app.core.ids import generate_id
from app.db.models.character import Character
from app.db.models.location import CharacterLocationDiscovery, Location
from app.db.models.quest import QuestObjective
from app.game import game_state
from app.game.combat import bridge as combat_bridge
from app.game.combat import service as combat_service
from app.game.combat.recovery import recover_character
from app.game.items.interactions import (
    ITEM_INTERACTION_INTENTS,
    resolve_item_interaction,
)
from app.game.npcs import service as npcs_service
from app.game.players import service as players_service
from app.game.quests import service as quests_service
from app.game.relationships import service as relationship_service
from app.game.progression.outcomes import resolve_progression_outcome
from app.game.skills.techniques import (
    TECHNIQUE_ACTION_MINUTES,
    resolve_technique_use,
)
from app.game.time import clock
from app.game.travel import service as travel_service
from app.services.event_log import log_event
from app.services.story_log import get_recent_story_log
from app.simulation import world_simulation
from app.game.perception import service as perception_service

logger = get_logger("game")


class CharacterDeadError(Exception):
    pass


class CharacterIncapacitatedError(Exception):
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


def resolve_action(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character_id: str,
    text: str,
    *,
    technique_id: str | None = None,
    action_key: str | None = None,
) -> ActionResult:
    character = db.get(Character, character_id)
    if character is None or character.campaign_id != campaign_id:
        raise ValueError(f"Personagem desconhecido nesta campanha: {character_id}")
    if character.status == CharacterStatus.DEAD:
        raise CharacterDeadError("Este personagem morreu. A morte é permanente — nenhuma ação é mais possível.")
    if character.status == CharacterStatus.INCAPACITATED:
        raise CharacterIncapacitatedError(
            "Este personagem está incapacitado e precisa ser estabilizado antes de agir."
        )
    if character.region_id is None or character.location_id is None:
        raise WorldNotStartedError("Inicie o mundo antes de realizar uma ação.")

    state = game_state.build_game_state(db, campaign_id, character_id)

    active_npc = npcs_service.get_active_interlocutor(
        db,
        campaign_id,
        character_id,
        character.location_id,
    )

    active_simulated_player = (
        players_service.get_active_simulated_player_interlocutor(
            db,
            campaign_id,
            character_id,
            character.location_id,
        )
    )

    context = context_builder.build_context(
        db,
        state,
        active_interlocutor=(
            active_npc.id
            if active_npc
            else None
        ),
        player_input=text,
        active_simulated_player=(
            active_simulated_player.id
            if active_simulated_player
            else None
        ),
    )

    mechanical_warnings: list[str] = []
    resolved_action_key = action_key
    technique_use = None
    if technique_id is not None:
        resolved_action_key = action_key or generate_id("action")
        technique_use = resolve_technique_use(
            db,
            campaign_id,
            character,
            technique_id=technique_id,
            action_key=resolved_action_key,
        )
        intent = Intent(
            type=ActionIntentType.TECHNIQUE,
            target=technique_use.technique.name,
            raw_text=text,
        )
    else:
        intent = intent_parser.parse(llm_service, text, context)
    logger.info("resolved intent=%s target=%r for character=%s", intent.type, intent.target, character_id)

    if technique_use is not None:
        mechanical_summary = technique_use.mechanical_summary
        minutes = 0 if technique_use.replayed else TECHNIQUE_ACTION_MINUTES
        progression = resolve_progression_outcome(
            db,
            llm_service,
            campaign_id,
            character,
            technique_use.progression_outcome,
        )
        mechanical_warnings.extend(progression.warnings)
    else:
        mechanical_summary, minutes = _apply_intent(
            db,
            campaign_id,
            character,
            intent,
            state,
            action_key=resolved_action_key,
        )

    # Capture who this action involved before advancing world time.
    # The NPC may become unavailable during the tick that follows.
    action_npc = npcs_service.get_active_interlocutor(
        db,
        campaign_id,
        character_id,
        character.location_id,
    )

    action_simulated_player = (
        players_service.get_active_simulated_player_interlocutor(
            db,
            campaign_id,
            character_id,
            character.location_id,
        )
    )

    if minutes > 0:
        if intent.type != ActionIntentType.TALK:
            clock.advance_world_time(
                db,
                campaign_id,
                minutes,
            )

        world_simulation.tick(
            db,
            campaign_id,
            minutes,
        )

    db.flush()

    fresh_state = game_state.build_game_state(db, campaign_id, character_id)
    recent_entries = get_recent_story_log(db, campaign_id, character_id)

    current_active_npc = npcs_service.get_active_interlocutor(
        db,
        campaign_id,
        character_id,
        character.location_id,
    )

    current_active_simulated_player = (
        players_service.get_active_simulated_player_interlocutor(
            db,
            campaign_id,
            character_id,
            character.location_id,
        )
    )

    context_npc = (
        action_npc
        or current_active_npc
    )

    context_simulated_player = (
        action_simulated_player
        or current_active_simulated_player
    )
    fresh_context = context_builder.build_context(
        db,
        fresh_state,
        active_interlocutor=(
            context_npc.id
            if context_npc
            else None
        ),
        player_input=text,
        active_simulated_player=(
            context_simulated_player.id
            if context_simulated_player
            else None
        ),
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

    if context_npc is not None:
        _teach_facts_revealed_in_narration(
            db,
            campaign_id,
            character,
            fresh_state,
            context_npc,
            player_input=text,
            narrated_text=validation.text,
        )

    action_has_interlocutor = (
        action_npc is not None
        or action_simulated_player is not None
    )

    is_dialogue = action_has_interlocutor and (
        intent.type == ActionIntentType.TALK
        or _looks_like_dialogue(text)
    )
    story_event = log_event(
        db,
        campaign_id,
        EventType.STORY_EXCHANGE,
        actor_type="character",
        actor_id=character.id,
        payload={
            "action_key": resolved_action_key,
            "technique_id": technique_id,
            "player_text": text,
            "narrative": validation.text,
            "narrator_unavailable": narrator_unavailable,
        },
        importance=2 if is_dialogue else 1,
    )

    if is_dialogue and action_npc is not None:
        relationship_service.record_npc_interaction(
            db,
            campaign_id,
            character.id,
            action_npc.id,
        )

        memory_manager.remember_dialogue(
            db,
            story_event,
            character,
            action_npc,
            text,
            validation.text,
            importance=(
                3
                if intent.type == ActionIntentType.TALK
                else 2
            ),
        )

    if (
        is_dialogue
        and action_simulated_player is not None
    ):
        relationship_service.record_simulated_player_interaction(
            db,
            campaign_id,
            character.id,
            action_simulated_player.id,
        )

        memory_manager.remember_simulated_player_dialogue(
            db,
            story_event,
            character,
            action_simulated_player,
            text,
            validation.text,
            importance=(
                3
                if intent.type == ActionIntentType.TALK
                else 2
            ),
        )

    db.commit()

    return ActionResult(
        narrative=validation.text,
        narrator_unavailable=narrator_unavailable,
        mechanical_summary=mechanical_summary,
        intent_type=intent.type.value,
        warnings=[*mechanical_warnings, *validation.warnings],
    )


def _teach_facts_revealed_in_narration(
    db: Session,
    campaign_id: str,
    character: Character,
    fresh_state,
    context_npc,
    *,
    player_input: str,
    narrated_text: str,
) -> None:
    """If the narrator actually voiced one of the active NPC's known facts,
    mechanically teach that same fact to the player. The narrator itself
    never gains authority to grant knowledge — this only promotes a fact
    the backend already trusts (it's in the NPC's own NPC KNOWLEDGE) once
    the produced text shows it was genuinely said, not merely available."""
    revealed_facts = context_builder.active_npc_relevant_facts(
        db,
        fresh_state,
        context_npc.id,
        player_input=player_input,
    )
    for fact in revealed_facts:
        if context_builder.fact_is_revealed_in_text(fact, narrated_text):
            npcs_service.teach_fact(
                db,
                campaign_id,
                fact.fact_key,
                KnowerType.PLAYER,
                character.id,
                source=f"revelado por {context_npc.name}",
                certainty=KnowledgeCertainty.CONFIRMED,
            )


def _estimate_talk_seconds(text: str) -> int:
    """
    Estimate conversational time from the player's text.

    Uses roughly 2.5 spoken words per second, with a
    minimum of 2 seconds for very short interactions.
    """

    word_count = len(text.split())

    estimated_seconds = (
        word_count * 2 + 4
    ) // 5

    return max(
        2,
        estimated_seconds,
    )


def _looks_like_dialogue(text: str) -> bool:
    stripped = text.strip()
    return bool(
        stripped.startswith(("—", "-", '"', "'"))
        or "?" in stripped
        or "—" in stripped
    )


def _apply_intent(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    state,
    *,
    action_key: str | None = None,
) -> tuple[str, int]:
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
        return _handle_rest(
            db,
            campaign_id,
            character,
            action_key=action_key,
        )
    if intent.type == ActionIntentType.WAIT:
        return f"{character.name} espera, deixando o tempo passar.", 15
    if intent.type == ActionIntentType.SKILL_CHECK:
        return _handle_skill_check(db, campaign_id, character, intent)
    if intent.type in ITEM_INTERACTION_INTENTS:
        return _handle_item_interaction(
            db,
            campaign_id,
            character,
            intent,
            action_key=action_key,
        )
    if intent.type == ActionIntentType.ATTACK:
        return combat_bridge.handle_attack_intent(
            db,
            campaign_id,
            character,
            intent,
            state,
            action_key=action_key,
        )
    if intent.type in combat_bridge.TACTICAL_INTENT_MAP:
        return combat_bridge.handle_combat_tactic_intent(
            db,
            campaign_id,
            character,
            intent,
            state,
            action_key=action_key,
        )

    return f"{character.name} tenta: \"{intent.raw_text}\". Nenhum sistema mecânico específico se aplica ainda.", 1


def _handle_item_interaction(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    *,
    action_key: str | None,
) -> tuple[str, int]:
    if combat_bridge.get_active_encounter_for_actor(
        db, CombatActorType.CHARACTER, character.id
    ) is not None:
        return combat_bridge.handle_item_interaction_intent(
            db,
            campaign_id,
            character,
            intent,
            action_key=action_key,
        )
    try:
        result = resolve_item_interaction(
            db,
            campaign_id,
            character,
            interaction=intent.type,
            target=intent.target,
            secondary_target=intent.secondary_target,
            slot=intent.slot,
            interaction_key=action_key,
        )
    except ValueError as exc:
        return f"A interação com o item não pôde ser realizada: {exc}", 0
    return result.summary, 0 if result.replayed else 1


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
        travel_result = travel_service.move_character(
            db,
            campaign_id,
            character,
            destination.id,
            pace=intent.pace,
        )
    except travel_service.TravelError as exc:
        return str(exc), 0

    summary = (
        f"{character.name} viaja até {destination.name}. "
        f"A viagem leva {travel_result.minutes} minutos e consome "
        f"{travel_result.stamina_spent:g} de stamina."
    )

    if travel_result.incident is not None:
        if travel_result.incident.kind == TravelIncidentKind.DELAY:
            summary += (
                f" Um incidente na rota causa um atraso adicional de "
                f"{travel_result.incident.extra_minutes} minutos."
            )

        elif travel_result.incident.kind == TravelIncidentKind.FATIGUE:
            summary += (
                f" Um incidente na rota causa "
                f"{travel_result.incident.extra_stamina:g} de fadiga adicional."
            )

    return summary, travel_result.minutes


def _handle_talk(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    state,
) -> tuple[str, int]:
    npc = None
    simulated_player = None

    if intent.target:
        target_lower = intent.target.casefold()

        npc_matches = [
            candidate
            for candidate in state.nearby_npcs
            if target_lower in candidate.name.casefold()
        ]

        simulated_player_matches = [
            candidate
            for candidate in state.nearby_simulated_players
            if target_lower in candidate.name.casefold()
        ]

        matches = [
            ("npc", candidate)
            for candidate in npc_matches
        ] + [
            ("simulated_player", candidate)
            for candidate in simulated_player_matches
        ]

        if len(matches) > 1:
            return (
                "Há mais de uma pessoa correspondente "
                "a essa descrição aqui.",
                0,
            )

        if len(matches) == 1:
            kind, person = matches[0]

            if kind == "npc":
                npc = person
            else:
                simulated_player = person

    else:
        nearby_people = [
            ("npc", candidate)
            for candidate in state.nearby_npcs
        ] + [
            ("simulated_player", candidate)
            for candidate in state.nearby_simulated_players
        ]

        if len(nearby_people) == 1:
            kind, person = nearby_people[0]

            if kind == "npc":
                npc = person
            else:
                simulated_player = person

    if npc is None and simulated_player is None:
        return (
            "Não há ninguém correspondente a essa "
            "descrição aqui para conversar.",
            0,
        )

    if npc is not None:
        npcs_service.meet_npc(
            db,
            campaign_id,
            character.id,
            npc.id,
        )

        _auto_complete_talk_objectives(
            db,
            campaign_id,
            character,
            npc,
        )

        crossed_minutes = clock.advance_world_time_seconds(
            db,
            campaign_id,
            _estimate_talk_seconds(intent.raw_text),
        )

        return (
            f"{character.name} conversa com "
            f"{npc.name} ({npc.role}).",
            crossed_minutes,
        )

    players_service.meet_simulated_player(
        db,
        campaign_id,
        character.id,
        simulated_player.id,
    )
    
    crossed_minutes = clock.advance_world_time_seconds(
        db,
        campaign_id,
        _estimate_talk_seconds(intent.raw_text),
    )

    return (
        f"{character.name} conversa com "
        f"{simulated_player.name}.",
        crossed_minutes,
    )


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


def _handle_rest(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    action_key: str | None = None,
) -> tuple[str, int]:
    result = recover_character(
        db,
        campaign_id,
        character,
        recovery_key=action_key or generate_id("action"),
    )
    return (
        result.mechanical_summary,
        0 if result.replayed else result.recovery.duration_minutes,
    )


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
