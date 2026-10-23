from pydantic import BaseModel


class EconomyListingResponse(BaseModel):
    listing_id: str
    name: str
    type: str
    quantity: int
    unit_price_bronze: int


class EconomySellableItemResponse(BaseModel):
    item_instance_id: str
    name: str
    quantity: int
    price_bronze: int


class EconomyShopResponse(BaseModel):
    shop_id: str
    name: str
    operator_available: bool
    listings: list[EconomyListingResponse]
    sellable_items: list[EconomySellableItemResponse]


class EconomyJobResponse(BaseModel):
    job_id: str
    title: str
    description: str
    employer_name: str
    wage_bronze: int
    payment_frequency: str
    work_minutes: int
    # "das 8h às 18h", "a qualquer hora", or "desconhecido" until learned.
    schedule: str
    application_status: str | None
    employer_available: bool


class EconomyRecipeItemResponse(BaseModel):
    name: str
    quantity: int


class EconomyRecipeResponse(BaseModel):
    key: str
    name: str
    description: str
    inputs: list[EconomyRecipeItemResponse]
    outputs: list[EconomyRecipeItemResponse]
    minutes: int
    required_tool: str | None
    can_produce: bool
    missing: list[str]


class EconomyStateResponse(BaseModel):
    balance_bronze: int
    location_name: str | None
    shops: list[EconomyShopResponse]
    jobs: list[EconomyJobResponse]
    recipes: list[EconomyRecipeResponse]
