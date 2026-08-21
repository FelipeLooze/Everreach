"""Phase 11K — Technique Execution Integration.

The Technique Service validates a named, already-LEARNED technique and
routes it to the right authoritative system: the Combat Engine
(resolve_combat_technique) when the character is actively fighting, the
generic skill-check path (resolve_technique_use) otherwise. The LLM only
ever names which technique and (optionally) which opponent — it never
decides whether the technique is known, whether it hits, or its effect.

This also closes a real gap found while auditing 11I: resolve_combat_technique
(the REAL combat resolution — weapon requirements, attack rolls, HP damage)
was never called from engine.py at all, even via the pre-existing explicit
technique_id parameter — that path always went through the generic,
damage-less resolve_technique_use, regardless of being in active combat.
"""

from app.ai.intent_parser import Intent
from app.ai.llm_service import LLMService
from app.core.enums import (
    ActionIntentType,
    CharacterAttributeKey,
    CharacterResourceKey,
    CombatActionType,
    CombatDamageType,
    TechniqueOrigin,
    TechniqueType,
)
from app.db.models.combat import CombatAction
from app.db.models.domain import DomainDefinition
from app.db.models.npc import NPC
from app.game import engine
from app.game.character.service import create_character
from app.game.combat import bridge as combat_bridge
from app.game.combat.techniques import configure_combat_technique
from app.game.skills.techniques import create_technique, grant_technique
from app.game.world.seed import create_campaign, seed_initial_region


class PassiveLLM(LLMService):
    def generate(self, system: str, prompt: str) -> str:
        return "A ação acontece conforme o resultado mecânico."


def _setup(db_session):
    if db_session.get(DomainDefinition, "WIND") is None:
        db_session.add(DomainDefinition(key="WIND", family="MANIFESTATION", description=""))
    campaign = create_campaign(db_session, "Technique Execution Integration")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Hero", region.id, village.id)
    enemy = NPC(
        campaign_id=campaign.id,
        region_id=region.id,
        location_id=village.id,
        name="Bandido",
        role="bandido",
        alive=True,
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
        resource_cost=3,
        base_damage_dice=2,
        damage_die_sides=6,
        damage_attribute=CharacterAttributeKey.INTELLIGENCE,
        damage_type=CombatDamageType.ARCANE,
        # No required_weapon_family: castable bare-handed.
    )
    db_session.commit()
    return campaign, character, enemy, technique


def _mock_technique_intent(monkeypatch, *, target, secondary_target=None):
    monkeypatch.setattr(
        engine.intent_parser,
        "parse",
        lambda *_args, **_kwargs: Intent(
            type=ActionIntentType.TECHNIQUE,
            target=target,
            secondary_target=secondary_target,
            raw_text=f"Uso {target}.",
        ),
    )


def test_named_technique_outside_combat_uses_the_generic_path(db_session, monkeypatch):
    campaign, character, enemy, technique = _setup(db_session)
    _mock_technique_intent(monkeypatch, target="Rajada de Vento")

    result = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id,
        "Uso Rajada de Vento.", action_key="named-technique-generic",
    )

    assert result.intent_type == ActionIntentType.TECHNIQUE.value
    assert db_session.query(CombatAction).count() == 0  # never touched the Combat Engine
    assert enemy.hp_current == enemy.hp_max  # no damage — there was no fight to apply it to


def test_named_technique_during_combat_uses_the_combat_engine(db_session, monkeypatch):
    campaign, character, enemy, technique = _setup(db_session)
    # Start a real encounter first, the same way ATTACK would.
    monkeypatch.setattr(
        engine.intent_parser, "parse",
        lambda *_a, **_k: Intent(type=ActionIntentType.ATTACK, target="Bandido", raw_text="Ataco!"),
    )
    engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id, "Ataco o bandido!",
        action_key="start-fight",
    )
    starting_hp = enemy.hp_current
    starting_mana = character.mana_current

    _mock_technique_intent(monkeypatch, target="Rajada de Vento", secondary_target="Bandido")
    result = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id,
        "Uso Rajada de Vento no bandido.", action_key="named-technique-combat",
    )

    assert result.intent_type == ActionIntentType.TECHNIQUE.value
    action = db_session.query(CombatAction).filter(CombatAction.technique_id == technique.id).one()
    assert action is not None
    # Mana only moves when resolve_combat_technique (not the generic path)
    # actually ran — the generic path never touches combat resources.
    assert character.mana_current < starting_mana
    assert enemy.hp_current <= starting_hp


def test_an_unknown_technique_name_is_a_graceful_noop(db_session, monkeypatch):
    campaign, character, enemy, technique = _setup(db_session)
    _mock_technique_intent(monkeypatch, target="Bola de Fogo Suprema")

    result = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id,
        "Uso Bola de Fogo Suprema.", action_key="unknown-technique",
    )

    assert "não conhece" in result.mechanical_summary
    assert db_session.query(CombatAction).count() == 0


def test_a_missing_technique_name_is_a_graceful_noop(db_session, monkeypatch):
    campaign, character, enemy, technique = _setup(db_session)
    _mock_technique_intent(monkeypatch, target=None)

    result = engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id,
        "Uso minha técnica.", action_key="missing-technique-name",
    )

    assert "precisa dizer qual técnica" in result.mechanical_summary


def test_handle_technique_intent_requires_an_active_encounter(db_session):
    _campaign, character, _enemy, technique = _setup(db_session)

    summary, resolution = combat_bridge.handle_technique_intent(
        db_session, character, technique, None, action_key="no-encounter",
    )

    assert "não está em combate" in summary
    assert resolution is None


def test_handle_technique_intent_rejects_an_unknown_opponent_name(db_session, monkeypatch):
    campaign, character, enemy, technique = _setup(db_session)
    monkeypatch.setattr(
        engine.intent_parser, "parse",
        lambda *_a, **_k: Intent(type=ActionIntentType.ATTACK, target="Bandido", raw_text="Ataco!"),
    )
    engine.resolve_action(
        db_session, PassiveLLM(), campaign.id, character.id, "Ataco o bandido!",
        action_key="start-fight-2",
    )

    summary, resolution = combat_bridge.handle_technique_intent(
        db_session, character, technique, "Fantasma Inexistente", action_key="bad-target",
    )

    assert "não é um oponente ativo" in summary
    assert resolution is None
