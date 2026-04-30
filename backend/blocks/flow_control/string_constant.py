"""String constant block — outputs a fixed string value."""

from __future__ import annotations

from blocks.base import BlockBase, PortDefinition, ParameterDefinition


class StringConstant(BlockBase):
    """Outputs a fixed string value.

    Useful for connecting a file path into a composite block's string input
    port without requiring a CSV dataset iterator.
    """

    block_type_id = "string_constant"
    display_name  = "String constant"
    category      = "Flow control"
    description   = (
        "Outputs a fixed string value. Useful for connecting a file path "
        "into a composite block's string input port."
    )

    inputs     = []
    outputs    = [
        PortDefinition(
            port_id="value",
            data_type="str",
            description="The constant string value.",
        )
    ]
    parameters = [
        ParameterDefinition(
            name="value",
            data_type="str",
            default="",
            description="The string to output.",
        )
    ]

    def run(self, inputs: dict, parameters: dict) -> dict:
        return {"value": parameters.get("value", "")}
