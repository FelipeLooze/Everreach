"""Hunger/thirst survival system — requested as a follow-up after Phase 17.
Deliberately slow-draining (not "ate, 30 minutes later hungry again") and
not hardcore (only a mild stamina-recovery penalty, never HP damage or
death). See app.game.survival.service for the design rationale."""

from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import ActionIntentType, CharacterAttributeKey, RecoveryType
from app.db.models.character import CharacterAttribute
from app.game import engine
from app.game.character.service import create_character
from app.game.combat.recovery import recover_character
from app.game.survival import service as survival
from app.game.time.clock import advance_world_time, get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


class _PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "O descanso transcorre conforme determinado pelo sistema."


def _set_endurance(db_session, character, value):
    attribute = (
        db_session.query(CharacterAttribute)
        .filter(
            CharacterAttribute.character_id == character.id,
            CharacterAttribute.key == CharacterAttributeKey.ENDURANCE.value,
        )
        .one()
    )
    attribute.value = value
    db_session.flush()


def test_character_starts_at_full_hunger_and_thirst_with_no_decay_tracked_yet(db_session):
    campaign = create_campaign(db_session, "Sobrevivencia Inicial", world_seed=1)
    logan = create_character(db_session, campaign.id, "Logan")

    assert logan.hunger_current == 100.0
    assert logan.hunger_max == 100.0
    assert logan.thirst_current == 100.0
    assert logan.thirst_max == 100.0
    assert logan.survival_updated_at_minute is None


def test_higher_endurance_raises_the_maximum_not_the_drain_rate(db_session):
    campaign = create_campaign(db_session, "Resistencia", world_seed=2)
    logan = create_character(db_session, campaign.id, "Logan")
    _set_endurance(db_session, logan, 16)

    survival.recalculate_survival_max(db_session, logan)

    assert logan.hunger_max == 100.0 + 6 * survival.ENDURANCE_MAX_BONUS_PER_POINT
    assert logan.thirst_max == 100.0 + 6 * survival.ENDURANCE_MAX_BONUS_PER_POINT
    assert logan.hunger_current == logan.hunger_current
    assert survival.HUNGER_DECAY_PER_HOUR == 100.0 / 48.0


def test_recalculate_survival_max_never_raises_current_above_new_lower_max(db_session):
    campaign = create_campaign(db_session, "Reducao De Maximo", world_seed=3)
    logan = create_character(db_session, campaign.id, "Logan")
    logan.hunger_current = 100.0
    _set_endurance(db_session, logan, 6)

    survival.recalculate_survival_max(db_session, logan)

    assert logan.hunger_max == 100.0 - 4 * survival.ENDURANCE_MAX_BONUS_PER_POINT
    assert logan.hunger_current == logan.hunger_max


def test_first_decay_call_only_establishes_the_baseline_without_draining(db_session):
    campaign = create_campaign(db_session, "Linha De Base", world_seed=4)
    logan = create_character(db_session, campaign.id, "Logan")

    survival.apply_survival_decay(db_session, campaign.id, logan)

    assert logan.hunger_current == 100.0
    assert logan.thirst_current == 100.0
    assert logan.survival_updated_at_minute is not None


def test_decay_is_slow_a_single_hour_barely_moves_the_needle(db_session):
    campaign = create_campaign(db_session, "Decaimento Lento", world_seed=5)
    logan = create_character(db_session, campaign.id, "Logan")
    survival.apply_survival_decay(db_session, campaign.id, logan)

    advance_world_time(db_session, campaign.id, 60)
    survival.apply_survival_decay(db_session, campaign.id, logan)

    assert logan.hunger_current == 100.0 - survival.HUNGER_DECAY_PER_HOUR
    assert logan.thirst_current == 100.0 - survival.THIRST_DECAY_PER_HOUR
    assert logan.hunger_current > 97.0
    assert logan.thirst_current > 96.0


