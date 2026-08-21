"""Bridge between player-facing intents and the Phase 9 Combat Engine.

Turns a parsed ATTACK/DEFEND/DODGE/APPROACH/RETREAT/DISENGAGE/FLEE intent into
concrete encounter/turn/action calls, then drives NPC/simulated-player turns
automatically until control returns to the protagonist. The LLM never decides
targeting, hit, damage, or turn order here — it only supplied the structured
intent; every mechanical result comes from the existing Combat Engine
(app/game/combat/*), which stays the sole authority.
"""

import random

from sqlalchemy.orm import Session

from app.ai.intent_parser import Intent
from app.core.enums import (
    ActionIntentType,
    BodyArea,
    CombatActionType,
    CombatActorType,
    CombatEncounterStatus,
    CombatRangeBand,
    CombatTacticalActionType,
    EquipmentSlot,
    ItemAccessibility,
    PhysicalDamageProfile,
    WeaponHandRequirement,
    WeaponReach,
)
from app.core.ids import generate_id
from app.db.models.character import Character
from app.db.models.combat import CombatEncounter, CombatParticipant
from app.db.models.item import ItemInstance
from app.db.models.npc import NPC
from app.db.models.simulated_player import SimulatedPlayer
from app.db.models.weapon import ItemWeaponProfile
from app.game.combat.actions import resolve_attack
from app.game.combat.autonomy import (
    AutonomousCombatResolution,
    resolve_until_player_turn,
)
from app.game.combat.encounters import (
    CombatantSpec,
    get_active_encounter_for_actor,
    list_active_participants,
    start_encounter,
)
from app.game.combat.hostility import mark_hostile_from_attack
from app.game.combat.tactics import resolve_tactical_action
from app.game.combat.turns import complete_current_turn, get_current_turn, roll_initiative
from app.game.inventory.service import list_inventory
from app.game.items.equipment import equip_item, item_accessibility
from app.game.items.interactions import resolve_item_interaction
from app.game.items.weapons import get_weapon_damage_profiles, resolve_weapon_attack


class CombatBridgeError(ValueError):
    """A player-facing combat request could not be resolved."""


TACTICAL_INTENT_MAP: dict[ActionIntentType, CombatTacticalActionType] = {
    ActionIntentType.DEFEND: CombatTacticalActionType.GUARD,
    ActionIntentType.DODGE: CombatTacticalActionType.DODGE,
    ActionIntentType.APPROACH: CombatTacticalActionType.APPROACH,
    ActionIntentType.RETREAT: CombatTacticalActionType.RETREAT,
    ActionIntentType.DISENGAGE: CombatTacticalActionType.DISENGAGE,
    ActionIntentType.FLEE: CombatTacticalActionType.FLEE,
}
_MOVEMENT_TACTICS = {
    CombatTacticalActionType.APPROACH,
    CombatTacticalActionType.RETREAT,
    CombatTacticalActionType.DISENGAGE,
}
_OUTCOME_LABELS = {
    "CRITICAL_HIT": "acerta um golpe crítico",
    "HIT": "acerta",
    "MISS": "erra",
    "CRITICAL_MISS": "erra de forma crítica",
}
_TACTIC_LABELS = {
    "GUARD": "assume postura defensiva",
    "DODGE": "prepara uma esquiva",
    "APPROACH": "avança",
    "RETREAT": "recua",
    "DISENGAGE": "rompe o combate corpo a corpo",
    "FLEE": "tenta fugir",
    "WAIT": "aguarda",
}
_END_LABELS = {
    CombatEncounterStatus.VICTORY.value: "O combate termina em vitória.",
    CombatEncounterStatus.DEFEAT.value: "O combate termina em derrota.",
    CombatEncounterStatus.FLED.value: "O combate termina com uma fuga.",
    CombatEncounterStatus.CANCELLED.value: "O combate é encerrado.",
}


