"""Port type validation for SynapChart pipelines.

Port Type System v2 (see docs/specs/12_port_type_system_v2.md): compatibility is
*derived* from a structural type + an advisory semantic role, not a
hand-maintained matrix. :func:`check_types` in ``neurodata.port_types`` returns
a three-state result (OK / WARN / ERROR); this module adapts it to the existing
string-based callers.
"""


from __future__ import annotations

from neurodata.port_types import Compat, check_types, parse_port_type


def validate_connection(
    output_port_type: str,
    input_port_type: str,
) -> tuple[Compat, str]:
    """Check whether a connection from an output port to an input port is allowed.

    Returns a (:class:`Compat`, message) pair:
      * ``Compat.OK``    — structure fits and roles agree (or are unspecified).
      * ``Compat.WARN``  — structure fits but roles differ; connectable with a
        confirmation. Callers that only gate on hard errors treat this as valid.
      * ``Compat.ERROR`` — structural mismatch; connection is rejected.

    Unknown / external types parse to a permissive ``any`` structure, so
    third-party blocks are never hard-rejected.
    """
    return check_types(parse_port_type(output_port_type),
                       parse_port_type(input_port_type))


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

        status, message = validate_connection(src_port["type"], tgt_port["type"])
        # Only structural mismatches block a workflow. Role mismatches are
        # advisory (surfaced at connection time in the UI), not hard errors.
        if status is Compat.ERROR:
            errors.append(f"Edge '{edge_id}': {message}")

    return errors
