"""
A single vocabulary for "check something about the current state," reused
in four places across the schema:
  - a step's postcondition (did this individual action actually work?)
  - an outcome's detector (are we looking at a declared business result,
    like "member not found"?)
  - a recovery's trigger (are we looking at a known, dismissable
    interstitial or transient state?)
  - the capability's final checkpoint (did the whole flow succeed?)

Reusing one Condition type for all four means there's one thing to learn
and one thing to implement evaluation for, rather than four similar-but-
different mini-languages.
"""
from __future__ import annotations

from typing import Annotated, List, Literal, Union

from pydantic import BaseModel, Field

from src.surfaces.targeting import TargetDescriptor


class TextPresentCondition(BaseModel):
    """True if `pattern` appears in the current accessibility tree text.
    Substring match, not regex -- simple and matches how these apps
    render fixed message copy (e.g. "No member matching")."""
    kind: Literal["text_present"] = "text_present"
    pattern: str


class ElementVisibleCondition(BaseModel):
    """True if the described target currently resolves to a visible
    element. Reuses the same TargetDescriptor/locator strategies used for
    acting on elements -- checking for something and acting on it use the
    same targeting language."""
    kind: Literal["element_visible"] = "element_visible"
    target: TargetDescriptor


class UrlMatchesCondition(BaseModel):
    """True if the current URL's path matches this regex pattern."""
    kind: Literal["url_matches"] = "url_matches"
    pattern: str


class AllOfCondition(BaseModel):
    """True only if every sub-condition is true. Lets a checkpoint or
    outcome require more than one signal at once (e.g. right URL AND a
    specific confirmation message present)."""
    kind: Literal["all_of"] = "all_of"
    conditions: List["Condition"]


Condition = Annotated[
    Union[
        TextPresentCondition,
        ElementVisibleCondition,
        UrlMatchesCondition,
        AllOfCondition,
    ],
    Field(discriminator="kind"),
]

# AllOfCondition references Condition before it's fully defined (a forward
# reference) -- this resolves that now that Condition exists.
AllOfCondition.model_rebuild()
