"""
Tracks who currently owns the live session -- "agent" or "human" -- and
provides the actual blocking mechanism that pauses automation until a
human resolves the situation. This is the literal answer to "there must
be a way to know who is (or should be) in control."

Designed to be shared, by reference, between two things running
concurrently in the same process: the automation thread (which blocks on
wait_until_agent_turn) and the operator Flask app's request-handling
thread (which calls resolve() when a human clicks a button). A
threading.Event is what makes that handoff real rather than simulated --
the automation thread is genuinely suspended, not polling.
"""
from __future__ import annotations

import threading
from typing import Optional


class SessionController:
    def __init__(self):
        self.owner = "agent"
        self._event = threading.Event()
        self._event.set()  # starts unblocked: agent has the turn
        self._last_resolution: Optional[dict] = None

    @property
    def current_owner(self) -> str:
        return self.owner

    def assert_agent_turn(self) -> None:
        """Called before any action. If a human currently holds the
        session, acting right now would be exactly the race condition
        the lease exists to prevent."""
        if self.owner != "agent":
            raise RuntimeError(
                f"Action attempted while session is owned by '{self.owner}', not 'agent'"
            )

    def request_human_control(self, reason: str) -> None:
        """Transfers the lease to the human and blocks any thread that
        subsequently calls wait_until_agent_turn()."""
        self.owner = "human"
        self._last_resolution = None
        self._event.clear()

    def wait_until_agent_turn(self, timeout: Optional[float] = None) -> Optional[dict]:
        """Blocks the calling thread until a human resolves the
        intervention. Returns the resolution dict ({"approved": bool,
        "note": str}) once resumed, or None if the wait timed out without
        a resolution."""
        completed = self._event.wait(timeout=timeout)
        if not completed:
            return None
        return self._last_resolution

    def resolve(self, approved: bool, note: str = "") -> None:
        """Called by the human-facing side (the operator page) to hand
        the lease back and unblock whatever is waiting."""
        self._last_resolution = {"approved": approved, "note": note}
        self.owner = "agent"
        self._event.set()