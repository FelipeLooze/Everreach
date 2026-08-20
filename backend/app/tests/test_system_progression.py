import json
import re

from app.ai.context_builder import build_context
from app.ai.llm_service import LLMService
from app.core.enums import (
    AttributeEvidenceSource,
    CharacterAttributeKey,
    CharacterResourceKey,
    CharacterXPSource,
    DomainEvidenceSource,
    ProfessionXPSource,
    ResourceGrowthSource,
)
from app.db.models.character_class import CharacterClassOffer
from app.db.models.domain import DomainDefinition
from app.db.models.progression_outcome import AppliedProgressionOutcome
from app.game.character.service import create_character
from app.game.classes.service import list_visible_class_offers
from app.game.game_state import build_game_state
from app.game.progression.outcomes import (
    AttributeProgressGain,
    CharacterXPGain,
    DomainProgressGain,
    DomainSynergyProgressGain,
    ProfessionProgressGain,
    ProgressionOutcome,
    ResourceProgressGain,
    resolve_progression_outcome,
)
from app.game.world.reset import delete_campaign
from app.game.world.seed import create_campaign, seed_initial_region


class DynamicClassLLM(LLMService):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        section = prompt.split("DOMÍNIOS COM MATURIDADE CONFIRMADA:", 1)[1]
        section = section.split("INTEGRAÇÕES CONFIRMADAS:", 1)[0]
        domains = re.findall(r"^- ([A-Z_]+) ", section, flags=re.MULTILINE)
        joined = ", ".join(domains)
        domain_json = json.dumps(domains)
        return json.dumps(
            {
                "name": f"Caminho de {joined}",
                "description": f"Um caminho já desenvolvido em {joined}.",
                "identity": f"Integração reconhecida de {joined}.",
                "theme": joined,
                "domains": json.loads(domain_json),
            }
        )


def _character(db_session):
    for key, family in (("SWORD", "WEAPON"), ("WIND", "MANIFESTATION")):
        if db_session.get(DomainDefinition, key) is None:
            db_session.add(
                DomainDefinition(key=key, family=family, description="")
            )
    db_session.flush()
    campaign = create_campaign(db_session, "System Progression Test")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    return campaign, character


def test_structured_outcome_routes_each_progression_to_authoritative_service(
    db_session,
):
    campaign, character = _character(db_session)
    llm = DynamicClassLLM()
    outcome = ProgressionOutcome(
        outcome_key="training:first-integrated-session",
        character_xp=CharacterXPGain(
            amount=5.0,
            source=CharacterXPSource.MEANINGFUL_NEW_EXPERIENCE,
        ),
        professions=(
            ProfessionProgressGain(
                source=ProfessionXPSource.PRACTICE,
                profession_key="COOKING",
                profession_name="Culinária",
                activity_key="first-field-meal",
                base_xp=0.5,
                task_complexity_level=0,
            ),
        ),
        domains=(
            DomainProgressGain(
                domain_key="SWORD",
                source=DomainEvidenceSource.TRAINING,
                evidence_key="first-sword-form",
                context_key="training-yard",
                amount=1.0,
            ),
            DomainProgressGain(
                domain_key="WIND",
                source=DomainEvidenceSource.EXPERIMENTATION,
                evidence_key="first-wind-shaping",
                context_key="training-yard",
                amount=1.0,
            ),
        ),
        synergies=(
            DomainSynergyProgressGain(
                first_domain_key="SWORD",
                second_domain_key="WIND",
                source=DomainEvidenceSource.TRAINING,
                evidence_key="first-integrated-form",
                context_key="training-yard",
                amount=0.5,
            ),
        ),
        attributes=(
            AttributeProgressGain(
                attribute_key=CharacterAttributeKey.AGILITY,
                source=AttributeEvidenceSource.TRAINING,
                evidence_key="precision-footwork",
                context_key="training-yard",
                amount=2.0,
            ),
        ),
        resources=(
            ResourceProgressGain(
                resource_key=CharacterResourceKey.MANA,
                source=ResourceGrowthSource.MAGICAL_PRACTICE,
                evidence_key="first-wind-mana-practice",
                context_key="training-yard",
                amount=2.0,
            ),
        ),
    )

    result = resolve_progression_outcome(
        db_session,
        llm,
        campaign.id,
        character,
        outcome,
    )

    assert result.applied is True
    assert character.xp == 5.0
    assert db_session.query(AppliedProgressionOutcome).count() == 1
    assert llm.calls == []  # Domains are real but not mature yet.