def handle_attack_intent(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    state,
    *,
    action_key: str | None,
    rng: random.Random | None = None,
) -> tuple[str, int]:
    resolved_key = action_key or generate_id("action")
    existing = get_active_encounter_for_actor(db, CombatActorType.CHARACTER, character.id)

    target_participant: CombatParticipant | None = None
    if existing is None:
        try:
            encounter, character_participant, target_participant = _start_new_encounter(
                db, campaign_id, character, intent.target, state, rng=rng,
            )
        except CombatBridgeError as exc:
            return str(exc), 0
    else:
        encounter = existing
        character_participant = _find_character_participant(db, encounter, character.id)

    lines = _advance_autonomy(db, encounter, prefix=f"combat:{resolved_key}", rng=rng)
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        return " ".join(lines) or _encounter_end_summary(encounter), 0

    current_turn = get_current_turn(db, encounter)
    if current_turn is None or current_turn.participant_id != character_participant.id:
        return " ".join(lines) or f"{character.name} aguarda sua vez no combate.", 0

    if target_participant is None:
        try:
            target_participant = _resolve_opposing_target(
                db, encounter, character_participant, intent.target,
            )
        except CombatBridgeError as exc:
            lines.append(str(exc))
            return " ".join(lines), 0

    try:
        attack_summary = _resolve_player_attack(
            db,
            encounter,
            character,
            character_participant,
            target_participant,
            intent,
            action_key=f"attack:{resolved_key}",
            rng=rng,
        )
    except CombatBridgeError as exc:
        lines.append(str(exc))
        return " ".join(lines), 0
    lines.append(attack_summary)

    if encounter.status == CombatEncounterStatus.ACTIVE.value:
        lines.extend(
            _advance_autonomy(db, encounter, prefix=f"combat:{resolved_key}:after", rng=rng)
        )
    else:
        lines.append(_encounter_end_summary(encounter))

    return " ".join(lines), 0


def handle_combat_tactic_intent(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    state,
    *,
    action_key: str | None,
    rng: random.Random | None = None,
) -> tuple[str, int]:
    tactic = TACTICAL_INTENT_MAP[intent.type]
    resolved_key = action_key or generate_id("action")
    encounter = get_active_encounter_for_actor(db, CombatActorType.CHARACTER, character.id)
    if encounter is None:
        return f"{character.name} não está em combate no momento.", 0

    character_participant = _find_character_participant(db, encounter, character.id)

    lines = _advance_autonomy(db, encounter, prefix=f"combat:{resolved_key}", rng=rng)
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        return " ".join(lines) or _encounter_end_summary(encounter), 0

    current_turn = get_current_turn(db, encounter)
    if current_turn is None or current_turn.participant_id != character_participant.id:
        return " ".join(lines) or f"{character.name} aguarda sua vez no combate.", 0

    target_participant = None
    if tactic in _MOVEMENT_TACTICS:
        try:
            target_participant = _resolve_opposing_target(
                db, encounter, character_participant, intent.target,
            )
        except CombatBridgeError as exc:
            lines.append(str(exc))
            return " ".join(lines), 0

    try:
        result = resolve_tactical_action(
            db,
            encounter,
            character_participant,
            action_type=tactic,
            target=target_participant,
            action_key=f"tactical:{resolved_key}",
            rng=rng,
        )
    except ValueError as exc:
        lines.append(f"A ação não pôde ser realizada: {exc}")
        return " ".join(lines), 0

    target_name = _participant_name(db, target_participant) if target_participant else None
    lines.append(_describe_tactical_outcome(character.name, target_name, result.action))

    if encounter.status == CombatEncounterStatus.ACTIVE.value:
        lines.extend(
            _advance_autonomy(db, encounter, prefix=f"combat:{resolved_key}:after", rng=rng)
        )
    else:
        lines.append(_encounter_end_summary(encounter))

    return " ".join(lines), 0


