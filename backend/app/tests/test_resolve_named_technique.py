from app.core.enums import TechniqueOrigin, TechniqueType
from app.db.models.domain import DomainDefinition
from app.game.character.service import create_character
from app.game.skills.techniques import create_technique, grant_technique, resolve_named_technique
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Named Technique")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, character


def _grant(db_session, campaign, character, name):
    technique = create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name=name,
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED
    )
    return technique


def test_no_name_returns_none(db_session):
    _campaign, character = _setup(db_session)

    assert resolve_named_technique(db_session, character.id, None) is None


def test_resolves_a_unique_case_insensitive_match(db_session):
    campaign, character = _setup(db_session)
    technique = _grant(db_session, campaign, character, "Rajada de Vento")

    assert resolve_named_technique(db_session, character.id, "rajada de vento") == technique
    assert resolve_named_technique(db_session, character.id, "Rajada") == technique


def test_no_match_returns_none(db_session):
    campaign, character = _setup(db_session)
    _grant(db_session, campaign, character, "Rajada de Vento")

    assert resolve_named_technique(db_session, character.id, "Bola de Fogo") is None


def test_ambiguous_match_returns_none(db_session):
    campaign, character = _setup(db_session)
    _grant(db_session, campaign, character, "Rajada de Vento")
    _grant(db_session, campaign, character, "Rajada Focada")

    assert resolve_named_technique(db_session, character.id, "Rajada") is None


def test_a_technique_only_aware_not_learned_does_not_match(db_session):
    from app.game.skills.techniques import mark_technique_aware

    campaign, character = _setup(db_session)
    technique = create_technique(
        db_session, skill_name="Manipulação do Vento", name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL, domain_keys=("WIND",),
    )
    mark_technique_aware(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.OBSERVED
    )

    assert resolve_named_technique(db_session, character.id, "Rajada de Vento") is None
