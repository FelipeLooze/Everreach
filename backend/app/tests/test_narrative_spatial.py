"""Phase 19H — Spatial Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.world.seed import create_campaign, seed_initial_region


def _proposal(text: str, *, location_id, character_id, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu observo.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
        character_id=character_id,
        location_id=location_id,
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Espacial {world_seed}", world_seed=world_seed)
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    return campaign, region, village, character


def test_npc_narrated_arriving_at_the_wrong_location_is_rejected(db_session):
    campaign, region, village, character = _setup(db_session, 1)
    from app.db.models.location import Location

    elsewhere = Location(region_id=region.id, name="Outro Lugar", type="generic")
    db_session.add(elsewhere)
    db_session.flush()
    distant_npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=elsewhere.id,
        name="Mira", role="caçadora",
    )
    db_session.add(distant_npc)
    db_session.flush()

    proposal = _proposal(
        "Mira entra pela porta e observa a sala.",
        location_id=village.id, character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_npc_narrated_arriving_at_their_actual_location_is_allowed(db_session):
    campaign, region, village, character = _setup(db_session, 2)
    local_npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=village.id,
        name="Mira", role="caçadora",
    )
    db_session.add(local_npc)
    db_session.flush()

    proposal = _proposal(
        "Mira entra pela porta e observa a sala.",
        location_id=village.id, character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_mentioning_a_distant_npc_without_a_presence_verb_is_allowed(db_session):
    """Only an actual arrival/presence claim is checked — referencing an
    absent NPC in passing (e.g. discussing them) is ordinary narration."""
    campaign, region, village, character = _setup(db_session, 3)
    from app.db.models.location import Location

    elsewhere = Location(region_id=region.id, name="Outro Lugar", type="generic")
    db_session.add(elsewhere)
    db_session.flush()
    distant_npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=elsewhere.id,
        name="Mira", role="caçadora",
    )
    db_session.add(distant_npc)
    db_session.flush()

    proposal = _proposal(
        "Alguém menciona que Mira anda ocupada ultimamente.",
        location_id=village.id, character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_active_npc_is_never_checked_against_this_validator(db_session):
    """The active interlocutor's presence is already guaranteed by
    construction (app.game.npcs.service resolves it from who is
    actually there) — this validator must never second-guess it."""
    campaign, region, village, character = _setup(db_session, 4)
    from app.db.models.location import Location

    elsewhere = Location(region_id=region.id, name="Outro Lugar", type="generic")
    db_session.add(elsewhere)
    db_session.flush()
    npc = NPC(
        campaign_id=campaign.id, region_id=region.id, location_id=elsewhere.id,
        name="Mira", role="caçadora",
    )
    db_session.add(npc)
    db_session.flush()

    proposal = _proposal(
        "Mira entra pela porta e observa a sala.",
        location_id=village.id, character_id=character.id,
        active_npc_id=npc.id, active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_proposal_without_a_location_id_is_never_checked(db_session):
    campaign, region, village, character = _setup(db_session, 5)

    proposal = _proposal(
        "Mira entra pela porta e observa a sala.",
        location_id=None, character_id=character.id,
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
