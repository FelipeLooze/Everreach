"""Phase 11L — System / Narrator Context.

The narrator previously had zero visibility into a character's techniques:
it could not phrase "Uso Rajada de Vento" using the technique's real name,
type or mastery tier, and had no guardrail against inventing numeric effects
for a technique it could not even see. This exposes exactly the same
LEARNED techniques and mastery tiers already computed for the character
sheet (Phase 11A/11D) as a read-only KNOWN TECHNIQUES section, mirroring how
RELEVANT INVENTORY AND EQUIPMENT already exposes items to the narrator.
"""

from app.core.enums import TechniqueOrigin, TechniqueType
from app.db.models.domain import DomainDefinition
from app.ai.context_builder import build_context
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.skills.technique_mastery import award_technique_mastery
from app.game.skills.techniques import create_technique, grant_technique
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Narrator Context")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, character


def test_known_techniques_section_lists_learned_techniques_with_mastery(db_session):
    campaign, character = _setup(db_session)
    technique = create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED
    )
    award_technique_mastery(db_session, character.id, technique.id, amount=10.0)
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, player_input="Olho ao redor.")

    technique_section = context.split("KNOWN TECHNIQUES", 1)[1]
    assert "- Rajada de Vento [MAGICAL, mastery: PRACTICED]" in technique_section
    assert "Never invent damage" in technique_section


def test_known_techniques_section_reports_none_when_nothing_is_learned(db_session):
    campaign, character = _setup(db_session)

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, player_input="Olho ao redor.")

    technique_section = context.split("KNOWN TECHNIQUES", 1)[1]
    assert "- none learned yet" in technique_section


def test_only_learned_techniques_are_exposed_not_merely_aware_ones(db_session):
    from app.game.skills.techniques import mark_technique_aware

    campaign, character = _setup(db_session)
    technique = create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    mark_technique_aware(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.OBSERVED
    )
    db_session.commit()

    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, player_input="Olho ao redor.")

    technique_section = context.split("KNOWN TECHNIQUES", 1)[1]
    assert "Rajada de Vento" not in technique_section
    assert "- none learned yet" in technique_section
