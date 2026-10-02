"""
Thin wrapper around the Anthropic API call. Deliberately minimal -- it
only knows how to send a system prompt + conversation and get back a raw
response. All the decision-parsing and loop logic lives in loop.py, so
this class can be swapped for a fake one in tests without touching
anything else.
"""
from __future__ import annotations

from anthropic import Anthropic

from src.agent.tool_schema import TAKE_ACTION_TOOL


class AnthropicDecisionClient:
    def __init__(self, api_key: str, model: str):
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def send(self, system_prompt: str, messages: list) -> object:
        """Returns the raw Anthropic response object. The caller is
        responsible for finding the tool_use block in response.content."""
        return self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            tools=[TAKE_ACTION_TOOL],
            tool_choice={"type": "tool", "name": "take_action"},
            messages=messages,
        )