from dataclasses import dataclass, field, replace
import hashlib
import re
import time
import unicodedata

from sqlalchemy.orm import Session

from app.ai import context_builder, intent_parser, memory_manager, narrator, narrative_validator
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService, LLMServiceError
from app.ai.conversational_act import economic_service_asked_about, is_price_question
from app.ai.observability import log_narrative_request
from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.core.config import get_settings
from app.core.enums import (
    ActionIntentType,
    CharacterStatus,
    CombatActorType,
    DiscoveryStatus,
    EventType,
    KnowerType,
    KnowledgeCertainty,
    ObjectiveTriggerType,
    TravelIncidentKind,
)
from app.core.logging import current_narrative_request_id, get_logger, with_narrative_request_id
from app.core.ids import generate_id
from app.db.models.character import Character
from app.db.models.location import (
    CharacterLocationDiscovery,
    Location,
    LocationConnection,
    LocationFeature,
)
from app.db.models.notice import Notice
from app.game import game_state
from app.game.combat import bridge as combat_bridge
from app.game.combat import hostility as combat_hostility
from app.game.combat import service as combat_service
from app.game.combat.recovery import recover_character
from app.game.items.interactions import (
    ITEM_INTERACTION_INTENTS,
    resolve_item_interaction,
)
from app.game.economy.economic_canon import (
    EconomicCanonError,
    materialize_economic_value,
    service_subject,
)
from app.game.npcs import service as npcs_service
from app.game.players import service as players_service
from app.game.notices.service import NoticeBoardError, read_notice_board
from app.game.quests import service as quests_service
from app.game.relationships import service as relationship_service
from app.game.progression.outcomes import resolve_progression_outcome
from app.game.skills.technique_experimentation import (
    TECHNIQUE_EXPERIMENT_MINUTES,
    resolve_technique_experiment,
)
from app.game.survival import service as survival_service
from app.game.skills.techniques import (
    TECHNIQUE_ACTION_MINUTES,
    resolve_named_technique,
    resolve_technique_use,
)
from app.game.time import clock
from app.game.travel import service as travel_service
from app.game.world.content_pools import SETTLEMENT_SERVICE_POOL
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


_DEFAULT_SERVICE_BY_LOCATION_TYPE = {
    "inn": ("lodging", "quarto", "por noite"),
    "blacksmith": ("repair", "reparo", "por serviço"),
    "stable": ("stabling", "estabulagem", "por noite"),
    "healer": ("healing", "tratamento", "por atendimento"),
    "shop": ("professional_service", "serviço comercial", "por serviço"),
}


def _materialize_requested_service_price(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character: Character,
    active_npc,
    player_input: str,
) -> None:
    if not is_price_question(player_input) or character.location_id is None:
        return
    location = db.get(Location, character.location_id)
    if location is None:
        return
    requested_key = economic_service_asked_about(player_input)
    fallback = _DEFAULT_SERVICE_BY_LOCATION_TYPE.get(location.type)
    if requested_key is None:
        if fallback is None:
            return
        requested_key, display_name, unit = fallback
    else:
        labels = {
            "lodging": ("quarto", "por noite"),
            "meal": ("refeição", "por unidade"),
            "repair": ("reparo", "por serviço"),
            "transport": ("transporte", "por viagem"),
            "stabling": ("estabulagem", "por noite"),
            "healing": ("tratamento", "por atendimento"),
            "crafting": ("fabricação", "por encomenda"),
            "labor": ("mão de obra", "por dia"),
            "rental": ("aluguel", "por período"),
        }
        display_name, unit = labels[requested_key]
    subject = service_subject(
        campaign_id,
        location.id,
        requested_key,
        f"{display_name} em {location.name}",
        unit=unit,
        provider_type="NPC",
        provider_id=active_npc.id,
    )
    try:
        materialize_economic_value(db, subject, llm_service=llm_service)
    except EconomicCanonError as exc:
        logger.debug(
            "economic materialization rejected location=%s service=%s reason=%s",
            location.id,
            requested_key,
            str(exc),
        )


