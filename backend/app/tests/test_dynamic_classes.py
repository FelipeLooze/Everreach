import pytest

from app.ai.llm_service import LLMService
from app.core.enums import ClassOfferStatus, DomainEvidenceSource
from app.db.models.character_class import (
    CharacterClassOffer,
    ClassDefinition,
    ClassDefinitionDomain,
)
from app.db.models.domain import DomainDefinition
from app.game.character.service import create_character
from app.game.classes.generator import (
    DynamicClassGenerationError,
    detect_mature_class_paths,
    generate_dynamic_class_offers,
)
from app.game.classes.resolver import MAX_CLASS_DOMAINS, resolve_class_paths
from app.game.classes.service import (
    list_visible_class_offers,
    make_pending_class_offers_available,
)
from app.game.domains.service import (
    award_domain_evidence,
    award_domain_synergy_evidence,
)
from app.game.world.seed import create_campaign, seed_initial_region


class ClassIdentityLLM(LLMService):
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self.response


def _character(db_session):
    for key, family in (("SWORD", "WEAPON"), ("WIND", "MANIFESTATION")):
        if db_session.get(DomainDefinition, key) is None:
            db_session.add(
                DomainDefinition(key=key, family=family, description="")
            )
    db_session.flush()
    campaign = create_campaign(db_session, "Dynamic Class Test")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session,
        campaign.id,
        "Hero",
        region.id,
        location.id,
    )
    return campaign, character


def _mature_domain(db_session, campaign, character, domain_key: str) -> None:
    award_domain_evidence(
        db_session,
        campaign.id,
        character,
        domain_key=domain_key,
        source=DomainEvidenceSource.TRAINING,
        evidence_key=f"{domain_key.lower()}-form",
        context_key="training-yard",
        amount=1.5,
    )
    award_domain_evidence(
        db_session,
        campaign.id,
        character,
        domain_key=domain_key,
        source=DomainEvidenceSource.COMBAT,
        evidence_key=f"{domain_key.lower()}-combat",
        context_key="real-danger",
        amount=1.5,
    )


def _proposal(*domains: str) -> str:
    domain_list = ", ".join(f'"{key}"' for key in domains)
    return (
        '{"name":"Espadachim do Vento",'
        '"description":"Um combatente que integra espada e vento em seu caminho.",'
        '"identity":"Integração disciplinada de esgrima e vento.",'
        '"theme":"Lâmina e vento",'
        f'"domains":[{domain_list}]}}'
    )


def test_immature_path_does_not_call_llm_or_create_offer(db_session):
    campaign, character = _character(db_session)
    award_domain_evidence(
        db_session,
        campaign.id,
        character,
        domain_key="SWORD",
        source=DomainEvidenceSource.TRAINING,
        evidence_key="first-form",
        context_key="yard",
        amount=10.0,
    )
    llm = ClassIdentityLLM(_proposal("SWORD"))

    assert detect_mature_class_paths(db_session, character) == []
    assert generate_dynamic_class_offers(
        db_session, llm, campaign.id, character
    ) == []
    assert llm.calls == []
    assert db_session.query(ClassDefinition).count() == 0


def test_mature_path_creates_hidden_pending_offer_from_llm_identity(db_session):
    campaign, character = _character(db_session)
    _mature_domain(db_session, campaign, character, "SWORD")
    llm = ClassIdentityLLM(_proposal("SWORD"))

    offers = generate_dynamic_class_offers(
        db_session, llm, campaign.id, character
    )

    assert len(offers) == 1
    offer = offers[0]
    assert offer.status == ClassOfferStatus.PENDING.value
    assert list_visible_class_offers(db_session, character.id) == []
    assert offer.class_definition.name == "Espadachim do Vento"
    assert offer.class_definition.identity
    assert offer.class_definition.theme == "Lâmina e vento"
    assert [row.domain_key for row in offer.class_definition.domains] == ["SWORD"]
    system, prompt = llm.calls[0]
    assert "identity" not in prompt.lower()
    assert "depth" not in prompt.lower()
    assert "consistency" not in prompt.lower()
    assert "3.0" not in prompt
    assert "SWORD" in prompt
    assert "não concede" in system


def test_two_mature_domains_do_not_form_combined_path_without_synergy(db_session):
    campaign, character = _character(db_session)
    _mature_domain(db_session, campaign, character, "SWORD")
    _mature_domain(db_session, campaign, character, "WIND")

    paths = detect_mature_class_paths(db_session, character)

    assert {path.domains for path in paths} == {("SWORD",), ("WIND",)}


def test_resolver_explains_why_domain_is_not_mature(db_session):
    campaign, character = _character(db_session)
    award_domain_evidence(
        db_session,
        campaign.id,
        character,
        domain_key="SWORD",
        source=DomainEvidenceSource.TRAINING,
        evidence_key="same-form",
        context_key="same-yard",
        amount=10.0,
    )

    resolution = resolve_class_paths(db_session, character)

    sword = next(row for row in resolution.domains if row.domain_key == "SWORD")
    assert sword.eligible is False
    assert sword.rejection_reasons == (
        "insufficient_consistency",
        "insufficient_diversity",
    )
    assert resolution.candidates == ()