def handle_item_interaction_intent(
    db: Session,
    campaign_id: str,
    character: Character,
    intent: Intent,
    *,
    action_key: str | None,
) -> tuple[str, int]:
    """Resolve an EQUIP/UNEQUIP/STORE/RETRIEVE/... intent as one combat turn.

    Manipulating equipment mid-fight (drawing, sheathing, stowing, swapping)
    is not free: it consumes the protagonist's current turn just like an
    attack or a tactical action, then hands control to the autonomy loop.
    """
    resolved_key = action_key or generate_id("action")
    encounter = get_active_encounter_for_actor(db, CombatActorType.CHARACTER, character.id)
    character_participant = _find_character_participant(db, encounter, character.id)

    lines = _advance_autonomy(db, encounter, prefix=f"combat:{resolved_key}")
    if encounter.status != CombatEncounterStatus.ACTIVE.value:
        return " ".join(lines) or _encounter_end_summary(encounter), 0

    current_turn = get_current_turn(db, encounter)
    if current_turn is None or current_turn.participant_id != character_participant.id:
        return " ".join(lines) or f"{character.name} aguarda sua vez no combate.", 0

    try:
        result = resolve_item_interaction(
            db,
            campaign_id,
            character,
            interaction=intent.type,
            target=intent.target,
            secondary_target=intent.secondary_target,
            slot=intent.slot,
            interaction_key=f"item:{resolved_key}",
        )
    except ValueError as exc:
        lines.append(f"A interação com o item não pôde ser realizada: {exc}")
        return " ".join(lines), 0

    complete_current_turn(
        db,
        encounter,
        character_participant,
        completion_key=f"item_turn:{resolved_key}",
    )
    lines.append(result.summary)

    if encounter.status == CombatEncounterStatus.ACTIVE.value:
        lines.extend(_advance_autonomy(db, encounter, prefix=f"combat:{resolved_key}:after"))
    else:
        lines.append(_encounter_end_summary(encounter))

    return " ".join(lines), 0


def _start_new_encounter(
    db: Session,
    campaign_id: str,
    character: Character,
    target_name: str | None,
    state,
    *,
    rng: random.Random | None = None,
) -> tuple[CombatEncounter, CombatParticipant, CombatParticipant]:
    target_kind, target_actor = _find_nearby_target(state, target_name)
    if target_actor is None:
        raise CombatBridgeError(
            "Nenhum alvo correspondente foi encontrado aqui para atacar."
            if target_name
            else "É preciso indicar um alvo para atacar."
        )

    combatants = (
        CombatantSpec(
            CombatActorType.CHARACTER,
            character.id,
            side_key="player",
            range_band=CombatRangeBand.ENGAGED,
        ),
        CombatantSpec(
            target_kind,
            target_actor.id,
            side_key="hostile",
            range_band=CombatRangeBand.ENGAGED,
        ),
    )
    try:
        encounter = start_encounter(db, campaign_id, character.location_id, combatants)
        roll_initiative(db, encounter, rng=rng)
    except ValueError as exc:
        raise CombatBridgeError(f"O combate não pôde começar: {exc}") from exc

    if target_kind == CombatActorType.NPC:
        mark_hostile_from_attack(target_actor)

    character_participant = _find_character_participant(db, encounter, character.id)
    target_participant = next(
        participant
        for participant in list_active_participants(db, encounter.id)
        if participant.id != character_participant.id
    )
    return encounter, character_participant, target_participant


def _find_nearby_target(
    state,
    target_name: str | None,
) -> tuple[CombatActorType | None, "NPC | SimulatedPlayer | None"]:
    npc_candidates = list(state.nearby_npcs)
    sim_candidates = list(state.nearby_simulated_players)
    if target_name:
        needle = target_name.casefold()
        npc_candidates = [n for n in npc_candidates if needle in n.name.casefold()]
        sim_candidates = [p for p in sim_candidates if needle in p.name.casefold()]
    matches = [(CombatActorType.NPC, n) for n in npc_candidates] + [
        (CombatActorType.SIMULATED_PLAYER, p) for p in sim_candidates
    ]
    if len(matches) == 1:
        return matches[0]
    return None, None


def _find_character_participant(
    db: Session,
    encounter: CombatEncounter,
    character_id: str,
) -> CombatParticipant:
    participant = next(
        (
            p
            for p in list_active_participants(db, encounter.id)
            if p.actor_type == CombatActorType.CHARACTER.value and p.actor_id == character_id
        ),
        None,
    )
    if participant is None:
        raise CombatBridgeError("Você não está mais ativo neste combate.")
    return participant


def _resolve_opposing_target(
    db: Session,
    encounter: CombatEncounter,
    character_participant: CombatParticipant,
    target_name: str | None,
) -> CombatParticipant:
    opponents = [
        p
        for p in list_active_participants(db, encounter.id)
        if p.side_key != character_participant.side_key
    ]
    if not opponents:
        raise CombatBridgeError("Não há oponentes ativos neste combate.")
    if target_name:
        needle = target_name.casefold()
        named = [p for p in opponents if needle in _participant_name(db, p).casefold()]
        if len(named) == 1:
            return named[0]
        if len(named) > 1:
            raise CombatBridgeError("Há mais de um alvo correspondente a essa descrição.")
        raise CombatBridgeError(f"'{target_name}' não é um oponente ativo neste combate.")
    if len(opponents) == 1:
        return opponents[0]
    raise CombatBridgeError("É preciso indicar contra qual oponente agir; há mais de um.")


