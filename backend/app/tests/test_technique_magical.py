"""Phase 11F — Magical Techniques.

Audit conclusion: the generic technique architecture built in 11A-11E
already supports magical techniques end to end — Mana is just another
CharacterResourceKey, domain/mastery/evidence are type-agnostic, and
CombatTechniqueProfile.required_weapon_family is optional (11E), so a
bare-handed magical technique needs no code change to "cast unarmed".
No production code changes were needed for this subphase; these tests
lock in that conclusion instead of leaving it unverified.

Explicitly NOT built here, per spec: spell slots, cooldowns, or any
class-gated magic — Mana is a baseline resource on every character
regardless of class (see create_character's mana_current/mana_max
defaults), and nothing in the technique system ever consults
active_class or ClassDefinition.
"""

import pytest

from app.core.enums import (
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionType,
    CombatActorType,
    CombatDamageType,
    CombatRangeBand,
    TechniqueOrigin,
    TechniqueType,
)
from app.db.models.combat import CombatParticipant
from app.db.models.domain import DomainDefinition
from app.db.models.npc import NPC
from app.game.character.service import create_character
from app.game.classes.service import get_active_class
from app.game.combat.costs import CombatResourceError
from app.game.combat.encounters import CombatantSpec, start_encounter
from app.game.combat.techniques import configure_combat_technique, resolve_combat_technique
from app.game.combat.turns import roll_initiative
from app.game.skills.techniques import create_technique, grant_technique
from app.game.world.seed import create_campaign, seed_initial_region


class SequenceRng:
    def __init__(self, *values: int):
        self.values = iter(values)

    def randint(self, _minimum: int, _maximum: int) -> int:
        return next(self.values)


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Magical Technique")
    region, location = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, location.id)
    enemy = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=location.id,
        name="Alvo",
        role="alvo de treino",
        hp_current=30,
        hp_max=30,
    )
    db_session.add(enemy)
    technique = create_technique(
        db_session,
        skill_name="Manipulação do Vento",
        name="Rajada de Vento",
        technique_type=TechniqueType.MAGICAL,
        domain_keys=("WIND",),
    )
    grant_technique(
        db_session, campaign.id, character, technique, origin=TechniqueOrigin.SELF_DISCOVERED
    )
    configure_combat_technique(
        db_session,
        technique,
        action_type=CombatActionType.RANGED_ATTACK,
        attack_attribute=CharacterAttributeKey.INTELLIGENCE,
        resource_key=CharacterResourceKey.MANA,
        resource_cost=4,
        base_damage_dice=2,
        damage_die_sides=6,
        damage_attribute=CharacterAttributeKey.INTELLIGENCE,
        damage_type=CombatDamageType.ARCANE,
        # No required_weapon_family: a bare-handed magical technique.
    )
    db_session.flush()
    encounter = start_encounter(
        db_session,
        campaign.id,
        location.id,
        (
            CombatantSpec(
                CombatActorType.CHARACTER, character.id, "heroes",
                range_band=CombatRangeBand.ENGAGED,
            ),
            CombatantSpec(
                CombatActorType.NPC, enemy.id, "enemies",
                range_band=CombatRangeBand.ENGAGED,
            ),
        ),
    )
    participants = {
        row.actor_id: row
        for row in db_session.query(CombatParticipant)
        .filter(CombatParticipant.encounter_id == encounter.id)
        .all()
    }
    roll_initiative(db_session, encounter, rng=SequenceRng(20, 1))
    return campaign, character, technique, encounter, participants[character.id], participants[enemy.id]


def test_a_pure_magical_technique_needs_no_weapon(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(db_session)

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        enemy,
        technique_id=technique.id,
        action_key="cast-wind-gust",
        rng=SequenceRng(10, 4, 5),
    )

    assert result.action.weapon_instance_id is None
    assert result.action.resource_key == CharacterResourceKey.MANA.value


def test_a_pure_magical_technique_actually_spends_mana(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(db_session)
    starting_mana = character.mana_current

    resolve_combat_technique(
        db_session,
        encounter,
        hero,
        enemy,
        technique_id=technique.id,
        action_key="cast-wind-gust",
        rng=SequenceRng(10, 4, 5),
    )

    assert character.mana_current == starting_mana - 4


def test_insufficient_mana_blocks_the_magical_technique(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(db_session)
    character.mana_current = 1  # below the technique's resource_cost of 4

    with pytest.raises(CombatResourceError, match="Insufficient mana"):
        resolve_combat_technique(
            db_session,
            encounter,
            hero,
            enemy,
            technique_id=technique.id,
            action_key="cast-wind-gust",
            rng=SequenceRng(10, 4, 5),
        )


def test_magic_does_not_require_an_active_class(db_session):
    campaign, character, technique, encounter, hero, enemy = _setup(db_session)

    assert get_active_class(db_session, character) is None

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        enemy,
        technique_id=technique.id,
        action_key="cast-wind-gust",
        rng=SequenceRng(10, 4, 5),
    )

    assert result.action.outcome is not None


def test_magical_technique_use_grows_its_own_domain_evidence(db_session):
    from app.ai.llm_service import LLMService
    from app.db.models.domain import CharacterDomainEvidence
    from app.game.progression.outcomes import resolve_progression_outcome

    class PassiveLLM(LLMService):
        def generate(self, system: str, prompt: str) -> str:
            return "A ação acontece conforme o resultado mecânico."

    campaign, character, technique, encounter, hero, enemy = _setup(db_session)

    result = resolve_combat_technique(
        db_session,
        encounter,
        hero,
        enemy,
        technique_id=technique.id,
        action_key="cast-wind-gust",
        rng=SequenceRng(20, 4, 5, 3, 2),  # natural 20: guaranteed critical hit (doubles damage dice)
    )
    assert {gain.domain_key for gain in result.progression_outcome.domains} == {"WIND"}

    resolve_progression_outcome(
        db_session, PassiveLLM(), campaign.id, character, result.progression_outcome
    )

    evidence = (
        db_session.query(CharacterDomainEvidence)
        .filter(
            CharacterDomainEvidence.character_id == character.id,
            CharacterDomainEvidence.domain_key == "WIND",
        )
        .one()
    )
    assert evidence.depth > 0
