"""Phase 17I — Expeditions."""

import pytest

from app.core.enums import CombatActorType, ExpeditionStatus, GeographicKnowledgeAspect, GroupType, KnowerType
from app.db.models.group import Group
from app.game.character.service import create_character
from app.game.exploration.expeditions import begin_expedition, organize_expedition, resolve_expedition
from app.game.knowledge.geography import knows_geographic_aspect
from app.game.time.clock import get_world_time
from app.game.world.seed import create_campaign, seed_initial_region


class _FixedRoll:
    def __init__(self, raw: int):
        self.raw = raw

    def randint(self, a, b):
        return self.raw


def _setup(db_session, world_seed):
    campaign = create_campaign(db_session, f"Expedicao {world_seed}", world_seed=world_seed)
    region, village = seed_initial_region(db_session, campaign.id)
    logan = create_character(db_session, campaign.id, "Logan", region_id=region.id, location_id=village.id)
    return campaign, region, village, logan


def test_organizing_an_expedition_creates_a_linked_group(db_session):
    campaign, _region, village, logan = _setup(db_session, 1)

    expedition = organize_expedition(
        db_session, campaign.id,
        purpose="Mapear o território ao norte.",
        origin_location_id=village.id,
        founding_members=[(CombatActorType.CHARACTER, logan.id)],
        leader_type=CombatActorType.CHARACTER,
        leader_id=logan.id,
    )

    assert expedition.status == ExpeditionStatus.PLANNED.value
    group = db_session.get(Group, expedition.group_id)
    assert group.group_type == GroupType.EXPEDITION.value
    assert group.purpose == "Mapear o território ao norte."


def test_beginning_an_expedition_advances_status_and_sets_start_time(db_session):
    campaign, _region, village, logan = _setup(db_session, 2)
    expedition = organize_expedition(
        db_session, campaign.id, purpose="Explorar.", origin_location_id=village.id,
        founding_members=[(CombatActorType.CHARACTER, logan.id)],
    )

    begin_expedition(db_session, campaign.id, expedition)

    assert expedition.status == ExpeditionStatus.UNDERWAY.value
    assert expedition.started_world_minute == get_world_time(db_session, campaign.id).total_minutes()

    with pytest.raises(ValueError):
        begin_expedition(db_session, campaign.id, expedition)


def test_resolving_before_underway_raises(db_session):
    campaign, _region, village, logan = _setup(db_session, 3)
    expedition = organize_expedition(
        db_session, campaign.id, purpose="Explorar.", origin_location_id=village.id,
        founding_members=[(CombatActorType.CHARACTER, logan.id)],
    )

    with pytest.raises(ValueError):
        resolve_expedition(db_session, campaign.id, expedition)


def test_successful_expedition_grants_knowledge_to_every_member(db_session):
    campaign, _region, village, logan = _setup(db_session, 4)
    expedition = organize_expedition(
        db_session, campaign.id,
        purpose="Encontrar a passagem norte.",
        origin_location_id=village.id,
        founding_members=[(CombatActorType.CHARACTER, logan.id)],
        target_subject_kind="subregion",
        target_entity_id="sub_north_test",
    )
    begin_expedition(db_session, campaign.id, expedition)

    resolve_expedition(db_session, campaign.id, expedition, rng=_FixedRoll(20))

    assert expedition.status == ExpeditionStatus.SUCCEEDED.value
    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "subregion", "sub_north_test", GeographicKnowledgeAspect.EXISTENCE,
    ) is True


def test_failed_expedition_grants_no_knowledge(db_session):
    campaign, _region, village, logan = _setup(db_session, 5)
    expedition = organize_expedition(
        db_session, campaign.id,
        purpose="Tentativa arriscada.",
        origin_location_id=village.id,
        founding_members=[(CombatActorType.CHARACTER, logan.id)],
        target_subject_kind="subregion",
        target_entity_id="sub_risky_test",
    )
    begin_expedition(db_session, campaign.id, expedition)

    resolve_expedition(db_session, campaign.id, expedition, rng=_FixedRoll(1))

    assert expedition.status == ExpeditionStatus.FAILED.value
    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.PLAYER, logan.id,
        "subregion", "sub_risky_test", GeographicKnowledgeAspect.EXISTENCE,
    ) is False


def test_npc_only_expedition_succeeds_without_any_player_involvement(db_session):
    """Discovery without the player (spec's own example)."""
    campaign, _region, village, _logan = _setup(db_session, 6)
    npc_id = "npc_expedition_leader_test"

    expedition = organize_expedition(
        db_session, campaign.id,
        purpose="A guilda dos caçadores busca uma nova rota.",
        origin_location_id=village.id,
        founding_members=[(CombatActorType.NPC, npc_id)],
        leader_type=CombatActorType.NPC,
        leader_id=npc_id,
        target_subject_kind="subregion",
        target_entity_id="sub_far_north_test",
    )
    begin_expedition(db_session, campaign.id, expedition)
    resolve_expedition(db_session, campaign.id, expedition, rng=_FixedRoll(20))

    assert expedition.status == ExpeditionStatus.SUCCEEDED.value
    assert knows_geographic_aspect(
        db_session, campaign.id, KnowerType.NPC, npc_id,
        "subregion", "sub_far_north_test", GeographicKnowledgeAspect.EXISTENCE,
    ) is True
