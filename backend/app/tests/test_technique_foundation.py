import pytest

from app.core.enums import TechniqueOrigin, TechniqueType
from app.db.models.domain import DomainDefinition
from app.game.skills import techniques as technique_service
from app.game.world.seed import create_campaign, seed_initial_region


def _ensure_domains(db_session, *keys):
    for key in keys:
        if db_session.get(DomainDefinition, key) is None:
            db_session.add(DomainDefinition(key=key, family="TEST", description=""))
    db_session.flush()


@pytest.mark.parametrize("technique_type", list(TechniqueType))
def test_create_technique_persists_its_declared_type(db_session, technique_type):
    _ensure_domains(db_session, "WIND")
    create_campaign(db_session, "Technique Foundation")

    technique = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name=f"Técnica {technique_type.value}",
        technique_type=technique_type,
        domain_keys=("WIND",),
    )

    assert technique.technique_type == technique_type.value


def test_create_technique_rejects_reusing_a_name_with_a_different_type(db_session):
    _ensure_domains(db_session, "WIND")
    create_campaign(db_session, "Technique Foundation")

    technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )

    with pytest.raises(ValueError, match="different type"):
        technique_service.create_technique(
            db_session,
            skill_name="Manipulação do Vento",
            name="Rajada",
            technique_type=TechniqueType.PHYSICAL,
            domain_keys=("WIND",),
        )


def test_create_technique_rejects_an_invalid_type(db_session):
    _ensure_domains(db_session, "WIND")
    create_campaign(db_session, "Technique Foundation")

    with pytest.raises(ValueError, match="Invalid technique type"):
        technique_service.create_technique(
            db_session,
            skill_name="Manipulação do Vento",
            name="Rajada",
            technique_type="MAGICAL",  # not the enum member
            domain_keys=("WIND",),
        )


def test_character_sheet_exposes_the_technique_type(db_session, client):
    _ensure_domains(db_session, "WIND", "SWORD")
    campaign = create_campaign(db_session, "Technique Foundation")
    region, location = seed_initial_region(db_session, campaign.id)
    from app.game.character.service import create_character

    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    technique = technique_service.create_technique(
        db_session,
        skill_name="Esgrima Arcana",
        name="Lâmina do Vento",
        technique_type=TechniqueType.HYBRID,
        domain_keys=("WIND", "SWORD"),
    )
    technique_service.grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED
    )
    db_session.commit()

    sheet = client.get(
        f"/api/campaigns/{campaign.id}/character",
        params={"character_id": character.id},
    )

    assert sheet.status_code == 200
    assert sheet.json()["techniques"] == [
        {
            "id": technique.id,
            "name": "Lâmina do Vento",
            "description": "",
            "type": "HYBRID",
            "mastery": "UNSTABLE",
        }
    ]
