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
from app.db.models.quest import Quest, QuestObjective
from app.game.economy.wallet import deposit, get_or_create_holding
from app.game.items.service import create_item_definition, create_item_instance, move_item_instance
from app.game.npcs.service import teach_fact
from app.game.quests.service import create_quest, quest_existence_fact_key

TRUST_ON_COMPLETION = 20

# Steps: ("talk", role prefix) | ("reach", place) | ("pick", item key) |
# ("give", item key, role prefix) | ("read_board",). Places: "forest",
# "river", "clearing". {giver}, {other} and {place} are filled in.
_REQUESTS = (
    {
        "giver": "caçador", "title": "As armadilhas do bosque",
        "worry": "as armadilhas no bosque, que ninguém conferiu desde a chegada de vocês",
        "description": "{giver} quer saber se as armadilhas no {place} ainda estão de pé. "
                       "Vá até lá e volte para contar o que viu.",
        "steps": (("reach", "forest"), ("talk", "caçador")),
        "objectives": ("Vá até o {place} e confira as armadilhas.", "Conte a {giver} o que viu."),
        "bronze": 8, "xp": 10,
    },
    {
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
        "giver": "velh", "title": "O gato fujão",
        "worry": "o gato, que vive fugindo para a clareira e sumiu de novo",
        "description": "O gato de {giver} sumiu outra vez; ele costuma se esconder na {place}.",
        "steps": (("reach", "clearing"), ("talk", "velh")),
        "objectives": ("Procure o gato na {place}.", "Avise {giver} de que o gato está bem."),
        "bronze": 4, "xp": 8,
    },
    {
        "giver": "lenhador", "title": "Um recado para a rival",
        "worry": "a briga com quem arma armadilhas no bosque, que já foi longe demais",
        "description": "{giver} quer fazer as pazes com {other}, mas não tem coragem de ir falar.",
        "steps": (("talk", "caçador"), ("talk", "lenhador")),
        "objectives": ("Leve o recado de paz a {other}.", "Conte a {giver} como foi a conversa."),
        "bronze": 3, "xp": 8, "other": "caçador",
    },
    {
        "giver": "beberr", "title": "A conta na estalagem",
        "worry": "a conta atrasada na estalagem",
        "description": "{giver} deve na estalagem e quer que alguém peça mais prazo a {other}.",
        "steps": (("talk", "estalajadeir"), ("talk", "beberr")),
        "objectives": ("Peça mais prazo a {other} em nome de {giver}.", "Conte a {giver} o que ouviu."),
        "bronze": 2, "xp": 6, "other": "estalajadeir",
    },
    {
        "giver": ("rapaz curioso", "moça curiosa"), "title": "Notícias do quadro",
        "worry": "o que dizem os avisos do quadro, que não consegue ler direito",
        "description": "{giver} quer saber o que está escrito no quadro de avisos da vila.",
        "steps": (("read_board",), ("talk", ("rapaz curioso", "moça curiosa"))),
        "objectives": ("Leia o quadro de avisos da vila.", "Conte a {giver} o que está escrito."),
        "bronze": 1, "xp": 5,
    },
)


def _by_role(people: list[NPC], prefix) -> NPC | None:
    prefixes = prefix if isinstance(prefix, tuple) else (prefix,)
    return next((npc for npc in people for p in prefixes if npc.role.startswith(p)), None)


def seed(db: Session, campaign_id: str, region_id: str, village: Location,
         places: dict[str, Location], rng: random.Random) -> list[Quest]:
    people = db.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.location_id == village.id).all()
    quests = []
    for spec in _REQUESTS:
        giver = _by_role(people, spec["giver"])
        other = _by_role(people, spec["other"]) if "other" in spec else None
        if giver is None or ("other" in spec and other is None):
            continue
        place_keys = [step[1] for step in spec["steps"] if step[0] == "reach"]
        item_spec = spec.get("item")
        place = places.get(place_keys[0] if place_keys else (item_spec[2] if item_spec else ""))
        if (place_keys or item_spec) and place is None:
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
            participation_type=QuestParticipationType.CLAIMABLE,
            xp_reward=float(spec["xp"]),
        )
        quest.giver_npc_id = giver.id
        quest.reward_bronze = spec["bronze"]
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
        deposit(db, purse, spec["bronze"] + rng.randint(3, 15), reason="Economias de um morador da vila")
        quests.append(quest)
    db.flush()
    return quests


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

    targets = []
    for objective in db.query(QuestObjective).filter(QuestObjective.quest_id == quest.id):
        if objective.trigger_type == ObjectiveTriggerType.REACH_LOCATION.value:
            targets.append(objective.trigger_subject_id)
        elif objective.trigger_type == ObjectiveTriggerType.RETRIEVE_ITEM.value:
            item = db.get(ItemInstance, objective.trigger_subject_id)
            if item is not None and item.location_type == ItemLocationType.WORLD_LOCATION.value:
                targets.append(item.location_ref)
    revealed = []
    for target in targets:
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
