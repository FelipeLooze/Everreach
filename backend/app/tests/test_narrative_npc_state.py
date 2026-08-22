"""Phase 19K — NPC State Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.db.models.npc import NPC
from app.game.world.seed import create_campaign, seed_initial_region


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu observo.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def test_dead_npc_narrated_acting_is_rejected(db_session):
    campaign = create_campaign(db_session, "NPC Morto Age", world_seed=1)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro", alive=False,
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal("Osgar entra na sala e observa Logan.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_living_npc_narrated_acting_is_allowed(db_session):
    campaign = create_campaign(db_session, "NPC Vivo Age", world_seed=2)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro", alive=True,
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal("Osgar entra na sala e observa Logan.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_dead_npc_merely_mentioned_without_being_the_subject_is_allowed(db_session):
    campaign = create_campaign(db_session, "NPC Morto Apenas Mencionado", world_seed=3)
    region, village = seed_initial_region(db_session, campaign.id)
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Osgar", role="ferreiro", alive=False,
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal("A forja de Osgar permanece fria e abandonada.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_no_dead_npcs_means_no_database_lookup_needed(db_session):
    campaign = create_campaign(db_session, "Sem Npc Morto", world_seed=4)

    proposal = _proposal("Uma brisa leve passa pela praça.")

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
