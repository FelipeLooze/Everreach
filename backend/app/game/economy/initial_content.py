"""Persistent starter economy for a generated campaign.

The transported protagonist receives nothing here.  The world receives real
businesses, finite shop stock and funded employers; the protagonist still
arrives with the shared outfit, empty backpack and zero Bronze, as established
by the arrival kit.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    BodyArea,
    BusinessType,
    CombatActorType,
    EconomicActorType,
    EquipmentSlot,
    ItemInstanceMode,
    ItemLocationType,
    ItemOwnerType,
    ItemType,
    JobPaymentFrequency,
    NoticeCategory,
    NoticeStatus,
    PhysicalDamageProfile,
    ToolCapability,
    WeaponFamily,
    WeaponHandRequirement,
    WeaponReach,
)
from app.db.models.business import Business
from app.db.models.item import ItemDefinition
from app.db.models.job import Job
from app.db.models.location import Location, LocationFeature
from app.db.models.notice import Notice
from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.db.models.shop import Shop
from app.game.economy.businesses import deposit_business_funds, found_business
from app.game.economy.jobs import create_job
from app.game.economy.pricing import set_item_base_value
from app.game.economy.shops import create_shop, deposit_till, stock_item
from app.game.items.armor import configure_item_armor_profile
from app.game.items.consumables import configure_consumable_profile
from app.game.items.equipment import configure_item_equipment_profile
from app.game.items.service import (
    create_item_definition,
    create_item_instance,
    get_item_definition,
    move_item_instance,
    set_item_owner,
)
from app.game.items.tools import configure_item_tool_profile
from app.game.items.weapons import configure_item_weapon_profile
from app.game.notices.service import post_notice
from app.game.schedules import ensure_job_schedule, job_hours_text


def _definition(
    db: Session,
    key: str,
    name: str,
    item_type: ItemType,
    mode: ItemInstanceMode,
    description: str,
    weight: float,
    value: int,
) -> ItemDefinition:
    definition = get_item_definition(db, key)
    if definition is None:
        definition = create_item_definition(
            db,
            key=key,
            name=name,
            item_type=item_type,
            instance_mode=mode,
            description=description,
            base_weight=weight,
        )
    if definition.base_value_bronze is None:
        set_item_base_value(db, definition, value)
    return definition


def ensure_economy_item_catalog(db: Session) -> dict[str, ItemDefinition]:
    items = {
        "knife": _definition(db, "economy_iron_knife", "Faca de Ferro", ItemType.WEAPON, ItemInstanceMode.UNIQUE, "Faca de trabalho simples, útil como ferramenta e arma curta.", 0.7, 18),
        "hammer": _definition(db, "economy_work_hammer", "Martelo de Trabalho", ItemType.TOOL, ItemInstanceMode.UNIQUE, "Martelo robusto para trabalho de forja e reparos.", 1.5, 14),
        "armor": _definition(db, "economy_leather_jerkin", "Gibão de Couro", ItemType.ARMOR, ItemInstanceMode.UNIQUE, "Proteção simples de couro para o torso.", 4.0, 45),
        "ration": _definition(db, "economy_travel_ration", "Ração de Viagem", ItemType.CONSUMABLE, ItemInstanceMode.STACKABLE, "Alimento conservado para uma refeição na estrada.", 0.35, 4),
        "water": _definition(db, "economy_water_skin", "Odre de Água", ItemType.CONSUMABLE, ItemInstanceMode.STACKABLE, "Uma porção de água potável em odre simples.", 1.0, 3),
        "rope": _definition(db, "economy_rope", "Corda", ItemType.MISC, ItemInstanceMode.STACKABLE, "Corda resistente de fibras vegetais.", 1.2, 8),
        "torch": _definition(db, "economy_torch", "Tocha", ItemType.MISC, ItemInstanceMode.STACKABLE, "Tocha de madeira e tecido embebido em óleo.", 0.6, 3),
        "fiber": _definition(db, "economy_plant_fiber", "Fibra Vegetal", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Fibras secas adequadas para trançado.", 0.15, 1),
        "iron": _definition(db, "economy_raw_iron", "Ferro Bruto", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Ferro ainda não trabalhado, pronto para a forja.", 0.8, 5),
        "wood": _definition(db, "economy_workshop_wood", "Madeira de Oficina", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Peças aproveitáveis de madeira seca.", 0.5, 2),
        "dried_meat": _definition(db, "economy_dried_meat", "Carne Seca", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Carne salgada que ainda precisa ser porcionada para viagem.", 0.4, 2),
        "hide": _definition(db, "economy_raw_hide", "Pele Bruta", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Pele animal ainda não curtida.", 1.0, 6),
        "horn": _definition(db, "economy_horn", "Chifre", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Chifre animal aproveitável por artesãos.", 0.4, 4),
        "feather": _definition(db, "economy_feather", "Pena", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Pena íntegra útil para flechas e ornamentos.", 0.02, 1),
        "raw_meat": _definition(db, "economy_raw_meat", "Carne Crua", ItemType.MATERIAL, ItemInstanceMode.STACKABLE, "Carne fresca obtida de um animal.", 0.5, 2),
    }

    configure_item_equipment_profile(
        db, items["knife"], allowed_slots={EquipmentSlot.MAIN_HAND, EquipmentSlot.OFF_HAND, EquipmentSlot.WAIST}
    )
    configure_item_weapon_profile(
        db,
        items["knife"],
        weapon_family=WeaponFamily.KNIFE,
        damage_profiles={PhysicalDamageProfile.SLASH, PhysicalDamageProfile.PIERCE},
        reach=WeaponReach.NORMAL,
        hand_requirement=WeaponHandRequirement.ONE_HAND,
    )
    configure_item_equipment_profile(
        db, items["hammer"], allowed_slots={EquipmentSlot.MAIN_HAND, EquipmentSlot.OFF_HAND, EquipmentSlot.WAIST}
    )
    configure_item_tool_profile(db, items["hammer"], capabilities={ToolCapability.HAMMERING})
    configure_item_equipment_profile(db, items["armor"], allowed_slots={EquipmentSlot.TORSO})
    configure_item_armor_profile(
        db,
        items["armor"],
        coverage={BodyArea.TORSO},
        physical_protections={
            PhysicalDamageProfile.SLASH: 2,
            PhysicalDamageProfile.PIERCE: 1,
            PhysicalDamageProfile.BLUNT: 1,
        },
    )
    configure_consumable_profile(db, items["ration"], hunger_restore=25, stamina_restore=2, use_minutes=5)
    configure_consumable_profile(db, items["water"], thirst_restore=30, use_minutes=2)
    return items


def _business(
    db: Session,
    campaign_id: str,
    name: str,
    business_type: BusinessType,
    operator: NPC,
    location_id: str,
    *,
    owner_type: EconomicActorType = EconomicActorType.NPC,
    owner_id: str | None = None,
) -> tuple[Business, bool]:
    existing = db.query(Business).filter(Business.campaign_id == campaign_id, Business.name == name).one_or_none()
    if existing is not None:
        return existing, False
    business = found_business(
        db,
        campaign_id,
        name,
        business_type,
        owner_type=owner_type,
        owner_id=owner_id or operator.id,
        operator_type=CombatActorType.NPC,
        operator_id=operator.id,
        location_id=location_id,
    )
    deposit_business_funds(db, business, 240, reason="Capital operacional inicial do estabelecimento.")
    return business, True


def _shop(
    db: Session,
    campaign_id: str,
    business: Business,
    operator: NPC,
    location_id: str,
    accepted: tuple[ItemType, ...],
) -> tuple[Shop, bool]:
    existing = db.query(Shop).filter(Shop.campaign_id == campaign_id, Shop.business_id == business.id).one_or_none()
    if existing is not None:
        return existing, False
    shop = create_shop(
        db,
        campaign_id,
        business.name,
        CombatActorType.NPC,
        operator.id,
        location_id=location_id,
        business_id=business.id,
        accepted_item_types=accepted,
    )
    deposit_till(db, shop, 160, reason="Troco e caixa inicial do estabelecimento.")
    return shop, True


def _stock(db: Session, shop: Shop, operator: NPC, definition: ItemDefinition, quantity: int) -> None:
    instance = create_item_instance(db, definition, quantity=quantity)
    move_item_instance(db, instance, location_type=ItemLocationType.NPC, location_ref=operator.id)
    set_item_owner(db, instance, owner_type=ItemOwnerType.NPC, owner_ref=operator.id)
    stock_item(db, shop, instance)


def _job(
    db: Session,
    campaign_id: str,
    business: Business,
    title: str,
    description: str,
    location_id: str,
    wage: int,
    minutes: int,
    profession_key: str,
    profession_name: str,
    xp: float,
    *,
    hours: tuple[int, int],
    hours_on_notice: bool,
) -> Job:
    existing = db.query(Job).filter(Job.campaign_id == campaign_id, Job.title == title).first()
    if existing is not None:
        return existing
    job = create_job(
        db,
        campaign_id,
        EconomicActorType.BUSINESS,
        business.id,
        title,
        description,
        wage_bronze=wage,
        payment_frequency=JobPaymentFrequency.PER_TASK,
        location_id=location_id,
        capacity=1,
        work_minutes=minutes,
        profession_key=profession_key,
        profession_name=profession_name,
        profession_xp=xp,
    )
    # The employer's own working hours (app.simulation.npc_routines).
    job.shift_start_hour, job.shift_end_hour = hours
    job.schedule_on_notice = hours_on_notice
    db.flush()
    return job


def _post_job_notice(db: Session, campaign_id: str, job: Job, author: NPC) -> None:
    existing = db.query(Notice).filter(
        Notice.campaign_id == campaign_id,
        Notice.category == NoticeCategory.JOB.value,
        Notice.title == job.title,
        Notice.status == NoticeStatus.ACTIVE.value,
    ).first()
    if existing is not None:
        return
    board = db.query(LocationFeature).join(Location).filter(
        Location.region_id == author.region_id,
        Location.type == "notice_board",
        LocationFeature.name.like("Quadro de Avisos%"),
    ).first()
    if board is None:
        return
    workplace = db.get(Location, job.location_id)
    hours, minutes = divmod(job.work_minutes, 60)
    shift = f"{hours}h{minutes:02d}" if minutes else f"{hours} horas"
    stated_hours = f" Turnos {job_hours_text(job)}." if job.schedule_on_notice and job_hours_text(job) else ""
    post_notice(
        db,
        campaign_id,
        board.id,
        category=NoticeCategory.JOB,
        title=job.title,
        text=(
            f"{job.description} Apresente-se em {workplace.name if workplace else 'o estabelecimento'}; "
            f"pagamento de {job.wage_bronze} Bronze por turno de {shift}.{stated_hours}"
        ),
        author_npc_id=author.id,
    )


def ensure_initial_economy_for_campaign(
    db: Session,
    campaign_id: str,
    *,
    blacksmith: NPC | None = None,
    innkeeper: NPC | None = None,
    merchant: NPC | None = None,
    merchant_organization: Organization | None = None,
) -> bool:
    """Create starter businesses once; return whether anything was added."""
    blacksmith = blacksmith or db.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.role == "ferreira").first()
    innkeeper = innkeeper or db.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.role == "estalajadeiro").first()
    merchant = merchant or db.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.role == "mestre da guilda de comerciantes").first()
    if not all((blacksmith, innkeeper, merchant)):
        return False
    if not all((blacksmith.workplace_location_id, innkeeper.workplace_location_id, merchant.workplace_location_id)):
        return False
    merchant_organization = merchant_organization or db.query(Organization).filter(
        Organization.campaign_id == campaign_id,
        Organization.founder_type == CombatActorType.NPC.value,
        Organization.founder_id == merchant.id,
    ).first()

    items = ensure_economy_item_catalog(db)
    created_any = False

    forge, forge_created = _business(
        db, campaign_id, f"Ferraria de {blacksmith.name}", BusinessType.SMITHY, blacksmith, blacksmith.workplace_location_id
    )
    forge_shop, forge_shop_created = _shop(
        db, campaign_id, forge, blacksmith, blacksmith.workplace_location_id,
        (ItemType.WEAPON, ItemType.ARMOR, ItemType.TOOL, ItemType.MATERIAL),
    )
    if forge_shop_created:
        _stock(db, forge_shop, blacksmith, items["knife"], 1)
        _stock(db, forge_shop, blacksmith, items["knife"], 1)
        _stock(db, forge_shop, blacksmith, items["hammer"], 1)
        _stock(db, forge_shop, blacksmith, items["armor"], 1)
    forge_job = _job(db, campaign_id, forge, "Ajudante de Ferreiro", "Auxiliar a ferreira em tarefas reais de forja e manutenção.", blacksmith.workplace_location_id, 12, 180, "BLACKSMITH", "Ferreiro", 0.8, hours=(8, 18), hours_on_notice=True)

    inn, inn_created = _business(
        db, campaign_id, f"Estalagem de {innkeeper.name}", BusinessType.INN, innkeeper, innkeeper.workplace_location_id
    )
    inn_shop, inn_shop_created = _shop(
        db, campaign_id, inn, innkeeper, innkeeper.workplace_location_id,
        (ItemType.CONSUMABLE, ItemType.MATERIAL),
    )
    if inn_shop_created:
        _stock(db, inn_shop, innkeeper, items["ration"], 6)
        _stock(db, inn_shop, innkeeper, items["water"], 4)
        _stock(db, inn_shop, innkeeper, items["dried_meat"], 4)
    inn_job = _job(db, campaign_id, inn, "Ajudante da Estalagem", "Ajudar no preparo, na limpeza e no atendimento da estalagem.", innkeeper.workplace_location_id, 8, 120, "COOK", "Cozinheiro", 0.5, hours=(8, 18), hours_on_notice=False)

    market_owner_type = EconomicActorType.ORGANIZATION if merchant_organization else EconomicActorType.NPC
    market_owner_id = merchant_organization.id if merchant_organization else merchant.id
    market, market_created = _business(
        db, campaign_id, "Entreposto da Guilda de Comerciantes", BusinessType.TRADING_COMPANY,
        merchant, merchant.workplace_location_id, owner_type=market_owner_type, owner_id=market_owner_id,
    )
    market_shop, market_shop_created = _shop(
        db, campaign_id, market, merchant, merchant.workplace_location_id,
        (ItemType.MATERIAL, ItemType.MISC, ItemType.CONSUMABLE, ItemType.CONTAINER),
    )
    if market_shop_created:
        for key, quantity in (("rope", 3), ("torch", 4), ("fiber", 9), ("iron", 6), ("wood", 6)):
            _stock(db, market_shop, merchant, items[key], quantity)
    market_job = _job(db, campaign_id, market, "Auxiliar de Armazém", "Separar mercadorias e ajudar a registrar cargas do entreposto.", merchant.workplace_location_id, 10, 150, "MERCHANT", "Comerciante", 0.6, hours=(8, 18), hours_on_notice=True)

    for job, author in ((forge_job, blacksmith), (inn_job, innkeeper), (market_job, merchant)):
        _post_job_notice(db, campaign_id, job, author)
        ensure_job_schedule(db, campaign_id, job, author)

    created_any = any((forge_created, forge_shop_created, inn_created, inn_shop_created, market_created, market_shop_created))
    db.flush()
    return created_any
