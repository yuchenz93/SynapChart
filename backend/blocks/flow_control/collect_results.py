"""Collect results block — accumulates iteration outputs into a stacked array."""


from __future__ import annotations

import numpy as np

from blocks.base import BlockBase, PortDefinition, ParameterDefinition
from neurodata.types import NeuroData


class CollectResults(BlockBase):
    """Accumulates outputs from repeated iterations into a single stacked array.

    In a batch context (driven by dataset_iterator) the executor bypasses
    run() and accumulates items directly, calling finalize() once all
    iterations are complete.

    In standalone context (no iterator in workflow) run() is called once and
    wraps the single input item in a 1-element array along the chosen axis.
    """

    block_type_id = "collect_results"
    display_name  = "Collect results"
    category      = "Flow control"
    description   = (
        "Accumulates outputs from repeated iterations into a single stacked "
        "array. Receives one NeuroData per iteration and outputs a single "
        "NeuroData where the array has an extra leading dimension "
        "(n_iterations × ...)."
    )

    inputs = [
        PortDefinition(
            port_id="item",
            data_type="NeuroData[any]",
            description="One result per iteration.",
        )
    ]
    outputs = [
        PortDefinition(
            port_id="collection",
            data_type="NeuroData[any]",
            description="Stacked array across all iterations.",
        )
    ]
    parameters = [
        ParameterDefinition(
            name="axis",
            data_type="int",
            default=0,
            description="Axis along which to stack results.",
        ),
        ParameterDefinition(
            name="keep_metadata_from",
            data_type="enum:first,last",
            default="first",
            description="Which iteration's metadata to carry forward.",
        ),
    ]

    def run(self, inputs: dict, parameters: dict) -> dict:
        """Standalone (non-batch) execution: wrap the single input in a 1-element array."""
        item = inputs.get("item")
        if item is None:
            raise ValueError("collect_results: input 'item' is required.")
        axis = int(parameters.get("axis", 0))
        return {"collection": _stack_items([item], axis)}

    @staticmethod
    def finalize(items: list, axis: int, keep_metadata_from: str) -> dict:
        """Called by the executor after all batch iterations are complete.

        Args:
            items:              List of NeuroData (or primitive) values collected
                                across all iterations, in iteration order.
            axis:               Axis along which to stack.
            keep_metadata_from: "first" or "last" — which item's metadata to use.

        Returns:
            Output dict with key "collection".
        """
        if not items:
            raise ValueError("collect_results: no items to collect.")
        return {"collection": _stack_items(items, axis, keep_metadata_from)}


def _stack_items(items: list, axis: int, keep_metadata_from: str = "first") -> "NeuroData":
    """Stack a list of NeuroData objects along the given axis.

    Args:
        items:              Non-empty list of NeuroData or array-like values.
        axis:               Stack axis.
        keep_metadata_from: "first" or "last".

    Returns:
        A new NeuroData with the stacked data array and metadata from the
        chosen item.  Falls back to a plain numpy array if inputs are not
        NeuroData instances.
    """
    arrays = []
    ref_item = items[0] if keep_metadata_from == "first" else items[-1]

    for item in items:
        if isinstance(item, NeuroData):
            arrays.append(item.array)
        else:
            arrays.append(np.asarray(item))

    # Validate that all shapes are compatible for stacking
    shape0 = arrays[0].shape
    for i, arr in enumerate(arrays[1:], start=1):
        if arr.shape != shape0:
            raise ValueError(
                f"collect_results: shape mismatch between iteration 0 "
                f"({shape0}) and iteration {i} ({arr.shape}). "
                "All iterations must produce arrays of the same shape."
            )

    stacked = np.stack(arrays, axis=axis)

    if isinstance(ref_item, NeuroData):
        return NeuroData(
            data_type=ref_item.data_type,
            array=stacked,
            sampling_rate=ref_item.sampling_rate,
            metadata=ref_item.metadata,
        )
    return stacked
