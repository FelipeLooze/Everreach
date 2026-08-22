"""Phase 19P — Contradiction Detection."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.db.models.npc import NPC
from app.game.world.seed import create_campaign, seed_initial_region


def _proposal(text: str, *, active_npc_id, active_npc_name, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu observo.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
        active_npc_id=active_npc_id,
        active_npc_name=active_npc_name,
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_contradicting_established_hair_color_is_rejected(db_session):
    campaign = create_campaign(db_session, "Contradicao De Cabelo", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Mira", role="caçadora", backstory="Mira tem cabelo ruivo e olhos verdes.",
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal(
        "O cabelo preto de Mira balança com o vento.",
        active_npc_id=npc.id, active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_matching_hair_color_is_allowed(db_session):
    campaign = create_campaign(db_session, "Cabelo Consistente", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Mira", role="caçadora", backstory="Mira tem cabelo ruivo e olhos verdes.",
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal(
        "O cabelo ruivo de Mira balança com o vento.",
        active_npc_id=npc.id, active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_narration_without_hair_mention_is_never_checked(db_session):
    campaign = create_campaign(db_session, "Sem Mencao De Cabelo", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Mira", role="caçadora", backstory="Mira tem cabelo ruivo e olhos verdes.",
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal("Mira observa a distância em silêncio.", active_npc_id=npc.id, active_npc_name="Mira")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_npc_with_no_established_hair_color_is_never_checked(db_session):
    campaign = create_campaign(db_session, "Sem Cor Estabelecida", world_seed=4)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Mira", role="caçadora",
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal(
        "O cabelo preto de Mira balança com o vento.",
        active_npc_id=npc.id, active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
