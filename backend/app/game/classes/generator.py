import json
import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.ai.llm_service import LLMService
from app.db.models.character import Character
from app.db.models.character_class import (
    CharacterClassOffer,
    ClassDefinition,
)
from app.db.models.domain import DomainDefinition
from app.game.classes.resolver import (
    MatureClassPath,
    resolve_class_paths,
)
from app.game.classes.service import (
    create_class_definition,
    create_class_offer,
)


_SYSTEM_PROMPT = """
Você propõe somente a identidade semântica de uma classe reconhecida pelo
System de Everreach. As capacidades já existem antes da classe.

Responda SOMENTE com um objeto JSON válido:
{
  "name": "nome curto da classe",
  "description": "descrição do caminho já desenvolvido",
  "identity": "identidade central da classe",
  "theme": "tema curto",
  "domains": ["DOMAIN_A", "DOMAIN_B"]
}

REGRAS:
- Use exatamente os domínios fornecidos, sem adicionar ou remover nenhum.
- Descreva apenas a integração das capacidades confirmadas.
- A classe reconhece um caminho; ela não concede habilidades ou poderes.
- Não invente técnicas, afinidades, atributos, bônus, XP, recursos ou requisitos.
- Não invente fatos, títulos, organizações, religiões ou lugares do mundo.
- Não mencione números, porcentagens, níveis de evidência ou regras internas.
- Não escreva nada fora do JSON.
""".strip()


_FORBIDDEN_MECHANICS = re.compile(
    r"(?:\+\s*\d|\d\s*%|mana\s+infinita|infinite\s+mana|"
    r"concede|conceder|grant(?:s|ed)?|aumenta\s+(?:o|a)|"
    r"increase(?:s|d)?\s+(?:the\s+)?(?:hp|mana|stamina|attribute)|"
    r"atributo|attribute|\bxp\b|requisito|requirement)",
    re.IGNORECASE,
)


class DynamicClassGenerationError(ValueError):
    pass


class DynamicClassProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=800)
    identity: str = Field(min_length=1, max_length=500)
    theme: str = Field(min_length=1, max_length=120)
    domains: list[str] = Field(min_length=1, max_length=12)


def detect_mature_class_paths(
    db: Session,
    character: Character,
) -> list[MatureClassPath]:
    """Compatibility facade over the authoritative mechanical resolver."""
    return list(resolve_class_paths(db, character).candidates)


def generate_dynamic_class_offers(
    db: Session,
    llm_service: LLMService,
    campaign_id: str,
    character: Character,
    *,
    max_new_offers: int = 3,
) -> list[CharacterClassOffer]:
    """Create hidden PENDING offers from authoritative, currently mature paths."""
    if character.campaign_id != campaign_id:
        raise ValueError("Character does not belong to campaign.")
    if max_new_offers < 1:
        raise ValueError("max_new_offers must be positive.")

    created: list[CharacterClassOffer] = []
    for path in detect_mature_class_paths(db, character):
        class_definition = (
            db.query(ClassDefinition)
            .filter(
                ClassDefinition.campaign_id == campaign_id,
                ClassDefinition.generation_key == path.generation_key,
            )
            .first()
        )
        if class_definition is not None:
            existing_offer = (
                db.query(CharacterClassOffer)
                .filter(
                    CharacterClassOffer.character_id == character.id,
                    CharacterClassOffer.class_definition_id
                    == class_definition.id,
                )
                .first()
            )
            if existing_offer is not None:
                continue
        else:
            proposal = _request_and_validate_proposal(
                db,
                llm_service,
                path,
            )
            class_definition = create_class_definition(
                db,
                campaign_id,
                proposal.name,
                proposal.description,
                identity=proposal.identity,
                theme=proposal.theme,
                generation_key=path.generation_key,
                domain_keys=path.domains,
            )

        created.append(
            create_class_offer(
                db,
                campaign_id,
                character,
                class_definition,
            )
        )
        if len(created) >= max_new_offers:
            break
    return created


def _request_and_validate_proposal(
    db: Session,
    llm_service: LLMService,
    path: MatureClassPath,
) -> DynamicClassProposal:
    definitions = {
        row.key: row
        for row in db.query(DomainDefinition)
        .filter(DomainDefinition.key.in_(path.domains))
        .all()
    }
    if set(definitions) != set(path.domains):
        raise DynamicClassGenerationError("Class path contains unknown domains.")

    domain_facts = "\n".join(
        f"- {key} (família: {definitions[key].family})"
        for key in path.domains
    )
    integrations = (
        "\n".join(f"- {first} + {second}" for first, second in path.integrations)
        or "- nenhuma integração entre domínios é necessária para este caminho"
    )
    prompt = (
        "DOMÍNIOS COM MATURIDADE CONFIRMADA:\n"
        f"{domain_facts}\n\n"
        "INTEGRAÇÕES CONFIRMADAS:\n"
        f"{integrations}\n\n"
        "Proponha uma identidade de classe coerente somente com esses fatos."
    )
    raw = llm_service.generate(_SYSTEM_PROMPT, prompt)
    proposal = _parse_proposal(raw)
    proposal_domains = tuple(sorted({key.strip().upper() for key in proposal.domains}))
    if proposal_domains != path.domains or len(proposal.domains) != len(path.domains):
        raise DynamicClassGenerationError(
            "LLM proposal changed the authoritative class domains."
        )

    cleaned = {
        field: " ".join(getattr(proposal, field).split())
        for field in ("name", "description", "identity", "theme")
    }
    if not all(cleaned.values()):
        raise DynamicClassGenerationError("LLM proposal contains empty fields.")
    semantic_text = " ".join(cleaned.values())
    if _FORBIDDEN_MECHANICS.search(semantic_text):
        raise DynamicClassGenerationError(
            "LLM proposal attempted to add mechanics or requirements."
        )
    return DynamicClassProposal(
        **cleaned,
        domains=list(proposal_domains),
    )


def _parse_proposal(raw: str) -> DynamicClassProposal:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        return DynamicClassProposal(**json.loads(raw[start:end]))
    except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
        raise DynamicClassGenerationError(
            "LLM returned an invalid dynamic class proposal."
        ) from exc
