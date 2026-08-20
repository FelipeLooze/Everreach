import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    ActionIntentType,
    CharacterStatus,
    EquipmentSlot,
    EventType,
    ItemLocationType,
    ItemOwnerType,
)
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.db.models.equipment import ItemEquipmentProfile
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.npc import NPC
from app.game.items.containers import (
    is_item_possessed_by_character,
    store_item_in_container,
)
from app.game.items.equipment import (
    equip_item,
    get_allowed_equipment_slots,
    unequip_item,
)
from app.game.items.service import move_item_instance, set_item_owner
from app.services.event_log import log_event


ITEM_INTERACTION_INTENTS = frozenset(
    {
        ActionIntentType.PICK_UP,
        ActionIntentType.DROP,
        ActionIntentType.GIVE,
        ActionIntentType.TAKE,
        ActionIntentType.EQUIP,
        ActionIntentType.UNEQUIP,
        ActionIntentType.STORE,
        ActionIntentType.RETRIEVE,
        ActionIntentType.MOVE_BETWEEN_CONTAINERS,
    }
)


class ItemInteractionError(ValueError):
    pass


@dataclass(frozen=True)
class ItemInteractionResult:
    interaction: ActionIntentType
    item_instance_id: str
    summary: str
    replayed: bool = False


def resolve_item_interaction(
    db: Session,
    campaign_id: str,
    actor: Character,
    *,
    interaction: ActionIntentType,
    target: str | None,
    secondary_target: str | None = None,
    slot: str | None = None,
    interaction_key: str | None = None,
) -> ItemInteractionResult:
    if interaction not in ITEM_INTERACTION_INTENTS:
        raise ItemInteractionError("Unsupported item interaction.")
    if actor.campaign_id != campaign_id:
        raise ItemInteractionError("Actor does not belong to this campaign.")
    if actor.status != CharacterStatus.ALIVE.value:
        raise ItemInteractionError("Only a living, active character can move items.")
    if not target:
        raise ItemInteractionError("No item was identified for the interaction.")

    replay = _find_replay(
        db,
        campaign_id,
        actor.id,
        interaction,
        interaction_key,
        target,
        secondary_target,
        slot,
    )
    if replay is not None:
        return replay

    item = _resolve_interaction_item(
        db, campaign_id, actor, interaction, target
    )
    before = _snapshot(item)

    if interaction == ActionIntentType.PICK_UP:
        _pick_up(db, actor, item)
        summary = f"{actor.name} pega {item.definition.name}."
    elif interaction == ActionIntentType.DROP:
        _require_possession(db, actor, item)
        _require_not_equipped(item)
        move_item_instance(
            db,
            item,
            location_type=ItemLocationType.WORLD_LOCATION,
            location_ref=actor.location_id,
        )
        summary = f"{actor.name} deixa {item.definition.name} no local."
    elif interaction == ActionIntentType.GIVE:
        _require_possession(db, actor, item)
        _require_not_equipped(item)
        recipient = _resolve_recipient(db, campaign_id, actor, secondary_target)
        _require_colocated(actor, recipient)
        if isinstance(recipient, Character):
            location_type = ItemLocationType.CHARACTER
            owner_type = ItemOwnerType.CHARACTER
        else:
            location_type = ItemLocationType.NPC
            owner_type = ItemOwnerType.NPC
        move_item_instance(
            db, item, location_type=location_type, location_ref=recipient.id
        )
        set_item_owner(db, item, owner_type=owner_type, owner_ref=recipient.id)
        summary = f"{actor.name} entrega {item.definition.name} a {recipient.name}."
    elif interaction == ActionIntentType.TAKE:
        holder = _physical_holder(db, item)
        if holder is None or holder.id == actor.id:
            raise ItemInteractionError("Item is not held by another reachable actor.")
        _require_colocated(actor, holder)
        _require_not_equipped(item)
        move_item_instance(
            db,
            item,
            location_type=ItemLocationType.CHARACTER,
            location_ref=actor.id,
        )
        summary = f"{actor.name} toma {item.definition.name} de {holder.name}."
    elif interaction == ActionIntentType.EQUIP:
        _require_possession(db, actor, item)
        equipment_slot = _resolve_equipment_slot(db, item, slot)
        with db.begin_nested():
            if item.location_type == ItemLocationType.CONTAINER.value:
                move_item_instance(
                    db,
                    item,
                    location_type=ItemLocationType.CHARACTER,
                    location_ref=actor.id,
                )
            equip_item(db, item, slot=equipment_slot)
        summary = f"{actor.name} equipa {item.definition.name} em {equipment_slot.value}."
    elif interaction == ActionIntentType.UNEQUIP:
        if (
            item.location_type != ItemLocationType.CHARACTER_EQUIPPED.value
            or item.location_ref != actor.id
        ):
            raise ItemInteractionError("Item is not equipped by the acting character.")
        unequip_item(db, item)
        summary = f"{actor.name} desequipa {item.definition.name}."
    elif interaction == ActionIntentType.STORE:
        _require_possession(db, actor, item)
        container = _resolve_possessed_container(
            db, campaign_id, actor, secondary_target
        )
        store_item_in_container(db, item, container)
        summary = (
            f"{actor.name} guarda {item.definition.name} em "
            f"{container.definition.name}."
        )
    elif interaction == ActionIntentType.RETRIEVE:
        _require_possession(db, actor, item)
        if item.location_type != ItemLocationType.CONTAINER.value:
            raise ItemInteractionError("Item is not stored in a container.")
        container = db.get(ItemInstance, item.location_ref)
        move_item_instance(
            db,
            item,
            location_type=ItemLocationType.CHARACTER,
            location_ref=actor.id,
        )
        summary = (
            f"{actor.name} retira {item.definition.name} de "
            f"{container.definition.name}."
        )
    else:
        _require_possession(db, actor, item)
        if item.location_type != ItemLocationType.CONTAINER.value:
            raise ItemInteractionError("Item is not inside a source container.")
        source_id = item.location_ref
        container = _resolve_possessed_container(
            db, campaign_id, actor, secondary_target
        )
        if source_id == container.id:
            raise ItemInteractionError("Item is already in the target container.")
        store_item_in_container(db, item, container)
        summary = (
            f"{actor.name} move {item.definition.name} para "
            f"{container.definition.name}."
        )

    after = _snapshot(item)
    log_event(
        db,
        campaign_id,
        EventType.ITEM_INTERACTION_RESOLVED,
        actor_type="character",
        actor_id=actor.id,
        payload={
            "interaction_key": interaction_key,
            "interaction": interaction.value,
            "requested_target": target,
            "requested_secondary_target": secondary_target,
            "requested_slot": slot,
            "item_instance_id": item.id,
            "secondary_target": secondary_target,
            "before": before,
            "after": after,
            "summary": summary,
        },
    )
    return ItemInteractionResult(interaction, item.id, summary)


