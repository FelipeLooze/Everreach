"""Survival (hunger/thirst) — requested as a follow-up after Phase 17's
own Natural Exploration Hazards subphase (17K) deliberately left this
out, since no resource system existed anywhere in the codebase for it to
plug into. This is that resource system, kept deliberately small:

- Deliberately SLOW: at the baseline (ENDURANCE 10), a full tank takes
  ~2 days of world time to drain from hunger and ~a day from thirst —
  never "ate, 30 minutes later hungry again". Nothing decays in
  real-time or on a tick loop; app.game.time.clock.advance_world_time
  is already the one place world time moves forward for a character's
  own action (app/game/engine.py calls it once per resolved intent,
  right before the world simulation tick), so apply_survival_decay is
  called from that exact spot — reused, not a new time-tracking
  mechanism.
- Deliberately NOT hardcore: no HP damage, no death, no forced actions.
  Being critically hungry or thirsty only mildly reduces how much
  stamina resting actually restores (app.game.combat.recovery) — you
  still recover, just not as well as with a full stomach.
- ENDURANCE (the closest existing attribute to "constitution" — see
  app.core.enums.CharacterAttributeKey, which has no literal CONSTITUTION)
  raises the maximum, never the drain rate: a higher-endurance character
  simply has a bigger tank, so the same fixed hourly drain takes
  proportionally longer to empty it.
"""

from sqlalchemy.orm import Session

from app.core.enums import CharacterAttributeKey
from app.db.models.character import Character
from app.game.attributes.service import get_character_attribute
from app.game.time.clock import get_world_time

BASE_HUNGER_MAX = 100.0
BASE_THIRST_MAX = 100.0
ENDURANCE_MAX_BONUS_PER_POINT = 5.0
BASELINE_ENDURANCE = 10

HUNGER_DECAY_PER_HOUR = 100.0 / 48.0
THIRST_DECAY_PER_HOUR = 100.0 / 28.0

_GOOD_THRESHOLD = 0.5
_LOW_THRESHOLD = 0.15

_CRITICAL_STAMINA_RECOVERY_MULTIPLIER = 0.5
_LOW_STAMINA_RECOVERY_MULTIPLIER = 0.8


def hunger_max_for_endurance(endurance_value: int) -> float:
    return BASE_HUNGER_MAX + (endurance_value - BASELINE_ENDURANCE) * ENDURANCE_MAX_BONUS_PER_POINT


def thirst_max_for_endurance(endurance_value: int) -> float:
    return BASE_THIRST_MAX + (endurance_value - BASELINE_ENDURANCE) * ENDURANCE_MAX_BONUS_PER_POINT


def _current_endurance(db: Session, character: Character) -> int:
    try:
        return get_character_attribute(db, character.id, CharacterAttributeKey.ENDURANCE).value
    except ValueError:
        return BASELINE_ENDURANCE


def recalculate_survival_max(db: Session, character: Character) -> None:
    """Call after ENDURANCE changes (or lazily whenever convenient — it's
    idempotent). Never raises current levels above the new max, but also
    never auto-refills; a bigger tank just means slower future drain."""
    endurance = _current_endurance(db, character)
    character.hunger_max = hunger_max_for_endurance(endurance)
    character.thirst_max = thirst_max_for_endurance(endurance)
    character.hunger_current = min(character.hunger_current, character.hunger_max)
    character.thirst_current = min(character.thirst_current, character.thirst_max)
    db.flush()


def apply_survival_decay(db: Session, campaign_id: str, character: Character) -> None:
    """Lazily catches up hunger/thirst to the current world time. Safe to
    call as often as convenient — zero elapsed time is a no-op. The
    first call for a character (survival_updated_at_minute is still
    NULL) only establishes the starting point, never drains a huge
    backlog of time the character existed before anyone started
    tracking it."""
    current_minute = get_world_time(db, campaign_id).total_minutes()

    if character.survival_updated_at_minute is None:
        character.survival_updated_at_minute = current_minute
        db.flush()
        return

    elapsed_minutes = current_minute - character.survival_updated_at_minute
    if elapsed_minutes <= 0:
        return

    elapsed_hours = elapsed_minutes / 60.0
    character.hunger_current = max(0.0, character.hunger_current - HUNGER_DECAY_PER_HOUR * elapsed_hours)
    character.thirst_current = max(0.0, character.thirst_current - THIRST_DECAY_PER_HOUR * elapsed_hours)
    character.survival_updated_at_minute = current_minute
    db.flush()


def feed(db: Session, character: Character, amount: float) -> None:
    if amount <= 0:
        raise ValueError("Feed amount must be positive.")
    character.hunger_current = min(character.hunger_max, character.hunger_current + amount)
    db.flush()


def drink(db: Session, character: Character, amount: float) -> None:
    if amount <= 0:
        raise ValueError("Drink amount must be positive.")
    character.thirst_current = min(character.thirst_max, character.thirst_current + amount)
    db.flush()


def _ratio(current: float, maximum: float) -> float:
    if maximum <= 0:
        return 0.0
    return current / maximum


def is_hunger_critical(character: Character) -> bool:
    return _ratio(character.hunger_current, character.hunger_max) < _LOW_THRESHOLD


def is_thirst_critical(character: Character) -> bool:
    return _ratio(character.thirst_current, character.thirst_max) < _LOW_THRESHOLD


def is_hunger_low(character: Character) -> bool:
    return _ratio(character.hunger_current, character.hunger_max) < _GOOD_THRESHOLD


def is_thirst_low(character: Character) -> bool:
    return _ratio(character.thirst_current, character.thirst_max) < _GOOD_THRESHOLD


def stamina_recovery_multiplier(character: Character) -> float:
    """A mild, non-punishing consequence — reused by
    app.game.combat.recovery.recover_character's stamina ratio. Never
    affects HP or mana recovery, never blocks resting itself."""
    if is_hunger_critical(character) or is_thirst_critical(character):
        return _CRITICAL_STAMINA_RECOVERY_MULTIPLIER
    if is_hunger_low(character) or is_thirst_low(character):
        return _LOW_STAMINA_RECOVERY_MULTIPLIER
    return 1.0
