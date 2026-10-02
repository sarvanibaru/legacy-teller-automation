"""
The single tool the discovery agent is forced to call on every turn. Using
tool use (function calling) rather than asking the model to emit
free-text JSON is far more reliable -- the API validates the shape for
us, so we don't need to defensively parse loosely-structured text.
"""

TAKE_ACTION_TOOL = {
    "name": "take_action",
    "description": (
        "Decide the single next action to take on the current screen in "
        "order to progress toward the stated goal. Call this once per "
        "turn. When the goal has been fully achieved, call it with "
        "action='finish'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "One or two sentences on why this action moves toward the goal.",
            },
            "action": {
                "type": "string",
                "enum": ["navigate", "click", "type", "read_text", "finish"],
            },
            "role": {
                "type": "string",
                "description": (
                    "Accessible role of the target element, e.g. 'textbox', "
                    "'button'. Required for click/type/read_text unless "
                    "using row_label instead."
                ),
            },
            "name": {
                "type": "string",
                "description": "Accessible name of the target element. Used together with 'role'.",
            },
            "row_label": {
                "type": "string",
                "description": (
                    "Alternative to role+name: the row-header label of a "
                    "labeled value you want to read or check, e.g. "
                    "'Savings Balance'. Use this for read_text on a "
                    "labeled field-value pair."
                ),
            },
            "value": {
                "type": "string",
                "description": "Text to type, or a URL path to navigate to. Required for 'type' and 'navigate'.",
            },
            "is_parameter": {
                "type": "boolean",
                "description": (
                    "True only if this value was taken directly from the "
                    "goal itself (e.g. a specific member ID the goal "
                    "named), meaning a reusable capability should accept "
                    "it as an input rather than hardcode it. False for "
                    "incidental values."
                ),
            },
            "parameter_name": {
                "type": "string",
                "description": "A short camelCase name for this parameter, only if is_parameter is true.",
            },
            "outputs": {
                "type": "object",
                "description": (
                    "Only for action='finish': a map of output name to the "
                    "value read during this run, for every distinct piece "
                    "of information the goal asked for."
                ),
            },
            "success": {
                "type": "boolean",
                "description": "Only for action='finish': whether the goal was actually achieved.",
            },
        },
        "required": ["reasoning", "action"],
    },
}