def _pick_up(db: Session, actor: Character, item: ItemInstance) -> None:
    if (
        item.location_type != ItemLocationType.WORLD_LOCATION.value
        or item.location_ref != actor.location_id
    ):
        raise ItemInteractionError("Item is not present at the actor's location.")
    move_item_instance(
        db,
        item,
        location_type=ItemLocationType.CHARACTER,
        location_ref=actor.id,
    )


def _resolve_interaction_item(
    db: Session,
    campaign_id: str,
    actor: Character,
    interaction: ActionIntentType,
    target: str,
) -> ItemInstance:
    direct = db.get(ItemInstance, target.strip())
    if direct is not None:
        if direct.campaign_id != campaign_id:
            raise ItemInteractionError("Item does not belong to this campaign.")
        return direct
    candidates = (
        db.query(ItemInstance)
        .join(ItemDefinition, ItemDefinition.id == ItemInstance.definition_id)
        .filter(ItemInstance.campaign_id == campaign_id)
        .all()
    )
    if interaction == ActionIntentType.PICK_UP:
        candidates = [
            item
            for item in candidates
            if item.location_type == ItemLocationType.WORLD_LOCATION.value
            and item.location_ref == actor.location_id
        ]
    elif interaction == ActionIntentType.TAKE:
        candidates = [
            item
            for item in candidates
            if (holder := _physical_holder(db, item)) is not None
            and holder.id != actor.id
            and holder.location_id == actor.location_id
        ]
    else:
        candidates = [
            item
            for item in candidates
            if is_item_possessed_by_character(db, item, actor.id)
        ]
        if interaction == ActionIntentType.UNEQUIP:
            candidates = [
                item
                for item in candidates
                if item.location_type == ItemLocationType.CHARACTER_EQUIPPED.value
            ]
        elif interaction in {
            ActionIntentType.RETRIEVE,
            ActionIntentType.MOVE_BETWEEN_CONTAINERS,
        }:
            candidates = [
                item
                for item in candidates
                if item.location_type == ItemLocationType.CONTAINER.value
            ]
    return _unique_named(candidates, target, lambda row: row.definition.name, "item")


def _resolve_possessed_container(
    db: Session,
    campaign_id: str,
    actor: Character,
    target: str | None,
) -> ItemInstance:
    if not target:
        raise ItemInteractionError("No target container was identified.")
    direct = db.get(ItemInstance, target.strip())
    if direct is not None:
        if direct.campaign_id != campaign_id:
            raise ItemInteractionError("Container does not belong to this campaign.")
        _require_possession(db, actor, direct)
        return direct
    candidates = (
        db.query(ItemInstance)
        .join(ItemDefinition, ItemDefinition.id == ItemInstance.definition_id)
        .filter(ItemInstance.campaign_id == campaign_id)
        .all()
    )
    possessed = [
        item
        for item in candidates
        if is_item_possessed_by_character(db, item, actor.id)
    ]
    return _unique_named(
        possessed, target, lambda row: row.definition.name, "container"
    )


