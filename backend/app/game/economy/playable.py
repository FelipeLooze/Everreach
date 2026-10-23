"""Player-facing orchestration for the Phase 14 economy.

The low-level Phase 14 services remain the authorities for money, ownership,
stock, wages and production.  This module only resolves a text action against
what is physically present and composes those services into playable turns.
"""

import json
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import (
    ActionIntentType,
    CombatActorType,
    ItemLocationType,
    JobApplicationStatus,
    JobStatus,
    ShopStatus,
    ToolCapability,
)
from app.db.models.business import Business
from app.db.models.character import Character
from app.db.models.item import ItemDefinition, ItemInstance
from app.db.models.job import Job, JobApplication
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.shop import Shop, ShopListing
from app.db.models.tool import ItemToolProfile
from app.game.economy.jobs import JobError, apply_to_job, end_employment, resolve_application
from app.game.economy.production import ProductionError, produce_goods
from app.game.economy.recipes import RECIPES, EconomyRecipe
from app.game.economy.shops import ShopError, buy_from_shop, sell_to_shop
from app.game.economy.supply_demand import resolve_local_market_price
from app.game.economy.wages import WageError, pay_wage
from app.game.economy.wallet import total_carried_by_owner
from app.game.items.tools import ToolError, validate_character_tool_use
from app.game.npcs.service import effective_npc_location_id
from app.game.schedules import (
    job_hours_text,
    job_schedule_fact_key,
    player_knows_job_schedule,
    shift_refusal,
    teach_schedule,
)
from app.game.time.clock import get_world_time
from app.game.professions.activities import award_crafting_xp, award_work_xp


@dataclass(frozen=True)
class EconomyActionResult:
    summary: str
    minutes: int
    changed: bool


def _normalized(text: str | None) -> str:
    value = unicodedata.normalize("NFKD", (text or "").casefold())
    return " ".join(
        re.sub(r"[^a-z0-9 ]+", " ", "".join(ch for ch in value if not unicodedata.combining(ch))).split()
    )


def _matches(query: str | None, value: str) -> bool:
    needle = _normalized(query)
    candidate = _normalized(value)
    return bool(needle and (needle == candidate or needle in candidate or candidate in needle))


# Player-facing: the raw enum ("HAMMERING") reached the screen in playtest.
_TOOL_CAPABILITY_PT = {
    ToolCapability.HAMMERING: "martelar",
    ToolCapability.CUTTING: "cortar",
    ToolCapability.MINING: "minerar",
    ToolCapability.SAWING: "serrar",
    ToolCapability.COOKING: "cozinhar",
    ToolCapability.FISHING: "pescar",
    ToolCapability.SEWING: "costurar",
    ToolCapability.LOCKPICKING: "abrir fechaduras",
}
_ARTICLES = {"o", "a", "os", "as", "um", "uma", "meu", "minha", "esse", "essa", "este", "esta"}


def _head_matches(query: str | None, value: str) -> bool:
    """Same head noun: "martelo de volta" (from "vendo o martelo de volta")
    is the "Martelo de Trabalho" when nothing matches more closely."""
    words = [word for word in _normalized(query).split() if word not in _ARTICLES]
    candidate = _normalized(value).split()
    return bool(words and candidate and words[0] == candidate[0])


def _closest(query: str | None, values: list, name) -> list:
    exact = [value for value in values if _matches(query, name(value))]
    return exact or [value for value in values if _head_matches(query, name(value))]


def _operator_available(db: Session, shop: Shop) -> bool:
    if shop.operator_type == CombatActorType.NPC.value:
        npc = db.get(NPC, shop.operator_id)
        return bool(
            npc
            and npc.alive
            and not npc.incapacitated
            and effective_npc_location_id(npc) == shop.location_id
        )
    return True


def _business_operator_available(db: Session, business: Business, location_id: str | None) -> bool:
    if business.operator_type == CombatActorType.NPC.value:
        npc = db.get(NPC, business.operator_id)
        return bool(
            npc
            and npc.alive
            and not npc.incapacitated
            and effective_npc_location_id(npc) == location_id
        )
    return business.operator_id is not None


