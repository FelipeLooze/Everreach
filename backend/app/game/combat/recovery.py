import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.enums import CharacterStatus, CombatActorType, EventType, RecoveryType
from app.db.models.character import Character
from app.db.models.recovery import CharacterRecovery
from app.game.combat.encounters import get_active_encounter_for_actor
from app.game.survival.service import stamina_recovery_multiplier
from app.game.time.clock import get_world_time
from app.services.event_log import log_event


SHORT_REST_MINUTES = 60
_RECOVERY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,179}$")
_RECOVERY_RATIOS = {
    "hp": 0.25,
    "mana": 0.25,
    "stamina": 0.5,
}


class CombatRecoveryError(ValueError):
    pass


@dataclass(frozen=True)
class RecoveryResolution:
    recovery: CharacterRecovery
    replayed: bool = False

    @property
    def mechanical_summary(self) -> str:
        row = self.recovery
        return (
            f"{row.character.name} descansa por {row.duration_minutes} minutos. "
            f"Recuperação: HP +{_amount(row.hp_before, row.hp_after)}, "
            f"Mana +{_amount(row.mana_before, row.mana_after)} e "
            f"Stamina +{_amount(row.stamina_before, row.stamina_after)}."
        )


def recover_character(
    db: Session,
    campaign_id: str,
    character: Character,
    *,
    recovery_key: str,
    recovery_type: RecoveryType = RecoveryType.SHORT_REST,
) -> RecoveryResolution:
    normalized_key = recovery_key.strip().lower()
    if not _RECOVERY_KEY_PATTERN.fullmatch(normalized_key):
        raise CombatRecoveryError("Invalid recovery key.")
    if character.campaign_id != campaign_id:
        raise CombatRecoveryError("Character does not belong to campaign.")
    if not isinstance(recovery_type, RecoveryType):
        raise CombatRecoveryError("Invalid recovery type.")

    existing = (
        db.query(CharacterRecovery)
        .filter(
            CharacterRecovery.character_id == character.id,
            CharacterRecovery.recovery_key == normalized_key,
        )
        .one_or_none()
    )
    if existing is not None:
        if existing.recovery_type != recovery_type.value:
            raise CombatRecoveryError("Recovery key already belongs to another recovery.")
        return RecoveryResolution(existing, replayed=True)

    if character.status == CharacterStatus.DEAD.value or character.hp_current <= 0:
        raise CombatRecoveryError("Dead characters cannot recover.")
    if (
        get_active_encounter_for_actor(
            db,
            CombatActorType.CHARACTER,
            character.id,
        )
        is not None
    ):
        raise CombatRecoveryError("Characters cannot rest during active combat.")

    before = {
        "hp": float(character.hp_current),
        "mana": float(character.mana_current),
        "stamina": float(character.stamina_current),
    }
    ratios = dict(_RECOVERY_RATIOS)
    ratios["stamina"] *= stamina_recovery_multiplier(character)
    after = {
        key: min(
            float(getattr(character, f"{key}_max")),
            value
            + round(
                float(getattr(character, f"{key}_max")) * ratios[key],
                1,
            ),
        )
        for key, value in before.items()
    }
    character.hp_current = after["hp"]
    character.mana_current = after["mana"]
    character.stamina_current = after["stamina"]

    recovery = CharacterRecovery(
        campaign_id=campaign_id,
        character_id=character.id,
        recovery_key=normalized_key,
        recovery_type=recovery_type.value,
        duration_minutes=SHORT_REST_MINUTES,
        started_world_minute=get_world_time(db, campaign_id).total_minutes(),
        hp_before=before["hp"],
        hp_after=after["hp"],
        mana_before=before["mana"],
        mana_after=after["mana"],
        stamina_before=before["stamina"],
        stamina_after=after["stamina"],
    )
    db.add(recovery)
    db.flush()
    log_event(
        db,
        campaign_id,
        EventType.PLAYER_RESTED,
        actor_type="character",
        actor_id=character.id,
        payload={
            "recovery_id": recovery.id,
            "recovery_type": recovery.recovery_type,
            "duration_minutes": recovery.duration_minutes,
            "hp": {"before": recovery.hp_before, "after": recovery.hp_after},
            "mana": {
                "before": recovery.mana_before,
                "after": recovery.mana_after,
            },
            "stamina": {
                "before": recovery.stamina_before,
                "after": recovery.stamina_after,
            },
        },
    )
    db.flush()
    return RecoveryResolution(recovery)


def _amount(before: float, after: float) -> str:
    return f"{after - before:.1f}".rstrip("0").rstrip(".")
