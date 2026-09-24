"""
InputParam and OutputField together are the capability's typed signature:
what an AI agent must supply to invoke it, and what shape it gets back.
This is what makes an artifact a callable capability rather than just a
recorded transcript -- a caller (human reviewer or agent) can understand
the contract without reading a single step.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

ParamType = Literal["string", "number", "boolean"]


class InputParam(BaseModel):
    name: str
    type: ParamType
    description: Optional[str] = None
    pattern: Optional[str] = None  # optional regex the value must satisfy
    sensitive: bool = False
    """Marks this parameter's *value* as sensitive. The parameter's name
    still appears in the artifact (so the contract is inspectable), but
    the actual value supplied at invocation must never be persisted into
    logs or evidence -- this flag is what the evidence logger's redaction
    keys off of for step-level logging."""


ExtractParse = Literal["raw", "currency", "integer"]


class OutputField(BaseModel):
    name: str
    type: ParamType
    description: Optional[str] = None
    extract_from_step: str
    """The id of the Step (a read_text action) whose extracted_text
    populates this output."""
    parse: ExtractParse = "raw"
    """How to convert the raw extracted string into this field's typed
    value -- e.g. "$4,210.55" -> 4210.55 via "currency"."""