def _nearby_shops(db: Session, character: Character) -> list[Shop]:
    if character.location_id is None:
        return []
    return db.query(Shop).filter(
        Shop.campaign_id == character.campaign_id,
        Shop.location_id == character.location_id,
        Shop.status == ShopStatus.OPEN.value,
    ).order_by(Shop.name, Shop.id).all()


def _application(db: Session, job_id: str, character_id: str) -> JobApplication | None:
    return db.query(JobApplication).filter(
        JobApplication.job_id == job_id,
        JobApplication.applicant_type == CombatActorType.CHARACTER.value,
        JobApplication.applicant_id == character_id,
        JobApplication.status.in_((JobApplicationStatus.PENDING.value, JobApplicationStatus.ACTIVE.value)),
    ).order_by(JobApplication.applied_world_minute.desc()).first()


def _job_employer_available(db: Session, job: Job) -> bool:
    if job.employer_type == "BUSINESS":
        business = db.get(Business, job.employer_id)
        return bool(business and _business_operator_available(db, business, job.location_id))
    if job.employer_type == "NPC":
        npc = db.get(NPC, job.employer_id)
        return bool(npc and effective_npc_location_id(npc) == job.location_id)
    return True


def _employer_name(db: Session, job: Job) -> str:
    if job.employer_type == "BUSINESS":
        business = db.get(Business, job.employer_id)
        return business.name if business else "Estabelecimento encerrado"
    if job.employer_type == "NPC":
        npc = db.get(NPC, job.employer_id)
        return npc.name if npc else "Empregador desconhecido"
    return "Organização"


def _recipe_at_location(recipe: EconomyRecipe, location: Location | None) -> bool:
    return bool(location and location.type in recipe.location_types)


def _inventory_quantities(db: Session, character_id: str) -> dict[str, int]:
    rows = db.query(ItemInstance, ItemDefinition).join(ItemDefinition).filter(
        ItemInstance.location_type == ItemLocationType.CHARACTER.value,
        ItemInstance.location_ref == character_id,
    ).all()
    totals: dict[str, int] = {}
    for instance, definition in rows:
        totals[definition.name] = totals.get(definition.name, 0) + instance.quantity
    return totals


def _tool_for_recipe(db: Session, character: Character, recipe: EconomyRecipe) -> str | None:
    if recipe.required_tool is None:
        return None
    candidates = db.query(ItemInstance).join(ItemToolProfile, ItemToolProfile.item_id == ItemInstance.definition_id).filter(
        ItemInstance.campaign_id == character.campaign_id,
        ItemInstance.location_ref == character.id,
        ItemInstance.location_type.in_((ItemLocationType.CHARACTER.value, ItemLocationType.CHARACTER_EQUIPPED.value)),
    ).all()
    for instance in candidates:
        try:
            validate_character_tool_use(
                db, character.id, instance.id, required_capability=recipe.required_tool
            )
            return instance.id
        except ToolError:
            continue
    return None


