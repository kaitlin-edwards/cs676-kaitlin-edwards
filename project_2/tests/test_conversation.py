"""
Tests for the conversation loop and the orchestrator's intent routing.

Everything runs against ScriptedLLM, so the whole suite is offline and free.
"""

import pytest

from personaforge import (
    Orchestrator,
    PersonaSpec,
    agent_from_spec,
    run_conversation,
    save_persona,
    save_transcript,
)
from personaforge.llm import ScriptedLLM
from personaforge.conversation import Turn, choose_next_speaker

PERSONA_MD = """---
name: {name}
role: {role}
summary: a summary
---

# {name}
Body text.
"""


def two_agents(replies=None):
    llm = ScriptedLLM(replies=replies or ["line A", "line B"])
    a = agent_from_spec(PersonaSpec(name="Alice", role="doctor", summary="", body="A"), llm)
    b = agent_from_spec(PersonaSpec(name="Bob", role="patient", summary="", body="B"), llm)
    return a, b, llm


def test_conversation_alternates_speakers():
    a, b, _ = two_agents()
    convo = run_conversation([a, b], topic="the results", turns=4)

    assert [t.speaker for t in convo.turns] == ["Alice", "Bob", "Alice", "Bob"]


def test_conversation_respects_turn_count():
    a, b, _ = two_agents()
    assert len(run_conversation([a, b], topic="x", turns=5).turns) == 5


def test_conversation_needs_two_agents():
    a, _, _ = two_agents()
    with pytest.raises(ValueError):
        run_conversation([a], topic="x", turns=2)


def test_on_turn_fires_per_turn():
    a, b, _ = two_agents()
    seen = []
    run_conversation([a, b], topic="x", turns=3, on_turn=seen.append)

    assert len(seen) == 3
    assert seen[0].speaker == "Alice"


def test_topic_reaches_the_agents():
    """The scene turn must be visible to the first speaker."""
    a, b, llm = two_agents()
    run_conversation([a, b], topic="UNIQUE_TOPIC_MARKER", turns=1)

    first_call = llm.calls[0]["messages"]
    assert any("UNIQUE_TOPIC_MARKER" in m["content"] for m in first_call)


def test_transcript_contains_every_line():
    a, b, _ = two_agents(replies=["hello", "hi there"])
    convo = run_conversation([a, b], topic="greetings", turns=2)
    text = convo.transcript()

    assert "Alice" in text and "Bob" in text
    assert "hello" in text and "hi there" in text


def test_save_transcript_writes_a_file(tmp_path):
    a, b, _ = two_agents()
    convo = run_conversation([a, b], topic="x", turns=2)
    path = save_transcript(convo, tmp_path)

    assert path.exists()
    assert "Alice" in path.read_text(encoding="utf-8")


# -- orchestrator routing -----------------------------------------------------


def test_create_persona_writes_a_file(tmp_path):
    llm = ScriptedLLM(replies=[PERSONA_MD.format(name="Maria Delgado", role="patient")])
    orch = Orchestrator(llm=llm, persona_dir=tmp_path)

    result = orch.handle("create a persona patient with back pain")

    assert "Maria Delgado" in result.reply
    assert (tmp_path / "maria-delgado.md").exists()


def test_list_personas_reports_what_exists(tmp_path):
    save_persona(PersonaSpec(name="Maria Delgado", role="patient", summary="s", body="b"), tmp_path)
    orch = Orchestrator(llm=ScriptedLLM(), persona_dir=tmp_path)

    assert "Maria Delgado" in orch.handle("list personas").reply


def test_list_personas_when_empty(tmp_path):
    orch = Orchestrator(llm=ScriptedLLM(), persona_dir=tmp_path)
    assert "No personas yet" in orch.handle("list personas").reply


def test_conversation_requires_two_personas(tmp_path):
    save_persona(PersonaSpec(name="Solo", role="patient", summary="", body="b"), tmp_path)
    orch = Orchestrator(llm=ScriptedLLM(), persona_dir=tmp_path)

    assert "at least two" in orch.handle("have them talk about the weather").reply


def test_conversation_runs_with_two_personas(tmp_path):
    for name, role in [("Alice Adams", "doctor"), ("Bob Brown", "patient")]:
        save_persona(PersonaSpec(name=name, role=role, summary="", body="b"), tmp_path)

    orch = Orchestrator(llm=ScriptedLLM(replies=["a line"]), persona_dir=tmp_path)
    result = orch.handle("have them talk about the test results")

    assert result.conversation is not None
    assert len(result.conversation.turns) == 9  # 6 open turns + closing note + 2 last words
    assert (tmp_path / "conversation.md").exists()


def test_named_participants_are_resolved(tmp_path):
    for name, role in [("Alice Adams", "doctor"), ("Bob Brown", "patient"), ("Carol Chen", "nurse")]:
        save_persona(PersonaSpec(name=name, role=role, summary="", body="b"), tmp_path)

    orch = Orchestrator(llm=ScriptedLLM(replies=["x"]), persona_dir=tmp_path)
    result = orch.handle("start a conversation between Carol and Bob about the chart")

    assert result.conversation is not None
    assert set(result.conversation.participants) == {"Carol Chen", "Bob Brown"}


