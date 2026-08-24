"""Phase 24A.1 — recent-history framing regression tests.

Real root cause confirmed by the Phase 24A live audit: build_recent_history
used to literally emit "PLAYER: ...\\nNARRATOR: ..." per turn — the exact
shape the model later reproduced as a fabricated multi-turn continuation,
because nothing distinguished "this already happened" from "this is a
script to continue." These tests lock in the new bounded framing.
"""
from dataclasses import dataclass

from app.ai.context_builder import build_recent_history


@dataclass
class _Entry:
    kind: str
    text: str


def test_recent_history_no_longer_uses_bare_player_narrator_labels():
    entries = [
        _Entry("player", "Olá, bom dia."),
        _Entry("narrator", "— Bom dia — responde o ancião."),
    ]
    history = build_recent_history(entries)

    assert "PLAYER:" not in history
    assert "NARRATOR:" not in history


def test_recent_history_wraps_content_in_explicit_historical_framing():
    entries = [
        _Entry("player", "Olá, bom dia."),
        _Entry("narrator", "— Bom dia — responde o ancião."),
    ]
    history = build_recent_history(entries)

    assert history.startswith("HISTÓRICO DE TROCAS RECENTES")
    assert history.rstrip().endswith("FIM DO HISTÓRICO DE TROCAS RECENTES")
    assert "Não continue este histórico" in history
    assert "Não gere um novo turno do jogador" in history


def test_recent_history_preserves_speaker_ownership_and_order():
    entries = [
        _Entry("player", "Qual o seu nome?"),
        _Entry("narrator", "— Sou Aldric — diz o ancião."),
        _Entry("player", "Onde estou?"),
        _Entry("narrator", "— Em Corford — responde ele."),
    ]
    history = build_recent_history(entries)

    first_turn = history.index("Turno 1:")
    second_turn = history.index("Turno 2:")
    assert first_turn < second_turn

    turn_1 = history[first_turn:second_turn]
    assert 'O jogador disse anteriormente: "Qual o seu nome?"' in turn_1
    assert 'Resposta narrada anteriormente: "— Sou Aldric — diz o ancião."' in turn_1

    turn_2 = history[second_turn:]
    assert 'O jogador disse anteriormente: "Onde estou?"' in turn_2
    assert 'Resposta narrada anteriormente: "— Em Corford — responde ele."' in turn_2


def test_recent_history_handles_leading_world_started_narration():
    # WORLD_STARTED contributes a lone narrator-only entry with no
    # preceding player turn — must never be mistaken for a player line
    # or silently dropped.
    entries = [
        _Entry("narrator", "A praça está cheia de recém-chegados."),
        _Entry("player", "Olhar ao redor"),
        _Entry("narrator", "Nada acontece de imediato."),
    ]
    history = build_recent_history(entries)

    assert "Narração inicial da cena (não é uma fala do jogador):" in history
    assert '"A praça está cheia de recém-chegados."' in history
    assert "Turno 1:" in history
    assert 'O jogador disse anteriormente: "Olhar ao redor"' in history


def test_recent_history_empty_stays_a_plain_marker():
    assert build_recent_history([]) == "(nenhuma troca anterior nesta cena)"