def _participant_name(db: Session, participant: CombatParticipant) -> str:
    if participant.actor_type == CombatActorType.CHARACTER.value:
        actor = db.get(Character, participant.actor_id)
    elif participant.actor_type == CombatActorType.NPC.value:
        actor = db.get(NPC, participant.actor_id)
    else:
        actor = db.get(SimulatedPlayer, participant.actor_id)
    return actor.name if actor is not None else "alguém"


def _advance_autonomy(
    db: Session,
    encounter: CombatEncounter,
    *,
    prefix: str,
    rng: random.Random | None = None,
) -> list[str]:
    try:
        resolutions = resolve_until_player_turn(
            db, encounter, decision_key_prefix=prefix, rng=rng
        )
    except ValueError:
        return []
    return [_describe_autonomous(db, resolution) for resolution in resolutions]


def describe_autonomous_resolution(
    db: Session, resolution: AutonomousCombatResolution
) -> str:
    """Public re-export of _describe_autonomous for callers outside the
    intent-driven flow (e.g. hostility.py's ambush turns)."""
    return _describe_autonomous(db, resolution)


def _describe_autonomous(db: Session, resolution: AutonomousCombatResolution) -> str:
    actor = db.get(CombatParticipant, resolution.decision.actor_participant_id)
    actor_name = _participant_name(db, actor) if actor else "alguém"
    if resolution.combat_action is not None:
        action = resolution.combat_action
        target = db.get(CombatParticipant, action.target_participant_id)
        target_name = _participant_name(db, target) if target else "o alvo"
        return _describe_attack_outcome(actor_name, target_name, action)
    if resolution.tactical_action is not None:
        action = resolution.tactical_action
        target_name = None
        if action.target_participant_id:
            target = db.get(CombatParticipant, action.target_participant_id)
            target_name = _participant_name(db, target) if target else None
        return _describe_tactical_outcome(actor_name, target_name, action)
    return f"{actor_name} aguarda."


def _describe_attack_outcome(
    attacker_name: str,
    target_name: str,
    action,
    *,
    weapon_name: str | None = None,
    drew_weapon: bool = False,
) -> str:
    label = _OUTCOME_LABELS.get(action.outcome, "ataca")
    if drew_weapon and weapon_name:
        actor_phrase = f"{attacker_name} saca {weapon_name} e"
        weapon_phrase = ""
    else:
        actor_phrase = attacker_name
        weapon_phrase = f" com {weapon_name}" if weapon_name else ""
    if action.outcome in {"MISS", "CRITICAL_MISS"}:
        return f"{actor_phrase} {label}{weapon_phrase} contra {target_name}."
    text = (
        f"{actor_phrase} {label}{weapon_phrase} em {target_name}, causando "
        f"{action.damage_total} de dano ({int(action.target_hp_before)} → "
        f"{int(action.target_hp_after)} de HP)."
    )
    if action.incapacitating:
        text += f" {target_name} fica incapacitado."
    if action.lethal:
        text += f" {target_name} morre."
    return text


def _describe_tactical_outcome(
    actor_name: str,
    target_name: str | None,
    action,
) -> str:
    label = _TACTIC_LABELS.get(action.action_type, "age taticamente")
    if action.action_type == CombatTacticalActionType.FLEE.value:
        return (
            f"{actor_name} {label} e consegue escapar."
            if action.success
            else f"{actor_name} {label}, mas não consegue escapar."
        )
    if target_name:
        return f"{actor_name} {label} em direção a {target_name}."
    return f"{actor_name} {label}."


def _encounter_end_summary(encounter: CombatEncounter) -> str:
    return _END_LABELS.get(encounter.status, "O combate termina.")


