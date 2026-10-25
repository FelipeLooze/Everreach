"""Favours the villagers ask of the player — starting village, part 4
(2026-10-24).

Each request is born from the worry of the resident who asks it (their
profile's worry is set to it), is known only to them, and is learned only by
talking to them: never on a board. Saying yes to them ("pode deixar", "eu
ajudo") accepts it. On completion they pay in bronze from their own purse
(money is finite), and trust them enough to share their secret.

Objectives only use triggers the engine fires from real state: talking to
someone, reaching a place, picking an item up, handing it to someone and
reading the notice board.
"""

import json
import random
import re

from sqlalchemy.orm import Session

from app.core.enums import (
    CombatActorType,
    ItemInstanceMode,
    ItemLocationType,
    ItemType,
    KnowerType,
    KnowledgeCertainty,
    ObjectiveTriggerType,
    ObjectiveType,
    QuestParticipationType,
    QuestSource,
    QuestStatus,
)
from app.db.models.knowledge import KnowledgeFact
from app.db.models.location import Location
from app.db.models.npc import NPC
from app.db.models.quest import (
    CharacterQuest,
    CharacterQuestObjective,
    DailyRequestGeneration,
    Quest,
    QuestObjective,
)
from app.game.creatures import population as creature_population
from app.game.creatures.species import all_species
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.items.service import create_item_definition, create_item_instance, move_item_instance
from app.game.npcs.service import teach_fact
from app.game.quests.service import create_quest, quest_existence_fact_key

TRUST_ON_COMPLETION = 20
DAY = 24 * 60
MIN_OPEN_REQUESTS = 6
MAX_OPEN_REQUESTS = 8

