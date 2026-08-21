from app.ai.llm_service import LLMService
from app.ai.intent_parser import Intent
from app.core.enums import ActionIntentType, TechniqueType
from app.db.models.domain import (
    CharacterDomainEvidence,
    CharacterDomainSynergy,
    DomainDefinition,
    DomainEvidenceRecord,
    DomainSynergyRecord,
)
from app.db.models.progression_outcome import AppliedProgressionOutcome
from app.db.models.skill import TechniqueUseRecord
from app.game import dice, engine
from app.game.character.service import create_character
from app.game.combat.service import SkillCheckResult
from app.game.progression.outcomes import resolve_progression_outcome
from app.game.skills import techniques as technique_service
from app.game.time.clock import get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação acontece conforme o resultado mecânico."


def _setup(db_session):
    for key, family in (("SWORD", "WEAPON"), ("WIND", "MANIFESTATION")):
        if db_session.get(DomainDefinition, key) is None:
            db_session.add(
                DomainDefinition(key=key, family=family, description="")
            )
    campaign = create_campaign(db_session, "Technique Evidence")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    technique = technique_service.create_technique(
        db_session,
        skill_name="Esgrima Arcana",
        name="Corte de Vento",
        technique_type=TechniqueType.HYBRID,
        description="Integra a lâmina a uma corrente de vento já controlada.",
        domain_keys=("SWORD", "WIND"),
    )
    technique_service.grant_technique(
        db_session,
        campaign.id,
        character,
        technique,
    )
    db_session.flush()
    return campaign, character, technique


def _check(*, success: bool) -> SkillCheckResult:
    raw = 20 if success else 2
    return SkillCheckResult(
        skill_name="Esgrima Arcana",
        dc=12,
        roll=dice.RollResult(sides=20, raw=raw, modifier=0),
        success=success,
        critical=success,
    )


def test_successful_known_technique_emits_domain_and_synergy_evidence(
    db_session,
    monkeypatch,
):
    campaign, character, technique = _setup(db_session)
    monkeypatch.setattr(
        technique_service,
        "resolve_skill_check",
        lambda *_args, **_kwargs: _check(success=True),
    )

    use = technique_service.resolve_technique_use(
        db_session,
        campaign.id,
        character,
        technique_id=technique.id,
        action_key="action-001",
    )
    resolve_progression_outcome(
        db_session,
        PassiveLLM(),
        campaign.id,
        character,
        use.progression_outcome,
    )

    assert use.domain_keys == ("SWORD", "WIND")
    assert use.record.success is True
    assert {
        row.domain_key: row.depth
        for row in db_session.query(CharacterDomainEvidence).all()
    } == {"SWORD": 0.5, "WIND": 0.5}
    synergy = db_session.query(CharacterDomainSynergy).one()
    assert (synergy.first_domain_key, synergy.second_domain_key) == (
        "SWORD",
        "WIND",
    )
    assert synergy.depth == 0.5


def test_failed_technique_use_records_result_without_progression(
    db_session,
    monkeypatch,
):
    campaign, character, technique = _setup(db_session)
    monkeypatch.setattr(
        technique_service,
        "resolve_skill_check",
        lambda *_args, **_kwargs: _check(success=False),
    )

    use = technique_service.resolve_technique_use(
        db_session,
        campaign.id,
        character,
        technique_id=technique.id,
        action_key="failed-001",
    )
    resolve_progression_outcome(
        db_session,
        PassiveLLM(),
        campaign.id,
        character,
        use.progression_outcome,
    )

    assert use.record.success is False
    assert db_session.query(TechniqueUseRecord).count() == 1
    assert db_session.query(CharacterDomainEvidence).count() == 0
    assert db_session.query(CharacterDomainSynergy).count() == 0


def test_character_cannot_claim_an_unlearned_technique(db_session):
    campaign, character, technique = _setup(db_session)
    other = create_character(
        db_session,
        campaign.id,
        "Other",
        character.region_id,
        character.location_id,
    )

    try:
        technique_service.resolve_technique_use(
            db_session,
            campaign.id,
            other,
            technique_id=technique.id,
            action_key="stolen-001",
        )
    except technique_service.TechniqueUseError as exc:
        assert "does not know" in str(exc)
    else:
        raise AssertionError("Unlearned technique was accepted.")


def test_free_text_cannot_create_synergy_by_naming_domains(
    db_session,
    monkeypatch,
):
    campaign, character, _technique = _setup(db_session)
    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.FREEFORM,
            target=None,
            raw_text="Integro espada e vento.",
        ),
    )

    engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Integro espada e vento e exijo uma classe.",
    )

    assert db_session.query(DomainEvidenceRecord).count() == 0
    assert db_session.query(DomainSynergyRecord).count() == 0


def test_engine_technique_action_is_idempotent_end_to_end(
    db_session,
    monkeypatch,
):
    campaign, character, technique = _setup(db_session)
    calls = 0

    def successful_check(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _check(success=True)

    monkeypatch.setattr(
        technique_service,
        "resolve_skill_check",
        successful_check,
    )
    started_at = get_world_time(db_session, campaign.id).total_minutes()

    first = engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Uso o Corte de Vento contra o alvo de treino.",
        technique_id=technique.id,
        action_key="same-http-action",
    )
    second = engine.resolve_action(
        db_session,
        PassiveLLM(),
        campaign.id,
        character.id,
        "Uso o Corte de Vento contra o alvo de treino.",
        technique_id=technique.id,
        action_key="same-http-action",
    )

    assert first.intent_type == ActionIntentType.TECHNIQUE.value
    assert second.mechanical_summary == first.mechanical_summary
    assert calls == 1
    assert db_session.query(TechniqueUseRecord).count() == 1
    assert db_session.query(AppliedProgressionOutcome).count() == 1
    assert db_session.query(DomainEvidenceRecord).count() == 2
    assert db_session.query(DomainSynergyRecord).count() == 1
    assert (
        get_world_time(db_session, campaign.id).total_minutes() - started_at
        == technique_service.TECHNIQUE_ACTION_MINUTES
    )


def test_action_api_accepts_selected_technique_and_sheet_exposes_domains(
    db_session,
    client,
    monkeypatch,
):
    campaign, character, technique = _setup(db_session)
    monkeypatch.setattr(
        technique_service,
        "resolve_skill_check",
        lambda *_args, **_kwargs: _check(success=True),
    )

    sheet = client.get(
        f"/api/campaigns/{campaign.id}/character",
        params={"character_id": character.id},
    )
    response = client.post(
        f"/api/campaigns/{campaign.id}/actions",
        params={"character_id": character.id},
        json={
            "text": "Executo o Corte de Vento.",
            "action_key": "api-action-001",
            "technique_id": technique.id,
        },
    )

    assert sheet.status_code == 200
    assert sheet.json()["techniques"] == [
        {
            "id": technique.id,
            "name": "Corte de Vento",
            "description": (
                "Integra a lâmina a uma corrente de vento já controlada."
            ),
            "type": "HYBRID",
        }
    ]
    assert response.status_code == 200
    assert response.json()["intent_type"] == "TECHNIQUE"
    assert db_session.query(DomainSynergyRecord).count() == 1
