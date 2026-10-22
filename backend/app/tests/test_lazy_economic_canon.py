import json
import threading

import pytest

from app.ai import narrator
from app.ai.context_builder import build_context
from app.ai.llm_service import LLMService, LLMServiceError
from app.core.enums import CombatActorType, ItemQuality, NPCActivity
from app.db.models.character import Character
from app.db.models.economic_value import EconomicCanonValue
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.game.economy.economic_canon import (
    EconomicCanonError,
    EconomicClassification,
    EconomicProposalUnavailable,
    current_price,
    get_service_value,
    item_subject,
    materialize_economic_value,
    service_subject,
    validate_proposal,
)
from app.game.economy.pricing import set_item_base_value
from app.game.economy.shops import create_shop, stock_item
from app.game.economy.supply_demand import adjust_supply, get_or_create_supply_level
from app.game.game_state import build_game_state
from app.game import engine
from app.game.npcs import service as npc_service
from app.game.inventory.service import add_item, get_or_create_item
from app.game.world.seed import create_campaign, seed_initial_region


class ProposalLLM(LLMService):
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        assert "propose" in system.lower()
        assert json.loads(prompt)["currency"]["bronze_per_gold"] == 10_000
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


class FailingLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        raise LLMServiceError("timeout")


class PriceOmittingLLM(LLMService):
    def __init__(self):
        self.calls = 0

    def generate(self, system: str, prompt: str) -> str:
        self.calls += 1
        return "O estalajadeiro sorri e espera a decisão de Logan."


def _world(db_session, name="S1.3"):
    campaign = create_campaign(db_session, name)
    region, village = seed_initial_region(db_session, campaign.id)
    character = Character(
        campaign_id=campaign.id,
        name="Logan",
        region_id=region.id,
        location_id=village.id,
    )
    db_session.add(character)
    db_session.flush()
    return campaign, region, village, character


def _inn_scene(db_session, name="S1.3 Inn"):
    campaign, region, _village, character = _world(db_session, name)
    innkeeper = db_session.query(NPC).filter(
        NPC.campaign_id == campaign.id, NPC.role == "estalajadeiro"
    ).one()
    innkeeper.activity = NPCActivity.WORKING.value
    inn = db_session.get(Location, innkeeper.workplace_location_id)
    character.location_id = inn.id
    db_session.flush()
    return campaign, inn, innkeeper, character


def test_existing_persisted_service_value_never_calls_llm(db_session):
    campaign, inn, innkeeper, _character = _inn_scene(db_session)
    subject = service_subject(
        campaign.id, inn.id, "lodging", "Quarto", provider_type="NPC", provider_id=innkeeper.id
    )
    first_llm = ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 8, "rationale": "modest inn"})
    first = materialize_economic_value(db_session, subject, llm_service=first_llm)
    exploding = ProposalLLM("not json")
    second = materialize_economic_value(db_session, subject, llm_service=exploding)
    assert first.base_price_bronze == second.base_price_bronze == 8
    assert second.reused is True
    assert first_llm.calls == 1
    assert exploding.calls == 0


def test_existing_deterministic_item_base_value_never_calls_llm(db_session):
    campaign, _region, village, _character = _world(db_session)
    definition = get_or_create_item(db_session, "Martelo comum", "tool")
    set_item_base_value(db_session, definition, 14)
    llm = ProposalLLM("bad")
    value = materialize_economic_value(
        db_session, item_subject(campaign.id, definition, location_id=village.id), llm_service=llm
    )
    assert value.base_price_bronze == 14
    assert value.provenance.value == "DETERMINISTIC"
    assert llm.calls == 0


def test_missing_mundane_item_is_proposed_validated_persisted_and_reused(db_session):
    campaign, _region, village, _character = _world(db_session)
    definition = get_or_create_item(db_session, "Machado de ferro", "weapon")
    subject = item_subject(campaign.id, definition, location_id=village.id)
    llm = ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 42, "rationale": "ordinary iron tool"})
    result = materialize_economic_value(db_session, subject, llm_service=llm)
    db_session.expire_all()
    replay = materialize_economic_value(db_session, subject, llm_service=llm)
    assert result.base_price_bronze == replay.base_price_bronze == 42
    assert definition.base_value_bronze == 42
    assert llm.calls == 1
    assert db_session.query(EconomicCanonValue).filter_by(canonical_key=subject.canonical_key).count() == 1


