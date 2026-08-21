"""Phase 11I integration: a freeform EXPERIMENT intent flowing through the
real engine.resolve_action pipeline, exactly as it would from a live LLM
classification (mocked here for determinism)."""

from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import ActionIntentType
from app.db.models.domain import DomainDefinition
from app.game import engine
from app.game.character.service import create_character
from app.game.skills import technique_evidence as evidence_service
from app.game.world.seed import create_campaign, seed_initial_region


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação acontece conforme o resultado mecânico."


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Engine Experiment")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    db_session.commit()
    return campaign, character


def test_experiment_intent_spends_mana_and_awards_evidence_end_to_end(db_session, monkeypatch):
    campaign, character = _setup(db_session)
    starting_mana = character.mana_current

    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.EXPERIMENT,
            target=None,
            raw_text="Eu comprimo vento na palma da mão e solto de uma vez.",
            pattern_key="wind-palm-compress",
            domains="WIND",
            technique_type="MAGICAL",
        ),
    )

    result = engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Eu comprimo vento na palma da mão e solto de uma vez.",
        action_key="engine-experiment-1",
    )

    assert result.intent_type == ActionIntentType.EXPERIMENT.value
    assert "experimenta" in result.mechanical_summary
    assert character.mana_current == starting_mana - 3.0

    maturity = evidence_service.technique_pattern_maturity(
        db_session, character.id, "wind-palm-compress"
    )
    assert maturity.evidence_count == 1
    assert maturity.depth > 0


def test_experiment_intent_is_idempotent_via_action_key(db_session, monkeypatch):
    campaign, character = _setup(db_session)

    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.EXPERIMENT,
            target=None,
            raw_text="Eu comprimo vento na palma da mão.",
            pattern_key="wind-palm-compress",
            domains="WIND",
            technique_type="MAGICAL",
        ),
    )

    first = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id,
        "Eu comprimo vento na palma da mão.",
        action_key="engine-experiment-replay",
    )
    mana_after_first = character.mana_current

    second = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id,
        "Eu comprimo vento na palma da mão.",
        action_key="engine-experiment-replay",
    )

    assert second.mechanical_summary == first.mechanical_summary
    assert character.mana_current == mana_after_first

    maturity = evidence_service.technique_pattern_maturity(
        db_session, character.id, "wind-palm-compress"
    )
    assert maturity.evidence_count == 1  # not double-counted on replay