# Steps: ("talk", role prefix) | ("reach", place) | ("pick", item key) |
# ("give", item key, role prefix) | ("read_board",). Places: "forest",
# "river", "clearing". {giver}, {other} and {place} are filled in.
_REQUESTS = (
    {
        "key": "check_hunter_traps",
        "giver": "caçador", "title": "As armadilhas do bosque",
        "worry": "as armadilhas no bosque, que ninguém conferiu desde a chegada de vocês",
        "description": "{giver} quer saber se as armadilhas no {place} ainda estão de pé. "
                       "Vá até lá e volte para contar o que viu.",
        "steps": (("reach", "forest"), ("talk", "caçador")),
        "objectives": ("Vá até o {place} e confira as armadilhas.", "Conte a {giver} o que viu."),
        "bronze": 8, "xp": 10,
    },
    {
        "key": "fever_herbs",
        "giver": "herbalista", "title": "Ervas da beira do riacho",
        "worry": "as ervas para a febre, que estão acabando",
        "description": "{giver} precisa de um ramo de erva-de-febre que cresce na beira do {place}.",
        "steps": (("pick", "erva_de_febre"), ("give", "erva_de_febre", "herbalista")),
        "objectives": ("Colha um ramo de erva-de-febre na beira do {place}.", "Entregue a erva a {giver}."),
        "bronze": 6, "xp": 10,
        "item": ("erva_de_febre", "Ramo de erva-de-febre", "river",
                 "Um ramo de folhas estreitas e cheiro amargo, usado contra a febre."),
    },
    {
        "key": "deliver_woodcutter_axe",
        "giver": "ferreir", "title": "A encomenda do lenhador",
        "worry": "a encomenda do lenhador, pronta há dias, sem ninguém para levar",
        "description": "{giver} terminou um machado para {other} e precisa que alguém o leve.",
        "steps": (("pick", "machado_encomendado"), ("give", "machado_encomendado", "lenhador")),
        "objectives": ("Pegue o machado embrulhado na ferraria.", "Entregue o machado a {other}."),
        "bronze": 5, "xp": 10, "other": "lenhador",
        "item": ("machado_encomendado", "Machado embrulhado em pano", "blacksmith",
                 "Um machado recém-forjado, enrolado num pano grosso e amarrado com barbante."),
    },
    {
        "key": "find_missing_cat",
        "giver": "velh", "title": "O gato fujão",
        "worry": "o gato, que vive fugindo para a clareira e sumiu de novo",
        "description": "O gato de {giver} sumiu outra vez; ele costuma se esconder na {place}.",
        "steps": (("reach", "clearing"), ("talk", "velh")),
        "objectives": ("Procure o gato na {place}.", "Avise {giver} de que o gato está bem."),
        "bronze": 4, "xp": 8,
    },
    {
        "key": "peace_message",
        "giver": "lenhador", "title": "Um recado para a rival",
        "worry": "a briga com quem arma armadilhas no bosque, que já foi longe demais",
        "description": "{giver} quer fazer as pazes com {other}, mas não tem coragem de ir falar.",
        "steps": (("talk", "caçador"), ("talk", "lenhador")),
        "objectives": ("Leve o recado de paz a {other}.", "Conte a {giver} como foi a conversa."),
        "bronze": 3, "xp": 8, "other": "caçador",
    },
    {
        "key": "inn_debt_message",
        "giver": "beberr", "title": "A conta na estalagem",
        "worry": "a conta atrasada na estalagem",
        "description": "{giver} deve na estalagem e quer que alguém peça mais prazo a {other}.",
        "steps": (("talk", "estalajadeir"), ("talk", "beberr")),
        "objectives": ("Peça mais prazo a {other} em nome de {giver}.", "Conte a {giver} o que ouviu."),
        "bronze": 2, "xp": 6, "other": "estalajadeir",
    },
    {
        "key": "read_notices",
        "giver": ("rapaz curioso", "moça curiosa"), "title": "Notícias do quadro",
        "worry": "o que dizem os avisos do quadro, que não consegue ler direito",
        "description": "{giver} quer saber o que está escrito no quadro de avisos da vila.",
        "steps": (("read_board",), ("talk", ("rapaz curioso", "moça curiosa"))),
        "objectives": ("Leia o quadro de avisos da vila.", "Conte a {giver} o que está escrito."),
        "bronze": 1, "xp": 5,
    },
    {
        "key": "barn_rat_infestation",
        "giver": "lojista", "title": "Ratos no depósito",
        "worry": "os ratos que estão roendo sacos e estragando o estoque do depósito",
        "description": "{giver} precisa que alguém elimine três ratos no depósito de {place} e volte para confirmar o serviço.",
        "steps": (
            ("defeat", "EV-M1-01", 3, "general_store", 5),
            ("harvest", "IT-EVR-CAUDA-DE-RATO", 2),
            ("talk", "lojista"),
        ),
        "objectives": (
            "Derrote 3 ratos de celeiro no depósito de {place}.",
            "Recolha 2 caudas dos ratos abatidos.",
            "Avise {giver} de que o depósito está seguro.",
        ),
        "bronze": 9, "xp": 12,
    },
    {
        "key": "repair_field_fence",
        "giver": "agricultor", "title": "A cerca dos campos",
        "worry": "a cerca quebrada dos campos, antes que os animais alcancem a plantação",
        "description": "{giver} precisa de duas horas de ajuda para reparar a cerca perto de {place}.",
        "steps": (("reach", "clearing"), ("work", "clearing", 2), ("talk", "agricultor")),
        "objectives": ("Vá até {place}.", "Trabalhe por 2 horas reparando a cerca.", "Conte a {giver} que o reparo terminou."),
        "bronze": 7, "xp": 10,
    },
    {
        "key": "hunt_gray_wolf",
        "giver": "caçador", "title": "Um lobo perto das trilhas",
        "worry": "o lobo cinzento visto perto das trilhas usadas pelos moradores",
        "description": "{giver} pede que um lobo cinzento perto de {place} seja abatido antes que se aproxime da vila.",
        "steps": (("defeat", "EV-TRAD-202", 1, "forest"), ("talk", "caçador")),
        "objectives": ("Derrote 1 lobo cinzento perto de {place}.", "Confirme a caça com {giver}."),
        "bronze": 12, "xp": 15,
    },
)


def _by_role(people: list[NPC], prefix) -> NPC | None:
    prefixes = prefix if isinstance(prefix, tuple) else (prefix,)
    return next((npc for npc in people for p in prefixes if npc.role.startswith(p)), None)


def seed(db: Session, campaign_id: str, region_id: str, village: Location,
         places: dict[str, Location], rng: random.Random) -> list[Quest]:
    """Create the first morning's bounded request pool from reusable models."""
    from app.game.time.clock import get_world_time

    return generate_for_village(
        db,
        campaign_id,
        region_id,
        village,
        places,
        world_day=get_world_time(db, campaign_id).total_minutes() // DAY,
        rng=rng,
        target_count=MIN_OPEN_REQUESTS,
    )


