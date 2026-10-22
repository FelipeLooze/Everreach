"""Phase 13 playable integration: registering with a guild in person.

Membership primitives existed but nothing in play called them, so the
character was permanently a non-member of every organization.
"""
import json

from app.ai.llm_service import LLMService
from app.core.enums import CombatActorType, NPCActivity, OrganizationMembershipStatus
from app.db.models.character import Character
from app.db.models.npc import NPC
from app.db.models.organization import Organization, OrganizationMember, OrganizationRole
from app.game import engine
from app.game.organizations.registration import leave_organization, register_with_organization


def _started_world(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Registration"}).json()
    character_data = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Logan"}
    ).json()
    client.post(
        f"/api/campaigns/{campaign['id']}/start", params={"character_id": character_data["id"]}
    )
    return campaign, db_session.get(Character, character_data["id"])


def _guild_and_master(db_session):
    master = db_session.query(NPC).filter(NPC.role == "mestre da guilda de aventureiros").one()
    guild = db_session.query(Organization).filter(
        Organization.headquarters_location_id == master.workplace_location_id
    ).one()
    return guild, master


def _membership(db_session, guild, character):
    return db_session.query(OrganizationMember).filter(
        OrganizationMember.organization_id == guild.id,
        OrganizationMember.member_type == CombatActorType.CHARACTER,
        OrganizationMember.member_id == character.id,
    ).order_by(OrganizationMember.joined_world_minute.desc()).first()


def test_registering_at_the_guild_makes_the_character_a_member(client, db_session):
    campaign, character = _started_world(client, db_session)
    guild, master = _guild_and_master(db_session)
    character.location_id = guild.headquarters_location_id
    db_session.flush()

    change = register_with_organization(db_session, campaign["id"], character, "Quero me registrar")

    assert change.changed
    assert master.name in change.summary
    member = _membership(db_session, guild, character)
    assert member.status == OrganizationMembershipStatus.ACTIVE
    assert db_session.get(OrganizationRole, member.role_id).title == "Aventureiro Registrado"

    again = register_with_organization(db_session, campaign["id"], character, "Quero me registrar")
    assert not again.changed and "já é membro" in again.summary

    social = client.get(
        f"/api/campaigns/{campaign['id']}/social", params={"character_id": character.id}
    ).json()
    entry = next(org for org in social["organizations"] if org["id"] == guild.id)
    assert (entry["membership"], entry["role"]) == ("MEMBER", "Aventureiro Registrado")


def test_registration_happens_at_headquarters_with_leadership_present(client, db_session):
    campaign, character = _started_world(client, db_session)
    guild, master = _guild_and_master(db_session)

    from_square = register_with_organization(
        db_session, campaign["id"], character, "Quero me registrar na guilda de aventureiros"
    )
    assert not from_square.changed and "sede" in from_square.summary

    # Off duty and away in the square: nobody from the leadership is here.
    character.location_id = guild.headquarters_location_id
    elder = db_session.query(NPC).filter(NPC.role == "ancião da vila").one()
    master.activity = NPCActivity.RESTING.value
    master.location_id = elder.location_id
    db_session.flush()
    absent = register_with_organization(db_session, campaign["id"], character, "Quero me registrar")
    assert not absent.changed and "liderança" in absent.summary
    assert _membership(db_session, guild, character) is None


def test_only_guilds_take_open_registration(client, db_session):
    campaign, character = _started_world(client, db_session)
    merchant = db_session.query(NPC).filter(NPC.role == "mestre da guilda de comerciantes").one()
    character.location_id = merchant.workplace_location_id
    db_session.flush()

    change = register_with_organization(db_session, campaign["id"], character, "Quero me registrar")

    assert not change.changed and "não aceita registro aberto" in change.summary


def test_leaving_and_rejoining(client, db_session):
    campaign, character = _started_world(client, db_session)
    guild, _master = _guild_and_master(db_session)
    character.location_id = guild.headquarters_location_id
    db_session.flush()
    register_with_organization(db_session, campaign["id"], character, "Quero me registrar")

    left = leave_organization(db_session, campaign["id"], character, "Quero sair da guilda")
    assert left.changed
    assert _membership(db_session, guild, character).status == OrganizationMembershipStatus.LEFT

    rejoined = register_with_organization(db_session, campaign["id"], character, "Quero me registrar")
    assert rejoined.changed
    assert db_session.query(OrganizationMember).filter(
        OrganizationMember.organization_id == guild.id,
        OrganizationMember.member_id == character.id,
        OrganizationMember.status == OrganizationMembershipStatus.ACTIVE,
    ).count() == 1


def test_saying_it_to_the_guildmaster_registers_through_the_engine(client, db_session):
    # The Intent Parser may read the request as plain TALK with the master;
    # the deterministic backstop still turns it into a registration.
    campaign, character = _started_world(client, db_session)
    guild, master = _guild_and_master(db_session)
    character.location_id = guild.headquarters_location_id
    db_session.commit()

    class TalkParser(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "TALK", "target": master.name})
            return "O mestre anota o nome no livro."

    llm = TalkParser()
    result = engine.resolve_action(
        db_session, llm, campaign["id"], character.id,
        f'"{master.name}, quero me registrar na guilda."', intent_llm_service=llm,
    )

    assert result.intent_type == "JOIN_ORGANIZATION"
    assert _membership(db_session, guild, character).status == OrganizationMembershipStatus.ACTIVE


def test_undo_reverts_a_registration(client, db_session):
    from app.api.dependencies.llm import set_role_llm_service_overrides

    campaign, character = _started_world(client, db_session)
    guild, master = _guild_and_master(db_session)
    character.location_id = guild.headquarters_location_id
    db_session.commit()

    class Parser(LLMService):
        def generate(self, system, prompt):
            if "Ação do jogador" in prompt:
                return json.dumps({"intent": "JOIN_ORGANIZATION", "target": None})
            return "O mestre anota o nome no livro."

    set_role_llm_service_overrides(intent=Parser(), narrative=Parser())
    params = {"character_id": character.id}
    assert client.post(f"/api/campaigns/{campaign['id']}/actions", params=params,
                       json={"text": "Quero me registrar"}).status_code == 200
    db_session.expire_all()
    assert _membership(db_session, guild, character) is not None

    undo = client.post(f"/api/campaigns/{campaign['id']}/actions/undo-last", params=params,
                       json={"reason": "teste"})

    assert undo.status_code == 200
    db_session.expire_all()
    assert _membership(db_session, guild, character) is None
