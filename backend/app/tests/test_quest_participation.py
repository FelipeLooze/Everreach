"""Phase 12K — Quest Participation & Competition.

The protagonist is not the only capable actor. OPEN/OFFICIAL_BOUNTY
quests already allowed unlimited simultaneous participants (the prior
default behavior, unchanged) — CLAIMABLE and LIMITED now actually
enforce a cap, so a second character trying to start a claimed quest is
told "too late," not silently allowed to duplicate it. Competition itself
(someone else resolving it off-screen) is Phase 12A's already-existing
resolve_quest_externally — not rebuilt here.
"""

import pytest

from app.core.enums import QuestParticipationType, QuestSource
from app.game.character.service import create_character
from app.game.quests.service import (
    QuestLifecycleError,
    create_quest,
    start_quest,
)
from app.game.world.seed import create_campaign, seed_initial_region


def _setup(db_session, n=1):
    campaign = create_campaign(db_session, "Quest Participation")
    region, village = seed_initial_region(db_session, campaign.id)
    characters = [
        create_character(db_session, campaign.id, f"Hero{i}", region.id, village.id)
        for i in range(n)
    ]
    db_session.flush()
    return campaign, region, characters


def test_open_quest_has_no_participant_limit(db_session):
    campaign, region, characters = _setup(db_session, n=3)
    quest = create_quest(
        db_session, region.id, "Peles de lobo", source=QuestSource.NPC_REQUEST,
        participation_type=QuestParticipationType.OPEN,
    )

    for character in characters:
        cq = start_quest(db_session, character.id, quest.id)
        assert cq.status == "ACTIVE"


def test_official_bounty_has_no_participant_limit(db_session):
    campaign, region, characters = _setup(db_session, n=2)
    quest = create_quest(
        db_session, region.id, "Chefe bandido procurado", source=QuestSource.OFFICIAL_CONTRACT,
        participation_type=QuestParticipationType.OFFICIAL_BOUNTY,
    )

    for character in characters:
        cq = start_quest(db_session, character.id, quest.id)
        assert cq.status == "ACTIVE"


def test_claimable_quest_rejects_a_second_participant(db_session):
    campaign, region, characters = _setup(db_session, n=2)
    quest = create_quest(
        db_session, region.id, "Entregar carta", source=QuestSource.NPC_REQUEST,
        participation_type=QuestParticipationType.CLAIMABLE,
    )

    start_quest(db_session, characters[0].id, quest.id)
    with pytest.raises(QuestLifecycleError):
        start_quest(db_session, characters[1].id, quest.id)


def test_limited_quest_accepts_up_to_capacity(db_session):
    campaign, region, characters = _setup(db_session, n=5)
    quest = create_quest(
        db_session, region.id, "Guardas para a caravana", source=QuestSource.NPC_REQUEST,
        participation_type=QuestParticipationType.LIMITED, capacity=4,
    )

    for character in characters[:4]:
        cq = start_quest(db_session, character.id, quest.id)
        assert cq.status == "ACTIVE"

    with pytest.raises(QuestLifecycleError):
        start_quest(db_session, characters[4].id, quest.id)


def test_limited_quest_requires_a_capacity(db_session):
    campaign, region, characters = _setup(db_session)

    with pytest.raises(QuestLifecycleError):
        create_quest(
            db_session, region.id, "Guardas para a caravana", source=QuestSource.NPC_REQUEST,
            participation_type=QuestParticipationType.LIMITED,
        )


def test_claimable_quest_is_freed_by_the_claimant_abandoning(db_session):
    from app.game.quests.service import abandon_quest

    campaign, region, characters = _setup(db_session, n=2)
    quest = create_quest(
        db_session, region.id, "Entregar carta", source=QuestSource.NPC_REQUEST,
        participation_type=QuestParticipationType.CLAIMABLE,
    )

    start_quest(db_session, characters[0].id, quest.id)
    abandon_quest(db_session, campaign.id, characters[0].id, quest.id)

    cq = start_quest(db_session, characters[1].id, quest.id)
    assert cq.status == "ACTIVE"


def test_default_participation_type_is_open(db_session):
    campaign, region, characters = _setup(db_session)
    quest = create_quest(db_session, region.id, "Genérica", source=QuestSource.SELF_DISCOVERED)

    assert quest.participation_type == QuestParticipationType.OPEN