def generate_for_village(
    db: Session,
    campaign_id: str,
    region_id: str,
    village: Location,
    places: dict[str, Location],
    *,
    world_day: int,
    rng: random.Random,
    target_count: int | None = None,
    template_keys: tuple[str, ...] | None = None,
) -> list[Quest]:
    """Run one idempotent daily director pass for a concrete village."""
    from app.game.time.clock import get_world_time

    previous = db.query(DailyRequestGeneration).filter_by(
        campaign_id=campaign_id,
        settlement_location_id=village.id,
        world_day=world_day,
    ).one_or_none()
    if previous is not None:
        return []

    people = db.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.location_id == village.id).all()
    open_requests = db.query(Quest).filter(
        Quest.settlement_location_id == village.id,
        Quest.giver_npc_id.is_not(None),
        Quest.status == QuestStatus.AVAILABLE,
    ).all()
    open_givers = {quest.giver_npc_id for quest in open_requests}
    room = max(0, MAX_OPEN_REQUESTS - len(open_requests))
    attempted = target_count if target_count is not None else rng.randint(5, 6)
    if len(open_requests) < MIN_OPEN_REQUESTS:
        attempted = max(attempted, MIN_OPEN_REQUESTS - len(open_requests))
    to_create = min(room, attempted)

    specs = [
        spec for spec in _REQUESTS
        if template_keys is None or spec["key"] in template_keys
    ]
    rng.shuffle(specs)
    quests = []
    for spec in specs:
        if len(quests) >= to_create:
            break
        giver = _by_role(people, spec["giver"])
        other = _by_role(people, spec["other"]) if "other" in spec else None
        if (
            giver is None
            or giver.id in open_givers
            or ("other" in spec and other is None)
        ):
            continue
        place_key = _request_place_key(spec)
        item_spec = spec.get("item")
        place = places.get(place_key) if place_key else None
        if place_key and place is None:
            continue
        fill = {"giver": giver.name, "other": other.name if other else "",
                "place": place.name if place else ""}

        item = None
        if item_spec:
            key, name, _where, description = item_spec
            definition = create_item_definition(
                db, key=key, name=name,
                item_type=ItemType.QUEST, instance_mode=ItemInstanceMode.UNIQUE,
                description=description, base_weight=0.2,
            )
            item = create_item_instance(db, definition)
            move_item_instance(db, item, location_type=ItemLocationType.WORLD_LOCATION, location_ref=place.id)

        quest = create_quest(
            db, region_id, spec["title"], spec["description"].format(**fill),
            source=QuestSource.NPC_REQUEST,
            objectives=tuple(text.format(**fill) for text in spec["objectives"]),
            deadline_world_minute=(
                get_world_time(db, campaign_id).total_minutes()
                + rng.randint(2, 4) * DAY
            ),
            participation_type=QuestParticipationType.CLAIMABLE,
            xp_reward=float(spec["xp"]),
        )
        quest.giver_npc_id = giver.id
        quest.reward_bronze = spec["bronze"]
        quest.request_template_key = spec["key"]
        quest.request_generated_world_day = world_day
        quest.settlement_location_id = village.id
        quest.target_location_id = place.id if place is not None else None
        fact = db.query(KnowledgeFact).filter(KnowledgeFact.fact_key == quest_existence_fact_key(quest.id)).one()
        fact.statement = f'{giver.name} ({giver.role}) tem um pedido, "{quest.name}": {quest.description}'

        objectives = db.query(QuestObjective).filter(QuestObjective.quest_id == quest.id).order_by(QuestObjective.order).all()
        for index, (objective, step) in enumerate(zip(objectives, spec["steps"], strict=True)):
            objective.prerequisite_objective_id = objectives[index - 1].id if index else None
            if step[0] == "talk":
                objective.objective_type = ObjectiveType.SOCIAL_INTERACTION
                objective.trigger_type = ObjectiveTriggerType.TALK_TO_NPC
                objective.trigger_subject_id = _by_role(people, step[1]).id
            elif step[0] == "reach":
                objective.objective_type = ObjectiveType.EXPLORATION
                objective.trigger_type = ObjectiveTriggerType.REACH_LOCATION
                objective.trigger_subject_id = places[step[1]].id
            elif step[0] == "pick":
                objective.objective_type = ObjectiveType.RETRIEVAL
                objective.trigger_type = ObjectiveTriggerType.RETRIEVE_ITEM
                objective.trigger_subject_id = item.id
            elif step[0] == "give":
                objective.objective_type = ObjectiveType.DELIVERY
                objective.trigger_type = ObjectiveTriggerType.DELIVER_ITEM
                objective.trigger_subject_id = f"{item.id}:{_by_role(people, step[2]).id}"
            elif step[0] == "defeat":
                objective.objective_type = ObjectiveType.COMBAT
                objective.trigger_type = ObjectiveTriggerType.DEFEAT_TARGET
                objective.trigger_subject_id = f"species:{step[1]}"
                objective.required_count = step[2]
                _ensure_request_creatures(
                    db,
                    campaign_id,
                    places[step[3]],
                    step[1],
                    step[4] if len(step) > 4 else step[2],
                    rng,
                )
            elif step[0] == "harvest":
                from app.game.creatures.loot_catalog import bestiary_item_key

                objective.objective_type = ObjectiveType.RETRIEVAL
                objective.trigger_type = ObjectiveTriggerType.RETRIEVE_ITEM
                objective.trigger_subject_id = f"definition:{bestiary_item_key(step[1])}"
                objective.required_count = step[2]
            elif step[0] == "work":
                objective.objective_type = ObjectiveType.WORLD_STATE_CHANGE
                objective.trigger_type = ObjectiveTriggerType.WORK_AT_LOCATION
                objective.trigger_subject_id = places[step[1]].id
                objective.required_count = step[2]
            else:
                objective.objective_type = ObjectiveType.OBSERVATION
                objective.trigger_type = ObjectiveTriggerType.READ_NOTICE_BOARD
                objective.trigger_subject_id = None  # any board read in the village

        teach_fact(db, campaign_id, quest_existence_fact_key(quest.id), KnowerType.NPC, giver.id,
                   source="pedido próprio", certainty=KnowledgeCertainty.CONFIRMED)
        profile = json.loads(giver.profile_json or "{}")
        profile["worry"] = spec["worry"]
        giver.profile_json = json.dumps(profile, ensure_ascii=False)
        purse = get_or_create_holding(db, campaign_id, CombatActorType.NPC, giver.id)
        if purse.amount_bronze < spec["bronze"]:
            deposit(
                db,
                purse,
                spec["bronze"] + rng.randint(3, 15) - purse.amount_bronze,
                reason="Economias de um morador da vila",
            )
        quests.append(quest)
        open_givers.add(giver.id)
    db.add(DailyRequestGeneration(
        campaign_id=campaign_id,
        settlement_location_id=village.id,
        world_day=world_day,
        attempted_count=attempted,
        created_count=len(quests),
    ))
    db.flush()
    return quests


