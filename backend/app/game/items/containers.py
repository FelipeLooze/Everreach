from math import isfinite

from sqlalchemy.orm import Session

from app.core.enums import ItemLocationType, ItemType
from app.db.models.container import ItemContainerProfile
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.material import MaterialDefinition
from app.game.items.durability import is_item_broken
from app.game.items.materials import material_weight_factor
from app.game.items.service import _set_item_location


class ContainerError(ValueError):
    pass


def configure_item_container_profile(
    db: Session,
    item: ItemDefinition,
    *,
    weight_capacity: float,
) -> ItemContainerProfile:
    if db.get(ItemDefinition, item.id) is None:
        raise ContainerError("Container item must be persisted before configuration.")
    if item.type != ItemType.CONTAINER.value:
        raise ContainerError("Only CONTAINER item definitions can contain items.")
    if (
        isinstance(weight_capacity, bool)
        or not isfinite(weight_capacity)
        or weight_capacity <= 0
    ):
        raise ContainerError("Container weight capacity must be finite and positive.")
    existing = db.get(ItemContainerProfile, item.id)
    if existing is not None:
        if existing.weight_capacity != float(weight_capacity):
            raise ContainerError(
                "Container already has a different canonical weight capacity."
            )
        return existing
    profile = ItemContainerProfile(
        item_id=item.id,
        weight_capacity=float(weight_capacity),
    )
    db.add(profile)
    db.flush()
    return profile


def list_container_contents(db: Session, container_id: str) -> list[ItemInstance]:
    return (
        db.query(ItemInstance)
        .filter(
            ItemInstance.location_type == ItemLocationType.CONTAINER.value,
            ItemInstance.location_ref == container_id,
        )
        .order_by(ItemInstance.id)
        .all()
    )


def get_item_own_weight(db: Session, instance: ItemInstance) -> float:
    definition = db.get(ItemDefinition, instance.definition_id)
    if definition is None:
        raise ContainerError("Item instance has no definition.")
    material = (
        db.get(MaterialDefinition, instance.material_id)
        if instance.material_id is not None
        else None
    )
    return definition.base_weight * instance.quantity * material_weight_factor(material)


def get_item_total_weight(db: Session, instance: ItemInstance) -> float:
    return _subtree_weight(db, instance, set())


def get_container_content_weight(db: Session, container: ItemInstance) -> float:
    _require_container(db, container)
    return sum(
        _subtree_weight(db, child, {container.id})
        for child in list_container_contents(db, container.id)
    )


def store_item_in_container(
    db: Session,
    instance: ItemInstance,
    container: ItemInstance,
) -> ItemInstance:
    if db.get(ItemInstance, instance.id) is None:
        raise ContainerError("Item instance does not exist.")
    _require_container(db, container)
    if instance.id == container.id:
        raise ContainerError("A container cannot contain itself.")
    if instance.location_type == ItemLocationType.CHARACTER_EQUIPPED.value:
        raise ContainerError("Equipped items must be unequipped before storage.")
    if is_item_broken(container):
        raise ContainerError("Broken container cannot safely hold items.")
    if container.campaign_id is None:
        raise ContainerError("Container must exist in a campaign before use.")
    if (
        instance.campaign_id is not None
        and container.campaign_id is not None
        and instance.campaign_id != container.campaign_id
    ):
        raise ContainerError("Items cannot be stored across campaigns.")
    _assert_no_cycle(db, instance, container)
    required = get_item_total_weight(db, instance)
    if instance.location_type == ItemLocationType.CONTAINER.value:
        if instance.location_ref == container.id:
            return instance
    for target in _container_chain(db, container):
        profile = _require_container(db, target)
        delta = 0.0 if _is_descendant_of(db, instance, target) else required
        if get_container_content_weight(db, target) + delta > profile.weight_capacity + 1e-9:
            raise ContainerError("Container weight capacity would be exceeded.")
    return _set_item_location(
        db,
        instance,
        location_type=ItemLocationType.CONTAINER,
        location_ref=container.id,
        equipped_slot=None,
    )


def is_item_possessed_by_character(
    db: Session,
    instance: ItemInstance,
    character_id: str,
) -> bool:
    current = instance
    visited: set[str] = set()
    while current.location_type == ItemLocationType.CONTAINER.value:
        if current.id in visited or not current.location_ref:
            raise ContainerError("Invalid recursive container hierarchy.")
        visited.add(current.id)
        parent = db.get(ItemInstance, current.location_ref)
        if parent is None:
            return False
        current = parent
    return current.location_type in {
        ItemLocationType.CHARACTER.value,
        ItemLocationType.CHARACTER_EQUIPPED.value,
    } and current.location_ref == character_id


def _require_container(db: Session, container: ItemInstance) -> ItemContainerProfile:
    if db.get(ItemInstance, container.id) is None:
        raise ContainerError("Container instance does not exist.")
    definition = db.get(ItemDefinition, container.definition_id)
    profile = db.get(ItemContainerProfile, container.definition_id)
    if definition is None or definition.type != ItemType.CONTAINER.value or profile is None:
        raise ContainerError("Target item is not an authoritative container.")
    return profile


def _assert_no_cycle(
    db: Session,
    instance: ItemInstance,
    container: ItemInstance,
) -> None:
    current = container
    visited: set[str] = set()
    while current.location_type == ItemLocationType.CONTAINER.value:
        if current.id == instance.id:
            raise ContainerError("Container nesting would create a recursive cycle.")
        if current.id in visited or not current.location_ref:
            raise ContainerError("Invalid recursive container hierarchy.")
        visited.add(current.id)
        parent = db.get(ItemInstance, current.location_ref)
        if parent is None:
            raise ContainerError("Container hierarchy references a missing item.")
        current = parent
    if current.id == instance.id:
        raise ContainerError("Container nesting would create a recursive cycle.")


def _container_chain(db: Session, container: ItemInstance) -> list[ItemInstance]:
    result: list[ItemInstance] = []
    current = container
    visited: set[str] = set()
    while True:
        if current.id in visited:
            raise ContainerError("Invalid recursive container hierarchy.")
        visited.add(current.id)
        result.append(current)
        if current.location_type != ItemLocationType.CONTAINER.value:
            return result
        if not current.location_ref:
            raise ContainerError("Invalid recursive container hierarchy.")
        parent = db.get(ItemInstance, current.location_ref)
        if parent is None:
            raise ContainerError("Container hierarchy references a missing item.")
        current = parent


def _is_descendant_of(
    db: Session,
    instance: ItemInstance,
    possible_ancestor: ItemInstance,
) -> bool:
    current = instance
    visited: set[str] = set()
    while current.location_type == ItemLocationType.CONTAINER.value:
        if current.id in visited or not current.location_ref:
            raise ContainerError("Invalid recursive container hierarchy.")
        visited.add(current.id)
        if current.location_ref == possible_ancestor.id:
            return True
        parent = db.get(ItemInstance, current.location_ref)
        if parent is None:
            raise ContainerError("Container hierarchy references a missing item.")
        current = parent
    return False


def _subtree_weight(
    db: Session,
    instance: ItemInstance,
    ancestors: set[str],
) -> float:
    if instance.id in ancestors:
        raise ContainerError("Invalid recursive container hierarchy.")
    branch = ancestors | {instance.id}
    return get_item_own_weight(db, instance) + sum(
        _subtree_weight(db, child, branch)
        for child in list_container_contents(db, instance.id)
    )
