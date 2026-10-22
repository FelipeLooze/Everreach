"""Phase 13 playable integration: inviting transported people to travel.

Group/invite primitives existed, but nothing in play called them, so the
character could never form a group.
"""
import json
import random

from app.ai import context_builder
from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import ActionIntentType, CombatActorType, GroupInviteStatus, GroupStatus
from app.db.models.character import Character
from app.db.models.group import Group, GroupInvite
from app.db.models.location import Location, LocationConnection
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.game import engine
from app.game.game_state import build_game_state
from app.game.groups.companions import (
    accompanies_a_character,
    character_group,
    companions_of,
    invite_simulated_player,
    leave_character_group,
)
from app.game.perception.service import observe_surroundings
from app.game.players import service as players_service
from app.simulation import player_simulation


def _started_world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Companions"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]}
    )
    character = db_session.get(Character, character_data["id"])
    transported = (
        db_session.query(SimulatedPlayer)
        .filter(
            SimulatedPlayer.campaign_id == campaign["id"],
            SimulatedPlayer.location_id == character.location_id,
        )
        .order_by(SimulatedPlayer.name)
        .first()
    )
    return campaign, character, transported


def test_a_stranger_declines_and_no_empty_group_is_left_behind(client, db_session):
    campaign, character, bram = _started_world(client, db_session)

    change = invite_simulated_player(db_session, campaign["id"], character, bram)

    assert not change.changed and "ainda não conhece" in change.summary
    assert character_group(db_session, character) is None
    assert db_session.query(GroupInvite).one().status == GroupInviteStatus.DECLINED


def test_someone_who_knows_the_character_accepts_and_travels_along(client, db_session):
    campaign, character, bram = _started_world(client, db_session)
    players_service.meet_simulated_player(db_session, campaign["id"], character.id, bram.id)

    change = invite_simulated_player(db_session, campaign["id"], character, bram)

    assert change.changed and bram.name in change.summary
    assert [companion.id for companion in companions_of(db_session, character)] == [bram.id]
    assert db_session.query(GroupInvite).one().status == GroupInviteStatus.ACCEPTED

    social = client.get(
        f"/api/campaigns/{campaign['id']}/social", params={"character_id": character.id}
    ).json()
    assert {member["name"] for member in social["active_group"]["members"]} == {
        character.name, bram.name
    }

    observe_surroundings(db_session, character)
    destination = (
        db_session.query(Location)
        .join(LocationConnection, LocationConnection.to_location_id == Location.id)
        .filter(LocationConnection.from_location_id == character.location_id, Location.type == "inn")
        .one()
    )
    engine._handle_move(
        db_session, campaign["id"], character,
        Intent(type=ActionIntentType.MOVE, target=destination.name, raw_text="Vou até a estalagem"),
    )
    state = build_game_state(db_session, campaign["id"], character.id)
    assert character.location_id == destination.id
    assert bram.id in {player.id for player in state.nearby_simulated_players}

    context = context_builder.build_context(db_session, state)
    assert f"Travel companions (accepted to travel with the protagonist and move with them): {bram.name}" in context


def test_autonomous_simulation_leaves_companions_with_the_character(client, db_session):
    campaign, character, bram = _started_world(client, db_session)
    players_service.meet_simulated_player(db_session, campaign["id"], character.id, bram.id)
    invite_simulated_player(db_session, campaign["id"], character, bram)
    start = bram.location_id

    assert accompanies_a_character(db_session, bram)
    player_simulation.tick(db_session, campaign["id"], minutes=12 * 60, rng=random.Random(3))

    db_session.refresh(bram)
    assert bram.location_id == start and bram.travel_destination_id is None


def test_villagers_decline_for_their_duties(client, db_session):
    campaign, character, _bram = _started_world(client, db_session)
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    state = build_game_state(db_session, campaign["id"], character.id)

    summary, _ = engine._apply_intent(
        db_session, campaign["id"], character,
        Intent(type=ActionIntentType.INVITE_TO_GROUP, target=elder.name,
               raw_text=f"Convido {elder.name} para viajar comigo"),
        state,
    )

    assert "obrigações" in summary
    assert character_group(db_session, character) is None


def test_disbanding_frees_the_companion(client, db_session):
    campaign, character, bram = _started_world(client, db_session)
    players_service.meet_simulated_player(db_session, campaign["id"], character.id, bram.id)
    invite_simulated_player(db_session, campaign["id"], character, bram)
    group_id = character_group(db_session, character).id

    change = leave_character_group(db_session, character)

    assert change.changed
    assert db_session.get(Group, group_id).status == GroupStatus.DISBANDED
    assert not accompanies_a_character(db_session, bram)


def test_asking_the_person_you_talk_to_if_they_want_to_come(client, db_session):
    # "Quer vir comigo?" names nobody; it goes to the current interlocutor,
    # and the Intent Parser reading it as TALK is turned into an invitation.
    campaign, character, bram = _started_world(client, db_session)
    db_session.commit()

    class Parser(LLMService):
        next_intent = {"intent": "TALK", "target": bram.name}

        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps(self.next_intent)
            return "A conversa segue."

    llm = Parser()
    engine.resolve_action(
        db_session, llm, campaign["id"], character.id, f"Falo com {bram.name}", intent_llm_service=llm
    )
    llm.next_intent = {"intent": "TALK", "target": None}
    result = engine.resolve_action(
        db_session, llm, campaign["id"], character.id, '"Quer vir comigo?"', intent_llm_service=llm
    )

    assert result.intent_type == "INVITE_TO_GROUP"
    assert [companion.id for companion in companions_of(db_session, character)] == [bram.id]