def _request_place_key(spec: dict) -> str | None:
    for step in spec["steps"]:
        if step[0] in ("reach", "work"):
            return step[1]
        if step[0] == "defeat":
            return step[3]
    item_spec = spec.get("item")
    return item_spec[2] if item_spec else None


def _ensure_request_creatures(
    db: Session,
    campaign_id: str,
    place: Location,
    species_key: str,
    count: int,
    rng: random.Random,
) -> None:
    from app.core.enums import NPCActivity
    from app.game.time.clock import get_world_time

    species = all_species()[species_key]
    living = db.query(NPC).filter(
        NPC.campaign_id == campaign_id,
        NPC.location_id == place.id,
        NPC.creature_species == species_key,
        NPC.alive.is_(True),
    ).count()
    for _ in range(max(0, count - living)):
        creature = creature_population._spawn(
            db,
            campaign_id,
            place,
            species,
            "proxima",
            rng,
            get_world_time(db, campaign_id).hour,
        )
        # An explicit infestation is present in the building regardless of
        # the wild species' ordinary sleep cycle.
        if species_key == "EV-M1-01":
            creature.activity = NPCActivity.AVAILABLE.value


def run_daily_director(db: Session, campaign_id: str, world_day: int) -> list[Quest]:
    """Generate bounded resident requests for every populated village."""
    villages = (
        db.query(Location)
        .join(NPC, NPC.location_id == Location.id)
        .filter(
            NPC.campaign_id == campaign_id,
            NPC.routine_json != "[]",
            NPC.creature_species.is_(None),
        )
        .distinct()
        .all()
    )
    created: list[Quest] = []
    for village in villages:
        places = {
            child.type: child
            for child in db.query(Location).filter(
                Location.parent_location_id == village.id
            )
        }
        if "shop" in places:
            places["general_store"] = places["shop"]
        for resident in db.query(NPC).filter(
            NPC.campaign_id == campaign_id,
            NPC.location_id == village.id,
            NPC.workplace_location_id.is_not(None),
        ):
            workplace = db.get(Location, resident.workplace_location_id)
            if workplace is not None:
                places.setdefault(workplace.type, workplace)
        clearing = db.query(Location).filter(
            Location.region_id == village.region_id,
            Location.type == "clearing",
        ).first()
        if clearing is not None:
            places["clearing"] = clearing
        rng = random.Random(f"daily-requests:{campaign_id}:{village.id}:{world_day}")
        created.extend(generate_for_village(
            db,
            campaign_id,
            village.region_id,
            village,
            places,
            world_day=world_day,
            rng=rng,
        ))
    return created


