
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from neurodata.types import NeuroData


@dataclass
class PortDefinition:
    """Describes a single input or output port on a block."""
    port_id: str
    data_type: str       # e.g. "NeuroData[lfp]", "float", "str"
    description: str
    required: bool = True


@dataclass
class ParameterDefinition:
    """Describes a single configurable parameter on a block."""
    name: str
    data_type: str       # "str" | "float" | "int" | "bool" | "enum:val1,val2,..."
    default: Any
    description: str


class BlockBase(ABC):
    """Base class for all SynapChart blocks.

    Subclasses must define the class-level attributes below and implement run().

    Attributes:
        block_type_id: Unique snake_case identifier (e.g. "bandpass_filter").
        display_name:  Human-readable name shown on the canvas.
        category:      One of the registered category strings.
        description:   One or two sentences describing what this block does.
        inputs:        List of PortDefinition for input ports.
        outputs:       List of PortDefinition for output ports.
        parameters:    List of ParameterDefinition for configurable params.
    """

    block_type_id: str = ""
    display_name: str = ""
    category: str = ""
    description: str = ""
    is_custom: bool = False   # True for auto-generated user blocks
    inputs: list[PortDefinition] = []
    outputs: list[PortDefinition] = []
    parameters: list[ParameterDefinition] = []

    @abstractmethod
    def run(
        self,
        inputs: dict[str, "NeuroData | Any"],
        parameters: dict[str, Any],
    ) -> dict[str, "NeuroData | Any"]:
        """Execute this block.

        Args:
            inputs:     Mapping of port_id -> NeuroData (or primitive) value.
            parameters: Mapping of parameter name -> current value.

        Returns:
            Mapping of output port_id -> NeuroData (or primitive) value.
        """
        ...

    def to_definition(self) -> dict:
        """Serialize block metadata to the JSON shape used by the API.

        Enum parameters (data_type="enum:a,b,c") are expanded to
        {"type": "enum", "enum": ["a", "b", "c"]} for the frontend.
        PortDefinition.data_type is surfaced as "type" to match the API schema.
        """
        inputs = [
            {
                "port_id": p.port_id,
                "type": p.data_type,
                "description": p.description,
                "required": p.required,
            }
            for p in self.inputs
        ]
        outputs = [
            {
                "port_id": p.port_id,
                "type": p.data_type,
                "description": p.description,
            }
            for p in self.outputs
        ]
        params = []
        for p in self.parameters:
            d: dict[str, Any] = {
                "name": p.name,
                "type": p.data_type,
                "default": p.default,
                "description": p.description,
            }
            if d["type"].startswith("enum:"):
                d["enum"] = d["type"][5:].split(",")
                d["type"] = "enum"
            params.append(d)

        return {
            "block_type_id": self.block_type_id,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "is_custom": self.is_custom,
            "is_composite": False,
            "is_iterator": bool(getattr(self, "is_iterator", False)),
            "inputs": inputs,
            "outputs": outputs,
            "parameters": params,
        }


class CompositeBlockDefinition:
    """A composite block loaded from a JSON definition file.

    Unlike BlockBase, holds no Python code — the executor runs the
    embedded subflow as a nested PipelineExecutor when it encounters
    a node whose block_type_id resolves to a CompositeBlockDefinition.
    """

    is_custom: bool = False
    is_composite: bool = True

    def __init__(self, definition: dict) -> None:
        self.block_type_id = definition["block_type_id"]
        self.display_name  = definition["display_name"]
        self.category      = definition.get("category", "Composite")
        self.description   = definition.get("description", "")
        self.inputs        = definition.get("inputs", [])   # each has port_id, data_type, maps_to
        self.outputs       = definition.get("outputs", [])  # each has port_id, data_type, maps_to
        self.subflow       = definition.get("subflow", {})
        self._raw          = definition

    def to_definition(self) -> dict:
        """Serialize to the API shape understood by the frontend and validator."""
        return {
            "block_type_id": self.block_type_id,
            "display_name":  self.display_name,
            "category":      self.category,
            "description":   self.description,
            "is_custom":     False,
            "is_composite":  True,
            "inputs": [
                {
                    "port_id":     p["port_id"],
                    "type":        p["data_type"],
                    "description": p.get("description", ""),
                    "required":    True,
                    "maps_to":     p.get("maps_to"),
                }
                for p in self.inputs
            ],
            "outputs": [
                {
                    "port_id":     p["port_id"],
                    "type":        p["data_type"],
                    "description": p.get("description", ""),
                    "maps_to":     p.get("maps_to"),
                }
                for p in self.outputs
            ],
            "parameters": [],
        }

    def full_definition(self) -> dict:
        """Return the complete raw definition dict including the subflow."""
        return self._raw
