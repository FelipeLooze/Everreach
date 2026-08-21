"""Phase 12L — Quest / Opportunity Context & System Presentation.

Closes Phase 12: the narrator can now see a character's active quests'
real objective text (the same safe, non-omniscient text Phase 12G locked
down — no trigger_subject_id, no coordinates), and examining a real
notice board reads its actual postings instead of a generic surroundings
blurb. Nothing here lets the narrator decide acceptance, completion, or
invent content — it only surfaces what the backend already established.
"""

from app.ai.intent_parser import Intent
from app.core.enums import ActionIntentType, NoticeCategory, QuestSource
from app.db.models.location import LocationFeature
from app.ai import context_builder
from app.game import engine
from app.game.character.service import create_character
from app.game.game_state import build_game_state
from app.game.notices.service import post_notice
from app.game.quests.service import create_quest, start_quest
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session):
    campaign = create_campaign(db_session, "Quest Narrator Context")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    db_session.flush()
    return campaign, region, village, character


def test_active_quests_section_shows_objective_text_and_completion(db_session):
    campaign, region, village, character = _setup(db_session)
    quest = create_quest(
        db_session, region.id, "Cabras desaparecidas",
        "Três cabras sumiram ao norte de Cardal.", source=QuestSource.NPC_REQUEST,
        objectives=["Encontrar as cabras.", "Levar as cabras de volta para Darven."],
    )
    start_quest(db_session, character.id, quest.id)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    quest_section = context.split("ACTIVE QUESTS", 1)[1].split("KNOWN TECHNIQUES", 1)[0]
    assert "Cabras desaparecidas" in quest_section
    assert "Encontrar as cabras. [pending]" in quest_section
    assert "Levar as cabras de volta para Darven. [pending]" in quest_section
    assert "no magic waypoints" in quest_section.lower() or "hidden facts" in quest_section.lower()


def test_no_active_quests_shows_none(db_session):
    campaign, region, village, character = _setup(db_session)

    state = build_game_state(db_session, campaign.id, character.id)
    context = context_builder.build_context(db_session, state, player_input="Olho ao redor.")

    quest_section = context.split("ACTIVE QUESTS", 1)[1].split("KNOWN TECHNIQUES", 1)[0]
    assert "- none" in quest_section


def test_examining_a_real_board_reads_its_notices(db_session, monkeypatch):
    campaign, region, village, character = _setup(db_session)
    board = LocationFeature(location_id=village.id, name="Quadro de Avisos de Cardal")
    db_session.add(board)
    db_session.flush()
    post_notice(
        db_session, campaign.id, board.id,
        category=NoticeCategory.MISSING_PERSON, title="Cabras desaparecidas",
        text="Três cabras sumiram ao norte de Cardal.",
    )
    db_session.commit()

    monkeypatch.setattr(
        engine.intent_parser, "parse",
        lambda *_a, **_k: Intent(
            type=ActionIntentType.EXAMINE, target="Quadro de Avisos de Cardal", raw_text="Examino o quadro."
        ),
    )
    from app.ai.llm_service import LLMService

    class PassiveLLM(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            return "A ação acontece conforme o resultado mecânico."

    result = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id, "Examino o quadro de avisos.",
    )

    assert "Cabras desaparecidas" in result.mechanical_summary
    assert "Três cabras sumiram" in result.mechanical_summary


def test_examining_an_ordinary_feature_still_uses_the_generic_summary(db_session, monkeypatch):
    campaign, region, village, character = _setup(db_session)

    monkeypatch.setattr(
        engine.intent_parser, "parse",
        lambda *_a, **_k: Intent(
            type=ActionIntentType.EXAMINE, target="praça central", raw_text="Examino a praça."
        ),
    )
    from app.ai.llm_service import LLMService

    class PassiveLLM(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            return "A ação acontece conforme o resultado mecânico."

    result = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id, "Examino a praça.",
    )

    assert "observa os arredores" in result.mechanical_summary