@pytest.mark.parametrize("raw", ["not json", "[]", '{"classification":"UNKNOWN"}', '{"classification":"MARKET_PRICE","base_price_bronze":"8"}'])
def test_malformed_proposals_are_rejected(raw, db_session):
    campaign, _region, village, _character = _world(db_session, f"bad-{len(raw)}")
    subject = service_subject(campaign.id, village.id, "labor", "Trabalho")
    with pytest.raises(EconomicCanonError):
        materialize_economic_value(db_session, subject, llm_service=ProposalLLM(raw))
    assert db_session.query(EconomicCanonValue).filter_by(canonical_key=subject.canonical_key).count() == 0


def test_absurd_mundane_gold_price_is_rejected_but_rare_magic_can_be_expensive(db_session):
    campaign, _region, village, _character = _world(db_session)
    mundane = item_subject(campaign.id, get_or_create_item(db_session, "Pão", "food"), location_id=village.id)
    with pytest.raises(EconomicCanonError, match="implausible"):
        validate_proposal('{"classification":"MARKET_PRICE","base_price_bronze":10000}', mundane)
    relic = item_subject(
        campaign.id,
        get_or_create_item(db_session, "Coroa arcana", "misc"),
        location_id=village.id,
        magical=True,
        unique=True,
        rarity="LEGENDARY",
    )
    accepted = validate_proposal('{"classification":"MARKET_PRICE","base_price_bronze":250000}', relic)
    assert accepted.base_price_bronze == 250_000


def test_commodity_value_is_shared_by_definition_not_physical_instance(db_session):
    campaign, _region, village, character = _world(db_session)
    first = add_item(db_session, character.id, "Maçã", 1)
    second = add_item(db_session, character.id, "Maçã", 2)
    assert first.id == second.id  # Phase 10 stack; Canon is still definition-scoped
    subject = item_subject(campaign.id, first, location_id=village.id)
    materialize_economic_value(
        db_session, subject,
        llm_service=ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 2, "rationale": "common fruit"}),
    )
    assert subject.canonical_key == f"item_definition:{first.definition_id}"


def test_item_entering_shop_can_lazily_materialize_generic_value(db_session):
    campaign, _region, village, character = _world(db_session)
    weapon = get_or_create_item(db_session, "Lança simples", "weapon")
    instance = add_item(db_session, character.id, weapon.name)
    shop = create_shop(
        db_session,
        campaign.id,
        "Armas da Praça",
        CombatActorType.CHARACTER,
        character.id,
        location_id=village.id,
    )
    llm = ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 35, "rationale": "simple weapon"})
    listing = stock_item(db_session, shop, instance, llm_service=llm)
    assert listing.asking_price_bronze is None  # current price remains Phase 14-derived
    assert weapon.base_value_bronze == 35
    assert llm.calls == 1


def test_quality_condition_and_local_scarcity_change_current_not_base(db_session):
    campaign, _region, village, character = _world(db_session)
    definition = get_or_create_item(db_session, "Espada usada", "weapon")
    set_item_base_value(db_session, definition, 100)
    item = add_item(db_session, character.id, "Espada usada", quality=ItemQuality.POOR)
    item.durability_current = 40
    item.durability_max = 100
    value = materialize_economic_value(db_session, item_subject(campaign.id, item, location_id=village.id))
    normal = current_price(db_session, value, item_instance=item, location_id=village.id)
    supply = get_or_create_supply_level(db_session, campaign.id, village.id, definition.id)
    adjust_supply(db_session, supply, -80, reason="escassez de aço")
    scarce = current_price(db_session, value, item_instance=item, location_id=village.id)
    assert normal.base_price_bronze == scarce.base_price_bronze == 100
    assert normal.current_price_bronze < 100
    assert scarce.current_price_bronze > normal.current_price_bronze


def test_lodging_meal_and_repair_use_the_same_generic_pipeline(db_session):
    campaign, inn, innkeeper, _character = _inn_scene(db_session)
    llm = ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 8, "rationale": "ordinary service"})
    for key in ("lodging", "meal", "repair"):
        result = materialize_economic_value(
            db_session,
            service_subject(campaign.id, inn.id, key, key, provider_type="NPC", provider_id=innkeeper.id),
            llm_service=llm,
        )
        assert result.base_price_bronze == 8
    assert llm.calls == 3


def test_nonmarket_unique_classification_persists_without_numeric_price(db_session):
    campaign, _region, village, _character = _world(db_session)
    subject = service_subject(campaign.id, village.id, "relic_appraisal", "Relíquia sem mercado")
    value = materialize_economic_value(
        db_session,
        subject,
        llm_service=ProposalLLM({"classification": "UNIQUE_OR_PRICELESS", "base_price_bronze": None, "rationale": "singular relic"}),
    )
    assert value.classification == EconomicClassification.UNIQUE_OR_PRICELESS
    assert current_price(db_session, value) is None


