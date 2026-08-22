"""Phase 12G — Quests Without Magical Markers.

The System must never hand the player an omniscient waypoint, exact
target id, or coordinate for an objective — only the same free-text
description a person in the world would have ("Mira was last seen near
the east road," not "target_location_id=loc_4f2a"). Auditing the existing
Quest API (built in 12A-12F) found no such leak already — this locks that
down as a permanent regression guard rather than leaving it as an
unenforced convention, since 12L (System/Narrator Context) will build
directly on this schema next and must not accidentally widen it.
"""

import json

from app.core.enums import ObjectiveTriggerType, QuestSource
from app.db.models.quest import QuestObjective
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.quests.service import create_quest, start_quest
from app.game.world.seed import create_campaign, seed_initial_region
from app.schemas.quest import QuestObjectiveResponse, QuestResponse


def test_objective_response_schema_exposes_only_player_facing_fields():
    assert set(QuestObjectiveResponse.model_fields) == {"id", "description", "completed"}


def test_quest_response_schema_exposes_only_player_facing_fields():
    assert set(QuestResponse.model_fields) == {
        "quest_id",
        "name",
        "description",
        "status",
        "objectives",
    }


def test_get_quests_endpoint_never_leaks_backend_only_fields(client, db_session):
    campaign = create_campaign(db_session, "No Magic Markers")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    osgar = db_session.query(NPC).filter(NPC.role == "ancião da vila").first()

    quest = create_quest(
        db_session,
        region.id,
        "Encontrar Mira",
        "Mira foi vista pela última vez perto da estrada leste.",
        source=QuestSource.NPC_REQUEST,
        deadline_world_minute=999999,
    )
    objective = QuestObjective(
        quest_id=quest.id,
        description="Falar com Osgar Vell sobre o paradeiro de Mira.",
        trigger_type=ObjectiveTriggerType.TALK_TO_NPC,
        trigger_subject_id=osgar.id,
    )
    db_session.add(objective)
    db_session.flush()
    start_quest(db_session, character.id, quest.id)
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign.id}/quests", params={"character_id": character.id}
    )
    assert response.status_code == 200
    raw = json.dumps(response.json())

    # No backend-internal ids or scheduling data — only what a person in
    # the world would actually know.
    assert osgar.id not in raw
    assert "999999" not in raw
    assert "trigger_subject_id" not in raw
    assert "trigger_type" not in raw
    assert "deadline_world_minute" not in raw
    assert "source" not in raw
    # The free-text description — the only "location info" a player gets
    # — is still present.
    assert "estrada leste" in raw
