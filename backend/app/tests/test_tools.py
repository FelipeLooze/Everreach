import json

import pytest

from app.core.enums import EventType, ItemType, ToolCapability
from app.db.models.event import WorldEvent
from app.game.character.service import create_character
from app.game.inventory.service import add_item, get_or_create_item
from app.game.items.tools import (
    ToolError,
    configure_item_tool_profile,
    get_tool_capabilities,
    validate_character_tool_use,
)
from app.game.professions.activities import award_work_xp
from app.game.world.seed import create_campaign, seed_initial_region


def _character(db_session):
    campaign = create_campaign(db_session, "Tools")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(
        db_session, campaign.id, "Hero", region.id, location.id
    )
    return campaign, character


def _pickaxe(db_session, character_id):
    definition = get_or_create_item(db_session, "Picareta", ItemType.TOOL.value)
    profile = configure_item_tool_profile(
        db_session,
        definition,
        capabilities={ToolCapability.MINING, ToolCapability.HAMMERING},
    )
    instance = add_item(db_session, character_id, definition.name)
    return profile, instance


def test_tool_profile_is_typed_immutable_and_has_no_generic_bonus(db_session):
    _campaign, character = _character(db_session)
    profile, instance = _pickaxe(db_session, character.id)

    assert get_tool_capabilities(profile) == {
        ToolCapability.MINING,
        ToolCapability.HAMMERING,
    }
    assert not hasattr(profile, "profession_bonus")
    assert not hasattr(profile, "xp_bonus")
    use = validate_character_tool_use(
        db_session,
        character.id,
        instance.id,
        required_capability=ToolCapability.MINING,
    )
    assert use.instance_id == instance.id
    assert use.accessibility.value == "STOWED"
    assert use.quality.value == "STANDARD"

    with pytest.raises(ToolError, match="different canonical"):
        configure_item_tool_profile(
            db_session,
            profile.item,
            capabilities={ToolCapability.FISHING},
        )


def test_tool_use_requires_physical_possession_and_matching_capability(db_session):
    campaign, character = _character(db_session)
    _profile, instance = _pickaxe(db_session, character.id)
    other = create_character(
        db_session,
        campaign.id,
        "Other",
        character.region_id,
        character.location_id,
    )

    with pytest.raises(ToolError, match="physically carried"):
        validate_character_tool_use(
            db_session,
            other.id,
            instance.id,
            required_capability=ToolCapability.MINING,
        )
    with pytest.raises(ToolError, match="required capability"):
        validate_character_tool_use(
            db_session,
            character.id,
            instance.id,
            required_capability=ToolCapability.FISHING,
        )


def test_profession_activity_records_tool_evidence_without_extra_xp(db_session):
    campaign, character = _character(db_session)
    _profile, instance = _pickaxe(db_session, character.id)

    result = award_work_xp(
        db_session,
        campaign.id,
        character,
        profession_key="MINING",
        profession_name="Mineração",
        activity_key="mine:surface-ore",
        base_xp=1.0,
        task_complexity_level=0,
        tool_instance_id=instance.id,
        required_tool_capability=ToolCapability.MINING,
    )

    assert result.profession_xp_before_affinity == 1.0
    assert result.progress is not None
    assert result.progress.xp == 1.0
    assert result.tool is not None
    event = (
        db_session.query(WorldEvent)
        .filter(WorldEvent.event_type == EventType.PLAYER_COMPLETED_PROFESSION_ACTIVITY.value)
        .one()
    )
    payload = json.loads(event.payload_json)
    assert payload["tool_instance_id"] == instance.id
    assert payload["tool_capability"] == "MINING"
    assert payload["tool_accessibility"] == "STOWED"
    assert payload["tool_quality"] == "STANDARD"


def test_profession_activity_rejects_incomplete_tool_requirement(db_session):
    campaign, character = _character(db_session)
    with pytest.raises(ValueError, match="provided together"):
        award_work_xp(
            db_session,
            campaign.id,
            character,
            profession_key="MINING",
            profession_name="Mineração",
            activity_key="mine:surface-ore",
            base_xp=1.0,
            task_complexity_level=0,
            required_tool_capability=ToolCapability.MINING,
        )


def test_inventory_api_exposes_tool_capabilities(client, db_session):
    campaign = client.post("/api/campaigns", json={"name": "Tool API"}).json()
    character = client.post(
        f"/api/campaigns/{campaign['id']}/characters", json={"name": "Hero"}
    ).json()
    definition = get_or_create_item(db_session, "Vara de Pesca", ItemType.TOOL.value)
    configure_item_tool_profile(
        db_session, definition, capabilities={ToolCapability.FISHING}
    )
    instance = add_item(db_session, character["id"], definition.name)

    response = client.get(
        f"/api/campaigns/{campaign['id']}/inventory",
        params={"character_id": character["id"]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["item_instance_id"] == instance.id
    assert item["tool"] == {"capabilities": ["FISHING"]}
    assert item["weapon"] is None
    assert item["armor"] is None
