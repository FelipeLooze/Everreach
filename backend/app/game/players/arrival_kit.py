"""Canonical arrival clothing shared by every transported person.

The protagonist receives real Phase 10 item instances. Simulated transported
people currently expose the same visual canon through their persisted identity
context; their inventory model does not yet own physical ItemInstances.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    EquipmentSlot,
    EventType,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ItemType,
)
from app.db.models.character import Character
from app.db.models.event import WorldEvent
from app.game.items.containers import configure_item_container_profile
from app.game.items.equipment import configure_item_equipment_profile, equip_item
from app.game.items.materials import get_material_definition, seed_core_materials
from app.game.items.service import (
    create_item_definition,
    create_item_instance,
    move_item_instance,
    set_item_owner,
)
from app.services.event_log import log_event


TRANSPORTED_OUTFIT_NAME = "Traje dos Transportados"
TRANSPORTED_BACKPACK_NAME = "Mochila dos Transportados"

TRANSPORTED_OUTFIT_APPEARANCE = (
    "Veste o traje padronizado dos Transportados: túnica de tecido cru bege-claro, "
    "acabamentos azul-escuro dessaturado na gola, nas bordas e na faixa da cintura, "
    "calças terrosas presas por faixas, botas gastas de couro marrom e um manto curto "
    "azul-escuro preso por broche circular. Um símbolo discreto marca a faixa e as "
    "barras do traje. Carrega nas costas uma mochila compacta de couro marrom-escuro "
    "com pequenos detalhes azuis e o mesmo símbolo."
)

_OUTFIT_DESCRIPTION = (
    "Conjunto simples e padronizado usado por quem foi transportado: túnica bege de "
    "pano resistente com detalhes azul-escuro, calças terrosas, botas de couro e manto "
    "curto preso por broche. O símbolo discreto nas barras identifica a origem comum. "
    "É roupa funcional e não oferece proteção de armadura."
)
_BACKPACK_DESCRIPTION = (
    "Mochila compacta e resistente de couro marrom-escuro, fechada por aba, tiras e "
    "fivela metálica. Costuras azul-escuras e um símbolo discreto repetem a identidade "
    "visual dos Transportados. Chega completamente vazia."
)


def transported_appearance(physical_description: str | None) -> str:
    physical = " ".join((physical_description or "").split())
    return f"{physical} {TRANSPORTED_OUTFIT_APPEARANCE}".strip()


def grant_transported_arrival_kit(db: Session, character: Character) -> tuple:
    """Give exactly one outfit and one empty backpack on arrival.

    The Event Log is the idempotency marker. This remains safe if the player
    later drops, sells or loses either object: calling /start again never
    manufactures a replacement.
    """
    already_granted = (
        db.query(WorldEvent)
        .filter(
            WorldEvent.campaign_id == character.campaign_id,
            WorldEvent.event_type == EventType.TRANSPORTED_ARRIVAL_KIT_GRANTED.value,
            WorldEvent.actor_type == "character",
            WorldEvent.actor_id == character.id,
        )
        .first()
    )
    if already_granted is not None:
        return ()

    seed_core_materials(db)
    leather = get_material_definition(db, "LEATHER")

    outfit_definition = create_item_definition(
        db,
        key="transported_outfit",
        name=TRANSPORTED_OUTFIT_NAME,
        item_type=ItemType.MISC,
        instance_mode=ItemInstanceMode.UNIQUE,
        description=_OUTFIT_DESCRIPTION,
        base_weight=2.2,
    )
    configure_item_equipment_profile(
        db, outfit_definition, allowed_slots={EquipmentSlot.TORSO}
    )
    backpack_definition = create_item_definition(
        db,
        key="transported_backpack",
        name=TRANSPORTED_BACKPACK_NAME,
        item_type=ItemType.CONTAINER,
        instance_mode=ItemInstanceMode.UNIQUE,
        description=_BACKPACK_DESCRIPTION,
        base_weight=2.0,
    )
    configure_item_equipment_profile(
        db, backpack_definition, allowed_slots={EquipmentSlot.BACK}
    )
    configure_item_container_profile(db, backpack_definition, weight_capacity=12.0)

    outfit = create_item_instance(db, outfit_definition)
    backpack = create_item_instance(db, backpack_definition, material=leather)
    for instance, slot in (
        (outfit, EquipmentSlot.TORSO),
        (backpack, EquipmentSlot.BACK),
    ):
        move_item_instance(
            db,
            instance,
            location_type=ItemLocationType.CHARACTER,
            location_ref=character.id,
        )
        set_item_owner(
            db,
            instance,
            owner_type=ItemOwnerType.CHARACTER,
            owner_ref=character.id,
        )
        equip_item(db, instance, slot=slot)

    log_event(
        db,
        character.campaign_id,
        EventType.TRANSPORTED_ARRIVAL_KIT_GRANTED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "outfit_item_instance_id": outfit.id,
            "backpack_item_instance_id": backpack.id,
            "backpack_starts_empty": True,
            "protective_armor": False,
        },
    )
    db.flush()
    return outfit, backpack
