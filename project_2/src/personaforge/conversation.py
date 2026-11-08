"""
conversation.py — put two or more agents in a room and let them talk.

The loop is deliberately dumb: agents take strict turns in the order given, for
a fixed number of turns, and then it stops. No agent decides who speaks next and
no agent can interrupt. Making that smarter is one of the more interesting
things you can do with this project.
"""

from __future__ import annotations
import re

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .agent import PersonaAgent

# How an agent signals it is walking away. Matched loosely ("[leaves]", "[ LEAVE ]")
# because models are inconsistent about exact formatting — strict about the
# meaning, generous about the spelling.
LEAVE_PATTERN = re.compile(r"\[\s*leaves?\s*\]", re.IGNORECASE)
# Announced when a conversation's time is up; everyone still present gets one last line.
DEFAULT_CLOSING = "Time's nearly up. Everyone gets one last word before this ends."


@dataclass
class Turn:
    """One line of dialogue."""

    speaker: str
    text: str


@dataclass
class Conversation:
    """A completed dialogue, plus the setup that produced it."""

    topic: str
    participants: List[str]
    turns: List[Turn] = field(default_factory=list)

    def transcript(self) -> str:
        """Render as plain text, suitable for saving or printing."""
        header = f"# Conversation: {self.topic}\n\nParticipants: {', '.join(self.participants)}\n\n"
        return header + "\n\n".join(f"**{t.speaker}:** {t.text}" for t in self.turns)

def _last_spoke(agents: List[PersonaAgent], history: Optional[List[Turn]]) -> dict:
    """For each agent, the position of their most recent line in history (-1 if they haven't spoken)."""
    positions = {a.name: -1 for a in agents}
    for position, turn in enumerate(history or []):
        if turn.speaker in positions:
            positions[turn.speaker] = position
    return positions


def choose_next_speaker(last_text: str, last_speaker: str, agents: List[PersonaAgent], history: Optional[List[Turn]] = None,) -> PersonaAgent:
    """
    Decide who talks next, the way people in a group actually hand off.

    If the last line names another participant (by first name), the one named
    *last* in the line speaks next — a question usually comes at the end
    ("...But Dana, you good with just gels?"). 
    If nobody is named, whoever has been quiet the longest speaks, so a quiet 
    character can't be starved out by two people talking to each other.
    """
    lowered = last_text.lower()
    chosen: Optional[PersonaAgent] = None
    chosen_position = -1

    for agent in agents:
        if agent.name == last_speaker:
            continue  # don't let the same person speak twice in a row
        first_name = agent.name.split()[0].lower()

        for match in re.finditer(r"\b" + re.escape(first_name) + r"\b", lowered):
            if match.start() > chosen_position:
                chosen = agent
                chosen_position = match.start()

    if chosen is not None:
        return chosen

    # Nobody named: the one who has gone longest without speaking gets the floor.
    last_spoke = _last_spoke(agents, history)
    
    candidates = [a for a in agents if a.name != last_speaker]
    return min(candidates, key=lambda a: last_spoke[a.name])

def run_conversation(
    agents: List[PersonaAgent],
    topic: str,
    turns: int = 6,
    on_turn: Optional[Callable[[Turn], None]] = None,
    closing: Optional[str] = None,
) -> Conversation:
    """
    Run a round-robin conversation between the given agents.

    :param agents:  two or more PersonaAgents. They speak in list order.
    :param topic:   seeds the opening; each agent sees it as the situation.
    :param turns:   total lines of dialogue, split across the agents.
    :param on_turn: called after each line, so a UI can print as it goes rather
                    than waiting for the whole conversation to finish.
    """
    if len(agents) < 2:
        raise ValueError("a conversation needs at least two agents")

    conversation = Conversation(topic=topic, participants=[a.name for a in agents])

    # The topic is injected as a scene-setting turn from a narrator. Every agent
    # sees it as context but nobody has to answer it directly.
    history: List[Turn] = [Turn(speaker="Scene", text=topic)]

    active = list(agents)  # who is still here; shrinks as people leave

    def record(turn: Turn) -> None:
        """Add a line to what the agents see, to the saved transcript, and to the screen."""
        history.append(turn)
        conversation.turns.append(turn)
        if on_turn is not None:
            on_turn(turn)

    for _ in range(turns):
        last = history[-1]
        speaker = choose_next_speaker(last.text, last.speaker, active, history)
        text = speaker.respond(history)

        # Spot the leave signal, then strip it so it never shows in the dialogue.
        leaving = bool(LEAVE_PATTERN.search(text))
        text = LEAVE_PATTERN.sub("", text).strip() or "(leaves without a word)"
        record(Turn(speaker=speaker.name, text=text))

        if leaving:
            active.remove(speaker)
            # Tell everyone still here, so nobody keeps talking to an empty spot.
            record(Turn(speaker="Scene", text=f"{speaker.name} has left."))
            if len(active) < 2:
                break  # nobody left to talk to

    # Time's up: announce it, then everyone still here gets a last word.
    if closing is not None and len(active) >= 2:
        record(Turn(speaker="Scene", text=closing))
        # Quietest first, so anyone left out speaks while the others can still reply.
        last_spoke = _last_spoke(active, history)
        for agent in sorted(active, key=lambda a: last_spoke[a.name]):
            text = LEAVE_PATTERN.sub("", agent.respond(history)).strip() or "(leaves without a word)"
            record(Turn(speaker=agent.name, text=text))

    return conversation


def save_transcript(conversation: Conversation, directory, filename: Optional[str] = None):
    """
    Write the transcript to disk and return its path.

    Without a filename, the name comes from the topic ("conversation-the-corral.md"),
    numbered if that file already exists, so a new conversation never overwrites
    an old one.
    """
    from pathlib import Path

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    if filename is None:
        slug = re.sub(r"[^a-z0-9]+", "-", conversation.topic.lower()).strip("-")[:40].strip("-") or "untitled"
        filename = f"conversation-{slug}.md"
        number = 2
        while (directory / filename).exists():
            filename = f"conversation-{slug}-{number}.md"
            number += 1

    path = directory / filename
    path.write_text(conversation.transcript(), encoding="utf-8")
    return path



# =============================================================================
# YOUR TASK
# =============================================================================
#
#  1. Turn-taking is strict round-robin. Real conversations do not alternate
#     politely. Who should decide who speaks next — a rule, or a model?
#
#  2. Conversations end after N turns regardless of whether anything was
#     resolved. There is no notion of the discussion being finished.
#
#  3. The "Scene" turn is a hack: a fake speaker that exists only to inject the
#     topic. Is there a cleaner way to set a scene?
#
#  4. Nobody observes the conversation. A third agent could summarize it, judge
#     it, or score whether the doctor actually answered the patient's question —
#     which is the natural bridge to the AI-judge requirement in the final
#     presentation rubric.
#
#  5. `save_transcript` always writes to the same filename, so each conversation
#     overwrites the last one.
#
#  6. If one agent's reply fails, the whole conversation raises and everything
#     said so far is lost.
