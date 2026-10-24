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
    connection_type_label_pt,
    ActionIntentType,
    ItemLocationType,
    CharacterStatus,
    CombatActorType,
    DiscoveryStatus,
    EventType,
    KnowerType,
    KnowledgeCertainty,
    NoticeStatus,
    ObjectiveTriggerType,
    QuestStatus,
    TravelIncidentKind,
)
from app.core.logging import current_narrative_request_id, get_logger, with_narrative_request_id
from app.core.ids import generate_id
from app.db.models.character import Character
from app.db.models.item import ItemInstance
from app.db.models.location import (
    CharacterLocationDiscovery,
    Location,
    LocationConnection,
    LocationFeature,
)
from app.db.models.notice import Notice
from app.game import game_state
from app.game.combat import bridge as combat_bridge
from app.game.combat import fainting
from app.game.combat import hostility as combat_hostility
from app.game.combat import service as combat_service
from app.game.combat.recovery import recover_character
from app.game.items.interactions import (
    ITEM_INTERACTION_INTENTS,
    resolve_item_interaction,
)
from app.game.items.consumables import ConsumableError, use_consumable
from app.game.items.loot import LootError, resolve_npc_loot
from app.game.economy.economic_canon import (
    EconomicCanonError,
    materialize_economic_value,
    service_subject,
)
from app.game.economy.initial_content import ensure_initial_economy_for_campaign
from app.game.quests.initial_content import ensure_initial_quest_opportunities_for_campaign
from app.game.economy.playable import resolve_economy_intent
from app.game.npcs import service as npcs_service
from app.game.players import service as players_service
from app.game.notices import service as notices_service
from app.game.organizations import registration as registration_service
from app.game.groups import companions as companions_service
from app.game.organizations import player_guilds as guilds_service
from app.game.travel import settlement_routes
from app.game import telling
from app.game.exploration import service as exploration
from app.ai import people_present
from app.game.players.appearance import ensure_transported_features
from app.game.notices.service import NoticeBoardError, read_notice_board
from app.game.quests import service as quests_service
from app.game.quests.rewards import grant_local_request_rewards, grant_pending_quest_completion_xp
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
from app.game.discovery import service as discovery_service
from app.game.world.content_pools import SETTLEMENT_SERVICE_POOL
from app.game.world.local_knowledge import ensure_settlement_public_knowledge
from app.services.event_log import log_event
from app.services.story_log import SPEAKER_NARRATOR, get_recent_story_log
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
    # A save left with a fallen character (before fainting existed) wakes
    # them first instead of refusing every action forever.
    woke_up = fainting.faint_and_wake(db, campaign_id, character)
    if character.region_id is None or character.location_id is None:
        raise WorldNotStartedError("Inicie o mundo antes de realizar uma ação.")

    # Backfills old campaigns and keeps generated public service knowledge in
    # sync before either the intent parser or narrator receives context.
    ensure_settlement_public_knowledge(
        db, campaign_id, character.location_id
    )
    # Backfill the Phase 12 boards and the real Phase 14 content for saves
    # created before them, quests first (job openings share the public
    # board). Both run inside the action checkpoint and are idempotent.
    ensure_initial_quest_opportunities_for_campaign(db, campaign_id)
    ensure_initial_economy_for_campaign(db, campaign_id)

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
        intent = intent_parser.parse(
            intent_llm_service,
            text,
            people_present.build_intent_context(
                db, state, context,
                active_npc_id=active_npc.id if active_npc else None,
                active_player_id=active_simulated_player.id if active_simulated_player else None,
            ),
        )
        intent = _refine_explicit_quest_intent(intent)
        intent = _refine_explicit_membership_intent(intent)
        intent = _refine_explicit_economy_intent(intent)
        # With the parser unavailable a line spoken to whoever the player is
        # already talking with stays a conversation, not "nothing applies".
        if (
            intent.type == ActionIntentType.FREEFORM
            and (active_npc is not None or active_simulated_player is not None)
            and _looks_like_dialogue(text)
        ):
            intent = replace(intent, type=ActionIntentType.TALK)
        # Saying yes to whoever just asked a favour is an answer to them,
        # however the parser read it. Playtest: "Pode deixar, eu procuro o
        # gato pra senhora" came back as a skill check and nothing was taken.
        if (
            active_npc is not None
            and intent.type not in (ActionIntentType.TALK, ActionIntentType.MOVE)
            and "?" not in text
            and _AGREEMENT_PATTERN.search(_strip_accents(text).casefold())
            and _known_request_of(db, campaign_id, character, active_npc) is not None
        ):
            intent = replace(intent, type=ActionIntentType.TALK, target=None, person_ref=None)
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
        if progression.techniques_recognized:
            discovered_names = ", ".join(
                technique.name for technique in progression.techniques_recognized
            )
            mechanical_summary += f" Nova técnica reconhecida: {discovered_names}."
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
        location_before = character.location_id
        mechanical_summary, minutes = _apply_intent(
            db,
            campaign_id,
            character,
            intent,
            state,
            action_key=resolved_action_key,
        )
        if character.location_id != location_before:
            quests_service.evaluate_objective_trigger(
                db, campaign_id, character.id, ObjectiveTriggerType.REACH_LOCATION,
                subject_id=character.location_id,
            )

    request_payments = grant_local_request_rewards(db, campaign_id, character)
    if request_payments:
        mechanical_summary = f"{mechanical_summary} {' '.join(request_payments)}"
    granted_quest_xp = grant_pending_quest_completion_xp(
        db,
        llm_service,
        campaign_id,
        character,
    )
    if granted_quest_xp:
        reward_lines = "; ".join(
            f"{name}: +{amount:g} XP" for name, amount in granted_quest_xp
        )
        mechanical_summary = f"{mechanical_summary} Recompensa de missão: {reward_lines}."

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

        notices_service.expire_notices(db, campaign_id)

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

    # Lost the fight: they faint and wake up back in the village.
    fainted = fainting.faint_and_wake(db, campaign_id, character)
    if fainted:
        mechanical_summary = f"{mechanical_summary} {fainted}"
    if woke_up:
        mechanical_summary = f"{woke_up} {mechanical_summary}"

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
    # What the NPC tells this turn is decided here, before narrating; the
    # narrator must say it and the player learns exactly that (app.game.telling).
    npc_telling = (
        telling.decide(db, campaign_id, character.id, context_npc, text)
        if context_npc is not None
        else telling.Telling()
    )
    if npc_telling.facts:
        fresh_context = f"{fresh_context}\n\n" + "\n".join(npc_telling.context_lines(context_npc.name))
    recent_history = context_builder.build_recent_history(recent_entries)
    settings = get_settings()

    narrator_unavailable = False
    # Asking "com quem?" answers the turn by itself: no conversation was
    # registered, so nobody may be narrated answering as if one were.
    asking_who = mechanical_summary.startswith(WHO_DO_YOU_MEAN_PREFIX) or WHERE_TO_QUESTION in mechanical_summary
    narrator_facts = _without_progression_numbers(mechanical_summary)
    if asking_who:
        narrative_text = mechanical_summary
    else:
        try:
            narrative_text = narrator.narrate(
                llm_service,
                narrator_facts,
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
    if settings.narrative_automatic_validation_enabled and not asking_who:
        canonical_facts = context_builder.build_canonical_facts(fresh_state)
        validation = narrative_validator.validate(narrative_text, canonical_facts)
        narrative_proposal = NarrativeProposal(
            text=validation.text,
            mode="CONTINUATION",
            context=fresh_context,
            mechanical_summary=narrator_facts,
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
    elif not asking_who:
        # First version accepted as is (the player regenerates if unhappy);
        # a direct price/wage question still gets its number, instantly.
        final_narrative = narrator.enforce_authorized_price_answer(
            narrative_text,
            fresh_context,
            text,
            context_npc.name if context_npc is not None else "",
        )

    if context_npc is not None and not asking_who:
        final_narrative = telling.tell(
            db, campaign_id, character.id, context_npc, npc_telling, final_narrative
        )
    if context_simulated_player is not None:
        # A transported person talks about their guild freely — unless it is
        # a secret bandit crew.
        guild = guilds_service.transported_guild_of(
            db, CombatActorType.SIMULATED_PLAYER, context_simulated_player.id
        )
        if guild is not None and guild.visibility != "SECRET":
            npcs_service.teach_fact(
                db, campaign_id, guilds_service.guild_fact_key(guild), KnowerType.PLAYER,
                character.id, source="conversa_com_membro", certainty=KnowledgeCertainty.CONFIRMED,
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


_EXPLICIT_QUEST_ACTION_PATTERN = re.compile(
    r"^\s*(?P<verb>aceit(?:o|ar|e)|pego|pegar|abandono|abandonar|cancelo|cancelar)"
    r"\s+(?:(?:a|o|essa|esta)\s+)?(?:miss[aã]o|contrato)\s+"
    r"(?P<target>.+?)\s*$",
    re.IGNORECASE,
)


# First-person requests to join or leave an organization. Asking HOW to join
# ("como faço para me registrar?") stays a conversation.
_JOIN_ORGANIZATION_PATTERN = re.compile(
    r"\b(?:quero|gostaria de|desejo|vou|posso)\s+(?:me\s+)?"
    r"(?:(?:registrar|inscrever|filiar|alistar)\b"
    r"|(?:juntar|entrar)\s+(?:a|ao|para|n[ao])\s+(?:a\s+|(?:sua|seu|tua|teu|vossa|vosso)\s+)?"
    r"(?:guilda|ordem|organizacao|irmandade|companhia|sociedade|bando)\b)"
    r"|\bme\s+(?:registro|inscrevo|filio|alisto)\b"
    r"|\bassino\s+o\s+registro\b"
)
_LEAVE_ORGANIZATION_PATTERN = re.compile(
    r"\b(?:quero|vou|desejo)\s+(?:sair|deixar|abandonar)\s+(?:d?[ao]s?\s+)?"
    r"(?:(?:minha|nossa|meu|nosso)\s+)?(?:guilda|ordem|organizacao|conselho|bando)\b"
    r"|\bsaio\s+d[ao]\s+(?:(?:minha|nossa|meu|nosso)\s+)?(?:guilda|ordem|organizacao|conselho|bando)\b"
    r"|\bcancelo\s+(?:o\s+|meu\s+)?registro\b"
)
_HOW_TO_QUESTION_PATTERN = re.compile(
    r"\bcomo\s+(?:faco|posso|eu|se|funciona|fazer)\b|\bquanto\s+custa\b"
    r"|\bo\s+que\s+(?:preciso|e\s+preciso)\b|\bquais\s+(?:sao\s+)?(?:os\s+)?requisitos\b"
)


_INVITE_TO_GROUP_PATTERN = re.compile(
    r"\bconvido\b"
    r"|\b(?:quer|querem|topa|topam|gostaria de|aceita)\s+(?:vir|viajar|ir|seguir)\s+comigo\b"
    r"|\bvamos\s+(?:viajar\s+|seguir\s+)?juntos\b|\bformar\s+um\s+grupo\b"
    r"|\bme\s+acompanhar\b|\bviajar\s+comigo\b"
)
_LEAVE_GROUP_PATTERN = re.compile(
    r"\b(?:saio|deixo)\s+do\s+grupo\b|\bdesfa(?:co|zer)\s+o\s+grupo\b"
    r"|\bdispenso\s+o\s+grupo\b|\bcada\s+um\s+(?:segue|seguir)\s+seu\s+caminho\b"
    r"|\bnos\s+separamos\b"
)


_FOUND_ORGANIZATION_PATTERN = re.compile(
    r"\b(?:fundamos|fundar|fundo|criamos|criar|crio)\b.{0,25}\b(?:guilda|bando|sociedade|companhia)\b"
)
_RECRUIT_PATTERN = re.compile(
    r"\b(?:convido|chamo|recruto|convidar|chamar|recrutar)\b.{0,40}"
    r"\b(?:para|pra)\s+(?:a\s+|o\s+|minha\s+|nossa\s+|meu\s+|nosso\s+)?(?:guilda|bando)\b"
    r"|\brecruto\b"
)
_EXPEL_PATTERN = re.compile(
    r"\b(?:expulso|expulsar|removo|remover)\b.{0,40}\b(?:guilda|bando)\b"
)
_FORMALIZE_PATTERN = re.compile(
    r"\b(?:registr\w*|formaliz\w*|oficializ\w*)\s+(?:a\s+)?(?:minha|nossa)\s+guilda\b"
    r"|\b(?:formaliz|oficializ)\w*\s+a\s+guilda\b"
)


# "Exploro os arredores", "vasculho a área", "procuro outras trilhas" —
# looking around ("olho ao redor") stays EXAMINE.
_EXPLORE_PATTERN = re.compile(
    r"\b(?:exploro|explorar|exploramos|vasculho|vasculhar|vasculhamos)\b"
    r"|\bprocur\w*\s+(?:outr[oa]s\s+|nov[oa]s\s+|alguma?\s+|um[a]?\s+)?(?:caminhos?|trilhas?|passagens?|rotas?|saidas?)\b"
    r"|\breconhec\w*\s+o\s+terreno\b|\bdescobrir\s+(?:a\s+)?(?:regiao|area|arredores)\b"
)


_GUILD_RANK_PATTERN = re.compile(
    r"\b(?:promovo|promover|promova|rebaixo|rebaixar|rebaixe)\b"
    r"|\b(?:passo|passar|entrego|entregar|transfiro|transferir)\s+(?:a\s+)?(?:lideranca|chefia|comando)\b"
    r"|\bnomeio\b.{0,40}\b(?:oficial|lider|braco direito)\b"
)
_GUILD_DIPLOMACY_PATTERN = re.compile(
    r"\b(?:proponho|propor|propomos|oferec\w*|firmar|firmamos|selar|selamos|fazer|quero)\b.{0,30}\balianca\b"
    r"|\bnos\s+aliar\b|\bnos\s+aliamos\b"
    r"|\b(?:rompo|romper|rompemos|desfaco|desfazer|encerro|encerrar)\b.{0,20}\balianca\b"
    r"|\bdeclar\w*\b.{0,50}\briva(?:l|is|lidade)\b"
)


_ECONOMY_INTENTS = {
    ActionIntentType.BUY,
    ActionIntentType.SELL,
    ActionIntentType.APPLY_JOB,
    ActionIntentType.WORK_JOB,
    ActionIntentType.LEAVE_JOB,
    ActionIntentType.PRODUCE,
}


def _quoted_values(text: str) -> list[str]:
    return [
        value.strip()
        for value in re.findall(r'["“”]([^"“”]+)["“”]', text)
        if value.strip()
    ]


def _after_economy_verb(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if match is None:
        return None
    value = text[match.end():].strip(" \t\r\n:.-\"'“”")
    value = re.sub(r"^(?:a|o|uma|um)\s+", "", value, flags=re.IGNORECASE)
    return value or None


_ECONOMY_VERB_PATTERN = re.compile(
    r"\b(?:compro|comprar|vendo|vender|candidato|aceito|quero|trabalho|produzo|fabrico|forjo|deixo|saio)\b"
)
# Accepting the work an employer just described, in plain words.
_APPLY_JOB_PHRASE_PATTERN = re.compile(
    r"\b(?:quero|aceito|pego)\s+(?:o\s+)?(?:trabalho|emprego|servico)\b"
    r"|\bquero\s+ser\s+(?:o\s+|a\s+)?(?:seu|sua|teu|tua)\s+ajudante\b"
    r"|\bquero\s+trabalhar\s+(?:aqui|pra\s+(?:voce|senhora?)|para\s+(?:voce|o\s+senhor|a\s+senhora))\b"
)


_PRODUCTION_ATTEMPT_PATTERN = re.compile(
    r"\b(?:produzo|fabrico|confecciono|forjo)\b"
    r"|\b(?:tento|vou|quero|posso|comeco a)\s+(?:forjar|fabricar|produzir|confeccionar)\b"
)


def _unquoted_speech(raw: str) -> str:
    """Speech marks removed, so text after a verb ('"Quero comprar a faca."')
    reads as 'a faca', not as the rest of a quoted sentence."""
    return re.sub(r'["“”]', "", raw)


def _refine_explicit_economy_intent(intent: Intent) -> Intent:
    """Backstop for commands that commit the player's own economic action.

    Questions about prices or work are deliberately not promoted: they remain
    dialogue. The backend, never the parser, still decides whether the action
    is physically and economically possible.
    """
    if intent.type in _ECONOMY_INTENTS:
        return intent
    raw = intent.raw_text or ""
    text = _strip_accents(raw).casefold()
    # "Tento forjar uma faca" reads to the parser as an attempt (a skill
    # check); with a production verb it is production. Only production: in
    # "estou vendo a trilha", "vendo" is seeing, not selling.
    if intent.type in (ActionIntentType.SKILL_CHECK, ActionIntentType.EXPERIMENT):
        if not _PRODUCTION_ATTEMPT_PATTERN.search(text):
            return intent
    elif intent.type not in (ActionIntentType.FREEFORM, ActionIntentType.TALK):
        return intent
    # Dialogue is naturally quoted ('"Aceito a vaga de ajudante."'); only a
    # quoted value without the verb itself names an item or a job.
    quoted = [
        value for value in _quoted_values(raw)
        if not _ECONOMY_VERB_PATTERN.search(_strip_accents(value).casefold())
    ]
    raw = _unquoted_speech(raw)

    if re.search(r"\b(?:compro|comprar|quero comprar|vou comprar)\b", text):
        target = quoted[0] if quoted else _after_economy_verb(
            raw, r"\b(?:compro|comprar|quero\s+comprar|vou\s+comprar)\b"
        )
        secondary = quoted[1] if len(quoted) > 1 else None
        if target and not quoted:
            parts = re.split(r"\s+(?:na|no|em)\s+", target, maxsplit=1, flags=re.IGNORECASE)
            target, secondary = parts[0], parts[1] if len(parts) > 1 else None
        return replace(intent, type=ActionIntentType.BUY, target=target, secondary_target=secondary)

    if re.search(r"\b(?:vendo|vender|quero vender|vou vender)\b", text):
        target = quoted[0] if quoted else _after_economy_verb(
            raw, r"\b(?:vendo|vender|quero\s+vender|vou\s+vender)\b"
        )
        secondary = quoted[1] if len(quoted) > 1 else None
        if target and not quoted:
            parts = re.split(r"\s+para\s+", target, maxsplit=1, flags=re.IGNORECASE)
            target, secondary = parts[0], parts[1] if len(parts) > 1 else None
        return replace(intent, type=ActionIntentType.SELL, target=target, secondary_target=secondary)

    if re.search(r"\b(?:candidato[- ]me|me candidato|aceito a vaga|quero a vaga|quero trabalhar como)\b", text) or (
        _APPLY_JOB_PHRASE_PATTERN.search(text)
    ):
        target = quoted[0] if quoted else _after_economy_verb(
            raw,
            r"\b(?:candidato-me|me\s+candidato|aceito\s+a\s+vaga|quero\s+a\s+vaga|quero\s+trabalhar\s+como)(?:\s+(?:ao|a|de))?\b",
        )
        target = re.sub(
            r"^(?:trabalho|emprego|vaga)\s+", "", target or "", flags=re.IGNORECASE
        ) or None
        return replace(intent, type=ActionIntentType.APPLY_JOB, target=target)

    if re.search(r"\b(?:faco meu turno|cumpro meu turno|trabalho no emprego|trabalho como)\b", text):
        target = quoted[0] if quoted else _after_economy_verb(
            raw,
            r"\b(?:faço\s+meu\s+turno|faco\s+meu\s+turno|cumpro\s+meu\s+turno|trabalho\s+no\s+emprego|trabalho\s+como)\b",
        )
        return replace(intent, type=ActionIntentType.WORK_JOB, target=target)

    if re.search(r"\b(?:deixo o emprego|saio do emprego|peco demissao|abandono o trabalho)\b", text):
        target = quoted[0] if quoted else _after_economy_verb(
            raw,
            r"\b(?:deixo\s+o\s+emprego|saio\s+do\s+emprego|peço\s+demissão|peco\s+demissao|abandono\s+o\s+trabalho)\b",
        )
        return replace(intent, type=ActionIntentType.LEAVE_JOB, target=target)

    if re.search(r"\b(?:produzo|fabrico|confecciono|forjo|preparo rac)\b", text) or re.search(
        r"\b(?:tento|vou|quero|posso|comeco a)\s+(?:forjar|fabricar|produzir|confeccionar)\b", text
    ):
        target = quoted[0] if quoted else _after_economy_verb(
            raw, r"\b(?:produzo|fabrico|confecciono|forjo|preparo|forjar|fabricar|produzir|confeccionar)\b"
        )
        return replace(intent, type=ActionIntentType.PRODUCE, target=target)
    return intent


def _refine_explicit_membership_intent(intent: Intent) -> Intent:
    """Deterministic backstop for joining/leaving an organization or a travel
    group, which the Intent Parser may read as plain conversation."""
    if intent.type not in (
        ActionIntentType.FREEFORM, ActionIntentType.TALK, ActionIntentType.APPROACH
    ):
        return intent
    text = _strip_accents(intent.raw_text or "").casefold()
    # Order matters: "convido o Bram para a guilda" is a recruitment before it
    # is a travel invitation, and "registrar nossa guilda" is not joining one.
    if _LEAVE_GROUP_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.LEAVE_GROUP)
    if _EXPLORE_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.EXPLORE)
    if _GUILD_DIPLOMACY_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.GUILD_DIPLOMACY)
    if _GUILD_RANK_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.CHANGE_GUILD_RANK)
    if _EXPEL_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.EXPEL_FROM_ORGANIZATION)
    if _RECRUIT_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.RECRUIT_TO_ORGANIZATION)
    if _INVITE_TO_GROUP_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.INVITE_TO_GROUP)
    if _FOUND_ORGANIZATION_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.FOUND_ORGANIZATION)
    if _FORMALIZE_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.FORMALIZE_ORGANIZATION)
    if _LEAVE_ORGANIZATION_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.LEAVE_ORGANIZATION)
    if _JOIN_ORGANIZATION_PATTERN.search(text) and not _HOW_TO_QUESTION_PATTERN.search(text):
        return replace(intent, type=ActionIntentType.JOIN_ORGANIZATION)
    return intent


