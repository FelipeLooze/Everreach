"""Grounded quest opportunities for the first settlement.

The boards do not generate content when opened. This module runs once while
the initial world package is seeded: organizations create needs, sponsor real
quests, and publish notices that merely expose those already-existing quests.
"""

from sqlalchemy.orm import Session

from app.core.enums import (
    KnowerType,
    KnowledgeCertainty,
    NoticeCategory,
    ObjectiveTriggerType,
    ObjectiveType,
    OrganizationNeedCategory,
    QuestParticipationType,
)
from app.db.models.location import Location, LocationFeature
from app.db.models.npc import NPC
from app.db.models.organization import Organization
from app.db.models.quest import QuestObjective
from app.db.models.region import Region
from app.game.npcs.service import teach_fact
from app.game.notices.service import post_notice
from app.game.organizations.goals import create_goal, create_need
from app.game.organizations.opportunities import (
    publish_organization_notice,
    sponsor_quest,
)
from app.game.quests.service import quest_existence_fact_key


def ensure_initial_quest_opportunities_for_campaign(
    db: Session, campaign_id: str
) -> bool:
    """Backfill the initial boards/contracts for a world seeded before this feature.

    Returns True only when content was created. New worlds already receive the
    same package directly from seed_initial_region; this function is primarily
    the data-migration bridge for existing local saves.
    """
    existing_guild_board = (
        db.query(LocationFeature)
        .join(Location, Location.id == LocationFeature.location_id)
        .join(Region, Region.id == Location.region_id)
        .filter(
            Region.campaign_id == campaign_id,
            LocationFeature.name == "Quadro de Contratos da Guilda",
        )
        .first()
    )
    if existing_guild_board is not None:
        return False

    guild_location = (
        db.query(Location)
        .join(Region, Region.id == Location.region_id)
        .filter(
            Region.campaign_id == campaign_id,
            Location.type == "adventurers_guild",
            Location.parent_location_id.isnot(None),
        )
        .first()
    )
    if guild_location is None:
        return False
    village = db.get(Location, guild_location.parent_location_id)
    if village is None:
        return False
    public_board_location = (
        db.query(Location)
        .filter(
            Location.parent_location_id == village.id,
            Location.type == "notice_board",
        )
        .first()
    )
    region = db.get(Region, village.region_id)
    elder = (
        db.query(NPC)
        .filter(NPC.campaign_id == campaign_id, NPC.role == "ancião da vila")
        .first()
    )
    guildmaster = (
        db.query(NPC)
        .filter(
            NPC.campaign_id == campaign_id,
            NPC.workplace_location_id == guild_location.id,
            NPC.role == "mestre da guilda de aventureiros",
        )
        .first()
    )
    adventurers_guild = (
        db.query(Organization)
        .filter(
            Organization.campaign_id == campaign_id,
            Organization.headquarters_location_id == guild_location.id,
        )
        .first()
    )
    village_organization = (
        db.query(Organization)
        .filter(
            Organization.campaign_id == campaign_id,
            Organization.headquarters_location_id == village.id,
        )
        .first()
    )
    if any(
        value is None
        for value in (
            public_board_location,
            region,
            elder,
            guildmaster,
            adventurers_guild,
            village_organization,
        )
    ):
        return False

    seed_initial_quest_opportunities(
        db,
        campaign_id=campaign_id,
        region=region,
        village=village,
        elder=elder,
        village_organization=village_organization,
        adventurers_guild=adventurers_guild,
        guildmaster=guildmaster,
        guild_location=guild_location,
        public_board_location=public_board_location,
    )
    return True