def build_economy_view(db: Session, character: Character) -> dict:
    """Character-scoped view: only the current place, carried money/items and jobs."""
    location = db.get(Location, character.location_id) if character.location_id else None
    inventory = _inventory_quantities(db, character.id)
    shops = []
    for shop in _nearby_shops(db, character):
        listings = []
        for listing in db.query(ShopListing).filter(ShopListing.shop_id == shop.id).order_by(ShopListing.id).all():
            item = db.get(ItemInstance, listing.item_instance_id)
            if item is None:
                continue
            price = listing.asking_price_bronze
            if price is None:
                price = resolve_local_market_price(db, item, shop.location_id)
            listings.append({
                "listing_id": listing.id,
                "name": item.definition.name,
                "type": item.definition.type,
                "quantity": item.quantity,
                "unit_price_bronze": price,
            })
        accepted = set(json.loads(shop.accepted_item_types_json))
        sellable = []
        held = db.query(ItemInstance, ItemDefinition).join(ItemDefinition).filter(
            ItemInstance.location_type == ItemLocationType.CHARACTER.value,
            ItemInstance.location_ref == character.id,
        ).order_by(ItemDefinition.name, ItemInstance.id).all()
        for item, definition in held:
            if accepted and definition.type not in accepted:
                continue
            sellable.append({
                "item_instance_id": item.id,
                "name": definition.name,
                "quantity": item.quantity,
                "price_bronze": resolve_local_market_price(db, item, shop.location_id) * item.quantity,
            })
        shops.append({
            "shop_id": shop.id,
            "name": shop.name,
            "operator_available": _operator_available(db, shop),
            "listings": listings,
            "sellable_items": sellable,
        })

    jobs = []
    if character.location_id:
        nearby_jobs = db.query(Job).filter(
            Job.campaign_id == character.campaign_id,
            Job.location_id == character.location_id,
            Job.status.in_((JobStatus.OPEN.value, JobStatus.FILLED.value)),
        ).order_by(Job.title, Job.id).all()
        for job in nearby_jobs:
            application = _application(db, job.id, character.id)
            if job.status == JobStatus.FILLED.value and application is None:
                continue
            jobs.append({
                "job_id": job.id,
                "title": job.title,
                "description": job.description,
                "employer_name": _employer_name(db, job),
                "wage_bronze": job.wage_bronze,
                "payment_frequency": job.payment_frequency,
                "work_minutes": job.work_minutes,
                "schedule": (
                    "a qualquer hora" if job_hours_text(job) is None
                    else job_hours_text(job)
                    if player_knows_job_schedule(db, character.campaign_id, character.id, job)
                    else "desconhecido"
                ),
                "application_status": application.status if application else None,
                "employer_available": _job_employer_available(db, job),
            })

    recipes = []
    for recipe in RECIPES:
        if not _recipe_at_location(recipe, location):
            continue
        missing = [
            f"{quantity}× {name}"
            for name, quantity in recipe.inputs
            if inventory.get(name, 0) < quantity
        ]
        tool_available = recipe.required_tool is None or _tool_for_recipe(db, character, recipe) is not None
        recipes.append({
            "key": recipe.key,
            "name": recipe.name,
            "description": recipe.description,
            "inputs": [{"name": name, "quantity": quantity} for name, quantity in recipe.inputs],
            "outputs": [{"name": name, "quantity": quantity} for name, quantity in recipe.outputs],
            "minutes": recipe.minutes,
            "required_tool": recipe.required_tool.value if recipe.required_tool else None,
            "can_produce": not missing and tool_available,
            "missing": missing + ([] if tool_available else [f"ferramenta: {recipe.required_tool.value}"]),
        })

    return {
        "balance_bronze": total_carried_by_owner(db, CombatActorType.CHARACTER, character.id),
        "location_name": location.name if location else None,
        "shops": shops,
        "jobs": jobs,
        "recipes": recipes,
    }


def _select_shop(db: Session, character: Character, hint: str | None) -> Shop:
    nearby = _nearby_shops(db, character)
    shops = [shop for shop in nearby if hint is None or _matches(hint, shop.name)]
    # "vendo o martelo para você" / "para a ferreira": a hint that names no
    # shop, said where only one shop stands, still means that shop.
    if not shops and len(nearby) == 1:
        shops = nearby
    if len(shops) != 1:
        if not shops:
            raise ShopError("Não há uma loja correspondente aberta neste local.")
        raise ShopError("Há mais de uma loja possível; diga em qual deseja negociar.")
    if not _operator_available(db, shops[0]):
        raise ShopError(f"O responsável por '{shops[0].name}' não está disponível aqui agora.")
    return shops[0]


def _buy(db: Session, character: Character, target: str | None, shop_hint: str | None) -> EconomyActionResult:
    # "uma ração de viagem e um odre de água": playtest charged only the
    # water while the narration announced both. Each item is its own
    # purchase; one that fails is reported, the others still go through.
    parts = [part for part in re.split(r"\s*,\s*|\s+e\s+", target or "") if part.strip()]
    if len(parts) > 1:
        summaries, minutes, changed = [], 0, False
        balance_before = total_carried_by_owner(db, CombatActorType.CHARACTER, character.id)
        for part in parts:
            try:
                result = _buy(db, character, part, shop_hint)
            except ShopError as exc:
                summaries.append(f"Não compra {part.strip()}: {exc}")
                continue
            summaries.append(result.summary)
            minutes, changed = minutes + result.minutes, True
        if not changed:
            raise ShopError(" ".join(summaries))
        # Stated outright: the narrator summed 4 + 2 as "sete" in playtest.
        spent = balance_before - total_carried_by_owner(db, CombatActorType.CHARACTER, character.id)
        summaries.append(f"Total pago, já entregue: {spent} Bronze.")
        return EconomyActionResult(" ".join(summaries), minutes, True)
    shop = _select_shop(db, character, shop_hint)
    offered = []
    for listing in db.query(ShopListing).filter(ShopListing.shop_id == shop.id).order_by(ShopListing.id).all():
        item = db.get(ItemInstance, listing.item_instance_id)
        if item:
            offered.append((listing, item.definition.name))
    listings = _closest(target, offered, lambda pair: pair[1])
    if not listings:
        raise ShopError("Esse item não está à venda nesta loja.")
    listing, item_name = listings[0]
    price = buy_from_shop(
        db, shop, listing, buyer_type=CombatActorType.CHARACTER, buyer_id=character.id
    )
    return EconomyActionResult(
        f"{character.name} compra 1× {item_name} em '{shop.name}' por {price} Bronze.", 2, True
    )