def _refine_explicit_quest_intent(intent: Intent) -> Intent:
    """Deterministic backstop for explicit quest-management commands.

    Groq remains the general intent interpreter, but accepting or abandoning a
    named quest should not silently become FREEFORM during a transient model
    failure. This only recognizes an explicit quest/contract noun.
    """
    if intent.type != ActionIntentType.FREEFORM:
        return intent
    match = _EXPLICIT_QUEST_ACTION_PATTERN.match(intent.raw_text or "")
    if match is None:
        return intent
    verb = _strip_accents(match.group("verb")).casefold()
    intent_type = (
        ActionIntentType.ABANDON_QUEST
        if verb.startswith(("abandon", "cancel"))
        else ActionIntentType.ACCEPT_QUEST
    )
    target = match.group("target").strip(" \t\r\n\"'“”‘’.!")
    return replace(intent, type=intent_type, target=target or None)


def _apply_intent(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    state,
    *,
    action_key: str | None = None,
) -> tuple[str, int]:
    if intent.type in _ECONOMY_INTENTS:
        if combat_bridge.get_active_encounter_for_actor(
            db, CombatActorType.CHARACTER, character.id
        ) is not None:
            return "Não é possível negociar, trabalhar ou produzir durante um combate ativo.", 0
        result = resolve_economy_intent(
            db,
            character,
            intent.type,
            intent.target,
            intent.secondary_target,
        )
        return result.summary, result.minutes
    if intent.type == ActionIntentType.INVITE_TO_GROUP:
        return _handle_group_invite(db, campaign_id, character, intent, state)
    if intent.type in (
        ActionIntentType.RECRUIT_TO_ORGANIZATION, ActionIntentType.EXPEL_FROM_ORGANIZATION
    ):
        return _handle_guild_membership(db, campaign_id, character, intent, state)
    if intent.type == ActionIntentType.FOUND_ORGANIZATION:
        change = guilds_service.found_guild(
            db, campaign_id, character, intent.raw_text or "", name_hint=intent.target
        )
        return change.summary, 10 if change.changed else 0
    if intent.type == ActionIntentType.FORMALIZE_ORGANIZATION:
        change = guilds_service.formalize(db, campaign_id, character)
        return change.summary, 15 if change.changed else 0
    if intent.type == ActionIntentType.EXPLORE:
        # "Vou até a clareira procurar o gato" is a walk to a known place.
        destination = _resolve_movement_target(db, character, intent.raw_text)
        if destination is not None and destination.id != character.location_id:
            return _handle_move(db, campaign_id, character, replace(intent, type=ActionIntentType.MOVE, target=destination.name))
        return _handle_explore(db, campaign_id, character)
    if intent.type == ActionIntentType.CHANGE_GUILD_RANK:
        return _handle_guild_rank(db, campaign_id, character, intent, state)
    if intent.type == ActionIntentType.GUILD_DIPLOMACY:
        return _handle_guild_diplomacy(db, campaign_id, character, intent, state)
    if intent.type == ActionIntentType.LEAVE_GROUP:
        change = companions_service.leave_character_group(db, character)
        return change.summary, 0
    if intent.type == ActionIntentType.JOIN_ORGANIZATION:
        change = registration_service.register_with_organization(
            db, campaign_id, character, " ".join(filter(None, (intent.target, intent.raw_text)))
        )
        return change.summary, 5 if change.changed else 0
    if intent.type == ActionIntentType.LEAVE_ORGANIZATION:
        change = registration_service.leave_organization(
            db, campaign_id, character, " ".join(filter(None, (intent.target, intent.raw_text)))
        )
        return change.summary, 1 if change.changed else 0
    if intent.type == ActionIntentType.ACCEPT_QUEST:
        quest = quests_service.find_character_quest_by_name(
            db,
            campaign_id,
            character.id,
            intent.target,
            status=QuestStatus.AVAILABLE,
        )
        if quest is None:
            # "Aceito ajudar": the request of whoever the player is talking to.
            active = npcs_service.get_active_interlocutor(db, campaign_id, character.id, character.location_id)
            quest = _known_request_of(db, campaign_id, character, active) if active else None
        if quest is None:
            return "Nenhuma missão conhecida e disponível corresponde a esse nome.", 0
        try:
            quests_service.accept_known_quest(
                db, campaign_id, character.id, quest.id
            )
        except quests_service.QuestLifecycleError as exc:
            return str(exc), 0
        if quest.giver_npc_id:
            from app.game.quests.local_requests import reveal_the_way

            reveal_the_way(db, character, quest)
        return f"{character.name} aceita a missão '{quest.name}'.", 1
    if intent.type == ActionIntentType.ABANDON_QUEST:
        quest = quests_service.find_character_quest_by_name(
            db,
            campaign_id,
            character.id,
            intent.target,
            status=QuestStatus.ACTIVE,
        )
        if quest is None:
            return "Nenhuma missão ativa corresponde a esse nome.", 0
        try:
            quests_service.abandon_known_quest(
                db, campaign_id, character.id, quest.id
            )
        except quests_service.QuestLifecycleError as exc:
            return str(exc), 0
        return f"{character.name} abandona a missão '{quest.name}'.", 1
    if intent.type == ActionIntentType.FREEFORM:
        # Phase 24J.3 — scoped narrowly to FREEFORM (not e.g. TALK, which
        # already resolves its own targets and may legitimately mention a
        # place name in passing while addressing a person): every
        # confirmed live failure was the Intent Parser classifying clear
        # movement phrasing as FREEFORM instead of MOVE.
        movement_target = _resolve_movement_target(db, character, intent.raw_text)
        if movement_target is not None:
            intent = replace(intent, type=ActionIntentType.MOVE, target=movement_target.name)
        elif _LOOK_AROUND_PATTERN.search(_strip_accents(intent.raw_text or "").casefold()):
            intent = replace(intent, type=ActionIntentType.EXAMINE, target=None)
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
        # "Vou até o quadro de avisos e leio" is classified EXAMINE; without
        # moving first the narration walked to the board while the character
        # stayed in the square (confirmed in playtest).
        movement_target = _resolve_movement_target(db, character, intent.raw_text)
        if movement_target is not None and movement_target.id != character.location_id:
            move_summary, move_minutes = _handle_move(
                db, campaign_id, character,
                replace(intent, type=ActionIntentType.MOVE, target=movement_target.name),
            )
            if character.location_id != movement_target.id:
                return move_summary, move_minutes
            examine_summary, examine_minutes = _handle_examine(db, campaign_id, character, intent)
            return f"{move_summary} {examine_summary}", move_minutes + examine_minutes
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
        now = clock.get_world_time(db, campaign_id)
        minutes = _wait_minutes(intent.raw_text or "", now.hour, now.minute)
        if minutes <= 15:
            return f"{character.name} espera, deixando o tempo passar.", 15
        until = (now.hour * 60 + now.minute + minutes) // 60 % 24
        return f"{character.name} espera, deixando o tempo passar, até por volta das {until}h.", minutes
    if intent.type == ActionIntentType.SKILL_CHECK:
        return _handle_skill_check(db, campaign_id, character, intent)
    if intent.type == ActionIntentType.USE:
        if combat_bridge.get_active_encounter_for_actor(
            db, CombatActorType.CHARACTER, character.id
        ) is not None:
            return combat_bridge.handle_consumable_intent(
                db, campaign_id, character, intent, action_key=action_key
            )
        if not intent.target:
            return "Nenhum consumível foi identificado.", 0
        try:
            result = use_consumable(
                db, campaign_id, character, intent.target, action_key=action_key
            )
        except ConsumableError as exc:
            return f"O consumível não pôde ser usado: {exc}", 0
        return f"{character.name} {result.summary[0].lower() + result.summary[1:]}", 0 if result.replayed else result.use_minutes
    if intent.type == ActionIntentType.LOOT:
        if not intent.target:
            return "Nenhum alvo para saque foi identificado.", 0
        try:
            result = resolve_npc_loot(
                db, campaign_id, character, intent.target, action_key=action_key
            )
        except LootError as exc:
            return f"O saque não pôde ser realizado: {exc}", 0
        return f"{character.name} {result.summary[0].lower() + result.summary[1:]}", 0 if result.replayed else 2
    if intent.type in ITEM_INTERACTION_INTENTS:
        return _handle_item_interaction(
            db,
            campaign_id,
            character,
            intent,
            action_key=action_key,
            state=state,
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
    if (
        intent.type == ActionIntentType.APPROACH
        and combat_bridge.get_active_encounter_for_actor(
            db, CombatActorType.CHARACTER, character.id
        ) is None
    ):
        # Outside combat, approaching someone starts a conversation
        # ("Me aproximo de um dos recém-chegados"); it used to answer
        # "não está em combate" (seen in playtest).
        return _handle_talk(db, campaign_id, character, intent, state)
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
    state=None,
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
    secondary_target = intent.secondary_target
    if intent.type == ActionIntentType.GIVE and state is not None:
        # "Entrego as ervas para a herbalista": the recipient by appearance,
        # trade or the current conversation, as for everyone else.
        npcs, _players = _resolve_target_person(
            db, campaign_id, character, replace(intent, target=intent.secondary_target), state
        )
        if len(npcs) == 1:
            secondary_target = npcs[0].id
    try:
        result = resolve_item_interaction(
            db,
            campaign_id,
            character,
            interaction=intent.type,
            target=intent.target,
            secondary_target=secondary_target,
            slot=intent.slot,
            interaction_key=action_key,
        )
    except ValueError as exc:
        return f"A interação com o item não pôde ser realizada: {exc}", 0
    if not result.replayed and intent.type == ActionIntentType.PICK_UP:
        quests_service.evaluate_objective_trigger(
            db, campaign_id, character.id, ObjectiveTriggerType.RETRIEVE_ITEM,
            subject_id=result.item_instance_id,
        )
    if not result.replayed and intent.type == ActionIntentType.GIVE:
        item = db.get(ItemInstance, result.item_instance_id)
        if item is not None and item.location_type == ItemLocationType.NPC.value:
            quests_service.evaluate_objective_trigger(
                db, campaign_id, character.id, ObjectiveTriggerType.DELIVER_ITEM,
                subject_id=f"{item.id}:{item.location_ref}",
            )
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

# Wild places are usually seen before their name is known, so players refer
# to them by kind ("vamos até a floresta"); confirmed in playtest as
# "Nenhum lugar conhecido correspondente a 'floresta'". Same exactly-one
# rule as above: two known forests resolve to nothing.
_WILD_LOCATION_TYPE_LABELS_PT: dict[str, tuple[str, ...]] = {
    "forest": ("floresta", "mata", "bosque"),
    "river": ("rio", "riacho", "ribeirao", "corrego"),
    "road": ("estrada",),
    "clearing": ("clareira",),
    "ruins": ("ruinas",),
    "temple_ruins": ("ruinas do templo", "templo em ruinas"),
    "fort_ruins": ("ruinas do forte", "forte em ruinas"),
    "cave": ("caverna", "gruta"),
    "hills": ("colinas", "morros"),
    "mountain_range": ("montanhas", "serra"),
    "plains": ("planicie", "campos"),
    "marsh": ("pantano", "brejo"),
    "coast": ("costa", "litoral", "praia"),
    "mine_entrance": ("mina",),
    "abandoned_mine": ("mina abandonada",),
    "tower": ("torre",),
}
# A plain "a guilda" is the adventurers' guild, where every transported
# person is sent; "guilda de comerciantes" still wins by its longer label.
_PLACE_TYPE_LABELS_PT = {
    **_HUB_LOCATION_TYPE_LABELS_PT,
    **_WILD_LOCATION_TYPE_LABELS_PT,
    "adventurers_guild": ("guilda", "guilda dos aventureiros"),
}

_OBSERVATION_CUE_PATTERN = re.compile(
    r"\b(?:olha|olho|observa|observo|examina|examino)\b", re.IGNORECASE
)

# "Olho ao redor" classified FREEFORM never ran observe_surroundings, so the
# buildings around the square stayed undiscovered (confirmed in playtest).
_LOOK_AROUND_PATTERN = re.compile(
    r"\b(?:olha|olho|olhar|observa|observo|observar|examina|examino|examinar)\b"
    r".{0,20}\b(?:ao redor|em volta|a volta|arredores|o lugar|a praca|a vila)\b",
    re.IGNORECASE,
)

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
_EXIT_PHRASE_PATTERN = re.compile(r"\bsai\b|\bsaio\b|\bsaiu\b|\bsair\b", re.IGNORECASE)

# Third person ("Logan vai..."), first person ("Vou...", "Volto...") and
# infinitive ("Ir até...") all occur in real play; first person was
# confirmed live to be ignored when the Intent Parser fell back to FREEFORM.
_MOVEMENT_PHRASE_PATTERN = re.compile(
    r"\b(vai|vou|ir|vamos)\b.{0,20}\b(direcao|para|ate)\b"
    r"|\b(segue|sigo|seguimos|seguir)\b.{0,25}\b(direcao|para|ate)\b"
    r"|\b(chega|chego|chegar)\b"
    r"|\b(entra|entro|entrar)\b.{0,15}\bn[ao]\b"
    r"|\b(caminha|caminho|caminhar)\b.{0,20}\b(direcao|para|ate)\b"
    r"|\b(volta|volto|voltar|retorna|retorno|retornar)\b.{0,20}\b(direcao|para|ate)\b"
    # Playtest: "Vou dar uma olhada na guilda" became EXAMINE in the square.
    r"|\b(dar|dou|da)\s+uma\s+(olhada|passada)\s+n[ao]s?\b"
    r"|\b(passa|passo|passar)\s+n[ao]s?\b",
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
                )
            ),
            Location.region_id == character.region_id,
        )
        .all()
    )

    def _mentioned(label: str) -> bool:
        return re.search(rf"\b{re.escape(_strip_accents(label).casefold())}\b", text_no_accents) is not None

    def _best_label(location: Location) -> int:
        """Length of the longest label of this place in the text; the most
        specific one wins ("ruínas do templo" over "ruínas")."""
        labels = [location.name, _LOCATION_TYPE_LABELS_PT.get(location.type, ""),
                  *_PLACE_TYPE_LABELS_PT.get(location.type, ())]
        return max((len(label) for label in labels if label and _mentioned(label)), default=0)

    scored = [(score, location) for location in candidates if (score := _best_label(location))]
    best = max((score for score, _location in scored), default=0)
    matches = [location for score, location in scored if score == best]
    if not matches:
        matches = _visible_service_matching(db, character, _best_label)
    if len(matches) != 1:
        return None
    return matches[0]


