"""Phase 17G — Physical Maps.

Reuses Phase 10 in full — a map is a real ItemInstance (ItemType.MAP,
always UNIQUE: two maps of the same place are never interchangeable,
since their content can genuinely differ), placed in the creator's
inventory exactly like any other item via app.game.inventory.service.add_item.
The app.db.models.map.Map row is a thin overlay (same pattern as
Settlement overlaying Location) holding a frozen JSON copy of the
creator's own 17F CartographicSurvey — never a live reference.

create_map raises ValueError if the creator's current knowledge can't
support a map at all (17F's can_produce_map) — "a character cannot
create an accurate map of somewhere they know nothing about" is
enforced here, not just documented.
"""

import json
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.core.enums import KnowerType
from app.db.models.item import ItemInstance
from app.db.models.map import Map
from app.game.inventory.service import add_item, get_or_create_item
from app.game.knowledge.cartography import CartographicSurvey, survey_cartographic_knowledge
from app.game.time.clock import get_world_time

DEFAULT_MAP_NAME = "Mapa"


def _serialize_survey(survey: CartographicSurvey) -> str:
    return json.dumps(
        {
            "subject_kind": survey.subject_kind,
            "entity_id": survey.entity_id,
            "aspects": [
                {
                    "aspect": surveyed.aspect.value,
                    "statement": surveyed.statement,
                    "precision": surveyed.precision.value if surveyed.precision else None,
                    "certainty": surveyed.certainty,
                }
                for surveyed in survey.aspects
            ],
        }
    )


def create_map(
    db: Session,
    campaign_id: str,
    character_id: str,
    subject_kind: str,
    entity_id: str,
    *,
    map_name: str = DEFAULT_MAP_NAME,
) -> tuple[ItemInstance, Map]:
    survey = survey_cartographic_knowledge(
        db, campaign_id, KnowerType.PLAYER, character_id, subject_kind, entity_id
    )
    if not survey.can_produce_map:
        raise ValueError(
            f"Character {character_id} does not know enough about {subject_kind}:{entity_id} to draw a map of it."
        )

    world_minute = get_world_time(db, campaign_id).total_minutes()

    # add_item's own get_or_create_item call defaults to item_type
    # "misc" — establish the real ItemType.MAP definition first so a
    # map is never accidentally created as a generic MISC item.
    get_or_create_item(db, map_name, item_type="map")
    instance = add_item(db, character_id, map_name)

    map_row = Map(
        item_instance_id=instance.id,
        subject_kind=subject_kind,
        entity_id=entity_id,
        creator_type=KnowerType.PLAYER.value,
        creator_id=character_id,
        created_world_minute=world_minute,
        content_json=_serialize_survey(survey),
    )
    db.add(map_row)
    db.flush()

    return instance, map_row


def map_content(map_row: Map) -> dict:
    return json.loads(map_row.content_json)
