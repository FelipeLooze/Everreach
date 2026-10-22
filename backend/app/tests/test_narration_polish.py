"""Playtest regressions: second-person narration and mechanical readouts.

The narrator prompt asks for third person and no game internals, yet live
turns came back as "Você chega à ferraria...", "São 08:16." and "a trilha que
leva ao local desconhecido". polish_player_facing_text fixes these outside
spoken dialogue only.
"""
from app.ai import narrator
from app.ai.narrator import polish_player_facing_text


def test_second_person_narration_becomes_the_protagonist_name():
    text = (
        "Você chega à ferraria após poucos minutos de caminhada.\n\n"
        "Wren interrompe o golpe e olha para você."
    )

    assert polish_player_facing_text(text, "Logan") == (
        "Logan chega à ferraria após poucos minutos de caminhada.\n\n"
        "Wren interrompe o golpe e olha para Logan."
    )


def test_dialogue_keeps_its_second_person():
    dash_dialogue = "— Você sabe lutar? — pergunta ela, olhando para você. — Se não, vá embora."
    quoted_dialogue = 'Ele diz "Você vem comigo?" e espera você responder.'

    assert polish_player_facing_text(dash_dialogue, "Logan") == (
        "— Você sabe lutar? — pergunta ela, olhando para Logan. — Se não, vá embora."
    )
    assert polish_player_facing_text(quoted_dialogue, "Logan") == (
        'Ele diz "Você vem comigo?" e espera Logan responder.'
    )


def test_plural_voces_is_left_alone():
    assert polish_player_facing_text("Vocês dois chegaram juntos.", "Logan") == (
        "Vocês dois chegaram juntos."
    )


def test_clock_time_and_stat_readouts_are_dropped_from_narration():
    text = (
        "A praça está como antes.\n\n"
        "São 08:16. Sua Stamina mal foi tocada. O vento sopra (distância 0.2) do leste."
    )

    assert polish_player_facing_text(text, "Logan") == "A praça está como antes."


def test_spoken_clock_time_is_kept():
    text = "— Volte às 12:00 — diz a ferreira."

    assert polish_player_facing_text(text, "Logan") == text


def test_unknown_place_placeholder_reads_as_prose():
    text = "A trilha que leva ao local desconhecido a leste segue entre as casas."

    assert polish_player_facing_text(text, "Logan") == (
        "A trilha que leva ao lugar que Logan ainda não conhece a leste segue entre as casas."
    )


def test_text_made_only_of_readouts_is_returned_unchanged():
    assert polish_player_facing_text("São 08:16.", "Logan") == "São 08:16."


def test_narrate_applies_the_polish_using_the_context_name(monkeypatch):
    monkeypatch.setattr(narrator, "_narrate_draft", lambda *args, **kwargs: "Você chega à praça.")
    context = "CURRENT PLAYER\nName: Logan (narrator metadata; NPCs do not know it automatically)\n"

    assert narrator.narrate(None, "", context, "", "") == "Logan chega à praça."
