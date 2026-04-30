"""DAG resolution for SynapChart workflow graphs."""


from __future__ import annotations

from collections import defaultdict, deque


def topological_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Return node_ids in valid execution order using Kahn's algorithm.

    Args:
        nodes: List of workflow node dicts, each with a ``node_id`` key.
        edges: List of workflow edge dicts, each with ``source_node_id``
               and ``target_node_id`` keys.

    Returns:
        Ordered list of node_ids safe for sequential execution.

    Raises:
        ValueError: If the graph contains a cycle.
    """
    in_degree: dict[str, int] = {n["node_id"]: 0 for n in nodes}
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src = edge["source_node_id"]
        tgt = edge["target_node_id"]
        adjacency[src].append(tgt)
        in_degree[tgt] += 1

    queue: deque[str] = deque(
        nid for nid, deg in in_degree.items() if deg == 0
    )
    order: list[str] = []

    while queue:
        nid = queue.popleft()
        order.append(nid)
        for neighbor in adjacency[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(nodes):
        raise ValueError("Workflow graph contains a cycle.")

    return order


def build_upstream_map(edges: list[dict]) -> dict[str, list[str]]:
    """Return a mapping of node_id -> list of direct predecessor node_ids.

    Args:
        edges: List of workflow edge dicts.

    Returns:
        Dict mapping each node_id to the ids of nodes that feed into it.
    """
    upstream: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        upstream[edge["target_node_id"]].append(edge["source_node_id"])
    return dict(upstream)


def build_downstream_map(edges: list[dict]) -> dict[str, list[str]]:
    """Return a mapping of node_id -> list of direct successor node_ids.

    Args:
        edges: List of workflow edge dicts.

    Returns:
        Dict mapping each node_id to the ids of nodes it feeds into.
    """
    downstream: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        downstream[edge["source_node_id"]].append(edge["target_node_id"])
    return dict(downstream)


def all_descendants(node_id: str, downstream: dict[str, list[str]]) -> set[str]:
    """Return all transitive descendants of a node (for cache invalidation).

    Args:
        node_id:    The starting node.
        downstream: Result of :func:`build_downstream_map`.

    Returns:
        Set of node_ids that are downstream (directly or transitively) of node_id.
    """
    visited: set[str] = set()
    queue: deque[str] = deque(downstream.get(node_id, []))
    while queue:
        nid = queue.popleft()
        if nid not in visited:
            visited.add(nid)
            queue.extend(downstream.get(nid, []))
    return visited
