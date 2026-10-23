"""A passing provider error must not cost the turn its mechanics (2026-10-23:
free NVIDIA answers an occasional 500 that clears within a second)."""
import json

import pytest

from app.ai import intent_parser
from app.ai.llm_service import LLMService, LLMServiceError, LLMTimeoutError
from app.core.enums import ActionIntentType
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.npcs import service as npcs_service
from app.game.world.seed import create_campaign, seed_initial_region


class _Flaky(LLMService):
    def __init__(self, failures, error=LLMServiceError):
        self.failures, self.error, self.calls = failures, error, 0

    def generate(self, system, prompt):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error("NVIDIA server error (500): provider unavailable")
        return json.dumps({"intent": "TALK", "target": None})


def test_one_provider_error_is_retried():
    flaky = _Flaky(failures=1)
    assert intent_parser.parse(flaky, '"Oi"', "").type == ActionIntentType.TALK
    assert flaky.calls == 2


def test_a_timeout_is_not_retried():
    flaky = _Flaky(failures=1, error=LLMTimeoutError)
    assert intent_parser.parse(flaky, '"Oi"', "").type == ActionIntentType.FREEFORM
    assert flaky.calls == 1


class _DownParser(LLMService):
    def generate(self, system, prompt):
        if "Ação do jogador" in prompt:
            raise LLMServiceError("down")
        return "A cena segue."


def test_speech_to_the_current_interlocutor_stays_a_conversation_when_the_parser_is_down(db_session):
    campaign = create_campaign(db_session, "Resiliência")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.flush()
    elder = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.role == "ancião da vila").one()
    npcs_service.meet_npc(db_session, campaign.id, character.id, elder.id)
    llm = _DownParser()

    result = engine.resolve_action(
        db_session, llm, campaign.id, character.id, '"Qual o nome do senhor?"', intent_llm_service=llm,
    )

    assert result.intent_type == ActionIntentType.TALK.value
    assert f"conversa com {elder.name}" in result.mechanical_summary


@pytest.mark.parametrize("text", ["Olho ao redor"])
def test_plain_actions_are_not_turned_into_talk(db_session, text):
    campaign = create_campaign(db_session, "Resiliência 2")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    db_session.flush()
    llm = _DownParser()

    result = engine.resolve_action(db_session, llm, campaign.id, character.id, text, intent_llm_service=llm)

    assert result.intent_type != ActionIntentType.TALK.value