def test_provider_failure_is_safe_and_persists_nothing(db_session):
    campaign, _region, village, _character = _world(db_session)
    subject = service_subject(campaign.id, village.id, "transport", "Transporte")
    with pytest.raises(EconomicProposalUnavailable):
        materialize_economic_value(db_session, subject, llm_service=FailingLLM())
    assert get_service_value(db_session, village.id, "transport") is None


def test_current_price_is_grounded_only_for_present_provider_and_vague_followup(db_session):
    campaign, inn, innkeeper, character = _inn_scene(db_session)
    materialize_economic_value(
        db_session,
        service_subject(campaign.id, inn.id, "lodging", "Quarto", provider_type="NPC", provider_id=innkeeper.id),
        llm_service=ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 8, "rationale": "room"}),
    )
    state = build_game_state(db_session, campaign.id, character.id)
    for question in ("Quanto custa um quarto?", "Quanto é?"):
        context = build_context(db_session, state, player_input=question, active_interlocutor=innkeeper.id)
        assert "BASE: 8 bronze." in context
        assert "CURRENT OFFER: 8 bronze." in context
        assert "SPEAKER KNOWS PRICE: yes." in context


def test_unrelated_npc_does_not_receive_hidden_precise_price(db_session):
    campaign, inn, innkeeper, character = _inn_scene(db_session)
    materialize_economic_value(
        db_session,
        service_subject(campaign.id, inn.id, "lodging", "Quarto", provider_type="NPC", provider_id=innkeeper.id),
        llm_service=ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 8, "rationale": "room"}),
    )
    elder = db_session.query(NPC).filter(NPC.campaign_id == campaign.id, NPC.id != innkeeper.id).first()
    state = build_game_state(db_session, campaign.id, character.id)
    context = build_context(db_session, state, player_input="Quanto custa um quarto?", active_interlocutor=elder.id)
    assert "SPEAKER KNOWS PRICE: yes." not in context


def test_service_modifier_changes_current_offer_without_overwriting_base(db_session):
    campaign, inn, innkeeper, _character = _inn_scene(db_session)
    value = materialize_economic_value(
        db_session,
        service_subject(campaign.id, inn.id, "lodging", "Quarto", provider_type="NPC", provider_id=innkeeper.id),
        llm_service=ProposalLLM({"classification": "MARKET_PRICE", "base_price_bronze": 8, "rationale": "room"}),
    )
    discounted = current_price(db_session, value, service_modifier=0.75)
    persisted = get_service_value(db_session, inn.id, "lodging")
    assert discounted.current_price_bronze == 6
    assert persisted.base_price_bronze == 8


