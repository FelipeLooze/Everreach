"""Phase 24E — Conversational Act Grounding.

classify() is a small, deterministic, single-label taxonomy — not a
dialogue tree, not an LLM call. These tests lock in the classification
rules for the taxonomy's examples and the priority order (a question
always wins over an incidental greeting/farewell in the same sentence,
since answering what was actually asked is the behavior Phase 24A.1
fixed and this must not regress it).
"""
from app.ai.conversational_act import ConversationalAct, classify


def test_question_name_variants():
    assert classify("Qual o seu nome?") == ConversationalAct.QUESTION_NAME
    assert classify("Como você se chama?") == ConversationalAct.QUESTION_NAME


def test_question_location_variants():
    assert classify("Onde estou?") == ConversationalAct.QUESTION_LOCATION
    assert classify("Qual é o nome desta vila?") in (
        ConversationalAct.QUESTION_LOCATION,
        ConversationalAct.QUESTION_NAME,
    )


def test_question_person_and_object():
    assert classify("Quem é você?") == ConversationalAct.QUESTION_PERSON
    assert classify("O que é isso?") == ConversationalAct.QUESTION_OBJECT


def test_generic_question_falls_back_to_request_information():
    assert classify("Quanto tempo vai demorar?") == ConversationalAct.REQUEST_INFORMATION


def test_greeting_alone_is_not_a_question():
    assert classify("Olá, bom dia.") == ConversationalAct.GREETING


def test_greeting_with_a_question_is_classified_as_the_question():
    # Real regression case (24A.1 test_case1): a greeting attached to a
    # direct question must not dilute the question into a mere greeting.
    assert classify("Olá, bom dia senhor. Qual o seu nome?") == ConversationalAct.QUESTION_NAME


def test_farewell_variants():
    assert classify("Tchau, até logo.") == ConversationalAct.FAREWELL
    assert classify("Adeus.") == ConversationalAct.FAREWELL


def test_request_help_variants():
    assert classify("Preciso de ajuda.") == ConversationalAct.REQUEST_HELP
    assert classify("Socorro!") == ConversationalAct.REQUEST_HELP


def test_imperative_information_request_without_question_mark():
    assert classify("Me conte sobre esta vila.") == ConversationalAct.REQUEST_INFORMATION


def test_plain_statement_is_the_default():
    assert classify("Eu sento perto da fogueira.") == ConversationalAct.STATEMENT


def test_empty_input_is_a_statement():
    assert classify("") == ConversationalAct.STATEMENT
    assert classify("   ") == ConversationalAct.STATEMENT
