"""Contracts and schedules are learned only when actually told (2026-10-23)."""

from app.core.enums import KnowerType, NPCActivity
from app.db.models.job import Job
from app.db.models.location import LocationFeature
from app.db.models.notice import Notice
from app.db.models.npc import NPC
from app.db.models.quest import Quest
from app.game import schedules
from app.game.character.service import create_character
from app.game.economy.initial_content import ensure_initial_economy_for_campaign
from app.game.economy.playable import build_economy_view
from app.game.engine import resolve_action
from app.game.notices.service import read_notice_board
from app.game.npcs.service import knows
from app.game.quests import discovery
from app.game.time import clock
from app.game.world.seed import create_campaign, seed_initial_region

DAY = 24 * 60


def _world(db_session):
    campaign = create_campaign(db_session, "Quando")
    region, village = seed_initial_region(db_session, campaign.id)
    character = create_character(db_session, campaign.id, "Logan", region.id, village.id)
    assert ensure_initial_economy_for_campaign(db_session, campaign.id)
    db_session.flush()
    return campaign, character


def _set_hour(db_session, campaign_id, hour):
    now = clock.get_world_time(db_session, campaign_id).total_minutes()
    target = (now // DAY + 1) * DAY + hour * 60
    clock.advance_world_time(db_session, campaign_id, target - now)


def _npc(db_session, campaign_id, role):
    return db_session.query(NPC).filter(NPC.campaign_id == campaign_id, NPC.role == role).one()


# --- Part 1: contracts are learned only when named ---------------------------


def test_asking_about_work_teaches_only_the_contracts_actually_named(db_session):
    campaign, character = _world(db_session)
    elder = _npc(db_session, campaign.id, "ancião da vila")
    (quest,) = discovery.open_quests_known_by_npc(db_session, campaign.id, elder.id)

    told = discovery.tell_contracts(db_session, campaign.id, character.id, elder, "— A forja precisa de braços.")

    assert f'"{quest.name}"' in told and f"acrescenta {elder.name}" in told
    assert discovery.is_quest_known_to_character(db_session, campaign.id, character.id, quest.id)


def test_a_contract_already_named_is_not_repeated(db_session):
    campaign, character = _world(db_session)
    elder = _npc(db_session, campaign.id, "ancião da vila")
    (quest,) = discovery.open_quests_known_by_npc(db_session, campaign.id, elder.id)
    said = f'— Fale com a guilda sobre o "{quest.name}".'

    assert discovery.tell_contracts(db_session, campaign.id, character.id, elder, said) == said


# --- Part 2: when ---------------------------------------------------------------


def test_a_shift_must_fit_the_hours_and_hiring_tells_them(db_session, fake_llm):
    campaign, character = _world(db_session)
    blacksmith = _npc(db_session, campaign.id, "ferreira")
    blacksmith.activity = NPCActivity.WORKING.value
    character.location_id = blacksmith.workplace_location_id
    job = db_session.query(Job).filter(Job.title == "Ajudante de Ferreiro").one()
    _set_hour(db_session, campaign.id, 10)

    hired = resolve_action(db_session, fake_llm, campaign.id, character.id, '"Quero o trabalho."')
    assert "Turnos das 8h às 18h; um turno pode começar agora mesmo." in hired.mechanical_summary
    assert schedules.player_knows_job_schedule(db_session, campaign.id, character.id, job)

    assert schedules.shift_refusal(job, 10 * 60) is None
    assert schedules.shift_refusal(job, 15 * 60) is None  # 15h + 3h ends at 18h
    late = schedules.shift_refusal(job, 16 * 60)
    assert late and "precisa começar até as 15h" in late and "agora são 16h00" in late


def test_job_hours_are_unknown_until_the_notice_states_them_or_someone_tells(db_session):
    campaign, character = _world(db_session)
    forge_job = db_session.query(Job).filter(Job.title == "Ajudante de Ferreiro").one()
    inn_job = db_session.query(Job).filter(Job.title == "Ajudante da Estalagem").one()
    innkeeper = _npc(db_session, campaign.id, "estalajadeiro")

    def schedule_of(job):
        character.location_id = job.location_id
        return next(row for row in build_economy_view(db_session, character)["jobs"] if row["job_id"] == job.id)["schedule"]

    assert schedule_of(forge_job) == schedule_of(inn_job) == "desconhecido"

    board_notice = db_session.query(Notice).filter(Notice.title == forge_job.title).one()
    assert "Turnos das 8h às 18h." in board_notice.text
    board = db_session.get(LocationFeature, board_notice.board_feature_id)
    character.location_id = board.location_id
    read_notice_board(db_session, character.id, board.id)
    assert schedule_of(forge_job) == "das 8h às 18h"
    assert schedule_of(inn_job) == "desconhecido"  # the inn's notice does not say

    told = schedules.tell_schedules(
        db_session, campaign.id, character.id, innkeeper, "Que horas posso trabalhar aqui?", "— Quando quiser."
    )
    assert "das 8h às 18h" in told and f"explica {innkeeper.name}" in told
    assert schedule_of(inn_job) == "das 8h às 18h"


def test_contract_schedule_on_the_notice_or_from_the_guildmaster(db_session, client):
    campaign, character = _world(db_session)
    arrival = db_session.query(Quest).filter(Quest.name == "Relato da Primeira Chegada").one()
    liaison = db_session.query(Quest).filter(Quest.name == "Ronda dos Avisos").one()
    guildmaster = _npc(db_session, campaign.id, "mestre da guilda de aventureiros")
    for quest in (arrival, liaison):
        discovery.learn_about_quest_from_notice(db_session, campaign.id, character.id, quest.id)
    db_session.commit()

    def shown():
        quests = client.get(f"/api/campaigns/{campaign.id}/quests", params={"character_id": character.id}).json()
        return {quest["name"]: quest["schedule"] for quest in quests["quests"]}

    assert shown() == {arrival.name: "desconhecido", liaison.name: "desconhecido"}

    schedules.tell_schedules(
        db_session, campaign.id, character.id, guildmaster,
        "Quando preciso fazer a Ronda dos Avisos?", "— Ainda hoje, antes do anoitecer.",
    )
    db_session.commit()
    assert shown()[liaison.name] == "ainda hoje, antes do anoitecer"
    assert not knows(db_session, KnowerType.PLAYER, character.id, schedules.quest_schedule_fact_key(arrival), campaign.id)


# --- Part 3: small narration fixes ---------------------------------------------


def test_a_bystander_may_chime_in_once_during_a_conversation():
    from app.ai import narrator

    context = "VISIBLE NPCS\n- Wren Sernn (ferreira; activity=WORKING)\n- Aldric Talbrook (estalajadeiro; activity=WORKING)\n"
    one_aside = "— Doze bronze por turno — diz Wren Sernn.\n\n— E é pouco — resmunga Aldric Talbrook."
    two_asides = one_aside + "\n\n— Pouco mesmo — insiste Aldric Talbrook."

    assert narrator._find_unauthorized_speaker_violations(one_aside, context, "Wren Sernn") == []
    assert narrator._find_unauthorized_speaker_violations(two_asides, context, "Wren Sernn")
    # With nobody being talked to, a bystander still needs an entrance.
    assert narrator._find_unauthorized_speaker_violations("— E é pouco — resmunga Aldric Talbrook.", context, "")


def test_strangers_are_unnamed_and_never_met_npcs_are_marked(db_session):
    from app.ai.context_builder import build_context
    from app.game.game_state import build_game_state
    from app.game.players import service as players_service

    campaign, character = _world(db_session)
    state = build_game_state(db_session, campaign.id, character.id)
    stranger = state.nearby_simulated_players[0]

    context = build_context(db_session, state)
    visible = context.split("VISIBLE TRANSPORTED PEOPLE", 1)[1].split("\n\n", 1)[0]
    assert stranger.name not in visible and "never name them" in visible
    assert "has NEVER met the character" in context

    players_service.meet_simulated_player(db_session, campaign.id, character.id, stranger.id)
    met = build_context(db_session, build_game_state(db_session, campaign.id, character.id))
    assert stranger.name in met.split("VISIBLE TRANSPORTED PEOPLE", 1)[1].split("\n\n", 1)[0]


def test_an_npc_answer_after_a_beat_naming_the_player_as_object_is_kept():
    from app.ai import narrator

    text = (
        "O ancião ergue o queixo na direção de Logan antes de responder.\n\n"
        "— Trabalho há, sim, meu jovem. A forja precisa de braços, e eu posso te indicar o seu caminho até lá."
    )
    assert narrator._fabricated_turn_violations(text, "Logan", "Garrick Wystan") == []
    fabricated = "Logan respira fundo e responde.\n\n— Eu vou com o senhor, então."
    assert narrator._fabricated_turn_violations(fabricated, "Logan", "Garrick Wystan")


def test_the_added_contract_line_reads_naturally_when_nothing_was_said(db_session):
    campaign, character = _world(db_session)
    elder = _npc(db_session, campaign.id, "ancião da vila")
    (quest,) = discovery.open_quests_known_by_npc(db_session, campaign.id, elder.id)

    told = discovery.tell_contracts(db_session, campaign.id, character.id, elder, "O ancião pensa um instante.")

    assert f'— Há o contrato "{quest.name}" — diz {elder.name}.' in told


def test_a_contract_the_player_already_knows_is_not_announced_again(db_session):
    campaign, character = _world(db_session)
    elder = _npc(db_session, campaign.id, "ancião da vila")
    (quest,) = discovery.open_quests_known_by_npc(db_session, campaign.id, elder.id)
    discovery.learn_about_quest_from_npc(db_session, campaign.id, character.id, quest.id)
    said = "— Pode ser feito a qualquer hora do dia."

    assert discovery.tell_contracts(db_session, campaign.id, character.id, elder, said) == said


def test_the_elder_is_found_by_his_white_beard_or_hair(db_session):
    from app.game import engine
    from app.game.visual.npc import resolve_npc_appearance

    campaign, character = _world(db_session)
    square_npcs = db_session.query(NPC).filter(NPC.location_id == character.location_id).all()
    elder = _npc(db_session, campaign.id, "ancião da vila")

    for text in (
        'Ir falar com o homem de barba branca "Ola, bom dia, senhor. Tudo bem?"',
        "Vou falar com o senhor de cabelos brancos: Ola senhor, bom dia, tudo bem?",
    ):
        npcs, players = engine._addressed_candidates(text, square_npcs, [])
        assert npcs == [elder] and players == []
    assert resolve_npc_appearance(db_session, campaign.id, elder.id)["hair_color"] == "white hair"
