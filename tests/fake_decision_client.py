"""
A scripted stand-in for AnthropicDecisionClient, used to test the
DiscoveryAgent's loop logic (stopping conditions, trace recording, action
execution) without making any real API calls. Mimics just enough of the
real Anthropic response shape (a .content list of objects with
.type/.id/.input) for loop.py's code to work identically against either.
"""
from __future__ import annotations

from types import SimpleNamespace


def _make_tool_use_block(block_id: str, decision: dict):
    return SimpleNamespace(type="tool_use", id=block_id, name="take_action", input=decision)


class FakeDecisionClient:
    def __init__(self, scripted_decisions: list[dict]):
        """scripted_decisions: a list of decision dicts, returned in order,
        one per call to send()."""
        self._decisions = list(scripted_decisions)
        self._call_count = 0

    def send(self, system_prompt: str, messages: list):
        if self._call_count >= len(self._decisions):
            # Loop kept going past the script -- return a safe "finish" so
            # tests fail clearly on an assertion rather than an IndexError.
            decision = {"reasoning": "script exhausted", "action": "finish", "success": False}
        else:
            decision = self._decisions[self._call_count]
        self._call_count += 1
        block = _make_tool_use_block(f"call_{self._call_count}", decision)
        return SimpleNamespace(content=[block])