"""Phase 19B/19C — Narrative Claim Extraction & Classification."""

from app.ai.validation.claims import ClaimCategory, classify_claim, extract_claims


def test_extract_claims_splits_at_sentence_boundaries():
    text = "Osgar entra na taverna carregando seu martelo. Ele reconhece Logan e acena."

    claims = extract_claims(text)

    assert [claim.text for claim in claims] == [
        "Osgar entra na taverna carregando seu martelo.",
        "Ele reconhece Logan e acena.",
    ]
    assert [claim.index for claim in claims] == [0, 1]


def test_purely_sensory_claim_is_never_classified_as_player_voluntary():
    categories = classify_claim(
        "O vento gelado arrepia a pele exposta.", character_name="Logan"
    )

    assert ClaimCategory.SENSORY in categories
    assert ClaimCategory.PLAYER_VOLUNTARY not in categories


def test_protagonist_voluntary_verb_is_classified_as_player_voluntary():
    categories = classify_claim("Logan sorri e decide seguir em frente.", character_name="Logan")

    assert ClaimCategory.PLAYER_VOLUNTARY in categories


def test_mixed_sensory_and_voluntary_claim_carries_both_categories():
    """Spec's own worked example: 'Logan feels the freezing wind and
    decides to return' is both SENSORY and PLAYER_VOLUNTARY — only the
    decision half should later be rejectable (19D), never the whole
    claim discarded just because it also contains valid sensation."""
    categories = classify_claim(
        "Logan sente o vento gelado e decide voltar.", character_name="Logan"
    )

    assert ClaimCategory.SENSORY in categories
    assert ClaimCategory.PLAYER_VOLUNTARY in categories


def test_voluntary_verb_without_the_protagonist_as_subject_is_not_flagged():
    """An NPC smiling/deciding is not a player-agency concern — only the
    protagonist's own voluntary behavior is restricted."""
    categories = classify_claim("Osgar sorri e acena para Logan.", character_name="Logan")

    assert ClaimCategory.PLAYER_VOLUNTARY not in categories


def test_persistent_entity_keywords_are_classified_as_persistent_canon():
    categories = classify_claim("Osgar tem uma filha chamada Elara.", character_name="Logan")

    assert ClaimCategory.PERSISTENT_CANON in categories


def test_mechanical_keywords_are_classified_as_mechanical():
    categories = classify_claim("O golpe acerta o alvo com força.", character_name="Logan")

    assert ClaimCategory.MECHANICAL in categories


def test_a_claim_mentioning_a_known_name_is_classified_as_authoritative():
    categories = classify_claim(
        "Osgar está sentado perto da fornalha.",
        character_name="Logan",
        known_names=("Osgar",),
    )

    assert ClaimCategory.AUTHORITATIVE in categories


def test_a_claim_matching_nothing_defaults_to_decorative():
    categories = classify_claim("A luz do fogo dança pela parede.", character_name="Logan")

    assert categories == frozenset({ClaimCategory.DECORATIVE})


# --- Phase 24G — NPC_DIALOGUE claim category ---


def test_dash_led_dialogue_is_classified_as_npc_dialogue():
    categories = classify_claim("— Sou Aldric, o ancião desta vila.", character_name="Logan")

    assert ClaimCategory.NPC_DIALOGUE in categories


def test_colon_attributed_dialogue_is_classified_as_npc_dialogue():
    # Screenplay-style attribution ("Nome: — fala") — the shape a local
    # model sometimes uses instead of the expected dash convention;
    # narrator.py already treats this as dialogue (_is_dialogue_paragraph),
    # and claim classification must not disagree with it.
    categories = classify_claim("Aldric: — Sim, é verdade.", character_name="Logan")

    assert ClaimCategory.NPC_DIALOGUE in categories


def test_quote_marked_dialogue_is_classified_as_npc_dialogue():
    categories = classify_claim('Aldric diz "Sim, é verdade."', character_name="Logan")

    assert ClaimCategory.NPC_DIALOGUE in categories


def test_plain_narration_is_not_classified_as_npc_dialogue():
    categories = classify_claim("A luz do fogo dança pela parede.", character_name="Logan")

    assert ClaimCategory.NPC_DIALOGUE not in categories


def test_extract_claims_classifies_each_sentence_independently():
    text = "Osgar entra na taverna. Logan sorri e o abraça."

    claims = extract_claims(text, character_name="Logan", known_names=("Osgar",))

    assert ClaimCategory.AUTHORITATIVE in claims[0].categories
    assert ClaimCategory.PLAYER_VOLUNTARY in claims[1].categories
    assert ClaimCategory.PLAYER_VOLUNTARY not in claims[0].categories
