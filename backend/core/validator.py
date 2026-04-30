"""Port type validation for SynapChart pipelines."""


from __future__ import annotations

# Maps each output type to the set of input types it is compatible with.
# "str" is also accepted by "str" (used by dataset_iterator dynamic ports).
_COMPATIBILITY: dict[str, set[str]] = {
    "NeuroData[raw_signal]":   {"NeuroData[raw_signal]", "NeuroData[any]"},
    "NeuroData[lfp]":          {"NeuroData[lfp]", "NeuroData[raw_signal]", "NeuroData[any]"},
    "NeuroData[spike_times]":  {"NeuroData[spike_times]", "NeuroData[any]"},
    "NeuroData[spike_matrix]": {"NeuroData[spike_matrix]", "NeuroData[any]"},
    "NeuroData[position]":     {"NeuroData[position]", "NeuroData[any]"},
    "NeuroData[tuning_curve]": {"NeuroData[tuning_curve]", "NeuroData[any]"},
    "NeuroData[decoded]":      {"NeuroData[decoded]", "NeuroData[any]"},
    "NeuroData[any]":          {"NeuroData[any]"},
    "float":                   {"float"},
    "int":                     {"int", "float"},
    "str":                     {"str"},
    # ── CRCNS / population types ────────────────────────────────────────────
    # tuning_curves_population is also compatible with tuning_curve so the
    # existing bayesian_decoder can accept a population rate map directly.
    "NeuroData[multi_spike_times]":        {"NeuroData[multi_spike_times]", "NeuroData[any]"},
    "NeuroData[epochs]":                   {"NeuroData[epochs]", "NeuroData[any]"},
    "NeuroData[tuning_curves_population]": {
        "NeuroData[tuning_curves_population]",
        "NeuroData[tuning_curve]",
        "NeuroData[any]",
    },
    "NeuroData[place_fields]":   {"NeuroData[place_fields]",   "NeuroData[any]"},
    "NeuroData[phase_precession]": {"NeuroData[phase_precession]", "NeuroData[any]"},
    "NeuroData[theta_cycles]":   {"NeuroData[theta_cycles]",   "NeuroData[any]"},
    "NeuroData[theta_sequence]": {"NeuroData[theta_sequence]", "NeuroData[any]"},
    "NeuroData[laps]":           {"NeuroData[laps]",           "NeuroData[any]"},
}


def validate_connection(
    output_port_type: str,
    input_port_type: str,
) -> tuple[bool, str]:
    """Check whether a connection from an output port to an input port is allowed.

    Types not present in _COMPATIBILITY (e.g. from external libraries) are
    accepted without type-checking rather than rejected, so that third-party
    blocks with custom NeuroData subtypes work without modifying core code.
    """
    accepted = _COMPATIBILITY.get(output_port_type)
    if accepted is None:
        # Unknown type (external library) — allow the connection
        return True, ""
    if input_port_type not in accepted:
        return False, (
            f"Type mismatch: output '{output_port_type}' is not compatible "
            f"with input '{input_port_type}'."
        )
    return True, ""


def validate_workflow(workflow: dict) -> list[str]:
    """Validate all connections in a workflow JSON.

    Looks up port definitions from the block registry (not from the workflow JSON,
    which only stores block_type_id and parameters).

    Returns:
        A list of error strings. Empty list means valid.
    """
    from core.block_registry import get_block  # local import to avoid circular dep

    errors: list[str] = []
    nodes_by_id: dict[str, dict] = {
        node["node_id"]: node for node in workflow.get("nodes", [])
    }

    # Resolve block definitions for each node via the registry
    block_defns: dict[str, dict] = {}
    for node_id, node in nodes_by_id.items():
        block_type_id = node.get("block_type_id", "")
        try:
            block_defns[node_id] = get_block(block_type_id).to_definition()
        except KeyError:
            errors.append(
                f"Node '{node_id}': block type '{block_type_id}' is not registered."
            )

    for edge in workflow.get("edges", []):
        edge_id = edge.get("edge_id", "?")
        src_id = edge.get("source_node_id")
        tgt_id = edge.get("target_node_id")

        if src_id not in nodes_by_id:
            errors.append(f"Edge '{edge_id}': source node '{src_id}' not found.")
            continue
        if tgt_id not in nodes_by_id:
            errors.append(f"Edge '{edge_id}': target node '{tgt_id}' not found.")
            continue

        src_defn = block_defns.get(src_id)
        tgt_defn = block_defns.get(tgt_id)
        if src_defn is None or tgt_defn is None:
            continue  # unregistered block already reported above

        src_port_id = edge.get("source_port_id")
        tgt_port_id = edge.get("target_port_id")

        src_port = next(
            (p for p in src_defn.get("outputs", []) if p["port_id"] == src_port_id),
            None,
        )
        tgt_port = next(
            (p for p in tgt_defn.get("inputs", []) if p["port_id"] == tgt_port_id),
            None,
        )

        if src_port is None:
            # Dynamic-output blocks (e.g. dataset_iterator) have no static port
            # definitions.  Skip type-checking for their edges rather than
            # rejecting valid workflows.
            src_block_type_id = nodes_by_id[src_id].get("block_type_id", "")
            try:
                src_block = get_block(src_block_type_id)
                if getattr(src_block, "is_iterator", False):
                    continue  # dynamic ports — skip validation
            except KeyError:
                pass
            errors.append(
                f"Edge '{edge_id}': output port '{src_port_id}' "
                f"not found on node '{src_id}'."
            )
            continue
        if tgt_port is None:
            errors.append(
                f"Edge '{edge_id}': input port '{tgt_port_id}' "
                f"not found on node '{tgt_id}'."
            )
            continue

        is_valid, message = validate_connection(src_port["type"], tgt_port["type"])
        if not is_valid:
            errors.append(f"Edge '{edge_id}': {message}")

    return errors
