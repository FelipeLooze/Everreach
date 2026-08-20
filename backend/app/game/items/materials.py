import re
from math import isfinite

from sqlalchemy.orm import Session

from app.db.models.material import MaterialDefinition


class MaterialError(ValueError):
    pass


CORE_MATERIALS = (
    ("IRON", "Ferro", 1.0, 1.0, "Metal comum, pesado e estruturalmente confiável."),
    ("STEEL", "Aço", 1.0, 1.25, "Liga resistente usada em ferramentas e equipamento."),
    ("BRONZE", "Bronze", 1.1, 0.9, "Liga relativamente pesada e de resistência moderada."),
    ("WOOD", "Madeira", 0.4, 0.65, "Material leve e rígido de origem vegetal."),
    ("LEATHER", "Couro", 0.5, 0.6, "Material orgânico flexível e moderadamente resistente."),
    ("WOOL", "Lã", 0.25, 0.35, "Fibra leve adequada a vestimentas e acolchoamento."),
    ("LINEN", "Linho", 0.2, 0.3, "Tecido vegetal leve e de resistência limitada."),
)


def create_material_definition(
    db: Session,
    *,
    key: str,
    name: str,
    weight_factor: float,
    wear_resistance: float,
    description: str = "",
) -> MaterialDefinition:
    normalized_key = key.strip().upper()
    normalized_name = name.strip()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", normalized_key):
        raise MaterialError("Invalid material key.")
    if not normalized_name:
        raise MaterialError("Material name is required.")
    if not isfinite(weight_factor) or weight_factor <= 0:
        raise MaterialError("Material weight factor must be finite and positive.")
    if not isfinite(wear_resistance) or wear_resistance <= 0:
        raise MaterialError("Material wear resistance must be finite and positive.")
    values = {
        "name": normalized_name,
        "description": description.strip(),
        "weight_factor": float(weight_factor),
        "wear_resistance": float(wear_resistance),
    }
    existing = (
        db.query(MaterialDefinition)
        .filter(MaterialDefinition.key == normalized_key)
        .one_or_none()
    )
    if existing is not None:
        if any(getattr(existing, field) != value for field, value in values.items()):
            raise MaterialError("Material already exists with different canonical data.")
        return existing
    material = MaterialDefinition(key=normalized_key, **values)
    db.add(material)
    db.flush()
    return material


def get_material_definition(db: Session, key: str) -> MaterialDefinition | None:
    return (
        db.query(MaterialDefinition)
        .filter(MaterialDefinition.key == key.strip().upper())
        .one_or_none()
    )


def seed_core_materials(db: Session) -> list[MaterialDefinition]:
    return [
        create_material_definition(
            db,
            key=key,
            name=name,
            weight_factor=weight_factor,
            wear_resistance=wear_resistance,
            description=description,
        )
        for key, name, weight_factor, wear_resistance, description in CORE_MATERIALS
    ]


def material_weight_factor(material: MaterialDefinition | None) -> float:
    return material.weight_factor if material is not None else 1.0


def material_wear_resistance(material: MaterialDefinition | None) -> float:
    return material.wear_resistance if material is not None else 1.0