def close_request_worry(db: Session, quest: Quest, *, expired: bool = False) -> None:
    giver = db.get(NPC, quest.giver_npc_id) if quest.giver_npc_id else None
    if giver is None:
        return
    profile = json.loads(giver.profile_json or "{}")
    profile["worry"] = (
        "o pedido que terminou sem ser atendido a tempo"
        if expired else "nenhuma preocupação urgente no momento"
    )
    giver.profile_json = json.dumps(profile, ensure_ascii=False)


def resolve_request_work(db: Session, character, text: str) -> tuple[str, int] | None:
    """Apply real hours to an active local-work objective at this location."""
    plain = text.casefold()
    if not re.search(r"\b(?:trabalh|repar|consert)", plain):
        return None
    objectives = (
        db.query(QuestObjective)
        .join(Quest, Quest.id == QuestObjective.quest_id)
        .join(CharacterQuest, CharacterQuest.quest_id == Quest.id)
        .filter(
            CharacterQuest.character_id == character.id,
            CharacterQuest.status == QuestStatus.ACTIVE,
            QuestObjective.trigger_type == ObjectiveTriggerType.WORK_AT_LOCATION,
            QuestObjective.trigger_subject_id == character.location_id,
        )
        .order_by(QuestObjective.order)
        .all()
    )
    if not objectives:
        return None
    objective = objectives[0]
    before = db.query(CharacterQuestObjective).filter_by(
        character_id=character.id,
        objective_id=objective.id,
    ).one_or_none()
    before_count = before.progress_count if before else 0
    match = re.search(r"\b(\d{1,2})\s*horas?\b", plain)
    hours = min(8, max(1, int(match.group(1)))) if match else 1

    from app.game.quests.service import evaluate_objective_trigger

    evaluate_objective_trigger(
        db,
        character.campaign_id,
        character.id,
        ObjectiveTriggerType.WORK_AT_LOCATION,
        subject_id=character.location_id,
        amount=hours,
    )
    after = db.query(CharacterQuestObjective).filter_by(
        character_id=character.id,
        objective_id=objective.id,
    ).one_or_none()
    if after is None or after.progress_count == before_count:
        return "O trabalho ainda depende da etapa anterior do pedido.", 0
    applied = after.progress_count - before_count
    state = " O serviço foi concluído." if after.completed else ""
    return (
        f"{character.name} trabalha por {applied} hora(s) na tarefa combinada."
        f" Progresso: {after.progress_count}/{objective.required_count}.{state}",
        applied * 60,
    )


def open_request_of(db: Session, npc: NPC) -> Quest | None:
    """This NPC's own request, while nobody has taken it."""
    return (
        db.query(Quest)
        .filter(Quest.giver_npc_id == npc.id, Quest.status == QuestStatus.AVAILABLE)
        .first()
    )


def reveal_the_way(db: Session, character, quest: Quest) -> list[Location]:
    """On accepting, the villager explains how to get there: every place the
    request sends the player to becomes known, with the trails leading to it
    from where they stand. Playtest-shaped: "vá conferir as armadilhas no
    bosque" was impossible while the forest's trail was still unknown."""
    from collections import deque

    from app.core.enums import DiscoveryStatus
    from app.db.models.item import ItemInstance
    from app.db.models.location import LocationConnection
    from app.game.discovery.service import discover_connection, set_location_discovery

    targets = [quest.target_location_id] if quest.target_location_id else []
    for objective in db.query(QuestObjective).filter(QuestObjective.quest_id == quest.id):
        if objective.trigger_type == ObjectiveTriggerType.REACH_LOCATION.value:
            targets.append(objective.trigger_subject_id)
        elif objective.trigger_type == ObjectiveTriggerType.RETRIEVE_ITEM.value:
            item = db.get(ItemInstance, objective.trigger_subject_id)
            if item is not None and item.location_type == ItemLocationType.WORLD_LOCATION.value:
                targets.append(item.location_ref)
    revealed = []
    for target in dict.fromkeys(targets):
        # Shortest trail from here, through active connections.
        previous = {character.location_id: None}
        queue = deque([character.location_id])
        while queue and target not in previous:
            here = queue.popleft()
            for connection in db.query(LocationConnection).filter(
                LocationConnection.from_location_id == here, LocationConnection.active.is_(True)
            ):
                if connection.to_location_id not in previous:
                    previous[connection.to_location_id] = connection
                    queue.append(connection.to_location_id)
        if target not in previous or target == character.location_id:
            continue
        step = target
        while previous[step] is not None:
            connection = previous[step]
            discover_connection(db, character.id, connection.id)
            set_location_discovery(db, character.id, step, DiscoveryStatus.DISCOVERED)
            step = connection.from_location_id
        revealed.append(db.get(Location, target))
    return revealed