@with_narrative_request_id
def resolve_action(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character_id: str,
    text: str,
    *,
    technique_id: str | None = None,
    action_key: str | None = None,
    intent_llm_service: LLMService | None = None,
) -> ActionResult:
    # Phase 24P — narrative_request_id is already set for the whole call
    # by the decorator above; captured here only so the summary line at
    # the end can report it and total latency alongside it.
    _narrative_request_started_at = time.monotonic()
    # Phase 24K — intent_llm_service is the NEW, optional role split;
    # llm_service (unchanged name/position, still positional) stays the
    # NARRATIVE-role service, used for narration, repair, and every
    # incidental content-generation helper this function calls, exactly
    # as before this phase. Defaulting to llm_service when not given
    # preserves every existing caller/test that only ever passed one.
    intent_llm_service = intent_llm_service or llm_service
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

    # S1.3: price Canon is materialized only when it first matters.  This
    # happens before context construction so the narrator receives the
    # accepted value on the same turn; failures degrade to an honest
    # "no established price" grounding rather than an invented number.
    if technique_id is None and active_npc is not None:
        _materialize_requested_service_price(
            db,
            llm_service,
            campaign_id,
            character,
            active_npc,
            text,
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
        intent = intent_parser.parse(intent_llm_service, text, context)
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
    elif intent.type == ActionIntentType.EXPERIMENT:
        resolved_action_key = resolved_action_key or generate_id("action")
        experiment = resolve_technique_experiment(
            db,
            campaign_id,
            character,
            raw_text=text,
            proposed_pattern_key=intent.pattern_key,
            proposed_domains=intent.domains,
            proposed_technique_type=intent.technique_type,
            action_key=resolved_action_key,
        )
        mechanical_summary = experiment.mechanical_summary
        minutes = 0 if experiment.replayed else TECHNIQUE_EXPERIMENT_MINUTES
        progression = resolve_progression_outcome(
            db,
            llm_service,
            campaign_id,
            character,
            experiment.progression_outcome,
        )
        mechanical_warnings.extend(progression.warnings)
    elif intent.type == ActionIntentType.TECHNIQUE:
        resolved_action_key = resolved_action_key or generate_id("action")
        named_technique = resolve_named_technique(db, character.id, intent.target)
        if named_technique is None:
            mechanical_summary = (
                f"{character.name} não conhece nenhuma técnica correspondente a "
                f"'{intent.target}'." if intent.target
                else f"{character.name} precisa dizer qual técnica está usando."
            )
            minutes = 0
        elif combat_bridge.get_active_encounter_for_actor(
            db, CombatActorType.CHARACTER, character.id
        ) is not None:
            mechanical_summary, technique_resolution = combat_bridge.handle_technique_intent(
                db,
                character,
                named_technique,
                intent.secondary_target,
                action_key=resolved_action_key,
            )
            minutes = 0
            if technique_resolution is not None:
                progression = resolve_progression_outcome(
                    db,
                    llm_service,
                    campaign_id,
                    character,
                    technique_resolution.progression_outcome,
                )
                mechanical_warnings.extend(progression.warnings)
        else:
            named_use = resolve_technique_use(
                db,
                campaign_id,
                character,
                technique_id=named_technique.id,
                action_key=resolved_action_key,
            )
            mechanical_summary = named_use.mechanical_summary
            minutes = 0 if named_use.replayed else TECHNIQUE_ACTION_MINUTES
            progression = resolve_progression_outcome(
                db,
                llm_service,
                campaign_id,
                character,
                named_use.progression_outcome,
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
            survival_service.apply_survival_decay(db, campaign_id, character)

        world_simulation.tick(
            db,
            campaign_id,
            minutes,
        )

        quests_service.check_deadlines(db, campaign_id, character_id)

        ambush = combat_hostility.resolve_ambush_for_character(
            db,
            campaign_id,
            character,
        )
        if ambush is not None:
            ambush_lines = [
                f"Enquanto isso, {ambush.npc_name} avança e inicia um combate "
                f"contra {character.name}."
            ]
            ambush_lines.extend(
                combat_bridge.describe_autonomous_resolution(db, resolution)
                for resolution in ambush.resolutions
            )
            mechanical_summary = f"{mechanical_summary} " + " ".join(ambush_lines)

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

    implicit_npc, implicit_simulated_player = _implicit_freeform_interlocutor_switch(
        db, campaign_id, character, intent, fresh_state
    )

    if implicit_npc is not None or implicit_simulated_player is not None:
        # An implicit switch resolves to exactly one interlocutor — never
        # fall through to the OTHER track's stale value, or both an NPC
        # and a simulated player would appear simultaneously "active" in
        # context, the exact ambiguity that let the model pick either one
        # inconsistently turn to turn (Phase 24J.1, confirmed via trace).
        context_npc = implicit_npc
        context_simulated_player = implicit_simulated_player
    else:
        context_npc = action_npc or current_active_npc
        context_simulated_player = action_simulated_player or current_active_simulated_player
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
    settings = get_settings()

    narrator_unavailable = False
    try:
        narrative_text = narrator.narrate(
            llm_service,
            mechanical_summary,
            fresh_context,
            player_input=text,
            recent_history=recent_history,
            enforce_player_agency=settings.narrative_player_agency_guard_enabled,
            automatic_validation=settings.narrative_automatic_validation_enabled,
        )
    except LLMServiceError:
        narrative_text = mechanical_summary
        narrator_unavailable = True

    final_narrative = narrative_text
    narrative_warnings: list[str] = []

    # Automatic narrative review is retained only as an opt-in diagnostic
    # mode. In normal play the first OpenRouter answer is persisted exactly as
    # returned; the player decides whether to regenerate it with feedback.
    if settings.narrative_automatic_validation_enabled:
        canonical_facts = context_builder.build_canonical_facts(fresh_state)
        validation = narrative_validator.validate(narrative_text, canonical_facts)
        narrative_proposal = NarrativeProposal(
            text=validation.text,
            mode="CONTINUATION",
            context=fresh_context,
            mechanical_summary=mechanical_summary,
            player_input=text,
            recent_history=recent_history,
            character_name=character.name,
            character_id=character.id,
            location_id=character.location_id,
            active_npc_id=context_npc.id if context_npc is not None else None,
            active_npc_name=context_npc.name if context_npc is not None else None,
            enforce_player_agency=settings.narrative_player_agency_guard_enabled,
        )
        narrative_validation = validate_narrative_proposal(
            db, campaign_id, narrative_proposal, llm_service
        )
        final_narrative = narrator.enforce_authorized_price_answer(
            narrative_validation.final_text,
            fresh_context,
            text,
            context_npc.name if context_npc is not None else "",
        )
        narrative_warnings = validation.warnings

    if context_npc is not None:
        _teach_facts_revealed_in_narration(
            db,
            campaign_id,
            character,
            fresh_state,
            context_npc,
            player_input=text,
            narrated_text=final_narrative,
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
            "narrative": final_narrative,
            "mechanical_summary": mechanical_summary,
            "narrator_unavailable": narrator_unavailable,
            # Phase 24D — the backend already resolved this deterministically
            # (context_npc, above); persisting it is the only way a LATER
            # turn's recent-history framing can attribute a past narrated
            # exchange to a specific NPC instead of just "the narrator" —
            # the LLM is never asked to infer or decide this after the fact.
            "npc_id": context_npc.id if context_npc is not None else None,
            "npc_name": context_npc.name if context_npc is not None else None,
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
            final_narrative,
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
            final_narrative,
            importance=(
                3
                if intent.type == ActionIntentType.TALK
                else 2
            ),
        )

    db.commit()

    # Phase 24P — one correlatable summary line per turn; every other
    # log line emitted anywhere above already carries the same
    # narrative_request_id automatically (app.core.logging's contextvar
    # filter), so this is the entry point for finding them, not a
    # duplicate of what they already contain.
    log_narrative_request(
        narrative_request_id=current_narrative_request_id(),
        campaign_id=campaign_id,
        character_id=character_id,
        active_npc_id=context_npc.id if context_npc is not None else None,
        player_input=text,
        # Phase 24K — role-aware: intent parsing and narration can now be
        # two different providers/models, so a single "model" field would
        # be misleading (and previously wasn't even accurate — it always
        # reported settings.ollama_model regardless of what actually
        # generated this turn). Read directly from each service instance
        # rather than Settings, so it's correct even when overridden in a
        # test. `model` is kept for back-compat with existing callers/
        # tests, mirroring narrative_model.
        model=llm_service.model_name,
        intent_provider=intent_llm_service.provider_name,
        intent_model=intent_llm_service.model_name,
        narrative_provider=llm_service.provider_name,
        narrative_model=llm_service.model_name,
        temperature=settings.ollama_temperature,
        num_predict=settings.ollama_num_predict,
        context_fingerprint=hashlib.sha256(fresh_context.encode()).hexdigest()[:12],
        context_chars=len(fresh_context),
        estimated_tokens=len(fresh_context) // 4,
        narrator_unavailable=narrator_unavailable,
        final_output=final_narrative,
        latency_ms=(time.monotonic() - _narrative_request_started_at) * 1000,
    )

    return ActionResult(
        narrative=final_narrative,
        narrator_unavailable=narrator_unavailable,
        mechanical_summary=mechanical_summary,
        intent_type=intent.type.value,
        # Phase 19S — narrative_validation.violations are internal
        # validator reasoning (e.g. "'Logan sorri...' atribui uma ação
        # voluntária..."), never player-facing: schemas/action.py
        # returns `warnings` verbatim over the public /actions API, and
        # the spec explicitly forbids surfacing claim-level rejection
        # reasons to the player. That information now goes through
        # app.ai.validation.trace's DEBUG-only log instead (called
        # inside validate_narrative_proposal).
        warnings=[*mechanical_warnings, *narrative_warnings],
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
    the produced text shows it was genuinely said, not merely available.

    This function cannot create arbitrary knowledge from prose: it only
    promotes a fact that was already present in the active NPC's canonical
    knowledge and whose authorized value appeared in the narration.
    """
    revealed_facts = context_builder.active_npc_relevant_facts(
        db,
        fresh_state,
        context_npc.id,
        player_input=player_input,
    )
    for fact in revealed_facts:
        revealed = context_builder.fact_is_revealed_in_text(fact, narrated_text)
        logger.info(
            "knowledge acquisition check: fact_key=%s subject=%s revealer=%s learner=%s "
            "persisted=%s",
            fact.fact_key,
            fact.subject,
            context_npc.id,
            character.id,
            revealed,
        )
        if revealed:
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
    if intent.type == ActionIntentType.FREEFORM:
        # Phase 24J.3 — scoped narrowly to FREEFORM (not e.g. TALK, which
        # already resolves its own targets and may legitimately mention a
        # place name in passing while addressing a person): every
        # confirmed live failure was the Intent Parser classifying clear
        # movement phrasing as FREEFORM instead of MOVE.
        movement_target = _resolve_movement_target(db, character, intent.raw_text)
        if movement_target is not None:
            intent = replace(intent, type=ActionIntentType.MOVE, target=movement_target.name)
    if intent.type == ActionIntentType.MOVE:
        summary, minutes = _handle_move(db, campaign_id, character, intent)
        # A compound utterance ("entra na estalagem e olha dentro") both
        # moves AND looks around in one turn — dispatching it to MOVE must
        # not silently drop the observation, or the new location's own
        # connections (e.g. the way back) never get discovered. Applies
        # regardless of whether MOVE came from this FREEFORM redirect or
        # was classified natively by the Intent Parser — confirmed via
        # live trace (req=nr_50465e57d586 / req=nr_bc3900cabbe6) that a
        # NATIVELY-classified MOVE for this exact phrasing bypassed the
        # FREEFORM branch entirely, so a version of this fix scoped only
        # to the backstop redirect still missed it: the settlement hub has
        # no self-discovery row of its own, and the only way to
        # (re)discover the route back is observing from the location the
        # character is now standing in.
        if _OBSERVATION_CUE_PATTERN.search(_strip_accents(intent.raw_text or "").casefold()):
            perception_service.observe_surroundings(db, character)
        return summary, minutes
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


_LOCATION_TYPE_LABELS_PT = {
    location_type: name for name, location_type, _description in SETTLEMENT_SERVICE_POOL.values()
}

# Phase 24J.3 — SETTLEMENT_SERVICE_POOL only labels services WITHIN a
# settlement (inn, blacksmith, ...); the settlement's own hub location
# ("village" type) has no entry there, yet players naturally refer to it
# generically ("praça central", "a vila") rather than by its procedurally
# generated proper noun. Confirmed via live playtest: "Logan volta para a
# praça central" matched zero candidates and silently stayed FREEFORM,
# leaving the character stranded at the previous destination.
_HUB_LOCATION_TYPE_LABELS_PT: dict[str, tuple[str, ...]] = {
    "village": ("praca central", "centro da vila", "praca", "vila"),
}

_OBSERVATION_CUE_PATTERN = re.compile(r"\bolha\b|\bobserva\b|\bexamina\b", re.IGNORECASE)

# Phase 24J.3 — a bare "sai da estalagem" (exit, no named destination)
# names the ORIGIN, not a destination, so it can never match anything by
# name/type-label — the Intent Parser was observed inventing a synthetic,
# non-existent target for exactly this phrasing ("fora da estalagem"),
# confirmed via live trace (req=nr_ae8dae921d71): the mechanical layer
# correctly refused that fake target, but the narrator still described a
# physical departure anyway, leaving character.location_id unchanged
# behind prose that claimed otherwise — the exact "movement in prose only"
# failure mode this whole phase exists to eliminate. Settlement services
# are hub-and-spoke (a leaf location connects back to exactly one "village"
# hub), so exiting one has an unambiguous, safe destination.
_EXIT_PHRASE_PATTERN = re.compile(r"\bsai\b|\bsaiu\b|\bsair\b", re.IGNORECASE)

_MOVEMENT_PHRASE_PATTERN = re.compile(
    r"\bvai\b.{0,20}\b(direcao|para|ate)\b"
    r"|\bchega\b"
    r"|\bentra\b.{0,15}\bn[ao]\b"
    r"|\bcaminha\b.{0,20}\b(direcao|para|ate)\b"
    r"|\b(volta|retorna)\b.{0,20}\b(direcao|para|ate)\b",
    re.IGNORECASE,
)


def _strip_accents(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char))


def _resolve_movement_target(db: Session, character: Character, raw_text: str) -> Location | None:
    """Phase 24J.3 — a deterministic backstop for clear movement phrasing
    ("Logan vai em direção à estalagem", "Logan chega à estalagem",
    "Logan entra na estalagem"), confirmed via live trace as a real
    regression: the Intent Parser classified every one of these as
    FREEFORM, not MOVE, across FOUR consecutive turns — so
    travel_service.move_character() never ran, character.location_id
    never actually changed, and (since PLAYER_MOVED never fired) the
    active interlocutor from three turns earlier stayed "active" through
    a departure, a walk, an arrival, and entering a different building.

    Mirrors _resolve_addressed_entity's own philosophy: deterministic,
    only acts when the raw text both (a) reads as movement phrasing and
    (b) names — by exact location name OR by the settlement-service type
    label a player would naturally use ("estalagem" for an "inn" —
    SETTLEMENT_SERVICE_POOL, the same Portuguese labels the world seed
    itself uses) — EXACTLY ONE location already known/discovered by this
    character. The safe failure mode is no match at all, never a guess.
    """
    text_no_accents = _strip_accents(raw_text).casefold()
    if not _MOVEMENT_PHRASE_PATTERN.search(text_no_accents):
        return None

    candidates = (
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
        )
        .all()
    )

    def _mentioned(label: str) -> bool:
        return re.search(rf"\b{re.escape(_strip_accents(label).casefold())}\b", text_no_accents) is not None

    matches = [
        location
        for location in candidates
        if _mentioned(location.name)
        or (location.type in _LOCATION_TYPE_LABELS_PT and _mentioned(_LOCATION_TYPE_LABELS_PT[location.type]))
        or (
            location.type in _HUB_LOCATION_TYPE_LABELS_PT
            and any(_mentioned(label) for label in _HUB_LOCATION_TYPE_LABELS_PT[location.type])
        )
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _handle_move(db: Session, campaign_id: str, character: Character, intent: Intent) -> tuple[str, int]:
    if not intent.target:
        return "Nenhum destino claro foi indicado.", 0

    def _destination_query(name_filter):
        return (
            db.query(Location)
            .filter(
                Location.region_id == character.region_id,
                name_filter,
            )
        )

    def _known_destination_query(name_filter):
        return (
            _destination_query(name_filter)
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
            )
            .first()
        )

    # Phase 24J.3 — settlement service locations are named "X de
    # {village_name}" ("Estalagem de Norbrook", "Ferraria de Norbrook"...),
    # so a bare village name ("Norbrook") is a substring of ALL of them.
    # An exact match must be tried first, or a target that IS the precise,
    # correct name (e.g. from the hub-label movement backstop) can resolve
    # ambiguously to an unrelated service via the old ilike-only substring
    # match — confirmed via live trace as the reason "Logan volta para a
    # praça central" resolved the right target in _resolve_movement_target
    # but then failed here with a "no path connects" error, because this
    # query separately re-resolved the name to the wrong location.
    destination = _known_destination_query(Location.name == intent.target)

    # The Intent Parser itself sometimes classifies MOVE directly (bypassing
    # _resolve_movement_target's backstop entirely) with a generic
    # Portuguese label as target instead of a proper noun — e.g. target=
    # 'praça central' for the settlement hub, or target='estalagem' for the
    # inn. Confirmed via live trace (req=nr_f17da5eec27e): this fell
    # straight to "nenhum lugar conhecido" and the narrator invented a
    # plausible-sounding "no plaza found here" scene around that failure,
    # even though the village was right there. Resolve the SAME service/hub
    # type labels _resolve_movement_target already knows, requiring exactly
    # one discovered candidate of that type — the same safe-failure-mode.
    if destination is None:
        target_normalized = _strip_accents(intent.target).casefold().strip()
        matched_types = [
            location_type
            for location_type, label in _LOCATION_TYPE_LABELS_PT.items()
            if _strip_accents(label).casefold() == target_normalized
        ] + [
            location_type
            for location_type, labels in _HUB_LOCATION_TYPE_LABELS_PT.items()
            if target_normalized in {_strip_accents(label).casefold() for label in labels}
        ]
        if matched_types:
            candidates = (
                _destination_query(Location.type.in_(matched_types))
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
                )
                .all()
            )
            if len(candidates) == 1:
                destination = candidates[0]

    if destination is None:
        destination = _known_destination_query(Location.name.ilike(f"%{intent.target}%"))

    # See _EXIT_PHRASE_PATTERN's own docstring: a departure with no
    # resolvable named destination falls back to the single settlement
    # hub connected to the character's current (non-hub) location.
    if destination is None and _EXIT_PHRASE_PATTERN.search(
        _strip_accents(intent.raw_text or "").casefold()
    ):
        current = db.get(Location, character.location_id)
        if current is not None and current.type != "village":
            hub_candidates = (
                db.query(Location)
                .join(LocationConnection, LocationConnection.to_location_id == Location.id)
                .filter(
                    LocationConnection.from_location_id == character.location_id,
                    LocationConnection.active.is_(True),
                    Location.type == "village",
                )
                .all()
            )
            if len(hub_candidates) == 1:
                destination = hub_candidates[0]

    if destination is None:
        return f"Nenhum lugar conhecido correspondente a '{intent.target}' pode ser alcançado a partir daqui.", 0

    # Phase 24J.3 — a repeated/redundant movement call toward the
    # location the character is already standing in (e.g. "Logan chega
    # à estalagem" and "Logan entra na estalagem", both resolved to the
    # same already-arrived-at destination by _resolve_movement_target)
    # would otherwise hit travel_service's "no connection FROM here TO
    # there" error — technically true, but a confusing thing to tell a
    # player who is already there. A plain, grounded acknowledgment is
    # more honest than either a scary error or narrating a second trip.
    if destination.id == character.location_id:
        return f"{character.name} já está em {destination.name}.", 0

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

    quests_service.evaluate_objective_trigger(
        db,
        campaign_id,
        character.id,
        ObjectiveTriggerType.REACH_LOCATION,
        subject_id=destination.id,
    )

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


_LEAVING_CLAUSE_PATTERN = re.compile(
    r"\bse\s+afasta\s+d[eoa]\s+.*?(?=\be\s+(?:se\s+)?aproxima\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_ROLE_REFERENCE_ALIASES = {
    "anciao": ("idoso", "velho", "senhor idoso"),
    "ancia": ("idosa", "velha", "senhora idosa"),
}

_LOCAL_INHABITANT_REFERENCE_PATTERN = re.compile(
    r"\b(?:alguem\s+(?:que\s+)?(?:parec\w+\s+ser\s+)?(?:local|dali)|"
    r"morador(?:a)?|habitante|nativ[oa])\b",
    re.IGNORECASE,
)


def _resolve_addressed_entity(
    raw_text: str,
    nearby_npcs,
    nearby_simulated_players,
) -> tuple["NPC | None", "SimulatedPlayer | None"]:
    """Phase 24J.1/24J.2 — does the player's own RAW text unambiguously
    name or role-reference exactly one nearby NPC or simulated player?
    Pure resolution, no persistence side effects (callers decide whether
    and how to record the result) — shared by both _handle_talk (when
    the Intent Parser's own `target` isn't trustworthy — see its own
    docstring) and _implicit_freeform_interlocutor_switch (FREEFORM/
    APPROACH intents, which never reach _handle_talk at all).

    24J.2, confirmed via live trace: restricting this resolution to only
    the non-TALK path was itself the bug — "Logan vai em direção ao
    velho ancião..." classified as TALK with an Intent-Parser-GUESSED
    target ("Rowan Quill") the player never literally typed, so
    _handle_talk's own literal-target gate correctly refused to trust it
    (working as designed) — but nothing then tried resolving "velho
    ancião" (a ROLE, not a name) against the raw text itself, so the
    elder was NEVER established as active interlocutor at all, and every
    later turn cascaded into "Há mais de uma pessoa aqui..." instead of
    continuing with him.

    "Logan se afasta de X e se aproxima de Y" legitimately names BOTH
    the person being left AND the one being approached — confirmed live
    as a real regression: counting every literal name as a candidate
    made this exact, extremely natural phrasing ambiguous (2 matches),
    so the switch to Y silently never fired. A name mentioned only
    inside a "se afasta de ___" clause is never who the player is
    addressing, so that clause is stripped before matching.

    Diacritics are stripped but case is preserved for name matching — a
    player very commonly types "anciao" for "ancião" (confirmed live: an
    exact-accent role match silently failed against unaccented input, an
    easy and common case, not an edge case), but a random character name
    can be spelled IDENTICALLY to an ordinary Portuguese word (confirmed
    live: the seed's own fixed simulated player "Dessa Marrow" collides
    with "dessa", the demonstrative in "o nome DESSA vila") — no amount
    of casefolded word-boundary matching alone can tell those apart,
    since they're the same token, so a name match additionally requires
    the matched word be capitalized in the player's own text (Portuguese
    proper-noun convention; role matching stays case-insensitive since
    players don't capitalize roles).

    Only acts when EXACTLY one candidate matches across BOTH nearby NPCs
    and nearby simulated players combined, to avoid any ambiguity risk —
    the safe failure mode (no match) just means the caller falls back to
    whatever it would otherwise have done, never a wrong guess.
    """
    search_text = _LEAVING_CLAUSE_PATTERN.sub(" ", raw_text)
    search_text_no_accents = "".join(
        char
        for char in unicodedata.normalize("NFKD", search_text)
        if not unicodedata.combining(char)
    )
    raw_lower = search_text_no_accents.casefold()

    def _name_mentioned(name: str) -> bool:
        return any(
            re.search(rf"\b{re.escape(word)}\b", search_text_no_accents) is not None
            for word in name.split()
            if len(word) >= 3 and word[0].isupper()
        )

    def _role_mentioned(role: str) -> bool:
        # Only the role's HEAD word ("ancião", not "da vila") — confirmed
        # via live trace as a real regression: a full-phrase match against
        # "ancião da vila" never matched the player's own natural
        # abbreviation ("o velho ancião", dropping "da vila"), so the
        # elder was never resolved at all. The head word alone is also
        # SAFER than matching on any word in the role: "vila" alone would
        # spuriously match this NPC on literally any village-name
        # question, which "ancião" never does.
        head_word = role.split()[0] if role.split() else role
        head_no_accents = "".join(
            char for char in unicodedata.normalize("NFKD", head_word) if not unicodedata.combining(char)
        )
        references = (head_no_accents, *_ROLE_REFERENCE_ALIASES.get(head_no_accents.casefold(), ()))
        return any(
            re.search(rf"\b{re.escape(reference)}\b", raw_lower) is not None
            for reference in references
        )

    npc_matches = [
        npc for npc in nearby_npcs if _name_mentioned(npc.name) or _role_mentioned(npc.role)
    ]
    if (
        not npc_matches
        and len(nearby_npcs) == 1
        and _LOCAL_INHABITANT_REFERENCE_PATTERN.search(raw_lower)
    ):
        npc_matches = [nearby_npcs[0]]
    simulated_player_matches = [
        player for player in nearby_simulated_players if _name_mentioned(player.name)
    ]

    if len(npc_matches) + len(simulated_player_matches) != 1:
        return None, None
    if npc_matches:
        return npc_matches[0], None
    return None, simulated_player_matches[0]


def _implicit_freeform_interlocutor_switch(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    state,
) -> tuple["NPC | None", "SimulatedPlayer | None"]:
    """Phase 24J.1 — a compound "approach + speak" sentence ("Logan se
    aproxima de Nessa e pergunta...", "Logan se aproxima do ancião e
    pergunta...", "Logan se afasta de Thane e se aproxima de Corren")
    is routinely classified FREEFORM or APPROACH by the Intent Parser
    rather than TALK — neither dispatches to _handle_talk (nor any
    equivalent for simulated players), so the active interlocutor's
    PERSISTED state silently never advances even though the player's
    own words unambiguously name or address a specific nearby NPC or
    transported person.

    Only handles the non-TALK case; a TALK-classified intent goes
    through _handle_talk, which now calls _resolve_addressed_entity
    itself (24J.2) when its own literal-target gate doesn't trust the
    Intent Parser's guess.
    """
    if intent.type == ActionIntentType.TALK:
        return None, None

    npc, player = _resolve_addressed_entity(
        intent.raw_text, state.nearby_npcs, state.nearby_simulated_players
    )
    if npc is not None:
        npcs_service.meet_npc(db, campaign_id, character.id, npc.id)
        return npc, None
    if player is not None:
        players_service.meet_simulated_player(db, campaign_id, character.id, player.id)
        return None, player
    return None, None


def _handle_talk(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    state,
) -> tuple[str, int]:
    npc = None
    simulated_player = None

    # Only trust the Intent Parser's `target` when at least one whole
    # word of it was actually typed by the player. The parser is an LLM
    # and can infer a plausible-sounding target (e.g. a nearby NPC's
    # role, or a full canonical name normalized from context) even when
    # the player named no one — trusting a target with ZERO connection
    # to the player's own words is exactly the class of mechanical
    # decision this project keeps out of LLM hands. A partial name
    # ("Falo com Osgar" -> target "Osgar Kessler") is still legitimate
    # and stays trusted, since "Osgar" itself was typed; a target the
    # player wrote nothing of at all ("Como está?" -> target
    # "estalajadeiro") falls through to the deterministic nearby-count
    # logic below, same as if no target had been given.
    literal_target = None
    if intent.target:
        raw_lower = intent.raw_text.casefold()
        target_words = [word for word in intent.target.split() if len(word) >= 3]
        if any(word.casefold() in raw_lower for word in target_words):
            literal_target = intent.target

    if literal_target:
        target_lower = literal_target.casefold()

        npc_matches = [
            candidate
            for candidate in state.nearby_npcs
            if target_lower in candidate.name.casefold()
            or target_lower in candidate.role.casefold()
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

        # A missing proper-name target is genuinely unavailable; do not let a
        # shared surname or role word silently redirect the conversation to a
        # different nearby person. The fallback exists for descriptive LLM
        # targets such as "homem idoso", which need deterministic role alias
        # resolution against the player's raw words.
        target_looks_like_proper_name = any(
            word[:1].isupper() for word in literal_target.split()
        )
        if len(matches) == 0 and not target_looks_like_proper_name:
            resolved_npc, resolved_player = _resolve_addressed_entity(
                intent.raw_text, state.nearby_npcs, state.nearby_simulated_players
            )
            if resolved_npc is not None:
                npc = resolved_npc
            elif resolved_player is not None:
                simulated_player = resolved_player

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
        elif len(nearby_people) > 1:
            # No literal target and several people present. The Intent
            # Parser's own `target` guess was already rejected above (not
            # literally typed) — but the player's raw text may still
            # unambiguously ROLE-reference someone ("o velho ancião")
            # rather than name them, which `literal_target` never checks
            # for at all. Confirmed via live trace as a real regression:
            # without this, "Logan vai em direção ao velho ancião..."
            # never resolved to anyone, and the elder was never
            # established as active interlocutor for the rest of the
            # scene (24J.2). An explicit reference in THIS turn takes
            # priority over merely continuing an old conversation.
            resolved_npc, resolved_player = _resolve_addressed_entity(
                intent.raw_text, state.nearby_npcs, state.nearby_simulated_players
            )
            if resolved_npc is not None:
                npc = resolved_npc
            elif resolved_player is not None:
                simulated_player = resolved_player
            else:
                # No explicit reference this turn either — before asking
                # for disambiguation, prefer an already-active
                # conversation. A follow-up question need not re-name the
                # NPC every turn (get_active_interlocutor's own docstring
                # says as much); without this check, any crowd scene
                # downgrades every untargeted follow-up to a
                # disambiguation prompt and silently drops the ongoing
                # conversation (Phase 24J.1, confirmed via live trace).
                active_npc = npcs_service.get_active_interlocutor(
                    db, campaign_id, character.id, character.location_id
                )
                if active_npc is not None and any(
                    candidate.id == active_npc.id for candidate in state.nearby_npcs
                ):
                    npc = active_npc
                else:
                    active_simulated_player = (
                        players_service.get_active_simulated_player_interlocutor(
                            db, campaign_id, character.id, character.location_id
                        )
                    )
                    if active_simulated_player is not None and any(
                        candidate.id == active_simulated_player.id
                        for candidate in state.nearby_simulated_players
                    ):
                        simulated_player = active_simulated_player
                    else:
                        return (
                            "Há mais de uma pessoa aqui. Diga com quem você quer falar.",
                            0,
                        )

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
    """Phase 12B: talking to an NPC is an authoritative backend fact — route
    it through the Objective Evaluator (structured trigger_type/
    trigger_subject_id matching) instead of guessing from free-text
    objective descriptions."""
    quests_service.evaluate_objective_trigger(
        db,
        campaign_id,
        character.id,
        ObjectiveTriggerType.TALK_TO_NPC,
        subject_id=npc.id,
    )


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
    board_lines = _examine_notice_board_if_targeted(db, character, intent)
    if board_lines is not None:
        return " ".join(board_lines), 2

    result = perception_service.observe_surroundings(
        db,
        character,
    )

    lines = [
        f"{character.name} observa os arredores de {result.location_name}."
        if result.location_name_known
        else f"{character.name} observa os arredores deste lugar.",
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


def _examine_notice_board_if_targeted(
    db: Session, character: Character, intent: Intent
) -> list[str] | None:
    """Phase 12L: examining a named feature that actually has notices
    posted to it reads the board (Phase 12I) instead of the generic
    surroundings summary. Returns None when the target isn't a real board
    at this location, so the caller falls through to the ordinary EXAMINE
    behavior — nothing here invents a board out of thin air."""
    if not intent.target:
        return None
    board = (
        db.query(LocationFeature)
        .filter(
            LocationFeature.location_id == character.location_id,
            LocationFeature.name.ilike(f"%{intent.target}%"),
        )
        .first()
    )
    if board is None:
        return None
    has_ever_had_a_notice = (
        db.query(Notice).filter(Notice.board_feature_id == board.id).first() is not None
    )
    if not has_ever_had_a_notice:
        return None

    try:
        notices = read_notice_board(db, character.id, board.id)
    except NoticeBoardError:
        return None

    lines = [f"{character.name} lê o {board.name}."]
    if not notices:
        lines.append("Não há nenhum aviso ativo no momento.")
    else:
        lines.extend(f"[{notice.category}] {notice.title}: {notice.text}" for notice in notices)
    return lines
