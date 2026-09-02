/**
 * BlockNode — React Flow custom node renderer for SynapChart blocks.
 *
 * Features:
 *  - Port reordering: long-press (600 ms) any port row → "jiggle mode".
 *    In jiggle mode all ports in that group (inputs or outputs) wiggle and show
 *    a ≡ grab icon.  Drag a port to reorder; release to confirm.
 *    Press Escape or click another node to exit.
 *  - Port order is persisted in node.data.portOrder and saved with the workflow.
 *  - Slightly transparent block background so edges behind it remain visible.
 */

import { useContext, useState, useRef, useCallback, useEffect } from 'react';
import { Handle, Position } from 'reactflow';
import usePipelineStore, { localBlockToDefinition } from '../store/pipelineStore';
import { CanvasContext, compatState } from './CanvasContext';

// ── Constants ─────────────────────────────────────────────────────────────────

const CATEGORY_COLORS = {
  'Data I/O':      '#5DCAA5',
  'CRCNS I/O':     '#5DCAA5',
  'Behavior':      '#EF9F27',
  'LFP / EEG':    '#7F77DD',
  'Spikes':        '#D85A30',
  'Visualization': '#378ADD',
  'Composite':     '#6366f1',
  'Flow control':  '#14b8a6',
  'local':         '#7c3aed',
};

