"""Who an NPC is, beyond their job: age, temperament, how they talk, what
they make of the transported, what they want, what worries them and one
small secret.

Sorted once per NPC from the pools below (seeded by the NPC's own id, so a
new save gives a new village and the same NPC never changes). The user's
rule (2026-10-24): toward transported people an NPC is at most distrustful
— distrust colours the tone, it never refuses a sale, a job or an answer.
"""

import json
import random

from sqlalchemy.orm import Session

SECRET_TRUST = 20

_TEMPERAMENTS = (
    "caloroso e expansivo, ri fácil",
    "rabugento, mas justo",
    "calmo e paciente, nada parece apressá-lo",
    "nervoso, se preocupa com tudo",
    "irônico, tem sempre um comentário seco",
    "sério e reservado, mede cada palavra",
    "alegre e falador, adora uma novidade",
    "orgulhoso do próprio trabalho, não gosta de ser corrigido",
    "gentil e um pouco tímido",
    "prático e direto, sem paciência para rodeios",
    "melancólico, vive lembrando de tempos melhores",
    "teimoso, raramente muda de ideia",
)

_SPEECH = (
    "fala pouco, em frases curtas",
    "fala demais e emenda um assunto no outro",
    "formal e cuidadoso com as palavras",
    "usa ditados do interior a toda hora",
    "fala alto e gesticula muito",
    "fala baixo, quase em tom de confidência",
    "faz muitas perguntas antes de responder",
    "responde com outra pergunta quando não quer se comprometer",
    "chama todo mundo de 'filho' ou 'filha'",
    "xinga baixinho quando algo dá errado",
)

_HABITS = (
    "esfrega as mãos quando pensa",
    "assobia enquanto trabalha",
    "nunca olha nos olhos por muito tempo",
    "coça a nuca quando fica sem graça",
    "conta moedas mesmo quando não precisa",
    "masca uma folha de hortelã o tempo todo",
    "ajeita a roupa sem parar",
    "bate os dedos em qualquer superfície",
)

# key -> (how it shows in Portuguese, what the narrator does with it)
_STANCES = {
    "WELCOMING": ("acolhedor com os transportados", "Treats them kindly, offers help without being asked."),
    "CURIOUS": ("curioso com os transportados", "Asks about where they came from, fascinated by their clothes and words."),
    "PRAGMATIC": ("prático com os transportados", "Judges them by what they do, like any newcomer."),
    "DISTRUSTFUL": ("desconfiado dos transportados", "Keeps a cool, guarded tone and watches them closely."),
    "OMEN": ("vê os transportados como um sinal", "Treats their arrival as an omen, with respect and a little awe."),
}
_STANCE_WEIGHTS = {"WELCOMING": 2, "CURIOUS": 3, "PRAGMATIC": 3, "DISTRUSTFUL": 2, "OMEN": 1}

_WANTS = (
    "juntar dinheiro para consertar o telhado de casa",
    "ter o próprio pedaço de terra um dia",
    "ser respeitado pelos mais velhos da vila",
    "ver a vila crescer e atrair mais comércio",
    "um inverno tranquilo, sem fome",
    "provar que é melhor no que faz do que todos acham",
    "um dia conhecer a capital",
    "paz e sossego, longe de confusão",
)

_WORRIES = (
    "os lobos que andam rondando os campos à noite",
    "a colheita, que este ano parece fraca",
    "as dívidas que vem acumulando com os comerciantes",
    "a própria saúde, que já não é a mesma",
    "o que a chegada dos transportados vai mudar na vila",
    "os preços, que só sobem",
    "a estrada, que anda perigosa para quem viaja sozinho",
)

_SECRETS = (
    "deve dinheiro a alguém e ninguém sabe",
    "já pensou em ir embora da vila para sempre",
    "esconde algumas moedas enterradas no quintal",
    "não sabe ler, e disfarça",
    "fugiu de outra vila quando era jovem e nunca contou por quê",
    "uma vez ficou com algo que não era seu e nunca devolveu",
    "tem medo do escuro desde criança",
    "escreve cartas para alguém que nunca responde",
)

_AGE_BY_ROLE = {
    "ancião da vila": (64, 82),
    "anciã da vila": (64, 82),
    "mestre da guilda de aventureiros": (38, 62),
    "mestre da guilda de comerciantes": (38, 62),
}
_DEFAULT_AGE = (24, 58)


def generate(rng: random.Random, role: str) -> tuple[int, dict]:
    low, high = _AGE_BY_ROLE.get(role.casefold(), _DEFAULT_AGE)
    stance = rng.choices(list(_STANCE_WEIGHTS), weights=list(_STANCE_WEIGHTS.values()))[0]
    return rng.randint(low, high), {
        "temperament": rng.choice(_TEMPERAMENTS),
        "speech": rng.choice(_SPEECH),
        "habit": rng.choice(_HABITS),
        "stance": stance,
        "want": rng.choice(_WANTS),
        "worry": rng.choice(_WORRIES),
        "secret": rng.choice(_SECRETS),
    }


def ensure(db: Session, npc) -> dict:
    """The NPC's profile, sorted on first use."""
    profile = json.loads(npc.profile_json or "{}")
    if profile and npc.age is not None:
        return profile
    npc.age, profile = generate(random.Random(f"profile:{npc.id}"), npc.role)
    npc.profile_json = json.dumps(profile, ensure_ascii=False)
    db.flush()
    return profile


def context_lines(db: Session, npc, trust: int) -> list[str]:
    """For the NPC the player is talking to."""
    profile = ensure(db, npc)
    stance_pt, stance_behavior = _STANCES[profile["stance"]]
    lines = [
        f"Age: {npc.age}",
        f"Temperament: {profile['temperament']}",
        f"Speech: {profile['speech']} — every line they say must sound like this.",
        f"Habit (at most once in a reply, and not in every reply): {profile['habit']}",
        (
            f"Toward transported people: {stance_pt}. {stance_behavior} This only colours the "
            "tone: they still answer, sell, hire and help like anyone else."
        ),
        f"Wants: {profile['want']}. Worried about: {profile['worry']}. "
        "Mention these only if the conversation turns that way. A worry is a feeling, not an "
        "event: never invent incidents behind it (attacks, deaths, missing caravans, dates).",
        "Family: none listed — they never mention children, grandchildren, a spouse or siblings.",
    ]
    if trust >= SECRET_TRUST:
        lines.append(f"Secret (they trust the player enough to hint at it, if it fits): {profile['secret']}")
    return lines
