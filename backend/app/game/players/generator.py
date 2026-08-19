import json

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService
from app.core.enums import (
    SimulatedPlayerArchetype,
    SimulatedPlayerGoalType,
    SimulatedPlayerStatus,
)
from app.db.models.location import Location
from app.db.models.region import Region
from app.db.models.simulated_player import SimulatedPlayer


_SYSTEM_PROMPT = """
Você cria a identidade inicial de uma pessoa da Terra que foi
fisicamente transportada para um mundo medieval fantástico.

Esta chamada acontece somente uma vez para esta pessoa.
Depois da criação, a identidade será persistida pelo backend.

Responda SOMENTE com um objeto JSON válido neste formato:

{
  "name": "nome da pessoa",
  "personality": "descrição curta da personalidade",
  "background": "breve passado da pessoa antes da Chegada",
  "motivation": "motivação pessoal atual",
  "physical_description": "descrição física objetiva da pessoa",
  "goal": "objetivo atual em texto livre",
  "archetype": "EXPLORER"
}

Valores permitidos para "archetype":
- EXPLORER
- TRAINER
- SOCIAL
- ADVENTURER

REGRAS:

- A pessoa veio da Terra e foi fisicamente transportada.
- Isto não é um videogame, servidor ou VRMMORPG.
- Nunca chame a pessoa de NPC, personagem ou jogador.
- O nome pode ter estética terrestre, fantástica ou uma mistura das duas.
- Não use o estilo do nome para determinar a origem da pessoa.
- O background deve tratar principalmente da vida anterior na Terra.
- A pessoa é comum e não é escolhida por profecia, destino ou linhagem especial.
- Não conceda poderes especiais, conhecimento secreto ou vantagens gratuitas.
- Não invente fatos sobre o mundo além do contexto fornecido.
- Não invente cidades, reinos, religiões, organizações, pessoas importantes
  ou acontecimentos históricos.
- O objetivo é TEXTO LIVRE e pode representar qualquer desejo plausível.
- Um desejo não confirma que aquilo que a pessoa procura realmente exista.
- A pessoa pode querer sobreviver, trabalhar, explorar, encontrar alguém,
  aprender alguma coisa, formar relações, voltar para a Terra ou qualquer
  outro objetivo humano plausível.
- O archetype representa apenas uma tendência geral de comportamento.
- Não escreva nenhuma explicação fora do JSON.
- "physical_description" deve descrever visualmente a pessoa de forma objetiva.
- Inclua características como idade aparente, cabelo, olhos, pele, altura aproximada,
  porte físico e outros traços visualmente relevantes quando apropriado.
- Evite metáforas e linguagem abstrata na descrição física.
- A descrição deve ser útil futuramente como base para gerar um retrato visual.
- Não invente equipamentos raros, mágicos ou especiais.
- Roupas simples podem ser descritas, mas não representam inventário ou equipamento
  mecânico confirmado pelo sistema.
""".strip()


class SimulatedPlayerMaterializationError(ValueError):
    pass


class SimulatedPlayerIdentity(BaseModel):
    name: str = Field(
        min_length=1,
        max_length=120,
    )

    personality: str = Field(
        min_length=1,
        max_length=1000,
    )

    background: str = Field(
        min_length=1,
        max_length=1500,
    )

    motivation: str = Field(
        min_length=1,
        max_length=1000,
    )

    physical_description: str = Field(
        min_length=1,
        max_length=1200,
    )

    goal: str = Field(
        min_length=1,
        max_length=1000,
    )

    archetype: SimulatedPlayerArchetype


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _parse_identity(
    raw: str,
) -> SimulatedPlayerIdentity:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1

        data = json.loads(
            raw[start:end]
        )

        identity = SimulatedPlayerIdentity(
            **data
        )

    except (
        ValueError,
        json.JSONDecodeError,
        ValidationError,
        TypeError,
    ) as exc:
        raise SimulatedPlayerMaterializationError(
            "LLM returned an invalid simulated player identity."
        ) from exc

    identity.name = _clean_text(
        identity.name
    )
    identity.personality = _clean_text(
        identity.personality
    )
    identity.background = _clean_text(
        identity.background
    )
    identity.motivation = _clean_text(
        identity.motivation
    )
    identity.physical_description = _clean_text(
        identity.physical_description
    )
    identity.goal = _clean_text(
        identity.goal
    )

    if not all(
        (
            identity.name,
            identity.personality,
            identity.background,
            identity.motivation,
            identity.physical_description,
            identity.goal,
        )
    ):
        raise SimulatedPlayerMaterializationError(
            "LLM returned empty simulated player identity fields."
        )

    return identity


def materialize_simulated_player(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    location_id: str,
) -> SimulatedPlayer:
    location_and_region = (
        db.query(
            Location,
            Region,
        )
        .join(
            Region,
            Location.region_id == Region.id,
        )
        .filter(
            Location.id == location_id,
            Region.campaign_id == campaign_id,
        )
        .one_or_none()
    )

    if location_and_region is None:
        raise ValueError(
            f"Location {location_id} does not belong "
            f"to campaign {campaign_id}."
        )

    location, region = location_and_region

    prompt = f"""
CONTEXTO CANÔNICO DISPONÍVEL

Região:
Nome: {region.name}
Descrição: {region.description or "Nenhuma descrição adicional."}

Local atual:
Nome: {location.name}
Tipo: {location.type}
Descrição: {location.description or "Nenhuma descrição adicional."}

Crie exatamente uma pessoa transportada que esteja atualmente neste local.

A identidade deve ser plausível sem acrescentar novos fatos ao mundo.
""".strip()

    raw = llm_service.generate(
        _SYSTEM_PROMPT,
        prompt,
    )

    identity = _parse_identity(raw)

    player = SimulatedPlayer(
        campaign_id=campaign_id,
        name=identity.name,
        level=0,
        location_id=location.id,
        archetype=identity.archetype.value,
        goal=identity.goal,
        goal_type=SimulatedPlayerGoalType.NONE.value,
        goal_subject=None,
        personality=identity.personality,
        background=identity.background,
        motivation=identity.motivation,
        physical_description=identity.physical_description,
        status=SimulatedPlayerStatus.ACTIVE.value,
    )

    db.add(player)
    db.flush()

    return player