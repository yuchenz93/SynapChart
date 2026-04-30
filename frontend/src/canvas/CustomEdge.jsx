/**
 * CustomEdge — a React Flow edge with a draggable midpoint control handle.
 *
 * Behaviour:
 *  - Default: standard React Flow bezier path.
 *  - When selected: a ⬤ handle appears at the midpoint of the edge.
 *  - Drag the handle to bend the edge (stored as a quadratic bezier control point).
 *  - Double-click the handle to snap back to the default straight bezier.
 *
 * Data shape stored in edge.data:
 *   { cp: { x: number, y: number } | null }
 *   cp is in React Flow's *flow coordinate* space (same units as node.position).
 */

import { useCallback, useState } from 'react';
import { getBezierPath, useReactFlow } from 'reactflow';
import usePipelineStore from '../store/pipelineStore';

export default function CustomEdge({
  id,
  sourceX, sourceY, sourcePosition,
  targetX, targetY, targetPosition,
  data = {},
  selected,
  style = {},
  markerEnd,
}) {
  const { getViewport } = useReactFlow();

  // Keep handle visible even when edge loses focus during drag
  const [isDragging, setIsDragging] = useState(false);

  // ── Control point ────────────────────────────────────────────────────────
  const cp = data?.cp ?? null;   // { x, y } in flow coords, or null for default

  // Geometric midpoint (used as default handle position)
  const midX = (sourceX + targetX) / 2;
  const midY = (sourceY + targetY) / 2;

  // ── Build SVG path ───────────────────────────────────────────────────────
  let edgePath;

  if (cp) {
    // Quadratic bezier through the user's control point:
    // The on-curve point at t=0.5 is: 0.25*S + 0.5*C + 0.25*T = cp
    // Solving for C: C = 2*cp - 0.5*S - 0.5*T
    const qcx = 2 * cp.x - 0.5 * sourceX - 0.5 * targetX;
    const qcy = 2 * cp.y - 0.5 * sourceY - 0.5 * targetY;
    edgePath = `M ${sourceX},${sourceY} Q ${qcx},${qcy} ${targetX},${targetY}`;
  } else {
    [edgePath] = getBezierPath({
      sourceX, sourceY, sourcePosition,
      targetX, targetY, targetPosition,
    });
  }

  // Visual position of the handle
  const handlePos = cp ?? { x: midX, y: midY };

  // ── Drag control handle ──────────────────────────────────────────────────
  const onHandleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    // Stop both React synthetic propagation AND native event propagation so
    // React Flow's pane never sees this mousedown and never starts panning.
    e.stopPropagation();
    e.nativeEvent?.stopImmediatePropagation();
    e.preventDefault();
    setIsDragging(true);

    // Capture viewport transform ONCE at drag start.
    // Re-querying on every mousemove would give wrong coords if the canvas
    // pans simultaneously (shouldn't happen, but this is more robust).
    const { x: vpX, y: vpY, zoom } = getViewport();
    const pane = document.querySelector('.react-flow__pane');
    if (!pane) { setIsDragging(false); return; }
    const rect = pane.getBoundingClientRect();

    const toFlow = (sx, sy) => ({
      x: (sx - rect.left - vpX) / zoom,
      y: (sy - rect.top  - vpY) / zoom,
    });

    const onMove = (me) => {
      usePipelineStore.setState(state => ({
        edges: state.edges.map(ed =>
          ed.id === id
            ? { ...ed, data: { ...ed.data, cp: toFlow(me.clientX, me.clientY) } }
            : ed
        ),
      }));
    };

    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
      setIsDragging(false);
      usePipelineStore.getState().setDirty(true);
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  }, [id, getViewport]);

  // ── Reset to default on double-click ────────────────────────────────────
  const onHandleDoubleClick = useCallback((e) => {
    e.stopPropagation();
    usePipelineStore.setState(state => ({
      edges: state.edges.map(ed =>
        ed.id === id
          ? { ...ed, data: { ...ed.data, cp: null } }
          : ed
      ),
    }));
    usePipelineStore.getState().setDirty(true);
  }, [id]);

  // ── Visual style ─────────────────────────────────────────────────────────
  const strokeColor = selected
    ? '#a5b4fc'
    : (style.stroke ?? '#4b5563');
  const strokeWidth = selected
    ? 2.5
    : (style.strokeWidth ?? 1.5);

  return (
    <>
      {/* Visible edge path */}
      <path
        id={id}
        d={edgePath}
        fill="none"
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        markerEnd={markerEnd}
        style={{
          filter: selected
            ? 'drop-shadow(0 0 4px rgba(165,180,252,0.5))'
            : undefined,
          transition: 'stroke 0.12s, stroke-width 0.12s',
        }}
      />

      {/* Wide transparent path to make clicking easier */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={14}
        style={{ cursor: 'pointer' }}
      />

      {/* Midpoint drag handle — visible when selected or actively dragging */}
      {(selected || isDragging) && (
        <g>
          {/* Outer glow ring */}
          <circle
            cx={handlePos.x}
            cy={handlePos.y}
            r={9}
            fill="none"
            stroke="#818cf8"
            strokeWidth={1}
            opacity={0.35}
          />
          {/* Wide invisible hit area so the handle is easy to grab */}
          <circle
            cx={handlePos.x}
            cy={handlePos.y}
            r={12}
            fill="rgba(0,0,0,0.01)"
            className="nopan"
            style={{ cursor: isDragging ? 'grabbing' : 'grab', pointerEvents: 'all' }}
            onMouseDown={onHandleMouseDown}
            onDoubleClick={onHandleDoubleClick}
          />
          {/* Main handle dot */}
          <circle
            cx={handlePos.x}
            cy={handlePos.y}
            r={6}
            fill="#1e293b"
            stroke="#a5b4fc"
            strokeWidth={2}
            style={{ pointerEvents: 'none' }}
          />
          {/* Tooltip cue — small inner dot */}
          <circle
            cx={handlePos.x}
            cy={handlePos.y}
            r={2}
            fill="#a5b4fc"
            style={{ pointerEvents: 'none' }}
          />
          <title>Drag to bend · Double-click to straighten</title>
        </g>
      )}
    </>
  );
}