def _resolve_player_attack(
    db: Session,
    encounter: CombatEncounter,
    character: Character,
    actor: CombatParticipant,
    target: CombatParticipant,
    intent: Intent,
    *,
    action_key: str,
    rng: random.Random | None = None,
) -> str:
    action_type = _parse_action_type(intent.attack_type)
    body_area = _parse_body_area(intent.body_area)
    weapon_instance, weapon_profile = _resolve_named_weapon(db, character, intent.weapon)

    if intent.weapon and weapon_instance is None:
        raise CombatBridgeError(
            f"'{intent.weapon}' não está equipado nem acessível na cintura para atacar."
        )

    target_name = _participant_name(db, target)

    if weapon_instance is not None:
        drew_weapon = item_accessibility(weapon_instance) == ItemAccessibility.QUICK
        if drew_weapon:
            try:
                _quick_draw(db, weapon_instance, weapon_profile)
            except ValueError as exc:
                raise CombatBridgeError(
                    f"Não foi possível sacar {weapon_instance.definition.name}: {exc}"
                ) from exc
        supported = get_weapon_damage_profiles(weapon_profile)
        damage_profile = _parse_damage_profile(intent.damage_profile)
        if damage_profile is None or damage_profile not in supported:
            damage_profile = sorted(supported, key=lambda profile: profile.value)[0]
        resolved_action_type = action_type or (
            CombatActionType.RANGED_ATTACK
            if weapon_profile.reach == WeaponReach.RANGED.value
            else CombatActionType.MELEE_ATTACK
        )
        try:
            resolution = resolve_weapon_attack(
                db,
                encounter,
                actor,
                target,
                weapon_instance_id=weapon_instance.id,
                action_type=resolved_action_type,
                damage_profile=damage_profile,
                action_key=action_key,
                target_body_area=body_area or BodyArea.TORSO,
                rng=rng,
            )
        except ValueError as exc:
            raise CombatBridgeError(
                f"O ataque com {weapon_instance.definition.name} falhou: {exc}"
            ) from exc
        return _describe_attack_outcome(
            character.name,
            target_name,
            resolution.action,
            weapon_name=weapon_instance.definition.name,
            drew_weapon=drew_weapon,
        )

    resolved_action_type = action_type or CombatActionType.MELEE_ATTACK
    try:
        resolution = resolve_attack(
            db,
            encounter,
            actor,
            target,
            action_type=resolved_action_type,
            action_key=action_key,
            rng=rng,
        )
    except ValueError as exc:
        raise CombatBridgeError(f"O ataque falhou: {exc}") from exc
    return _describe_attack_outcome(character.name, target_name, resolution.action)


def _quick_draw(
    db: Session,
    instance: ItemInstance,
    profile: ItemWeaponProfile,
) -> None:
    """Move a weapon from the waist (QUICK access) into hand, for free.

    Not a turn cost, not a separate action — a weapon riding at the waist is
    assumed ready to draw in the same motion as the attack. Anything deeper
    (STOWED, e.g. in a backpack) still requires a real EQUIP turn first.
    """
    hand_requirement = WeaponHandRequirement(profile.hand_requirement)
    slot = (
        EquipmentSlot.BOTH_HANDS
        if hand_requirement == WeaponHandRequirement.TWO_HANDS
        else EquipmentSlot.MAIN_HAND
    )
    equip_item(db, instance, slot=slot)


def _resolve_named_weapon(
    db: Session,
    character: Character,
    weapon_name: str | None,
) -> tuple[ItemInstance | None, ItemWeaponProfile | None]:
    if not weapon_name:
        return None, None
    needle = weapon_name.casefold()
    candidates = [
        entry
        for entry in list_inventory(db, character.id)
        if needle in entry.definition.name.casefold()
        and item_accessibility(entry) in {ItemAccessibility.IMMEDIATE, ItemAccessibility.QUICK}
    ]
    usable = [
        entry for entry in candidates if db.get(ItemWeaponProfile, entry.definition_id) is not None
    ]
    if len(usable) != 1:
        return None, None
    instance = usable[0]
    return instance, db.get(ItemWeaponProfile, instance.definition_id)


def _parse_action_type(value: str | None) -> CombatActionType | None:
    if not value:
        return None
    try:
        return CombatActionType(value.strip().upper())
    except ValueError:
        return None


def _parse_body_area(value: str | None) -> BodyArea | None:
    if not value:
        return None
    try:
        return BodyArea(value.strip().upper())
    except ValueError:
        return None


def _parse_damage_profile(value: str | None) -> PhysicalDamageProfile | None:
    if not value:
        return None
    try:
        return PhysicalDamageProfile(value.strip().upper())
    except ValueError:
        return None
