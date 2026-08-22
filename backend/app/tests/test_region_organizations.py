"""Phase 15J — Regional Organizations & Major NPCs.

Every major settlement gets one organization (type matching its own
SettlementType) and one named leader NPC who founds and leads it.
Deliberately not every citizen — just the individuals who matter
structurally right now.
"""

from app.db.models.npc import NPC
from app.db.models.organization import Organization, OrganizationMember
from app.db.models.settlement import Settlement
from app.game.world.content_pools import ORG_TYPE_BY_SETTLEMENT_TYPE
from app.game.world.seed import create_campaign, seed_initial_region


def test_every_major_settlement_gets_one_organization(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    settlements = db_session.query(Settlement).all()
    organizations = db_session.query(Organization).filter(Organization.campaign_id == campaign.id).all()

    assert len(organizations) == len(settlements)


def test_organization_type_matches_settlement_type(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    settlements = db_session.query(Settlement).all()
    organizations = db_session.query(Organization).filter(Organization.campaign_id == campaign.id).all()
    orgs_by_headquarters = {org.headquarters_location_id: org for org in organizations}

    for settlement in settlements:
        org = orgs_by_headquarters[settlement.location_id]
        expected_type = ORG_TYPE_BY_SETTLEMENT_TYPE[str(settlement.settlement_type)]
        assert org.organization_type == expected_type


def test_every_organization_has_a_founding_leader_npc_as_member(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    organizations = db_session.query(Organization).filter(Organization.campaign_id == campaign.id).all()

    for org in organizations:
        members = (
            db_session.query(OrganizationMember)
            .filter(OrganizationMember.organization_id == org.id, OrganizationMember.status == "ACTIVE")
            .all()
        )
        assert len(members) == 1
        assert members[0].member_type == "NPC"
        leader_npc = db_session.get(NPC, members[0].member_id)
        assert leader_npc is not None
        assert leader_npc.name not in ("Osgar Vell", "Mira Draske", "Talven Brooks")


def test_leader_npc_names_never_collide(db_session):
    campaign = create_campaign(db_session, "Campanha A")
    region, _village = seed_initial_region(db_session, campaign.id)

    npc_names = [npc.name for npc in db_session.query(NPC).filter(NPC.campaign_id == campaign.id).all()]

    assert len(npc_names) == len(set(npc_names))
