import { createContext } from 'react';

/**
 * Shared context between Canvas and BlockNode for the click-to-connect
 * pending connection state and port-click handler.
 *
 * Value shape: {
 *   pendingConnection: { sourceNodeId, sourcePortId, sourcePortType, sx, sy } | null,
 *   handlePortClick: (event, nodeId, portId, portType, direction) => void,
 * }
 */
export const CanvasContext = createContext(null);

// ── Port Types v2 — client-side mirror of backend neurodata/port_types.py ────
// Used only for *live* pending-connection feedback; the backend remains the
// authoritative validator (called on actual connect).

const ROLE_PARENTS = {
  lfp: 'signal',
  tuning_curves_population: 'tuning_curve',
};

// Legacy NeuroData[role] → structural facets {dtype, ndim, timed, role}.
const nd = (dtype, ndim, timed, role) => ({ container: 'neurodata', dtype, ndim, timed, role });
const LEGACY = {
  raw_signal: nd('float', null, true, 'signal'),
  signal:     nd('float', null, true, 'signal'),
  lfp:        nd('float', null, true, 'lfp'),
  spike_times:       nd('float', 1, true, 'spike_times'),
  spike_matrix:      nd('float', 2, true, 'spike_matrix'),
  multi_spike_times: nd('float', null, true, 'multi_spike_times'),
  position:                 nd('float', 2, true, 'position'),
  tuning_curve:             nd('float', null, false, 'tuning_curve'),
  tuning_curves_population: nd('float', 2, false, 'tuning_curves_population'),
  decoded:                  nd('float', 2, true, 'decoded'),
  epochs:         nd('float', 2, false, 'epochs'),
  laps:           nd('float', 2, false, 'laps'),
  theta_cycles:   nd('float', 2, false, 'theta_cycles'),
  theta_sequence: nd('float', 2, false, 'theta_sequence'),
  place_fields:     nd('any', null, false, 'place_fields'),
  phase_precession: nd('any', null, false, 'phase_precession'),
};

export function parsePortType(spec) {
  if (!spec) return { container: 'any' };
  const s = String(spec).trim();
  if (s === 'any' || s === 'NeuroData[any]') return { container: 'any' };
  if (s === 'float' || s === 'int' || s === 'bool') return { container: 'scalar', dtype: s };
  if (s === 'str') return { container: 'str' };
  if (s === 'dict') return { container: 'dict' };
  if (s === 'list' || /^list\[/.test(s)) return { container: 'list' };
  const m = /^NeuroData\[([A-Za-z0-9_]+)\]$/.exec(s);
  if (m) return LEGACY[m[1]] ?? nd('any', null, null, m[1]);
  const a = /^array<\s*(float|int|bool|any)\s*(?:,\s*(\d)d\s*)?(?:,\s*(timed|untimed)\s*)?>$/.exec(s);
  if (a) return { container: 'neurodata', dtype: a[1], ndim: a[2] ? Number(a[2]) : null, timed: a[3] ? a[3] === 'timed' : null };
  if (LEGACY[s]) return LEGACY[s];
  return { container: 'any' };
}

const dtypeOk = (o, r) =>
  r == null || r === 'any' || o == null || o === 'any' || o === r || (o === 'int' && r === 'float');

const isAncestor = (role, anc) => {
  let cur = role; const seen = new Set();
  while (cur && !seen.has(cur)) { if (cur === anc) return true; seen.add(cur); cur = ROLE_PARENTS[cur]; }
  return false;
};
const roleMatches = (a, b) => a === b || isAncestor(a, b) || isAncestor(b, a);

/**
 * Three-state compatibility: 'ok' | 'warn' | 'error'.
 * Mirrors backend check_types(): structure is hard, role is a soft warning.
 */
export function compatState(srcType, tgtType) {
  const out = parsePortType(srcType);
  const req = parsePortType(tgtType);
  if (req.container !== 'any' && out.container !== 'any') {
    if (out.container !== req.container) return 'error';
    if (req.container === 'neurodata' || req.container === 'scalar') {
      if (!dtypeOk(out.dtype, req.dtype)) return 'error';
    }
    if (req.container === 'neurodata') {
      if (req.ndim != null && out.ndim != null && out.ndim !== req.ndim) return 'error';
      if (req.timed === true && out.timed === false) return 'error';
    }
  }
  if (req.role && out.role && !roleMatches(out.role, req.role)) return 'warn';
  return 'ok';
}

/**
 * Backward-compatible boolean check (true unless a hard structural error).
 */
export function isCompatible(srcType, tgtType) {
  return compatState(srcType, tgtType) !== 'error';
}