def _visible_service_matching(db: Session, character: Character, best_label) -> list[Location]:
    """A building right next to where the character stands is in plain view,
    known or not. Playtest: the elder said "a guilda de aventureiros, ao
    norte", and "Vou dar uma olhada na guilda" only looked around the square.
    The one chosen becomes discovered, with its path, so the walk can run."""
    connections = (
        db.query(LocationConnection, Location)
        .join(Location, Location.id == LocationConnection.to_location_id)
        .filter(
            LocationConnection.from_location_id == character.location_id,
            LocationConnection.active.is_(True),
            Location.type.in_(tuple(_LOCATION_TYPE_LABELS_PT)),
        )
        .all()
    )
    scored = [(score, connection, location) for connection, location in connections if (score := best_label(location))]
    best = max((score for score, _c, _l in scored), default=0)
    chosen = [(connection, location) for score, connection, location in scored if score == best]
    if len(chosen) != 1:
        return []
    connection, location = chosen[0]
    discovery_service.set_location_discovery(db, character.id, location.id, DiscoveryStatus.DISCOVERED)
    discovery_service.discover_connection(db, character.id, connection.id)
    return [location]


def _handle_move(db: Session, campaign_id: str, character: Character, intent: Intent) -> tuple[str, int]:
    if not intent.target:
        return _where_to(db, character, ""), 0

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
            for location_type, labels in _PLACE_TYPE_LABELS_PT.items()
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
        # "a direção que ele indicou" is a pointer, not a place name.
        pointer = re.search(r"\b(?:que|direcao|onde|ali|la)\b", _strip_accents(intent.target).casefold())
        lead = "" if pointer else f"Você não conhece um lugar chamado '{intent.target}' por aqui."
        return _where_to(db, character, lead), 0

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
        travel_result = settlement_routes.move_within_reach(
            db,
            campaign_id,
            character,
            destination.id,
            pace=intent.pace,
        )
    except travel_service.TravelError as exc:
        walked = _walk_known_route(db, campaign_id, character, destination, intent.pace)
        if walked is None:
            return str(exc), 0
        return walked

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