def seed_initial_quest_opportunities(
    db: Session,
    *,
    campaign_id: str,
    region: Region,
    village: Location,
    elder: NPC,
    village_organization: Organization,
    adventurers_guild: Organization,
    guildmaster: NPC,
    guild_location: Location,
    public_board_location: Location,
) -> tuple[LocationFeature, LocationFeature]:
    public_board = LocationFeature(
        location_id=public_board_location.id,
        name=f"Quadro de Avisos de {village.name}",
        description=(
            "Um quadro público para comunicados, trabalho, comércio, alertas e "
            "necessidades da comunidade. Nem todo aviso é um contrato."
        ),
    )
    guild_board = LocationFeature(
        location_id=guild_location.id,
        name="Quadro de Contratos da Guilda",
        description=(
            "Contratos formais publicados pela Guilda de Aventureiros, com "
            "responsáveis e condições registradas."
        ),
    )
    db.add_all((public_board, guild_board))
    db.flush()

    post_notice(
        db,
        campaign_id,
        public_board.id,
        category=NoticeCategory.COMMUNITY_NOTICE,
        title="Orientação aos recém-chegados",
        text=(
            "Os Transportados que precisarem de orientação podem procurar a "
            f"praça, a estalagem ou a Guilda de Aventureiros de {village.name}."
        ),
        author_organization_id=village_organization.id,
    )

    arrival_goal = create_goal(
        db,
        adventurers_guild,
        "Compreender os efeitos da chegada dos Transportados sobre a comunidade.",
        priority=8,
    )
    arrival_need = create_need(
        db,
        adventurers_guild,
        "Reunir um relato local confiável sobre a Primeira Chegada.",
        category=OrganizationNeedCategory.INFORMATION,
        priority=8,
        goal_id=arrival_goal.id,
    )
    arrival_quest = sponsor_quest(
        db,
        adventurers_guild,
        region.id,
        "Relato da Primeira Chegada",
        (
            f"A guilda quer registrar como a chegada dos Transportados afetou {village.name}. "
            f"Converse com o ancião {elder.name} e leve o relato ao mestre da guilda."
        ),
        objectives=(
            f"Converse com {elder.name} sobre o que ocorreu durante a Primeira Chegada.",
            f"Leve o relato a {guildmaster.name}, mestre da Guilda de Aventureiros.",
        ),
        participation_type=QuestParticipationType.CLAIMABLE,
        xp_reward=10.0,
    )
    _configure_objectives(
        db,
        arrival_quest.id,
        (
            (ObjectiveType.INVESTIGATION, ObjectiveTriggerType.TALK_TO_NPC, elder.id, None),
            (ObjectiveType.DELIVERY, ObjectiveTriggerType.TALK_TO_NPC, guildmaster.id, 0),
        ),
    )
    publish_organization_notice(
        db,
        adventurers_guild,
        guild_board.id,
        category=NoticeCategory.QUEST_REQUEST,
        title=arrival_quest.name,
        text=arrival_quest.description,
        need_id=arrival_need.id,
        quest_id=arrival_quest.id,
    )

    liaison_goal = create_goal(
        db,
        adventurers_guild,
        "Manter os contratos da guilda ligados às necessidades públicas da vila.",
        priority=6,
    )
    liaison_need = create_need(
        db,
        adventurers_guild,
        "Conferir os avisos comunitários e trazer as prioridades atuais à guilda.",
        category=OrganizationNeedCategory.INFORMATION,
        priority=6,
        goal_id=liaison_goal.id,
    )
    liaison_quest = sponsor_quest(
        db,
        adventurers_guild,
        region.id,
        "Ronda dos Avisos",
        (
            f"Leia o quadro público de {village.name} e relate ao mestre da guilda "
            "o que a comunidade está divulgando."
        ),
        objectives=(
            f"Leia o Quadro de Avisos de {village.name}.",
            f"Converse com {guildmaster.name} depois de conferir o quadro público.",
        ),
        participation_type=QuestParticipationType.CLAIMABLE,
        xp_reward=15.0,
    )
    _configure_objectives(
        db,
        liaison_quest.id,
        (
            (ObjectiveType.OBSERVATION, ObjectiveTriggerType.READ_NOTICE_BOARD, public_board.id, None),
            (ObjectiveType.DELIVERY, ObjectiveTriggerType.TALK_TO_NPC, guildmaster.id, 0),
        ),
    )
    publish_organization_notice(
        db,
        adventurers_guild,
        guild_board.id,
        category=NoticeCategory.QUEST_REQUEST,
        title=liaison_quest.name,
        text=liaison_quest.description,
        need_id=liaison_need.id,
        quest_id=liaison_quest.id,
    )

    for quest, informed_npcs in (
        (arrival_quest, (guildmaster, elder)),
        (liaison_quest, (guildmaster,)),
    ):
        for npc in informed_npcs:
            teach_fact(
                db,
                campaign_id,
                quest_existence_fact_key(quest.id),
                KnowerType.NPC,
                npc.id,
                source="organization_contract",
                certainty=KnowledgeCertainty.CONFIRMED,
            )

    return public_board, guild_board


def _configure_objectives(
    db: Session,
    quest_id: str,
    configurations: tuple[
        tuple[ObjectiveType, ObjectiveTriggerType, str, int | None], ...
    ],
) -> None:
    objectives = (
        db.query(QuestObjective)
        .filter(QuestObjective.quest_id == quest_id)
        .order_by(QuestObjective.order)
        .all()
    )
    if len(objectives) != len(configurations):
        raise ValueError("A configuração mecânica não corresponde aos objetivos da missão.")
    for objective, (objective_type, trigger_type, subject_id, prerequisite_order) in zip(
        objectives, configurations, strict=True
    ):
        objective.objective_type = objective_type
        objective.trigger_type = trigger_type
        objective.trigger_subject_id = subject_id
        objective.prerequisite_objective_id = (
            objectives[prerequisite_order].id
            if prerequisite_order is not None
            else None
        )
    db.flush()
