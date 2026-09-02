"""Port Type System v2 — structural type + advisory semantic role.

See docs/specs/12_port_type_system_v2.md.

A port declares a **structural type** (hard-enforced: container / dtype / ndim /
timed) plus an optional **semantic role** (soft-enforced advisory tag). Port
definitions keep declaring a *string* (e.g. "NeuroData[lfp]", "float", "str");
:func:`parse_port_type` turns it into a :class:`PortType`, and
:func:`check_types` returns a three-state :class:`Compat` result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Compat(Enum):
    """Three-state connection compatibility."""
    OK = "ok"        # structure fits, roles agree (or unspecified)
    WARN = "warn"    # structure fits, roles differ — connectable with confirm
    ERROR = "error"  # structural mismatch — connection blocked


@dataclass(frozen=True)
class PortType:
    """The parsed type of a single port.

    Attributes:
        container: "neurodata" | "scalar" | "str" | "bool" | "list" | "dict" | "any"
        dtype:     "float" | "int" | "bool" | "any" | None  (array/scalar element type)
        ndim:      1 | 2 | None(=any)                        (array rank)
        timed:     True(requires timing) | False | None(=any)
        role:      advisory domain tag; None = unspecified
    """
    container: str
    dtype: str | None = None
    ndim: int | None = None
    timed: bool | None = None
    role: str | None = None


# ── Role hierarchy ──────────────────────────────────────────────────────────
# Maps a role to its parent role. Compatibility treats a child as usable where
# its ancestor is expected (and vice-versa) without a warning. Replaces the two
# hand-patched is-a rows of the v1 compatibility matrix.
ROLE_PARENTS: dict[str, str] = {
    "lfp": "signal",                        # lfp is-a signal (was lfp → raw_signal)
    "tuning_curves_population": "tuning_curve",
}


# ── Legacy string → PortType ────────────────────────────────────────────────
# Structural facets for the v1 registered NeuroData tags. Anything not listed
# (external/library tags) parses to a NeuroData envelope with `any` structure and
# the tag preserved as its role, so it keeps chaining but now warns on mismatch.
_ND = "neurodata"


def _nd(dtype, ndim, timed, role) -> PortType:
    return PortType(_ND, dtype=dtype, ndim=ndim, timed=timed, role=role)


_LEGACY: dict[str, PortType] = {
    # signal family
    "raw_signal": _nd("float", None, True, "signal"),
    "signal":     _nd("float", None, True, "signal"),
    "lfp":        _nd("float", None, True, "lfp"),
    # spikes
    "spike_times":       _nd("float", 1, True, "spike_times"),
    "spike_matrix":      _nd("float", 2, True, "spike_matrix"),
    "multi_spike_times": _nd("float", None, True, "multi_spike_times"),
    # behavior / decoding
    "position":                 _nd("float", 2, True, "position"),
    "tuning_curve":             _nd("float", None, False, "tuning_curve"),
    "tuning_curves_population":  _nd("float", 2, False, "tuning_curves_population"),
    "decoded":                  _nd("float", 2, True, "decoded"),
    # interval / event tables
    "epochs":        _nd("float", 2, False, "epochs"),
    "laps":          _nd("float", 2, False, "laps"),
    "theta_cycles":  _nd("float", 2, False, "theta_cycles"),
    "theta_sequence": _nd("float", 2, False, "theta_sequence"),
    # structured records
    "place_fields":      _nd("any", None, False, "place_fields"),
    "phase_precession":  _nd("any", None, False, "phase_precession"),
}

_NEURODATA_RE = re.compile(r"^NeuroData\[(?P<role>[A-Za-z0-9_]+)\]$")
_ARRAY_RE = re.compile(
    r"^array<\s*(?P<dtype>float|int|bool|any)\s*"
    r"(?:,\s*(?P<ndim>\d)d\s*)?"
    r"(?:,\s*(?P<timed>timed|untimed)\s*)?>$"
)
_LIST_RE = re.compile(r"^list\[(?P<inner>[A-Za-z0-9_]+)\]$")


def parse_port_type(spec: str | None) -> PortType:
    """Parse a port `data_type` string into a :class:`PortType`.

    Unknown / unparseable strings degrade to ``PortType("any")`` so third-party
    blocks never hard-fail validation.
    """
    if not spec:
        return PortType("any")
    s = spec.strip()

    if s == "any":
        return PortType("any")
    if s in ("float", "int", "bool"):
        return PortType("scalar", dtype=s)
    if s == "str":
        return PortType("str")
    if s == "dict":
        return PortType("dict")
    if s == "list":
        return PortType("list")

    m = _LIST_RE.match(s)
    if m:
        return PortType("list", dtype=m["inner"])

    # NeuroData[any] is a true match-all (v1 also lets scalars feed it).
    if s == "NeuroData[any]":
        return PortType("any")

    m = _NEURODATA_RE.match(s)
    if m:
        role = m["role"]
        if role in _LEGACY:
            return _LEGACY[role]
        # Unknown external role: NeuroData envelope, any structure, role kept.
        return _nd("any", None, None, role)

    m = _ARRAY_RE.match(s)
    if m:
        ndim = int(m["ndim"]) if m["ndim"] else None
        timed = None if m["timed"] is None else (m["timed"] == "timed")
        return PortType(_ND, dtype=m["dtype"], ndim=ndim, timed=timed)

    # Bare legacy role (rare) or anything else: be permissive.
    if s in _LEGACY:
        return _LEGACY[s]
    return PortType("any")


# ── Compatibility checks ────────────────────────────────────────────────────

def _dtype_ok(out_dtype: str | None, req_dtype: str | None) -> bool:
    if req_dtype in (None, "any") or out_dtype in (None, "any"):
        return True
    if out_dtype == req_dtype:
        return True
    # numeric widening: an int array/scalar can feed a float port
    return out_dtype == "int" and req_dtype == "float"


def _is_ancestor(role: str, ancestor: str) -> bool:
    """True if `ancestor` is `role` or a (transitive) parent of `role`."""
    seen: set[str] = set()
    cur: str | None = role
    while cur and cur not in seen:
        if cur == ancestor:
            return True
        seen.add(cur)
        cur = ROLE_PARENTS.get(cur)
    return False


def _role_matches(a: str, b: str) -> bool:
    return a == b or _is_ancestor(a, b) or _is_ancestor(b, a)


def check_types(out: PortType, req: PortType) -> tuple[Compat, str]:
    """Return (Compat, message) for wiring an `out` port into a `req` input port."""
    # 1. Structural — hard.
    if req.container != "any" and out.container != "any":
        if out.container != req.container:
            return Compat.ERROR, (
                f"expects {req.container}, got {out.container}"
            )
        if req.container in (_ND, "scalar"):
            if not _dtype_ok(out.dtype, req.dtype):
                return Compat.ERROR, (
                    f"expects {req.dtype} {req.container}, got {out.dtype}"
                )
        if req.container == _ND:
            if req.ndim is not None and out.ndim not in (None, req.ndim):
                return Compat.ERROR, (
                    f"expects {req.ndim}-D array, got {out.ndim}-D"
                )
            if req.timed is True and out.timed is False:
                return Compat.ERROR, (
                    "expects a timed signal (sampling_rate/timestamps)"
                )
    # 2. Semantic role — soft.
    if req.role and out.role and not _role_matches(out.role, req.role):
        return Compat.WARN, f"role mismatch: '{out.role}' → '{req.role}'"
    return Compat.OK, ""