def _sell(db: Session, character: Character, target: str | None, shop_hint: str | None) -> EconomyActionResult:
    shop = _select_shop(db, character, shop_hint)
    items = db.query(ItemInstance).join(ItemDefinition).filter(
        ItemInstance.location_type == ItemLocationType.CHARACTER.value,
        ItemInstance.location_ref == character.id,
    ).order_by(ItemInstance.id).all()
    matches = _closest(target, items, lambda item: item.definition.name)
    if not matches:
        raise ShopError("Você não carrega um item correspondente disponível para venda.")
    item = matches[0]
    quantity = item.quantity
    item_name = item.definition.name
    price = sell_to_shop(
        db, shop, item, seller_type=CombatActorType.CHARACTER, seller_id=character.id
    )
    return EconomyActionResult(
        f"{character.name} vende {quantity}× {item_name} para '{shop.name}' por {price} Bronze.", 2, True
    )


def _select_job(db: Session, character: Character, target: str | None, *, active_only: bool) -> tuple[Job, JobApplication | None]:
    jobs = db.query(Job).filter(
        Job.campaign_id == character.campaign_id,
        Job.location_id == character.location_id,
    ).order_by(Job.id).all()
    eligible: list[tuple[Job, JobApplication | None]] = []
    for job in jobs:
        application = _application(db, job.id, character.id)
        if active_only and (application is None or application.status != JobApplicationStatus.ACTIVE.value):
            continue
        eligible.append((job, application))
    candidates = [(job, application) for job, application in eligible if _matches(target, job.title)]
    # "Aceito a vaga" / "quero o trabalho" standing in the only workplace
    # with one opening names no title — but there is nothing to choose.
    if not candidates and len(eligible) == 1:
        candidates = eligible
    if len(candidates) != 1:
        if not candidates:
            raise JobError("Nenhum trabalho correspondente está disponível neste local.")
        raise JobError("Há mais de um trabalho possível; diga o título completo.")
    return candidates[0]


def _apply_for_job(db: Session, character: Character, target: str | None) -> EconomyActionResult:
    job, existing = _select_job(db, character, target, active_only=False)
    if existing and existing.status == JobApplicationStatus.ACTIVE.value:
        return EconomyActionResult(f"{character.name} já trabalha como '{job.title}'.", 0, False)
    if not _job_employer_available(db, job):
        raise JobError("O empregador não está presente para receber uma candidatura agora.")
    application = existing or apply_to_job(db, job, CombatActorType.CHARACTER, character.id)
    resolve_application(db, application, hired=True, reason="Vaga aberta e candidato presente no estabelecimento.")
    summary = f"{character.name} é contratado para o trabalho '{job.title}' em '{_employer_name(db, job)}'."
    hours = job_hours_text(job)
    if hours:
        # Whoever hires states the hours: the new hire knows them now.
        teach_schedule(db, character.campaign_id, character.id, job_schedule_fact_key(job), "contratação")
        now = get_world_time(db, character.campaign_id).total_minutes()
        refusal = shift_refusal(job, now)
        summary += f" Turnos {hours}; " + (
            "um turno pode começar agora mesmo." if refusal is None
            else f"o próximo turno começa às {job.shift_start_hour}h."
        )
    return EconomyActionResult(summary, 10, True)


