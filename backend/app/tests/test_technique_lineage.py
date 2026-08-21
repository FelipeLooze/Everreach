"""Phase 11H — Technique Evolution & Variants.

No videogame-style "Fireball -> Fireball II -> Ultimate Fireball" upgrade
chain here: parent_technique_id is pure provenance, established only when
a caller explicitly says "this variant emerged from that technique," and
it must share a domain with its parent (a real continuity check, not an
arbitrary label). It never gates learning, using, or recognizing either
technique — that's still entirely evidence/mastery driven (11B-11D).
"""

import pytest

from app.core.enums import TechniqueType
from app.db.models.domain import DomainDefinition
from app.game.skills import techniques as technique_service


def _ensure_domains(db_session, *keys):
    for key in keys:
        if db_session.get(DomainDefinition, key) is None:
            db_session.add(DomainDefinition(key=key, family="TEST", description=""))
    db_session.flush()


def test_a_technique_may_be_created_without_a_parent(db_session):
    _ensure_domains(db_session, "WIND")

    technique = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Passo do Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )

    assert technique.parent_technique_id is None


def test_a_variant_must_share_a_domain_with_its_parent(db_session):
    _ensure_domains(db_session, "WIND", "FIRE")
    wind_push = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )

    with pytest.raises(ValueError, match="shares a domain"):
        technique_service.create_technique(
            db_session,
            skill_name="Manipulação do Fogo",
            name="Bola de Fogo",
            technique_type=TechniqueType.MAGICAL,
            domain_keys=("FIRE",),
            parent_technique_id=wind_push.id,
        )


def test_a_variant_referencing_a_nonexistent_parent_is_rejected(db_session):
    _ensure_domains(db_session, "WIND")

    with pytest.raises(ValueError, match="does not exist"):
        technique_service.create_technique(
            db_session,
            skill_name="Manipulação do Vento",
            name="Rajada de Vento",
            technique_type=TechniqueType.MAGICAL,
            domain_keys=("WIND",),
            parent_technique_id="tech_does_not_exist",
        )


def test_a_valid_variant_is_recorded(db_session):
    _ensure_domains(db_session, "WIND")
    wind_push = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )

    focused = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada Focada",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
        parent_technique_id=wind_push.id,
    )

    assert focused.parent_technique_id == wind_push.id


def test_reusing_an_existing_name_with_a_different_parent_is_rejected(db_session):
    _ensure_domains(db_session, "WIND")
    wind_push = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada Focada",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
        parent_technique_id=wind_push.id,
    )

    with pytest.raises(ValueError, match="different parent"):
        technique_service.create_technique(
            db_session,
            skill_name="Manipulação do Vento",
            name="Rajada Focada",
            technique_type=TechniqueType.MAGICAL,
            domain_keys=("WIND",),
            parent_technique_id=None,
        )


def test_technique_lineage_returns_the_whole_emerged_family(db_session):
    _ensure_domains(db_session, "WIND")
    wind_push = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    focused = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada Focada",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
        parent_technique_id=wind_push.id,
    )
    wide = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada Ampla",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
        parent_technique_id=wind_push.id,
    )
    # A grandchild: a refinement of a refinement.
    burst = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Explosão de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
        parent_technique_id=focused.id,
    )
    unrelated = technique_service.create_technique(
        db_session,
        skill_name="Culinária",
        name="Corte Preciso",
        technique_type=TechniqueType.PHYSICAL,
        domain_keys=("WIND",),
    )

    family = technique_service.technique_lineage(db_session, focused.id)
    family_ids = {t.id for t in family}

    assert family_ids == {wind_push.id, focused.id, wide.id, burst.id}
    assert unrelated.id not in family_ids


def test_technique_lineage_rejects_an_unknown_technique(db_session):
    with pytest.raises(ValueError, match="Unknown technique"):
        technique_service.technique_lineage(db_session, "tech_does_not_exist")


def test_find_similar_techniques_matches_domain_set_and_type(db_session):
    _ensure_domains(db_session, "WIND", "SWORD")
    wind_step = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento (Hero)",
        name="Passo do Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    gale_step = technique_service.create_technique(
        db_session,
        skill_name="Manipulação do Vento (Outro Heroi)",
        name="Passo da Rajada",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    technique_service.create_technique(
        db_session,
        skill_name="Esgrima Arcana",
        name="Corte de Vento",
        technique_type=TechniqueType.HYBRID,
        domain_keys=("WIND", "SWORD"),
    )

    similar = technique_service.find_similar_techniques(
        db_session,
        domain_keys=("WIND",),
        technique_type=TechniqueType.MAGICAL,
        exclude_technique_id=wind_step.id,
    )

    assert [technique.id for technique in similar] == [gale_step.id]


def test_find_similar_techniques_does_not_force_a_merge(db_session):
    """Two characters independently develop similarly-purposed techniques —
    they remain distinct rows; find_similar_techniques is advisory only."""
    _ensure_domains(db_session, "WIND")
    wind_step = technique_service.create_technique(
        db_session,
        skill_name="Vento (A)",
        name="Passo do Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    gale_step = technique_service.create_technique(
        db_session,
        skill_name="Vento (B)",
        name="Passo da Rajada",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )

    assert wind_step.id != gale_step.id
    assert gale_step.id in {
        t.id
        for t in technique_service.find_similar_techniques(
            db_session, domain_keys=("WIND",), technique_type=TechniqueType.MAGICAL
        )
    }