def test_decay_never_drops_below_zero_even_after_a_huge_gap(db_session):
    campaign = create_campaign(db_session, "Jejum Longo", world_seed=6)
    logan = create_character(db_session, campaign.id, "Logan")
    survival.apply_survival_decay(db_session, campaign.id, logan)

    advance_world_time(db_session, campaign.id, 60 * 24 * 10)
    survival.apply_survival_decay(db_session, campaign.id, logan)

    assert logan.hunger_current == 0.0
    assert logan.thirst_current == 0.0


def test_feed_and_drink_restore_but_cap_at_max(db_session):
    campaign = create_campaign(db_session, "Alimentacao", world_seed=7)
    logan = create_character(db_session, campaign.id, "Logan")
    logan.hunger_current = 40.0
    logan.thirst_current = 40.0
    db_session.flush()

    survival.feed(db_session, logan, 30.0)
    survival.drink(db_session, logan, 90.0)

    assert logan.hunger_current == 70.0
    assert logan.thirst_current == 100.0


def test_stamina_recovery_is_unaffected_when_well_fed(db_session):
    campaign = create_campaign(db_session, "Bem Alimentado", world_seed=8)
    logan = create_character(db_session, campaign.id, "Logan")
    logan.stamina_current = 0.0
    db_session.flush()

    result = recover_character(
        db_session, campaign.id, logan,
        recovery_key="rest_1", recovery_type=RecoveryType.SHORT_REST,
    )

    assert result.recovery.stamina_after == 10.0


def test_stamina_recovery_is_penalized_when_critically_hungry(db_session):
    campaign = create_campaign(db_session, "Fome Critica", world_seed=9)
    logan = create_character(db_session, campaign.id, "Logan")
    logan.stamina_current = 0.0
    logan.hunger_current = 5.0
    db_session.flush()

    result = recover_character(
        db_session, campaign.id, logan,
        recovery_key="rest_1", recovery_type=RecoveryType.SHORT_REST,
    )

    assert result.recovery.stamina_after == 5.0


def test_stamina_recovery_is_mildly_penalized_when_low_on_thirst(db_session):
    campaign = create_campaign(db_session, "Sede Baixa", world_seed=10)
    logan = create_character(db_session, campaign.id, "Logan")
    logan.stamina_current = 0.0
    logan.thirst_current = 30.0
    db_session.flush()

    result = recover_character(
        db_session, campaign.id, logan,
        recovery_key="rest_1", recovery_type=RecoveryType.SHORT_REST,
    )

    assert result.recovery.stamina_after == 8.0


def test_hp_and_mana_recovery_are_never_affected_by_survival_state(db_session):
    campaign = create_campaign(db_session, "Recuperacao Isolada", world_seed=11)
    logan = create_character(db_session, campaign.id, "Logan")
    logan.hp_current = 1.0
    logan.mana_current = 0.0
    logan.hunger_current = 1.0
    logan.thirst_current = 1.0
    db_session.flush()

    result = recover_character(
        db_session, campaign.id, logan,
        recovery_key="rest_1", recovery_type=RecoveryType.SHORT_REST,
    )

    assert result.recovery.hp_after == 6.0
    assert result.recovery.mana_after == 2.5


def test_resting_through_the_engine_advances_world_time_and_decays_survival(db_session, monkeypatch):
    campaign = create_campaign(db_session, "Descanso Via Engine", world_seed=12)
    region, location = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region.id, location.id)
    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.REST,
            target=None,
            raw_text="Eu descanso.",
        ),
    )

    started_at = get_world_time(db_session, campaign.id).total_minutes()
    logan.survival_updated_at_minute = started_at
    db_session.flush()

    engine.resolve_action(
        db_session,
        _PassiveLLM(),
        campaign.id,
        logan.id,
        "Eu descanso.",
        action_key="rest-survival-001",
    )

    assert logan.survival_updated_at_minute == started_at + 60
    assert logan.hunger_current == 100.0 - survival.HUNGER_DECAY_PER_HOUR
    assert logan.thirst_current == 100.0 - survival.THIRST_DECAY_PER_HOUR