def _work(db: Session, character: Character, target: str | None) -> EconomyActionResult:
    job, application = _select_job(db, character, target, active_only=True)
    refusal = shift_refusal(job, get_world_time(db, character.campaign_id).total_minutes())
    if refusal is not None:
        raise JobError(refusal)
    if not _job_employer_available(db, job):
        raise JobError("O estabelecimento não pode supervisionar nem pagar um turno agora.")
    amount = pay_wage(db, job, application, reason=f"Turno concluído: {job.title}.")
    xp = 0.0
    if job.profession_key and job.profession_name and job.profession_xp > 0:
        progress = award_work_xp(
            db,
            character.campaign_id,
            character,
            profession_key=job.profession_key,
            profession_name=job.profession_name,
            activity_key=f"job:{job.id}",
            base_xp=job.profession_xp,
            task_complexity_level=0,
        )
        xp = progress.profession_xp_before_affinity
    suffix = f" e desenvolve {job.profession_name} (+{xp:g} XP base)" if xp > 0 else ""
    return EconomyActionResult(
        f"{character.name} conclui um turno como '{job.title}', recebe {amount} Bronze{suffix}.",
        job.work_minutes,
        True,
    )


def _leave_job(db: Session, character: Character, target: str | None) -> EconomyActionResult:
    job, application = _select_job(db, character, target, active_only=True)
    end_employment(db, application, reason="O trabalhador encerrou voluntariamente o vínculo.")
    return EconomyActionResult(
        f"{character.name} encerra seu trabalho como '{job.title}'.", 5, True
    )


def _produce(db: Session, character: Character, target: str | None) -> EconomyActionResult:
    location = db.get(Location, character.location_id) if character.location_id else None
    matches = [recipe for recipe in RECIPES if _recipe_at_location(recipe, location) and (_matches(target, recipe.name) or _matches(target, recipe.key))]
    if len(matches) != 1:
        if not matches:
            raise ProductionError("Nenhuma receita correspondente pode ser produzida neste local.")
        raise ProductionError("Há mais de uma produção possível; diga o nome completo.")
    recipe = matches[0]
    tool_id = _tool_for_recipe(db, character, recipe)
    if recipe.required_tool is not None and tool_id is None:
        raise ProductionError(
            f"A produção exige uma ferramenta para {_TOOL_CAPABILITY_PT.get(recipe.required_tool, 'o trabalho')}."
        )
    produced = produce_goods(
        db,
        character.campaign_id,
        character.id,
        inputs=list(recipe.inputs),
        outputs=list(recipe.outputs),
    )
    progress = award_crafting_xp(
        db,
        character.campaign_id,
        character,
        profession_key=recipe.profession_key,
        profession_name=recipe.profession_name,
        activity_key=f"recipe:{recipe.key}",
        base_xp=recipe.profession_xp,
        task_complexity_level=0,
        tool_instance_id=tool_id,
        required_tool_capability=recipe.required_tool,
    )
    output_text = ", ".join(f"{instance.quantity}× {instance.definition.name}" for instance in produced)
    return EconomyActionResult(
        f"{character.name} conclui '{recipe.name}' e produz {output_text} (+{progress.profession_xp_before_affinity:g} XP base de {recipe.profession_name}).",
        recipe.minutes,
        True,
    )


def resolve_economy_intent(
    db: Session,
    character: Character,
    intent_type: ActionIntentType,
    target: str | None,
    secondary_target: str | None,
) -> EconomyActionResult:
    try:
        if intent_type == ActionIntentType.BUY:
            return _buy(db, character, target, secondary_target)
        if intent_type == ActionIntentType.SELL:
            return _sell(db, character, target, secondary_target)
        if intent_type == ActionIntentType.APPLY_JOB:
            return _apply_for_job(db, character, target)
        if intent_type == ActionIntentType.WORK_JOB:
            return _work(db, character, target)
        if intent_type == ActionIntentType.LEAVE_JOB:
            return _leave_job(db, character, target)
        if intent_type == ActionIntentType.PRODUCE:
            return _produce(db, character, target)
    except (ShopError, JobError, WageError, ProductionError, ToolError, ValueError) as exc:
        return EconomyActionResult(f"A ação econômica não pôde ser concluída: {exc}", 0, False)
    return EconomyActionResult("Nenhuma ação econômica reconhecida.", 0, False)