def _walk_known_route(db: Session, campaign_id: str, character: Character, destination: Location, pace):
    """A known place a few trails away ("vou até a clareira", past the
    forest) is walked leg by leg along the character's known route.
    None when no known route links them."""
    from app.game.map.planning import plan_known_route

    plan = plan_known_route(db, campaign_id, character.id, character.location_id, destination.id)
    if plan is None or not plan.segments:
        return None
    minutes, stamina, passed = 0, 0.0, []
    for segment in plan.segments:
        try:
            leg = settlement_routes.move_within_reach(
                db, campaign_id, character, segment.to_location_id, pace=pace
            )
        except travel_service.TravelError as exc:
            stopped = db.get(Location, character.location_id)
            return (
                f"{character.name} segue a rota mas para em {stopped.name}: {exc}",
                minutes,
            )
        minutes += leg.minutes
        stamina += leg.stamina_spent
        passed.append(db.get(Location, segment.to_location_id).name)
    via = f", passando por {', '.join(passed[:-1])}" if len(passed) > 1 else ""
    return (
        f"{character.name} viaja até {destination.name}{via}. A viagem leva {minutes} minutos "
        f"e consome {stamina:g} de stamina.",
        minutes,
    )


_LEAVING_CLAUSE_PATTERN = re.compile(
    r"\bse\s+afasta\s+d[eoa]\s+.*?(?=\be\s+(?:se\s+)?aproxima\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)

# Age cues name the elder too. Playtest (the user's own save): "Ir falar com
# o homem de barba branca" resolved nobody, so the conversation was never
# registered and "qual o nome do senhor?" went unanswered next turn.
_ELDER_APPEARANCE_CUES = (
    "barba branca", "barbas brancas", "barba grisalha", "cabelo branco", "cabelos brancos",
    "cabelo grisalho", "cabelos grisalhos", "grisalho", "de cajado", "com o cajado", "com cajado",
)
_ROLE_REFERENCE_ALIASES = {
    "anciao": ("idoso", "velho", "senhor idoso", *_ELDER_APPEARANCE_CUES),
    "ancia": (
        "idosa", "velha", "senhora idosa", "grisalha", "cabelo branco", "cabelos brancos",
        "de cajado", "com o cajado", "com cajado",
    ),
}

_ROLE_FILLER_WORDS = frozenset({"da", "de", "do", "das", "dos", "e"})


def _role_content_words(role: str) -> list[str]:
    """Accent-stripped, casefolded words of a role, minus connectors."""
    return [
        word
        for word in re.findall(r"\w+", _strip_accents(role).casefold())
        if word not in _ROLE_FILLER_WORDS
    ]


_LOCAL_INHABITANT_REFERENCE_PATTERN = re.compile(
    r"\b(?:alguem\s+(?:que\s+)?(?:parec\w+\s+ser\s+)?(?:local|dali)|"
    r"morador(?:a)?|habitante|nativ[oa])\b",
    re.IGNORECASE,
)


def _addressed_candidates(
    raw_text: str,
    nearby_npcs,
    nearby_simulated_players,
) -> tuple[list["NPC"], list["SimulatedPlayer"]]:
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
        if any(
            re.search(rf"\b{re.escape(reference)}\b", raw_lower) is not None
            for reference in references
        ):
            return True
        # The qualifier alone ("a mulher da guilda de aventureiros") also
        # identifies the role, but only when it carries two or more content
        # words — "da vila" alone must stay unmatched (see above).
        qualifier_words = _role_content_words(role)[1:]
        return len(qualifier_words) >= 2 and re.search(
            r"\b" + r"\W+(?:\w+\W+){0,2}?".join(map(re.escape, qualifier_words)) + r"\b",
            raw_lower,
        ) is not None

    npc_matches = [
        npc for npc in nearby_npcs if _name_mentioned(npc.name) or _role_mentioned(npc.role)
    ]
    if len(npc_matches) > 1:
        # Two roles sharing a head word ("mestre da guilda de aventureiros"
        # / "...de comerciantes", confirmed in playtest) are told apart by
        # how many of each role's words the player actually used.
        def _role_score(npc) -> int:
            return sum(
                re.search(rf"\b{re.escape(word)}\b", raw_lower) is not None
                for word in _role_content_words(npc.role)
            )

        best = max(_role_score(npc) for npc in npc_matches)
        leaders = [npc for npc in npc_matches if _role_score(npc) == best]
        if len(leaders) == 1:
            npc_matches = leaders
    if (
        not npc_matches
        and len(nearby_npcs) == 1
        and _LOCAL_INHABITANT_REFERENCE_PATTERN.search(raw_lower)
    ):
        npc_matches = [nearby_npcs[0]]
    simulated_player_matches = [
        player for player in nearby_simulated_players if _name_mentioned(player.name)
    ]
    return npc_matches, simulated_player_matches


def _resolve_addressed_entity(
    raw_text: str,
    nearby_npcs,
    nearby_simulated_players,
) -> tuple["NPC | None", "SimulatedPlayer | None"]:
    """The single nearby person the raw text addresses, or (None, None)."""
    npc_matches, simulated_player_matches = _addressed_candidates(
        raw_text, nearby_npcs, nearby_simulated_players
    )
    if len(npc_matches) + len(simulated_player_matches) != 1:
        return None, None
    if npc_matches:
        return npc_matches[0], None
    return None, simulated_player_matches[0]


# Words that describe almost anyone; they can't single out a person from the
# narration the way a detail like "cajado" or "avental" can.
_GENERIC_PERSON_WORDS = frozenset({
    "senhor", "senhora", "homem", "mulher", "rapaz", "moca", "menino", "menina",
    "pessoa", "alguem", "aquele", "aquela", "esse", "essa", "este", "esta",
    "outro", "outra", "lado", "oposto", "perto", "ali", "aqui", "local",
})


# "Me aproximo de um dos recém-chegados" explicitly leaves the choice to the
# game; answering "diga com qual deles" asked for names the player can't
# know yet (confirmed in playtest).
_ANY_NEWCOMER_PATTERN = re.compile(
    r"\bum[a]? d[oa]s (?:outr[oa]s )?(?:recem[- ]chegad[oa]s|transportad[oa]s|forasteir[oa]s)\b"
)


def _any_newcomer(raw_text: str, nearby_simulated_players) -> "SimulatedPlayer | None":
    if not nearby_simulated_players:
        return None
    if not _ANY_NEWCOMER_PATTERN.search(_strip_accents(raw_text).casefold()):
        return None
    social = [player for player in nearby_simulated_players if player.archetype == "SOCIAL"]
    return sorted(social or nearby_simulated_players, key=lambda player: player.id)[0]


def _resolve_by_narrated_description(
    db: Session,
    campaign_id: str,
    character_id: str,
    intent: Intent,
    nearby_npcs,
    nearby_simulated_players,
) -> tuple["NPC | None", "SimulatedPlayer | None"]:
    """Resolve a target the player picked out by a detail the narrator gave
    ("o senhor de cajado") rather than by name or role.

    Confirmed live: the opening narration described the elder as "o mais
    velho ... apoia as mãos no cajado"; "Vou até o senhor de cajado" matched
    nobody, so no interlocutor was recorded and the next question to him came
    back as "Nada acontece de imediato." The detail words of the Intent
    Parser's target (only those the player actually typed) are looked up in
    recent narration, newest first, and the sentences holding them go through
    the same deterministic name/role resolution. The newest narration that
    identifies anyone decides: exactly one person, or nothing at all.
    """
    if not intent.target:
        return None, None
    raw_words = set(re.findall(r"\w+", _strip_accents(intent.raw_text).casefold()))
    descriptors = {
        word
        for word in re.findall(r"\w+", _strip_accents(intent.target).casefold())
        if len(word) >= 4 and word not in _GENERIC_PERSON_WORDS and word in raw_words
    }
    if not descriptors:
        return None, None

    narrations = [
        entry.text
        for entry in get_recent_story_log(db, campaign_id, character_id)
        if entry.kind == SPEAKER_NARRATOR and entry.text
    ]
    for narration in reversed(narrations):
        sentences = [
            sentence
            for sentence in re.split(r"(?<=[.!?])\s+|\n+", narration)
            if descriptors & set(re.findall(r"\w+", _strip_accents(sentence).casefold()))
        ]
        if not sentences:
            continue
        resolved = {
            result
            for result in (
                _resolve_addressed_entity(sentence, nearby_npcs, nearby_simulated_players)
                for sentence in sentences
            )
            if result != (None, None)
        }
        if len(resolved) > 1:
            return None, None
        if resolved:
            return next(iter(resolved))
    return None, None


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
    if npc is None and player is None:
        npc, player = _resolve_by_narrated_description(
            db, campaign_id, character.id, intent, state.nearby_npcs, state.nearby_simulated_players
        )
    if npc is None and player is None:
        player = _any_newcomer(intent.raw_text, state.nearby_simulated_players)
    if npc is not None:
        npcs_service.meet_npc(db, campaign_id, character.id, npc.id)
        return npc, None
    if player is not None:
        players_service.meet_simulated_player(db, campaign_id, character.id, player.id)
        return None, player
    return None, None


def _resolve_target_person(
    db: Session, campaign_id: str, character: Character, intent: Intent, state
) -> tuple[list, list]:
    """Who an invitation/recruitment/expulsion is about: a name the player
    used, then a reference in the raw text, then whoever they are already
    talking to ("Quer vir comigo?")."""
    chosen = people_present.person_for_ref(state, intent.person_ref) or (
        people_present.match_by_appearance(db, state, intent.raw_text)
    )
    if chosen is not None:
        kind, person = chosen
        return ([person], []) if kind == "npc" else ([], [person])
    target = _strip_accents(intent.target or "").casefold().strip()

    def _named(people):
        return [
            person for person in people
            if target and (
                target in _strip_accents(person.name).casefold()
                or _strip_accents(person.name).casefold().split()[0] in target.split()
            )
        ]

    npc_hits, player_hits = _named(state.nearby_npcs), _named(state.nearby_simulated_players)
    if len(npc_hits) + len(player_hits) != 1:
        npc, player = _resolve_addressed_entity(
            intent.raw_text, state.nearby_npcs, state.nearby_simulated_players
        )
        npc_hits, player_hits = ([npc] if npc else []), ([player] if player else [])
    if not npc_hits and not player_hits:
        active_player = players_service.get_active_simulated_player_interlocutor(
            db, campaign_id, character.id, character.location_id
        )
        active_npc = npcs_service.get_active_interlocutor(
            db, campaign_id, character.id, character.location_id
        )
        if active_player is not None and any(
            candidate.id == active_player.id for candidate in state.nearby_simulated_players
        ):
            player_hits = [active_player]
        elif active_npc is not None and any(
            candidate.id == active_npc.id for candidate in state.nearby_npcs
        ):
            npc_hits = [active_npc]
    return npc_hits, player_hits


def _handle_group_invite(
    db: Session, campaign_id: str, character: Character, intent: Intent, state
) -> tuple[str, int]:
    npc_hits, player_hits = _resolve_target_person(db, campaign_id, character, intent, state)
    if player_hits and not npc_hits:
        change = companions_service.invite_simulated_player(
            db, campaign_id, character, player_hits[0]
        )
    elif npc_hits and not player_hits:
        change = companions_service.decline_for_duties(
            character, npc_hits[0].name, db.get(Location, character.location_id)
        )
    else:
        return "Diga quem você quer convidar para viajar junto.", 0
    return change.summary, 1


def _handle_guild_membership(
    db: Session, campaign_id: str, character: Character, intent: Intent, state
) -> tuple[str, int]:
    npc_hits, player_hits = _resolve_target_person(db, campaign_id, character, intent, state)
    if npc_hits and not player_hits:
        return (
            f"{npc_hits[0].name} é morador daqui e não faz parte de guildas de Transportados.",
            0,
        )
    if not player_hits:
        return "Diga de quem você está falando.", 0
    if intent.type == ActionIntentType.RECRUIT_TO_ORGANIZATION:
        change = guilds_service.recruit(db, campaign_id, character, player_hits[0])
    else:
        change = guilds_service.expel(db, character, player_hits[0])
    return change.summary, 1


def _handle_explore(db: Session, campaign_id: str, character: Character) -> tuple[str, int]:
    """Active search around here: at most one unknown route found, told as
    the player can know it — direction and kind of place, never the name of
    somewhere they have not been."""
    outcome = exploration.explore_current_location(db, campaign_id, character)
    hours = f"{outcome.minutes_spent // 60}h{outcome.minutes_spent % 60:02d}"
    if not outcome.success:
        return (
            f"{character.name} explora os arredores por {hours}, mas não encontra nenhum caminho novo.",
            outcome.minutes_spent,
        )
    connection = db.get(LocationConnection, outcome.found_connection_id)
    destination = db.get(Location, outcome.found_location_id)
    kind = _PLACE_TYPE_LABELS_PT.get(destination.type, ("um lugar",))[0]
    route = connection_type_label_pt(connection.connection_type)
    direction = f" para o {connection.direction}" if connection.direction else ""
    return (
        f"{character.name} explora os arredores por {hours} e encontra uma {route}{direction}, "
        f"que leva a {_with_article(kind)} ainda desconhecido.",
        outcome.minutes_spent,
    )


_FEMININE_PLACE_WORDS = ("floresta", "mata", "clareira", "caverna", "gruta", "torre", "mina", "estrada",
                         "costa", "praia", "planicie", "serra", "vila", "praca", "ruinas")


def _with_article(kind: str) -> str:
    if kind in ("um lugar",):
        return kind
    head = kind.split()[0]
    return f"{'uma' if head in _FEMININE_PLACE_WORDS else 'um'} {kind}"


def _handle_guild_rank(
    db: Session, campaign_id: str, character: Character, intent: Intent, state
) -> tuple[str, int]:
    text = " ".join(filter(None, (intent.target, intent.raw_text)))
    member = guilds_service.member_named(db, character, text)
    if member is None:
        _npc_hits, player_hits = _resolve_target_person(db, campaign_id, character, intent, state)
        member = player_hits[0] if len(player_hits) == 1 else None
    if member is None:
        return "Diga qual membro da guilda você quer promover, rebaixar ou nomear líder.", 0
    normalized = _strip_accents(intent.raw_text or "").casefold()
    if re.search(r"\brebaix", normalized):
        change = guilds_service.demote(db, character, member)
    elif re.search(r"\b(?:lideranca|chefia|comando|lider)\b", normalized):
        change = guilds_service.transfer_leadership(db, character, member)
    else:
        change = guilds_service.promote(db, character, member)
    return change.summary, 1


def _handle_guild_diplomacy(
    db: Session, campaign_id: str, character: Character, intent: Intent, state
) -> tuple[str, int]:
    """The other guild is named, or is the guild of the transported person
    the player is addressing. An alliance needs that guild's leader or a
    founder standing here to accept."""
    text = " ".join(filter(None, (intent.target, intent.raw_text)))
    other = guilds_service.known_guild_named(db, character, text)
    present = guilds_service.guilds_with_leadership_present(db, character.location_id)
    if other is None:
        _npc_hits, player_hits = _resolve_target_person(db, campaign_id, character, intent, state)
        if len(player_hits) == 1:
            other = guilds_service.transported_guild_of(
                db, CombatActorType.SIMULATED_PLAYER, player_hits[0].id
            )
    if other is None and len(present) == 1:
        other = present[0][0]
    if other is None:
        return "Diga com qual guilda (pelo nome) você quer tratar.", 0
    normalized = _strip_accents(intent.raw_text or "").casefold()
    if re.search(r"\b(?:rompo|romper|rompemos|desfaco|desfazer|encerro|encerrar)\b", normalized):
        change = guilds_service.break_alliance(db, character, other)
    elif re.search(r"\briva(?:l|is|lidade)\b", normalized):
        change = guilds_service.declare_rivalry(db, character, other)
    else:
        envoy = next((player for organization, player in present if organization.id == other.id), None)
        if envoy is None:
            return (
                f'Uma aliança com "{other.name}" precisa ser acertada com o líder ou um fundador '
                "dela, frente a frente.",
                0,
            )
        change = guilds_service.propose_alliance(db, campaign_id, character, other, envoy)
    return change.summary, 5 if change.changed else 1


_WAIT_UNTIL = (
    # (pattern, hour) — first match wins, so the specific ones come first.
    (r"meia[- ]noite", 0),
    (r"amanhecer|nascer do sol|alvorada|de manha cedo|amanha de manha", 6),
    (r"meio[- ]dia|almoco", 12),
    (r"fim da tarde|final da tarde|entardecer|por do sol|anoitecer|cair da noite", 18),
    (r"\bnoite\b|jantar|ceia", 19),
    (r"\btarde\b", 14),
    (r"\bmanha\b", 8),
)
_WAIT_NUMBERS = {"uma": 1, "um": 1, "duas": 2, "dois": 2, "tres": 3, "quatro": 4, "cinco": 5,
                 "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12}
_MAX_WAIT_MINUTES = 16 * 60


def _wait_minutes(text: str, hour: int, minute: int) -> int:
    """How long the player asked to wait. Playtest: "Espero até o fim da
    tarde" always passed 15 minutes, while the narration let the whole
    afternoon go by and nobody who comes to the inn at night showed up."""
    plain = _strip_accents(text).casefold()
    if re.search(r"meia hora", plain):
        return 30
    amount = re.search(r"\b(\d{1,2}|" + "|".join(_WAIT_NUMBERS) + r")\s+(hora|horas|minuto|minutos)\b", plain)
    if amount:
        value = int(amount.group(1)) if amount.group(1).isdigit() else _WAIT_NUMBERS[amount.group(1)]
        return min(value * (60 if amount.group(2).startswith("hora") else 1), _MAX_WAIT_MINUTES)
    if re.search(r"\b(?:ate|por)\b", plain):
        for pattern, target in _WAIT_UNTIL:
            if re.search(pattern, plain):
                minutes = (target * 60 - (hour * 60 + minute)) % (24 * 60)
                return min(minutes or 24 * 60, _MAX_WAIT_MINUTES)
    return 15


WHO_DO_YOU_MEAN_PREFIX = "Há mais de uma pessoa aqui."
WHERE_TO_QUESTION = "Para onde você quer ir?"


def _where_to(db: Session, character: Character, lead: str) -> str:
    """Asked instead of narrated. Playtest: "vou na direção que ele indicou"
    moved nobody, yet the narration walked Logan out of the village."""
    known = (
        db.query(Location)
        .join(CharacterLocationDiscovery, CharacterLocationDiscovery.location_id == Location.id)
        .filter(
            CharacterLocationDiscovery.character_id == character.id,
            CharacterLocationDiscovery.status.in_((DiscoveryStatus.DISCOVERED.value, DiscoveryStatus.VISITED.value)),
            Location.region_id == character.region_id,
            Location.id != character.location_id,
        )
        .order_by(Location.name)
        .all()
    )
    names = [discovery_service.place_label(db, location, location.name) for location in known]
    listed = f" Lugares que você conhece: {', '.join(names)}." if names else ""
    return f"{lead} {WHERE_TO_QUESTION}{listed}".strip()

_QUEST_XP_REWARD = re.compile(r"\s*Recompensa de missão: (.+?)\.\s*$")
_XP_NOTE = re.compile(r"\s*\(\+[\d.,]+ XP base[^)]*\)")


def _without_progression_numbers(mechanical_summary: str) -> str:
    """What the narrator may know of progression: that a contract was done,
    never its XP. Playtest: "+10 XP" became "— Dez de experiência pelo
    trabalho" in the guildmaster's mouth. The full summary (with numbers)
    stays in the event log and the action result."""
    text = _XP_NOTE.sub("", mechanical_summary)
    reward = _QUEST_XP_REWARD.search(text)
    if reward:
        names = "; ".join(part.rsplit(":", 1)[0].strip() for part in reward.group(1).split(";"))
        text = text[: reward.start()] + f" Missão concluída: {names}."
    return text



def _who_do_you_mean(db: Session, state) -> str:
    """Asked instead of narrated: the narrator used to voice someone anyway
    while the engine had registered no conversation (the user's own save:
    two turns "answered" by the elder, none of them counted)."""
    descriptions = []
    for kind, person in people_present.present_people(state):
        if kind == "npc":
            descriptions.append(people_present.npc_appearance_pt(db, state.character.campaign_id, person, short=True))
        else:
            features = ensure_transported_features(db, person).rstrip(".")
            descriptions.append(f"{features[:1].lower()}{features[1:]}, com o traje dos transportados")
    listed = "; ".join(dict.fromkeys(descriptions))
    return f"{WHO_DO_YOU_MEAN_PREFIX} Com quem você quer falar? Aqui estão: {listed}."


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
    chosen = people_present.person_for_ref(state, intent.person_ref) or (
        people_present.match_by_appearance(db, state, intent.raw_text)
    )
    if chosen is not None:
        kind, person = chosen
        npc, simulated_player = (person, None) if kind == "npc" else (None, person)

    literal_target = None
    if intent.target and chosen is None:
        raw_lower = intent.raw_text.casefold()
        target_words = [word for word in intent.target.split() if len(word) >= 3]
        if any(word.casefold() in raw_lower for word in target_words):
            literal_target = intent.target

    resolve_from_nearby = not literal_target and chosen is None
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
            if resolved_npc is None and resolved_player is None:
                resolved_npc, resolved_player = _resolve_by_narrated_description(
                    db, campaign_id, character.id, intent,
                    state.nearby_npcs, state.nearby_simulated_players,
                )
            if resolved_npc is not None:
                npc = resolved_npc
            elif resolved_player is not None:
                simulated_player = resolved_player
            else:
                # A scene description the narrator itself offered ("o
                # homem do lado oposto") names no role or name at all.
                # Confirmed live: refusing it outright told the narrator
                # "ninguém aqui" while the active interlocutor stood right
                # there, so the narration made him vanish. Treat it like an
                # untargeted address instead.
                resolve_from_nearby = True

    if resolve_from_nearby:
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
            referenced_npcs, referenced_players = _addressed_candidates(
                intent.raw_text, state.nearby_npcs, state.nearby_simulated_players
            )
            if resolved_npc is not None:
                npc = resolved_npc
            elif resolved_player is not None:
                simulated_player = resolved_player
            elif len(referenced_npcs) + len(referenced_players) > 1:
                # "Falo com o mestre da guilda" with two guild masters here
                # named someone, just not one person; continuing the old
                # conversation answered as the wrong NPC (seen in playtest).
                return _who_do_you_mean(db, state), 0
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
                    elif (
                        newcomer := _any_newcomer(intent.raw_text, state.nearby_simulated_players)
                    ) is not None:
                        simulated_player = newcomer
                    else:
                        return _who_do_you_mean(db, state), 0

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
        accepted, way = _accept_request_by_agreement(db, campaign_id, character, npc, intent.raw_text)

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
            f"{npc.name} ({npc.role})."
            + (f" {character.name} aceita o pedido '{accepted.name}'." if accepted else "")
            + (f" {npc.name} explica o caminho até {', '.join(place.name for place in way)}." if way else ""),
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


_AGREEMENT_PATTERN = re.compile(
    r"\b(?:pode deixar|deixa comigo|deixe comigo|conte comigo|pode contar comigo|eu ajudo|"
    r"vou ajudar|ajudo sim|aceito|combinado|fechado|eu faco|eu levo|eu vejo|eu procuro|eu busco|"
    r"eu vou (?:la|ver|buscar|levar|procurar|falar|conferir))\b"
)


def _known_request_of(db: Session, campaign_id: str, character: Character, npc):
    """This NPC's open request, once they have told the player about it."""
    from app.game.quests.discovery import is_quest_known_to_character
    from app.game.quests.local_requests import open_request_of

    quest = open_request_of(db, npc)
    if quest is None or not is_quest_known_to_character(db, campaign_id, character.id, quest.id):
        return None
    return quest


def _accept_request_by_agreement(db: Session, campaign_id: str, character: Character, npc, text: str):
    """Saying yes to the one who asked ("Pode deixar, eu vejo as armadilhas")
    takes their request. Only a request they already told about, and never
    a question ("posso ajudar?")."""
    plain = _strip_accents(text or "").casefold()
    if "?" in plain or not _AGREEMENT_PATTERN.search(plain):
        return None, []
    quest = _known_request_of(db, campaign_id, character, npc)
    if quest is None:
        return None, []
    try:
        quests_service.accept_known_quest(db, campaign_id, character.id, quest.id)
    except quests_service.QuestLifecycleError:
        return None, []
    from app.game.quests.local_requests import reveal_the_way

    places = reveal_the_way(db, character, quest)
    return quest, places


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

    # An empty board must say so, or the narrator fills it with invented
    # papers (seen in playtest) — but only when no board here has an active
    # notice; boards now carry real postings.
    location = db.get(Location, character.location_id)
    if location is not None and location.type == "notice_board":
        has_active_notice = (
            db.query(Notice)
            .join(LocationFeature, LocationFeature.id == Notice.board_feature_id)
            .filter(
                LocationFeature.location_id == location.id,
                Notice.status == NoticeStatus.ACTIVE,
            )
            .first()
            is not None
        )
        if not has_active_notice:
            lines.append("Não há nenhum aviso pregado no quadro.")

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

    quests_service.evaluate_objective_trigger(
        db,
        character.campaign_id,
        character.id,
        ObjectiveTriggerType.READ_NOTICE_BOARD,
        subject_id=board.id,
    )

    lines = [f"{character.name} lê o {board.name}."]
    if not notices:
        lines.append("Não há nenhum aviso ativo no momento.")
    else:
        lines.extend(f"[{notice.category}] {notice.title}: {notice.text}" for notice in notices)
    return lines