def test_unknown_participant_is_reported(tmp_path):
    for name in ["Alice Adams", "Bob Brown"]:
        save_persona(PersonaSpec(name=name, role="x", summary="", body="b"), tmp_path)

    orch = Orchestrator(llm=ScriptedLLM(), persona_dir=tmp_path)
    result = orch.handle("start a conversation between Zaphod and Bob about lunch")

    assert "couldn't find" in result.reply


def test_unmatched_input_falls_through_to_chat(tmp_path):
    llm = ScriptedLLM(replies=["Tell me who you want to build."])
    orch = Orchestrator(llm=llm, persona_dir=tmp_path)

    result = orch.handle("hello, what is this thing?")

    assert result.reply == "Tell me who you want to build."
    assert result.conversation is None

# -- choosing the next speaker -----------------------------------------------


def four_runners():
    llm = ScriptedLLM()
    names = ["Dana Reilly", "Erin Billstein", "Katie Smith", "Susan Canning"]
    return [agent_from_spec(PersonaSpec(name=n, role="runner", summary="", body=n), llm) for n in names]


def test_last_named_person_speaks_next():
    """From the real 'before' run: Katie asked Erin something, then Dana."""
    runners = four_runners()
    line = "Erin, you packed glitter? But Dana, you good with just gels?"
    assert choose_next_speaker(line, "Katie Smith", runners).name == "Dana Reilly"


def test_name_inside_another_word_does_not_count():
    runners = four_runners()
    line = "I've been dancing around this all morning."  # 'dan' in 'dancing', not 'Dana'
    assert choose_next_speaker(line, "Susan Canning", runners).name == "Dana Reilly"



def test_conversation_follows_who_was_addressed():
    """Susan is asked directly; when nobody is named, Katie, who hasn't spoken yet, gets the floor."""
    llm = ScriptedLLM(replies=["Susan, are you nervous?", "A little, yeah.", "Katie, what's your pace?"])
    dana, katie, susan = (
        agent_from_spec(PersonaSpec(name=n, role="runner", summary="", body=n), llm)
        for n in ["Dana Reilly", "Katie Smith", "Susan Canning"]
    )
    convo = run_conversation([dana, katie, susan], topic="the corral", turns=4)

    assert [t.speaker for t in convo.turns] == ["Dana Reilly", "Susan Canning", "Katie Smith", "Dana Reilly"]


def test_quiet_runner_gets_the_floor_when_nobody_is_named():
    """The midway run: Dana and Erin ping-ponged and Susan never spoke."""
    runners = four_runners()
    history = [
        Turn("Dana Reilly", "a"),
        Turn("Erin Billstein", "b"),
        Turn("Katie Smith", "c"),
        Turn("Dana Reilly", "d"),
        Turn("Erin Billstein", "e"),
    ]
    assert choose_next_speaker("No names here.", "Erin Billstein", runners, history).name == "Susan Canning"


def test_runner_who_leaves_stops_speaking():
    llm = ScriptedLLM(replies=["Gotta find a porta-potty. [LEAVES]", "Bye!", "Just us now."])
    dana, katie, susan = (
        agent_from_spec(PersonaSpec(name=n, role="runner", summary="", body=n), llm)
        for n in ["Dana Reilly", "Katie Smith", "Susan Canning"]
    )
    convo = run_conversation([dana, katie, susan], topic="the corral", turns=4)
    speakers = [t.speaker for t in convo.turns]

    assert speakers[:2] == ["Dana Reilly", "Scene"]  # she spoke, then the exit note
    assert "Dana Reilly" not in speakers[2:]         # and never again
    assert "[LEAVES]" not in convo.transcript()      # marker hidden from the dialogue


def test_conversation_ends_when_one_person_is_left():
    a, b, _ = two_agents(replies=["See you at the finish! [leaves]"])  # lowercase on purpose
    convo = run_conversation([a, b], topic="x", turns=6)

    assert [t.speaker for t in convo.turns] == ["Alice", "Scene"]

def test_closing_gives_everyone_a_last_word():
    a, b, _ = two_agents()
    convo = run_conversation([a, b], topic="x", turns=2, closing="Corral closing!")

    assert [t.speaker for t in convo.turns] == ["Alice", "Bob", "Scene", "Alice", "Bob"]
    assert convo.turns[2].text == "Corral closing!"


def test_no_closing_when_everyone_already_left():
    a, b, _ = two_agents(replies=["Bye! [LEAVES]"])
    convo = run_conversation([a, b], topic="x", turns=4, closing="Corral closing!")

    assert "Corral closing!" not in convo.transcript()

def test_closing_lets_the_quietest_speak_first():
    """The 'after' run: Susan was left out, then got the very last word and nobody could answer her."""
    llm = ScriptedLLM(replies=["Katie, ready?", "Dana, yes.", "Last word."])
    dana, katie, susan = (
        agent_from_spec(PersonaSpec(name=n, role="runner", summary="", body=n), llm)
        for n in ["Dana Reilly", "Katie Smith", "Susan Canning"]
    )
    convo = run_conversation([dana, katie, susan], topic="the corral", turns=2, closing="Corral closing!")

    assert [t.speaker for t in convo.turns] == [
        "Dana Reilly", "Katie Smith", "Scene", "Susan Canning", "Dana Reilly", "Katie Smith"
    ]