def test_progression_outcome_is_idempotent_across_all_awards(db_session):
    campaign, character = _character(db_session)
    llm = DynamicClassLLM()
    outcome = ProgressionOutcome(
        outcome_key="challenge:one-time",
        character_xp=CharacterXPGain(
            amount=5.0,
            source=CharacterXPSource.SIGNIFICANT_CHALLENGE,
        ),
        attributes=(
            AttributeProgressGain(
                attribute_key=CharacterAttributeKey.STRENGTH,
                source=AttributeEvidenceSource.REAL_CHALLENGE,
                evidence_key="lifted-collapse",
                context_key="rescue",
                amount=3.0,
            ),
        ),
    )

    first = resolve_progression_outcome(
        db_session, llm, campaign.id, character, outcome
    )
    repeated = resolve_progression_outcome(
        db_session, llm, campaign.id, character, outcome
    )

    assert first.applied is True
    assert repeated.applied is False
    assert character.xp == 5.0
    assert db_session.query(AppliedProgressionOutcome).count() == 1


def test_mature_path_generates_pending_classes_then_reveals_at_safe_moment(
    db_session,
):
    campaign, character = _character(db_session)
    llm = DynamicClassLLM()
    first = ProgressionOutcome(
        outcome_key="training:forms",
        domains=tuple(
            DomainProgressGain(
                domain_key=key,
                source=DomainEvidenceSource.TRAINING,
                evidence_key=f"{key.lower()}-form",
                context_key="training-yard",
                amount=1.5,
            )
            for key in ("SWORD", "WIND")
        ),
    )
    second = ProgressionOutcome(
        outcome_key="combat:integrated-technique",
        domains=tuple(
            DomainProgressGain(
                domain_key=key,
                source=DomainEvidenceSource.COMBAT,
                evidence_key=f"{key.lower()}-combat",
                context_key="real-danger",
                amount=1.5,
            )
            for key in ("SWORD", "WIND")
        ),
        synergies=(
            DomainSynergyProgressGain(
                first_domain_key="SWORD",
                second_domain_key="WIND",
                source=DomainEvidenceSource.TECHNIQUE_USED,
                evidence_key="wind-cut",
                context_key="real-danger",
                amount=1.0,
            ),
        ),
        safe_to_notify=False,
    )
    resolve_progression_outcome(
        db_session, llm, campaign.id, character, first
    )

    generated = resolve_progression_outcome(
        db_session, llm, campaign.id, character, second
    )

    assert generated.class_offers_created
    assert all(
        offer.status == "PENDING" for offer in generated.class_offers_created
    )
    assert list_visible_class_offers(db_session, character.id) == []

    safe_retry = resolve_progression_outcome(
        db_session,
        llm,
        campaign.id,
        character,
        ProgressionOutcome(
            outcome_key=second.outcome_key,
            safe_to_notify=True,
        ),
    )

    assert safe_retry.applied is False
    assert safe_retry.class_offers_revealed
    assert list_visible_class_offers(db_session, character.id)


def test_system_progression_endpoint_exposes_only_player_facing_information(
    client,
    db_session,
):
    campaign, character = _character(db_session)
    character.xp = 2.56
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/character/progression",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["character_xp"] == {
        "level": 0,
        "current": 2.6,
        "to_next_level": 25.0,
    }
    assert payload["professions"] == []
    assert payload["active_class"] is None
    assert payload["class_offers"] == []
    assert {row["key"] for row in payload["attributes"]} == {
        key.value for key in CharacterAttributeKey
    }
    assert {row["key"] for row in payload["resources"]} == {
        "HP",
        "MANA",
        "STAMINA",
    }
    serialized = json.dumps(payload).lower()
    assert "domain" not in serialized
    assert "evidence" not in serialized
    assert "requirement" not in serialized
    assert "development" not in serialized


def test_narrator_context_does_not_receive_system_build_requirements(db_session):
    campaign, character = _character(db_session)
    state = build_game_state(db_session, campaign.id, character.id)

    context = build_context(db_session, state)

    assert "LUCK" not in context
    assert "Sorte" not in context
    assert "domain evidence" not in context.lower()
    assert "class requirement" not in context.lower()
    assert "profession_affinity" not in context


def test_campaign_reset_removes_progression_outcome_idempotency(db_session):
    campaign, character = _character(db_session)
    llm = DynamicClassLLM()
    resolve_progression_outcome(
        db_session,
        llm,
        campaign.id,
        character,
        ProgressionOutcome(outcome_key="rest:safe-moment"),
    )

    assert delete_campaign(db_session, campaign.id) is True
    assert db_session.query(AppliedProgressionOutcome).count() == 0
    assert db_session.query(CharacterClassOffer).count() == 0