def test_engine_materializes_price_before_same_turn_narration(db_session):
    campaign, inn, innkeeper, character = _inn_scene(db_session, "S1.3 Same Turn")
    npc_service.meet_npc(db_session, campaign.id, character.id, innkeeper.id)

    class UnifiedLLM(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            lowered = system.lower()
            if "propose a missing canonical" in lowered:
                return '{"classification":"MARKET_PRICE","base_price_bronze":8,"rationale":"modest room"}'
            if "intent" in lowered:
                return '{"intent":"TALK","target":null}'
            return f"{innkeeper.name} responde: um quarto custa 8 bronze por noite."

    result = engine.resolve_action(
        db_session,
        UnifiedLLM(),
        campaign.id,
        character.id,
        'Logan pergunta: "Quanto custa um quarto?"',
    )
    persisted = get_service_value(db_session, inn.id, "lodging")
    assert persisted is not None and persisted.base_price_bronze == 8
    assert "8" in result.narrative


def test_concurrent_first_materialization_has_one_canonical_winner(tmp_path):
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.database import enable_sqlite_foreign_keys

    database_path = tmp_path / "economic-race.sqlite3"
    sql_engine = create_engine(
        f"sqlite:///{database_path}", connect_args={"check_same_thread": False, "timeout": 10}
    )
    event.listen(sql_engine, "connect", enable_sqlite_foreign_keys)
    Base.metadata.create_all(sql_engine)
    SessionLocal = sessionmaker(bind=sql_engine, autocommit=False, autoflush=False)
    with SessionLocal() as seed_db:
        campaign = create_campaign(seed_db, "S1.3 Race")
        _region, village = seed_initial_region(seed_db, campaign.id)
        campaign_id, location_id = campaign.id, village.id
        seed_db.commit()

    barrier = threading.Barrier(2)
    outcomes: list[int] = []
    failures: list[Exception] = []

    class RacingLLM(LLMService):
        def __init__(self, amount: int):
            self.amount = amount

        def generate(self, system: str, prompt: str) -> str:
            barrier.wait(timeout=5)
            return json.dumps({
                "classification": "MARKET_PRICE",
                "base_price_bronze": self.amount,
                "rationale": "concurrent proposal",
            })

    def worker(amount: int) -> None:
        try:
            with SessionLocal() as worker_db:
                value = materialize_economic_value(
                    worker_db,
                    service_subject(campaign_id, location_id, "transport", "Transporte"),
                    llm_service=RacingLLM(amount),
                )
                worker_db.commit()
                outcomes.append(value.base_price_bronze)
        except Exception as exc:  # surfaced below with the original exception
            failures.append(exc)

    threads = [threading.Thread(target=worker, args=(amount,)) for amount in (18, 21)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert not failures
    assert all(not thread.is_alive() for thread in threads)
    with SessionLocal() as check_db:
        rows = check_db.query(EconomicCanonValue).filter(
            EconomicCanonValue.canonical_key == f"service:{location_id}:transport"
        ).all()
        assert len(rows) == 1
        assert rows[0].base_price_bronze in {18, 21}
        assert set(outcomes) == {rows[0].base_price_bronze}


def test_direct_price_question_cannot_omit_backend_authorized_offer():
    llm = PriceOmittingLLM()
    context = (
        "CURRENT PLAYER\nName: Logan\n\n"
        "ACTIVE NPC CONTEXT\nName: Colm Corrin\nLocation: Estalagem de Uldor\n\n"
        "DIRECT QUESTION GROUNDING\n"
        "The player is asking the PRICE of a specific local service.\n"
        "ECONOMIC SUBJECT: lodging at Estalagem de Uldor\n"
        "BASE: 8 bronze.\n"
        "CURRENT OFFER: 8 bronze.\n"
        "SPEAKER KNOWS PRICE: yes.\n"
        "Authorized answer: 8 bronze."
    )

    result = narrator.narrate(
        llm,
        "Nenhuma mudança mecânica.",
        context,
        "Quanto custa um quarto?",
        "(nenhuma troca anterior nesta cena)",
    )

    assert "8 bronze" in result.lower()
    assert "Colm Corrin" in result
    assert llm.calls == 3


def test_final_price_guard_survives_a_later_validator_rewrite():
    context = (
        "DIRECT QUESTION GROUNDING\n"
        "CURRENT OFFER: 8 bronze.\n"
        "Authorized answer: 8 bronze."
    )
    result = narrator.enforce_authorized_price_answer(
        "O estalajadeiro sorri, mas não informa o valor.",
        context,
        "Quanto custa um quarto?",
        "Colm Corrin",
    )
    assert result == "— 8 bronze. — responde Colm Corrin."


_FIFTEEN_BRONZE_CONTEXT = (
    "DIRECT QUESTION GROUNDING\n"
    "CURRENT OFFER: 15 bronze.\n"
    "Authorized answer: 15 bronze."
)


def test_price_spelled_out_in_words_counts_as_answered():
    # Bake-off: Nemotron answered "— Quinze bronze." on every attempt and the
    # digits-only check replaced that answer with "— 15 bronze. — responde
    # Lena Sowerby." after three wasted calls, on every model tested.
    for answer in (
        "— Quinze bronze. — A voz sai rouca. — Lâmina de ferro, cabo simples.",
        "— São quinze moedas de bronze — diz ela.",
        "— 15 de bronze, e nem um a menos.",
        "— Quinze peças de bronze.",
    ):
        assert narrator.enforce_authorized_price_answer(
            answer, _FIFTEEN_BRONZE_CONTEXT, "Quanto custa uma faca simples aqui?", "Lena Sowerby"
        ) == answer


def test_a_different_amount_in_words_is_still_rejected():
    for answer in ("— Dezesseis bronze.", "— Cento e quinze bronze.", "— Quinze dias e trinta bronze."):
        assert narrator.enforce_authorized_price_answer(
            answer, _FIFTEEN_BRONZE_CONTEXT, "Quanto custa uma faca simples aqui?", "Lena Sowerby"
        ) == "— 15 bronze. — responde Lena Sowerby."


def test_feminine_and_large_amounts_in_words():
    assert narrator._mentions_bronze_amount("Duas moedas de bronze.", 2)
    assert narrator._mentions_bronze_amount("Duzentas moedas de bronze.", 200)
    assert narrator._mentions_bronze_amount("Mil e duzentos bronzes.", 1200)
    assert narrator._mentions_bronze_amount("1.200 bronze.", 1200)
