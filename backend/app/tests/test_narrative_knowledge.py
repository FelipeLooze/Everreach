"""Phase 19G — Knowledge & Information Validator."""

from app.ai.validation import NarrativeProposal, validate_narrative_proposal
from app.core.enums import KnowerType, KnowledgeCertainty
from app.db.models.knowledge import KnowledgeFact
from app.game.npcs.service import teach_fact
from app.game.world.seed import create_campaign


def _proposal(text: str, **overrides) -> NarrativeProposal:
    defaults = dict(
        text=text,
        mode="CONTINUATION",
        context="CURRENT PLAYER\nName: Logan",
        mechanical_summary="",
        player_input="Eu escuto.",
        recent_history="(nenhuma troca anterior nesta cena)",
        character_name="Logan",
        active_npc_id=None,
        active_npc_name=None,
    )
    defaults.update(overrides)
    return NarrativeProposal(**defaults)


_HIDDEN_NAME_CONTEXT = (
    "CURRENT PLAYER\nName: Logan\n\n"
    "CANONICAL LOCATION CONTEXT — PRIVATE WORLD TRUTH\n"
    "Name: Cardal\nRegion: Vale Verdejante\n\n"
    "Current location canonical name known to player: NO\n"
    "Current region canonical name known to player: NO\n\n"
    "NPC KNOWLEDGE\n- none supplied"
)


def test_unknown_canonical_location_name_leaking_into_narration_is_rejected(db_session):
    campaign = create_campaign(db_session, "Nome Oculto Vaza")
    proposal = _proposal("Você reconhece a entrada de Cardal.", context=_HIDDEN_NAME_CONTEXT)

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_narration_without_the_hidden_name_is_allowed(db_session):
    campaign = create_campaign(db_session, "Sem Nome Oculto")
    proposal = _proposal("Você avista um vilarejo cercado por muralhas baixas.", context=_HIDDEN_NAME_CONTEXT)

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_npc_dialogue_stating_a_fact_it_was_never_taught_is_rejected(db_session):
    campaign = create_campaign(db_session, "NPC Sabe De Mais")
    fact = KnowledgeFact(
        campaign_id=campaign.id, subject="npc:npc_fake", fact_key="mira_knows_nothing_yet",
        statement="Mira mora em Cardal.",
    )
    db_session.add(fact)
    db_session.flush()

    proposal = _proposal(
        "— O rei de Arven morreu ontem.",
        active_npc_id="npc_fake", active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_npc_dialogue_stating_a_fact_it_actually_knows_is_allowed(db_session):
    campaign = create_campaign(db_session, "NPC Sabe O Suficiente")
    fact = KnowledgeFact(
        campaign_id=campaign.id, subject="npc:npc_fake", fact_key="osgar_born_in_cardal",
        statement="Osgar nasceu em Cardal.",
    )
    db_session.add(fact)
    db_session.flush()
    teach_fact(
        db_session, campaign.id, "osgar_born_in_cardal", KnowerType.NPC, "npc_fake",
        certainty=KnowledgeCertainty.CONFIRMED,
    )

    proposal = _proposal(
        "— Osgar nasceu em Cardal, isso todos sabem.",
        active_npc_id="npc_fake", active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True


def test_colon_attributed_dialogue_fabricating_a_fact_is_also_rejected(db_session):
    # Phase 24G — before the NPC_DIALOGUE claim category existed, this
    # validator's own dialogue check only recognized a leading dash and
    # silently skipped this screenplay-style ("Nome: — fala") shape,
    # even though narrator.py itself already treats it as dialogue.
    campaign = create_campaign(db_session, "NPC Sabe De Mais Estilo Roteiro")
    fact = KnowledgeFact(
        campaign_id=campaign.id, subject="npc:npc_fake", fact_key="mira_knows_nothing_yet_2",
        statement="Mira mora em Cardal.",
    )
    db_session.add(fact)
    db_session.flush()

    proposal = _proposal(
        "Mira: — O rei de Arven morreu ontem.",
        active_npc_id="npc_fake", active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_quote_marked_dialogue_fabricating_a_fact_is_also_rejected(db_session):
    campaign = create_campaign(db_session, "NPC Sabe De Mais Com Aspas")
    fact = KnowledgeFact(
        campaign_id=campaign.id, subject="npc:npc_fake", fact_key="mira_knows_nothing_yet_3",
        statement="Mira mora em Cardal.",
    )
    db_session.add(fact)
    db_session.flush()

    proposal = _proposal(
        'Mira diz "O rei de Arven morreu ontem."',
        active_npc_id="npc_fake", active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is False


def test_non_dialogue_narration_is_not_checked_against_npc_knowledge(db_session):
    """Only claims shaped like the NPC's OWN spoken dialogue are checked
    against its Knowledge — ordinary narration mentioning a name is a
    different (already-covered) concern."""
    campaign = create_campaign(db_session, "Narracao Nao E Fala De NPC")
    proposal = _proposal(
        "Mira observa Logan em silêncio.",
        active_npc_id="npc_fake", active_npc_name="Mira",
    )

    result = validate_narrative_proposal(db_session, campaign.id, proposal)

    assert result.valid is True
