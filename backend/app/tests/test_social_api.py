"""Playable/readable integration for Phase 13 social state."""

from app.core.enums import CombatActorType, GroupType
from app.db.models.character import Character
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.game.groups.service import create_group


def _started_world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Phase 13 Social"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start",
        params={"character_id": character_data["id"]},
    )
    return campaign, db_session.get(Character, character_data["id"])


def test_social_endpoint_only_exposes_organizations_visible_from_current_place(
    client, db_session
):
    campaign, character = _started_world(client, db_session)

    at_village = client.get(
        f"/api/campaigns/{campaign['id']}/social",
        params={"character_id": character.id},
    )
    assert at_village.status_code == 200
    village_names = {row["name"] for row in at_village.json()["organizations"]}
    village_organization = db_session.query(Organization).filter(
        Organization.campaign_id == campaign["id"],
        Organization.headquarters_location_id == character.location_id,
    ).one()
    assert village_organization.name in village_names
    assert not any(name.startswith("Guilda de Aventureiros") for name in village_names)

    guild_location = db_session.query(Location).filter(
        Location.region_id == character.region_id,
        Location.type == "adventurers_guild",
    ).one()
    character.location_id = guild_location.id
    db_session.commit()

    at_guild = client.get(
        f"/api/campaigns/{campaign['id']}/social",
        params={"character_id": character.id},
    ).json()
    organization_names = {row["name"] for row in at_guild["organizations"]}
    assert any(name.startswith("Guilda de Aventureiros") for name in organization_names)
    guild = next(
        row for row in at_guild["organizations"] if row["name"].startswith("Guilda de Aventureiros")
    )
    assert guild["leader_title"] == "Mestre da Guilda"
    assert guild["membership"] == "NON_MEMBER"
    assert guild["reputation"] == "NEUTRAL"
    assert guild["active_notices"] == 2


def test_social_endpoint_projects_the_characters_real_group(client, db_session):
    campaign, character = _started_world(client, db_session)
    elder = db_session.query(NPC).filter(
        NPC.campaign_id == campaign["id"], NPC.role == "ancião da vila"
    ).one()
    create_group(
        db_session,
        campaign["id"],
        group_type=GroupType.TRAVEL,
        founding_members=(
            (CombatActorType.CHARACTER, character.id),
            (CombatActorType.NPC, elder.id),
        ),
        name="Companhia da Estrada",
        purpose="Viajar com segurança.",
        location_id=character.location_id,
        leader_type=CombatActorType.CHARACTER,
        leader_id=character.id,
    )
    db_session.commit()

    response = client.get(
        f"/api/campaigns/{campaign['id']}/social",
        params={"character_id": character.id},
    )

    assert response.status_code == 200
    group = response.json()["active_group"]
    assert group["name"] == "Companhia da Estrada"
    assert {member["name"] for member in group["members"]} == {"Logan", elder.name}
    assert next(member for member in group["members"] if member["name"] == "Logan")["leader"] is True