def _resolve_recipient(
    db: Session,
    campaign_id: str,
    actor: Character,
    target: str | None,
) -> Character | NPC:
    if not target:
        raise ItemInteractionError("No recipient was identified.")
    direct_character = db.get(Character, target.strip())
    if direct_character is not None and direct_character.campaign_id == campaign_id:
        candidates: list[Character | NPC] = [direct_character]
    else:
        direct_npc = db.get(NPC, target.strip())
        if direct_npc is not None and direct_npc.campaign_id == campaign_id:
            candidates = [direct_npc]
        else:
            candidates = [
                *db.query(Character).filter(Character.campaign_id == campaign_id).all(),
                *db.query(NPC).filter(NPC.campaign_id == campaign_id).all(),
            ]
            candidates = [row for row in candidates if row.id != actor.id]
            return _unique_named(candidates, target, lambda row: row.name, "recipient")
    recipient = candidates[0]
    if recipient.id == actor.id:
        raise ItemInteractionError("Actor cannot be the recipient of their own item.")
    return recipient


def _resolve_equipment_slot(
    db: Session,
    item: ItemInstance,
    slot: str | None,
) -> EquipmentSlot:
    if slot:
        try:
            return EquipmentSlot(slot.strip().upper())
        except ValueError as exc:
            raise ItemInteractionError("A valid equipment slot is required.") from exc
    profile = db.get(ItemEquipmentProfile, item.definition_id)
    if profile is None:
        raise ItemInteractionError("Item has no authoritative equipment profile.")
    allowed = get_allowed_equipment_slots(profile)
    if len(allowed) != 1:
        raise ItemInteractionError(
            "Equipment slot must be specified when multiple positions are possible."
        )
    return next(iter(allowed))


def _physical_holder(db: Session, item: ItemInstance) -> Character | NPC | None:
    current = item
    visited: set[str] = set()
    while current.location_type == ItemLocationType.CONTAINER.value:
        if current.id in visited or not current.location_ref:
            raise ItemInteractionError("Invalid recursive container hierarchy.")
        visited.add(current.id)
        parent = db.get(ItemInstance, current.location_ref)
        if parent is None:
            raise ItemInteractionError("Container hierarchy references a missing item.")
        current = parent
    if current.location_type in {
        ItemLocationType.CHARACTER.value,
        ItemLocationType.CHARACTER_EQUIPPED.value,
    }:
        return db.get(Character, current.location_ref)
    if current.location_type == ItemLocationType.NPC.value:
        return db.get(NPC, current.location_ref)
    return None


def _require_possession(
    db: Session, actor: Character, item: ItemInstance
) -> None:
    if not is_item_possessed_by_character(db, item, actor.id):
        raise ItemInteractionError("Item is not physically possessed by the actor.")


def _require_not_equipped(item: ItemInstance) -> None:
    if item.location_type == ItemLocationType.CHARACTER_EQUIPPED.value:
        raise ItemInteractionError("Equipped item must be unequipped first.")


def _require_colocated(actor: Character, other: Character | NPC) -> None:
    if other.location_id != actor.location_id:
        raise ItemInteractionError("The other actor is not at the same location.")
    if isinstance(other, Character) and other.status == CharacterStatus.DEAD.value:
        raise ItemInteractionError("Cannot complete this transfer with a dead character.")
    if isinstance(other, NPC) and not other.alive:
        raise ItemInteractionError("Cannot complete this transfer with a dead NPC.")


def _unique_named(candidates, target: str, name, kind: str):
    normalized = target.strip().casefold()
    exact = [row for row in candidates if name(row).casefold() == normalized]
    matches = exact or [row for row in candidates if normalized in name(row).casefold()]
    if not matches:
        raise ItemInteractionError(f"No matching {kind} exists in this campaign.")
    if len(matches) > 1:
        raise ItemInteractionError(f"The {kind} target is ambiguous.")
    return matches[0]


def _snapshot(item: ItemInstance) -> dict:
    return {
        "location_type": item.location_type,
        "location_ref": item.location_ref,
        "owner_type": item.owner_type,
        "owner_ref": item.owner_ref,
        "equipped_slot": item.equipped_slot,
    }


def _find_replay(
    db: Session,
    campaign_id: str,
    actor_id: str,
    interaction: ActionIntentType,
    interaction_key: str | None,
    target: str,
    secondary_target: str | None,
    slot: str | None,
) -> ItemInteractionResult | None:
    if not interaction_key:
        return None
    events = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == campaign_id,
            WorldEvent.event_type == EventType.ITEM_INTERACTION_RESOLVED.value,
            WorldEvent.actor_id == actor_id,
        )
        .all()
    )
    for event in events:
        payload = json.loads(event.payload_json)
        if payload.get("interaction_key") != interaction_key:
            continue
        if (
            payload.get("interaction") != interaction.value
            or payload.get("requested_target") != target
            or payload.get("requested_secondary_target") != secondary_target
            or payload.get("requested_slot") != slot
        ):
            raise ItemInteractionError(
                "Interaction key was already used for a different item action."
            )
        return ItemInteractionResult(
            interaction=interaction,
            item_instance_id=payload["item_instance_id"],
            summary=payload["summary"],
            replayed=True,
        )
    return None
