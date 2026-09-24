"""
Every place a Step needs a piece of text (what to type, what URL to
navigate to) can come from one of two places: a fixed value baked in at
recording time, or one of the capability's declared input parameters,
substituted in at invocation time. This is the actual mechanism that
turns a recorded run into a reusable, parameterized capability rather
than a fixed macro that only ever does the exact thing it was recorded
doing.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class LiteralValue(BaseModel):
    kind: Literal["literal"] = "literal"
    value: str


class ParamValue(BaseModel):
    """References one of the capability's declared `inputs` by name. At
    replay time, this gets substituted with whatever value the caller
    supplied for that parameter."""
    kind: Literal["param"] = "param"
    param: str


ValueSource = Annotated[
    Union[LiteralValue, ParamValue],
    Field(discriminator="kind"),
]