def test_real_synergy_enables_combined_dynamic_class_path(db_session):
    campaign, character = _character(db_session)
    _mature_domain(db_session, campaign, character, "SWORD")
    _mature_domain(db_session, campaign, character, "WIND")
    award_domain_synergy_evidence(
        db_session,
        campaign.id,
        character,
        first_domain_key="SWORD",
        second_domain_key="WIND",
        source=DomainEvidenceSource.TECHNIQUE_USED,
        evidence_key="wind-cut",
        context_key="real-combat",
        amount=1.0,
    )
    llm = ClassIdentityLLM(_proposal("SWORD", "WIND"))

    offer = generate_dynamic_class_offers(
        db_session,
        llm,
        campaign.id,
        character,
        max_new_offers=1,
    )[0]

    assert offer.class_definition.generation_key == "domains:SWORD+WIND"
    assert [row.domain_key for row in offer.class_definition.domains] == [
        "SWORD",
        "WIND",
    ]
    assert "SWORD + WIND" in llm.calls[0][1]


def test_resolver_ranks_confirmed_integration_before_isolated_paths(db_session):
    campaign, character = _character(db_session)
    _mature_domain(db_session, campaign, character, "SWORD")
    _mature_domain(db_session, campaign, character, "WIND")
    award_domain_synergy_evidence(
        db_session,
        campaign.id,
        character,
        first_domain_key="SWORD",
        second_domain_key="WIND",
        source=DomainEvidenceSource.TECHNIQUE_USED,
        evidence_key="wind-cut",
        context_key="real-combat",
        amount=1.0,
    )

    resolution = resolve_class_paths(db_session, character)

    assert resolution.candidates[0].domains == ("SWORD", "WIND")
    assert resolution.candidates[0].score > resolution.candidates[1].score
    assert resolution.synergies[0].eligible is True


def test_weak_synergy_is_audited_but_does_not_combine_paths(db_session):
    campaign, character = _character(db_session)
    _mature_domain(db_session, campaign, character, "SWORD")
    _mature_domain(db_session, campaign, character, "WIND")
    award_domain_synergy_evidence(
        db_session,
        campaign.id,
        character,
        first_domain_key="SWORD",
        second_domain_key="WIND",
        source=DomainEvidenceSource.TRAINING,
        evidence_key="first-combination-drill",
        context_key="training-yard",
        amount=0.5,
    )

    resolution = resolve_class_paths(db_session, character)

    assert {path.domains for path in resolution.candidates} == {
        ("SWORD",),
        ("WIND",),
    }
    assert resolution.synergies[0].eligible is False
    assert resolution.synergies[0].rejection_reasons == (
        "insufficient_synergy_depth",
    )


def test_connected_evidence_builds_bounded_multi_domain_paths(db_session):
    campaign, character = _character(db_session)
    extra_domains = ("FIRE", "MOBILITY", "PRECISION")
    for key in extra_domains:
        db_session.add(
            DomainDefinition(key=key, family="STYLE", description="")
        )
    db_session.flush()
    domain_keys = ("SWORD", "WIND", *extra_domains)
    for key in domain_keys:
        _mature_domain(db_session, campaign, character, key)
    for first, second in zip(domain_keys, domain_keys[1:]):
        award_domain_synergy_evidence(
            db_session,
            campaign.id,
            character,
            first_domain_key=first,
            second_domain_key=second,
            source=DomainEvidenceSource.TECHNIQUE_USED,
            evidence_key=f"{first.lower()}-{second.lower()}",
            context_key="integrated-technique",
            amount=1.0,
        )

    resolution = resolve_class_paths(db_session, character)

    assert any(
        len(path.domains) == MAX_CLASS_DOMAINS
        for path in resolution.candidates
    )
    assert all(
        len(path.domains) <= MAX_CLASS_DOMAINS
        for path in resolution.candidates
    )


def test_backend_rejects_domains_or_mechanics_invented_by_llm(db_session):
    campaign, character = _character(db_session)
    _mature_domain(db_session, campaign, character, "SWORD")
    invented_domain = ClassIdentityLLM(_proposal("SWORD", "TIME"))

    with pytest.raises(DynamicClassGenerationError, match="domains"):
        generate_dynamic_class_offers(
            db_session, invented_domain, campaign.id, character
        )

    invented_power = ClassIdentityLLM(
        _proposal("SWORD").replace(
            "Um combatente que integra espada e vento em seu caminho.",
            "Concede +20% de força e mana infinita.",
        )
    )
    with pytest.raises(DynamicClassGenerationError, match="mechanics"):
        generate_dynamic_class_offers(
            db_session, invented_power, campaign.id, character
        )

    assert db_session.query(ClassDefinition).count() == 0
    assert db_session.query(CharacterClassOffer).count() == 0


def test_generation_is_idempotent_and_safe_notification_is_separate(db_session):
    campaign, character = _character(db_session)
    _mature_domain(db_session, campaign, character, "SWORD")
    llm = ClassIdentityLLM(_proposal("SWORD"))

    first = generate_dynamic_class_offers(
        db_session, llm, campaign.id, character
    )
    second = generate_dynamic_class_offers(
        db_session, llm, campaign.id, character
    )

    assert len(first) == 1
    assert second == []
    assert len(llm.calls) == 1
    make_pending_class_offers_available(
        db_session,
        campaign.id,
        character,
        safe_to_notify=False,
    )
    assert first[0].status == ClassOfferStatus.PENDING.value
    make_pending_class_offers_available(
        db_session,
        campaign.id,
        character,
        safe_to_notify=True,
    )
    assert first[0].status == ClassOfferStatus.AVAILABLE.value
    assert list_visible_class_offers(db_session, character.id) == first
    assert db_session.query(ClassDefinitionDomain).count() == 1
