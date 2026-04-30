
from __future__ import annotations

from typing import Any

import numpy as np

from blocks.base import BlockBase, ParameterDefinition, PortDefinition
from neurodata.types import NeuroData


class LinearizePosition(BlockBase):
    """Project 2-D position onto a 1-D linear track axis."""

    block_type_id = "linearize_position"
    display_name = "Linearize Position"
    category = "Behavior"
    description = "Projects 2-D position onto a 1-D linear track using PCA or a manual axis."

    inputs = [
        PortDefinition("position", "NeuroData[position]", "2-D position data (N × 2)."),
    ]
    outputs = [
        PortDefinition("linear_pos", "NeuroData[position]", "1-D linearized position (N,)."),
    ]
    parameters = [
        ParameterDefinition("method", "enum:pca,manual_axis", "pca", "Linearization method."),
    ]

    def run(self, inputs: dict[str, NeuroData], parameters: dict[str, Any]) -> dict:
        pos: NeuroData = inputs["position"]
        method = parameters.get("method", "pca")
        xy = pos.array.astype(float)

        if method == "pca":
            centered = xy - xy.mean(axis=0)
            _, _, vt = np.linalg.svd(centered, full_matrices=False)
            principal_axis = vt[0]
            linear = centered @ principal_axis
        else:
            # manual_axis: project onto the vector from first to last point
            axis = xy[-1] - xy[0]
            norm = np.linalg.norm(axis)
            if norm == 0:
                linear = np.zeros(len(xy))
            else:
                axis = axis / norm
                linear = (xy - xy[0]) @ axis

        # Shift so minimum is 0
        linear -= linear.min()

        return {
            "linear_pos": NeuroData(
                data_type="position",
                array=linear,
                sampling_rate=pos.sampling_rate,
                timestamps=pos.timestamps,
                metadata={**pos.metadata, "linearized": True, "method": method},
            )
        }