const STATUS_STYLES = {
  pending:    { background: '#9ca3af', label: '●' },
  running:    { background: '#3b82f6', label: '⟳', spin: true },
  done:       { background: '#22c55e', label: '✓' },
  viz_result: { background: '#22c55e', label: '✓' },
  cached:     { background: '#eab308', label: '⚡' },
  error:      { background: '#ef4444', label: '✕' },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Reorder ports according to a saved portId array, appending unseen ports at end. */
function applyPortOrder(ports, savedIds) {
  if (!savedIds?.length) return ports;
  const byId = Object.fromEntries(ports.map(p => [p.port_id, p]));
  const ordered  = savedIds.filter(id => byId[id]).map(id => byId[id]);
  const unseen   = ports.filter(p => !savedIds.includes(p.port_id));
  return [...ordered, ...unseen];
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function BlockNode({ id, data, selected }) {
  const nodeStatuses      = usePipelineStore(s => s.nodeStatuses);
  const blockIndex        = usePipelineStore(s => s.blockIndex);
  const localBlocks       = usePipelineStore(s => s.localBlocks);
  const edges             = usePipelineStore(s => s.edges);
  const breakpointNodeIds = usePipelineStore(s => s.breakpointNodeIds);
  const hasBreakpoint     = breakpointNodeIds.has(id);

  const ctx             = useContext(CanvasContext);
  const pending         = ctx?.pendingConnection ?? null;
  const handlePortClick = ctx?.handlePortClick   ?? null;

  // ── Block definition ───────────────────────────────────────────────────────
  const definition = data.definition ?? (() => {
    const lb = localBlocks.find(b => b.block_type_id === data.block_type_id);
    if (lb) return localBlockToDefinition(lb);
    return blockIndex[data.block_type_id] ?? null;
  })();

  const isLocal     = data.is_local || definition?.is_local || false;
  const displayName = definition?.display_name ?? data.block_type_id;
  const category    = isLocal ? 'local' : (definition?.category ?? '');
  const inputs      = definition?.inputs  ?? [];

  // Iterator blocks (dataset_iterator) declare outputs=[] statically because
  // their ports are dynamic — one per entry in the column_mappings parameter.
  // Parse column_mappings from the node's current parameters to render live ports.
  let outputs = definition?.outputs ?? [];
  if (definition?.is_iterator) {
    try {
      const raw = (data.parameters?.column_mappings ?? '').trim();
      const colMappings = raw ? JSON.parse(raw) : {};
      const portIds = Object.keys(colMappings);
      outputs = portIds.length
        ? portIds.map(pid => ({ port_id: pid, type: 'str', description: `CSV column "${colMappings[pid]}"` }))
        : [{ port_id: '(set column_mappings)', type: '', description: '' }];
    } catch {
      outputs = [{ port_id: '(invalid column_mappings)', type: '', description: '' }];
    }
  }

  const headerColor = CATEGORY_COLORS[category] ?? '#6b7280';
  const status      = nodeStatuses[id] ?? 'pending';
  const statusStyle = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  const isRunning   = status === 'running';

  // ── Port ordering (from saved data, or definition order) ──────────────────
  const savedOrder     = data.portOrder ?? {};
  const orderedInputs  = applyPortOrder(inputs,  savedOrder.inputs);
  const orderedOutputs = applyPortOrder(outputs, savedOrder.outputs);

  // ── Port reorder state ─────────────────────────────────────────────────────
  // reorderGroup: which port group is in "jiggle" mode
  const [reorderGroup, setReorderGroup] = useState(null); // null | 'inputs' | 'outputs'
  // dragPortId: which port is currently being dragged
  const [dragPortId,  setDragPortId]  = useState(null);
  // dropIdx: current insertion index during drag
  const [dropIdx,     setDropIdx]     = useState(null);

  const longPressTimer   = useRef(null);
  const inputsListRef    = useRef(null);
  const outputsListRef   = useRef(null);

  // ── Exit reorder mode on Escape ────────────────────────────────────────────
  useEffect(() => {
    if (!reorderGroup) return;
    const handler = (e) => { if (e.key === 'Escape') setReorderGroup(null); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [reorderGroup]);

  // ── Long-press: start reorder mode ────────────────────────────────────────
  const onPortRowMouseDown = useCallback((e, group) => {
    if (e.button !== 0 || reorderGroup === group) return;
    // NOTE: do NOT stopPropagation here — React Flow needs to see the mousedown
    // to select the node.  The "nodrag" className on the port list divs already
    // prevents accidental node-dragging when the user clicks in the port area.

    longPressTimer.current = setTimeout(() => {
      setReorderGroup(group);
    }, 600);

    // Cancel only when the mouse button is released — NOT on mouseleave.
    // Port rows are tiny; any slight movement would fire mouseleave and kill
    // the timer before the 600 ms threshold was ever reached.
    const onEarlyUp = () => {
      clearTimeout(longPressTimer.current);
      document.removeEventListener('mouseup', onEarlyUp);
    };
    document.addEventListener('mouseup', onEarlyUp);
  }, [reorderGroup]);

  // ── Drag-to-reorder ────────────────────────────────────────────────────────
  const getDropIdx = useCallback((mouseY, group) => {
    const ref = group === 'inputs' ? inputsListRef : outputsListRef;
    if (!ref.current) return 0;
    const rect  = ref.current.getBoundingClientRect();
    const ports = group === 'inputs' ? orderedInputs : orderedOutputs;
    if (!ports.length) return 0;
    const rowH  = rect.height / ports.length;
    const relY  = mouseY - rect.top;
    return Math.max(0, Math.min(ports.length - 1, Math.floor(relY / rowH)));
  }, [orderedInputs, orderedOutputs]);

  const startPortDrag = useCallback((e, portId, group) => {
    if (reorderGroup !== group) return;
    e.stopPropagation();   // prevent React Flow from moving the node
    e.preventDefault();
    setDragPortId(portId);

    const onMove = (me) => {
      setDropIdx(getDropIdx(me.clientY, group));
    };

    const onUp = (me) => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);

      const ports   = group === 'inputs' ? orderedInputs : orderedOutputs;
      const fromIdx = ports.findIndex(p => p.port_id === portId);
      const toIdx   = getDropIdx(me.clientY, group);

      if (fromIdx !== -1 && fromIdx !== toIdx) {
        const newOrder = ports.map(p => p.port_id);
        newOrder.splice(fromIdx, 1);
        newOrder.splice(toIdx, 0, portId);

        usePipelineStore.setState(state => ({
          nodes: state.nodes.map(n =>
            n.id === id
              ? { ...n, data: { ...n.data, portOrder: {
                  ...n.data.portOrder,
                  [group]: newOrder,
                }}}
              : n
          ),
        }));
        usePipelineStore.getState().setDirty(true);
      }

      setDragPortId(null);
      setDropIdx(null);
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  }, [reorderGroup, orderedInputs, orderedOutputs, getDropIdx, id]);

  // ── Handle styles (same logic as before) ──────────────────────────────────
  const isSourceNode = pending?.sourceNodeId === id;

  const isOccupied = (portId) =>
    edges.some(e => e.target === id && e.targetHandle === portId);

  const targetHandleStyle = (port) => {
    const occupied = isOccupied(port.port_id);
    if (pending && !isSourceNode) {
      // Three-state feedback: green = ok, amber = role warning, red = blocked.
      const state = compatState(pending.sourcePortType, port.type);
      const ringColor = state === 'ok' ? '#22c55e' : state === 'warn' ? '#f59e0b' : '#ef4444';
      return {
        width: 10, height: 10,
        background: occupied ? ringColor : 'transparent',
        border: `2px solid ${ringColor}`,
        boxShadow: `0 0 5px ${ringColor}80`,
        transition: 'box-shadow 0.15s',
        cursor: state !== 'error' && !occupied ? 'pointer' : 'not-allowed',
      };
    }
    return {
      width: 10, height: 10,
      background: occupied ? headerColor : 'transparent',
      border: `2px solid ${headerColor}`,
      cursor: pending ? 'default' : 'crosshair',
    };
  };

  const sourceHandleStyle = (port) => {
    const isActive = isSourceNode && pending.sourcePortId === port.port_id;
    return {
      width: 10, height: 10,
      background: isActive ? '#c4b5fd' : headerColor,
      border: isActive ? '2px solid #a78bfa' : 'none',
      boxShadow: isActive ? '0 0 6px #818cf8' : 'none',
      cursor: 'crosshair',
    };
  };

  // ── Render a single port row ───────────────────────────────────────────────
  const renderInputPort = (port, idx, group) => {
    const inJiggle = reorderGroup === group;
    const isDragging = dragPortId === port.port_id;
    const isDropTarget = inJiggle && dropIdx === idx && dragPortId && dragPortId !== port.port_id;

    return (
      <div
        key={port.port_id}
        // "nodrag" prevents React Flow from starting a node-drag when the user
        // clicks on a port row, while still allowing click-to-select to fire.
        className="nodrag"
        style={{
          position: 'relative',
          padding: '2px 0',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          opacity: isDragging ? 0.4 : 1,
          cursor: inJiggle ? 'grab' : undefined,
          borderTop: isDropTarget ? '2px solid #818cf8' : '2px solid transparent',
          transition: 'border-color 0.1s',
        }}
        onMouseDown={(e) => {
          onPortRowMouseDown(e, group);
          if (inJiggle) startPortDrag(e, port.port_id, group);
        }}
      >
        {/* ≡ drag handle — only in jiggle mode */}
        {inJiggle && (
          <span style={{
            fontSize: 10, color: '#6b7280',
            marginRight: 2, userSelect: 'none',
            cursor: 'grab', flexShrink: 0,
          }}>
            ≡
          </span>
        )}

        <Handle
          type="target"
          position={Position.Left}
          id={port.port_id}
          title={`${port.port_id}: ${port.type ?? ''}`}
          style={{
            ...targetHandleStyle(port),
            // In jiggle mode disable React Flow connect interactions
            pointerEvents: inJiggle ? 'none' : undefined,
          }}
          onClick={!inJiggle && handlePortClick
            ? (e) => handlePortClick(e, id, port.port_id, port.type, 'target')
            : undefined
          }
        />
        <span style={{ marginLeft: 6, color: '#d1d5db', userSelect: 'none' }}>
          {port.port_id}
        </span>
      </div>
    );
  };

  const renderOutputPort = (port, idx, group) => {
    const inJiggle   = reorderGroup === group;
    const isDragging = dragPortId === port.port_id;
    const isDropTarget = inJiggle && dropIdx === idx && dragPortId && dragPortId !== port.port_id;

    return (
      <div
        key={port.port_id}
        className="nodrag"
        style={{
          position: 'relative',
          padding: '2px 0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: 4,
          opacity: isDragging ? 0.4 : 1,
          cursor: inJiggle ? 'grab' : undefined,
          borderTop: isDropTarget ? '2px solid #818cf8' : '2px solid transparent',
          transition: 'border-color 0.1s',
        }}
        onMouseDown={(e) => {
          onPortRowMouseDown(e, group);
          if (inJiggle) startPortDrag(e, port.port_id, group);
        }}
      >
        <span style={{ marginRight: 6, color: '#d1d5db', userSelect: 'none' }}>
          {port.port_id}
        </span>

        {/* ≡ drag handle — only in jiggle mode */}
        {inJiggle && (
          <span style={{
            fontSize: 10, color: '#6b7280',
            marginLeft: 2, userSelect: 'none',
            cursor: 'grab', flexShrink: 0,
          }}>
            ≡
          </span>
        )}

        <Handle
          type="source"
          position={Position.Right}
          id={port.port_id}
          title={`${port.port_id}: ${port.type ?? ''}`}
          style={{
            ...sourceHandleStyle(port),
            pointerEvents: inJiggle ? 'none' : undefined,
          }}
          onClick={!inJiggle && handlePortClick
            ? (e) => handlePortClick(e, id, port.port_id, port.type, 'source')
            : undefined
          }
        />
      </div>
    );
  };

  // ── Root node container ────────────────────────────────────────────────────
  return (
    <div
      // "nodrag" class prevents React Flow from interpreting mousedown on this
      // node as a node-drag while the user is in port-reorder mode.
      className={reorderGroup ? 'nodrag' : undefined}
      style={{
        border: `1px solid ${
          isRunning  ? '#3b82f6' :
          selected   ? '#818cf8' :
                       '#374151'
        }`,
        borderRadius: 6,
        minWidth: 160,
        // Semi-transparent so edges routed behind the block remain visible
        background: 'rgba(31, 41, 55, 0.88)',
        backdropFilter: 'blur(2px)',
        color: '#f9fafb',
        fontSize: 12,
        boxShadow: isRunning
          ? '0 0 0 0 rgba(59,130,246,0.6)'
          : selected
            ? '0 0 0 2px #6366f1, 0 2px 8px rgba(0,0,0,0.4)'
            : '0 2px 8px rgba(0,0,0,0.4)',
        animation: isRunning ? 'nf-pulse 1.4s ease-out infinite' : 'none',
        zIndex: reorderGroup ? 10 : undefined,
        outline: reorderGroup
          ? '2px dashed rgba(129,140,248,0.6)'
          : undefined,
      }}
    >
      {/* ── Header ── */}
      <div style={{
        background: headerColor,
        borderRadius: '5px 5px 0 0',
        padding: '4px 8px',
        fontWeight: 600,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: 'rgba(255,255,255,0.5)',
          display: 'inline-block', flexShrink: 0,
        }} />
        <span style={{ flex: 1 }}>{displayName}</span>
        {hasBreakpoint && (
          <div title="Breakpoint set" style={{
            width: 10, height: 10, borderRadius: '50%',
            backgroundColor: '#ef4444',
            boxShadow: '0 0 0 2px #fff',
            flexShrink: 0,
          }} />
        )}
        {reorderGroup && (
          <span
            title="Press Escape or click elsewhere to exit reorder mode"
            style={{
              fontSize: 9, lineHeight: '14px', padding: '0 4px',
              background: 'rgba(0,0,0,0.3)', borderRadius: 3,
              color: '#fff', flexShrink: 0, cursor: 'default',
            }}
          >
            reordering
          </span>
        )}
        {!reorderGroup && isLocal && (
          <span title="Workflow-local block" style={{
            fontSize: 9, lineHeight: '14px', padding: '0 4px',
            background: 'rgba(0,0,0,0.35)', borderRadius: 3,
            color: '#fff', flexShrink: 0,
          }}>
            local
          </span>
        )}
      </div>

      {/* ── Input ports ── */}
      {orderedInputs.length > 0 && (
        <div
          ref={inputsListRef}
          className="nodrag"
          style={{ padding: '4px 8px' }}
        >
          {orderedInputs.map((port, idx) =>
            renderInputPort(port, idx, 'inputs')
          )}
        </div>
      )}

      {/* ── Hint when reorder mode is active but not the current group ── */}
      {reorderGroup && reorderGroup !== 'inputs' && orderedInputs.length > 0 && (
        <div style={{ padding: '0 8px 2px', fontSize: 9, color: '#6b7280' }}>
          long-press inputs to reorder
        </div>
      )}
      {reorderGroup && reorderGroup !== 'outputs' && orderedOutputs.length > 0 && (
        <div style={{ padding: '0 8px 2px', fontSize: 9, color: '#6b7280', textAlign: 'right' }}>
          long-press outputs to reorder
        </div>
      )}

      {/* ── Output ports ── */}
      {orderedOutputs.length > 0 && (
        <div
          ref={outputsListRef}
          className="nodrag"
          style={{
            padding: '4px 8px',
            borderTop: orderedInputs.length ? '1px solid #374151' : undefined,
          }}
        >
          {orderedOutputs.map((port, idx) =>
            renderOutputPort(port, idx, 'outputs')
          )}
        </div>
      )}

      {/* ── Status bar ── */}
      <div style={{
        borderTop: '1px solid #374151',
        padding: '3px 8px',
        display: 'flex', alignItems: 'center', gap: 4,
        borderRadius: '0 0 5px 5px',
        background: 'rgba(17,24,39,0.85)',
      }}>
        <span style={{
          color: statusStyle.background,
          fontSize: 10,
          display: 'inline-block',
          animation: isRunning ? 'nf-spin 1s linear infinite' : 'none',
        }}>
          {statusStyle.label}
        </span>
        <span style={{ color: '#9ca3af', fontSize: 10 }}>{status}</span>
        {!reorderGroup && (orderedInputs.length > 0 || orderedOutputs.length > 0) && (
          <span
            title="Long-press a port to reorder"
            style={{
              marginLeft: 'auto', fontSize: 9, color: '#4b5563',
              cursor: 'default', userSelect: 'none',
            }}
          >
            ⇅
          </span>
        )}
      </div>
    </div>
  );
}
