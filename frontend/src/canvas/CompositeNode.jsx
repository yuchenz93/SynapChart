import { useContext } from 'react';
import { Handle, Position } from 'reactflow';
import usePipelineStore, { compositeBlockToDefinition } from '../store/pipelineStore';
import { CanvasContext, compatState } from './CanvasContext';

/** Maps composite category names to header background colors. */
const CATEGORY_COLORS = {
  'Composite':     '#6366f1',  // indigo — default composite color
  'Data I/O':      '#5DCAA5',
  'Behavior':      '#EF9F27',
  'LFP / EEG':    '#7F77DD',
  'Spikes':        '#D85A30',
  'Visualization': '#378ADD',
};

const STATUS_STYLES = {
  pending: { background: '#9ca3af', label: '●' },
  running: { background: '#3b82f6', label: '⟳', spin: true },
  done:    { background: '#22c55e', label: '✓' },
  cached:  { background: '#eab308', label: '⚡' },
  error:   { background: '#ef4444', label: '✕' },
};

/**
 * Composite block node renderer — visually distinct from BlockNode.
 *
 * Shows a double border, a ⊞ icon in the header, and a "Drill in" button.
 *
 * @param {object} props
 * @param {string} props.id   - Node ID
 * @param {object} props.data - { block_type_id, parameters, definition?, onDrillIn? }
 */
export default function CompositeNode({ id, data }) {
  const nodeStatuses      = usePipelineStore(s => s.nodeStatuses);
  const compositeBlocks   = usePipelineStore(s => s.compositeBlocks);
  const edges             = usePipelineStore(s => s.edges);
  const breakpointNodeIds = usePipelineStore(s => s.breakpointNodeIds);
  const hasBreakpoint     = breakpointNodeIds.has(id);

  const ctx = useContext(CanvasContext);
  const pending         = ctx?.pendingConnection ?? null;
  const handlePortClick = ctx?.handlePortClick ?? null;
  const onDrillIn       = ctx?.onDrillIn ?? null;

  // Resolve definition: embedded in node data → compositeBlocks store
  const definition = data.definition ?? (() => {
    const cb = compositeBlocks.find(b => b.block_type_id === data.block_type_id);
    if (cb) return compositeBlockToDefinition(cb);
    return null;
  })();

  const displayName  = definition?.display_name ?? data.block_type_id;
  const category     = definition?.category ?? 'Composite';
  const inputs       = definition?.inputs  ?? [];
  const outputs      = definition?.outputs ?? [];
  const headerColor  = CATEGORY_COLORS[category] ?? '#6366f1';
  const status       = nodeStatuses[id] ?? 'pending';
  const statusStyle  = STATUS_STYLES[status] ?? STATUS_STYLES.pending;
  const isRunning    = status === 'running';
  const isSourceNode = pending?.sourceNodeId === id;

  const isOccupied = (portId) =>
    edges.some(e => e.target === id && e.targetHandle === portId);

  const targetHandleStyle = (port) => {
    const occupied = isOccupied(port.port_id);
    if (pending && !isSourceNode) {
      const state = compatState(pending.sourcePortType, port.type);
      const ringColor = state === 'ok' ? '#22c55e' : state === 'warn' ? '#f59e0b' : '#ef4444';
      return {
        width: 10, height: 10,
        background: occupied ? ringColor : 'transparent',
        border: `2px solid ${ringColor}`,
        boxShadow: `0 0 5px ${ringColor}80`,
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

  return (
    <div style={{
      // Double border effect: outer box-shadow mimics a second border
      border: `2px solid ${isRunning ? '#3b82f6' : headerColor}`,
      outline: `1px solid ${isRunning ? '#3b82f6' : headerColor}`,
      outlineOffset: 2,
      borderRadius: 6,
      minWidth: 180,
      background: '#1a1f2e',
      color: '#f9fafb',
      fontSize: 12,
      boxShadow: isRunning
        ? `0 0 0 0 rgba(59,130,246,0.6), 0 0 12px ${headerColor}40`
        : `0 2px 8px rgba(0,0,0,0.4), 0 0 8px ${headerColor}30`,
      animation: isRunning ? 'nf-pulse 1.4s ease-out infinite' : 'none',
    }}>

      {/* ── Header ── */}
      <div style={{
        background: headerColor,
        borderRadius: '4px 4px 0 0',
        padding: '4px 8px',
        fontWeight: 700,
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}>
        {/* ⊞ composite icon */}
        <span style={{
          fontSize: 11, fontWeight: 900,
          background: 'rgba(0,0,0,0.3)',
          borderRadius: 3, padding: '0 3px',
          flexShrink: 0, letterSpacing: 0,
        }}>⊞</span>
        <span style={{ flex: 1 }}>{displayName}</span>
        {hasBreakpoint && (
          <div title="Breakpoint set" style={{
            width: 10, height: 10, borderRadius: '50%',
            backgroundColor: '#ef4444',
            boxShadow: '0 0 0 2px #fff',
            flexShrink: 0,
          }} />
        )}
        <span title="Composite block" style={{
          fontSize: 9, lineHeight: '14px', padding: '0 4px',
          background: 'rgba(0,0,0,0.35)', borderRadius: 3,
          color: '#fff', flexShrink: 0,
        }}>
          composite
        </span>
      </div>

      {/* ── Input ports ── */}
      {inputs.length > 0 && (
        <div style={{ padding: '4px 8px' }}>
          {inputs.map(port => (
            <div key={port.port_id} style={{
              position: 'relative', padding: '2px 0',
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <Handle
                type="target"
                position={Position.Left}
                id={port.port_id}
                title={`${port.port_id}: ${port.type ?? ''}`}
                style={targetHandleStyle(port)}
                onClick={handlePortClick
                  ? (e) => handlePortClick(e, id, port.port_id, port.type, 'target')
                  : undefined}
              />
              <span style={{ marginLeft: 6, color: '#d1d5db' }}>{port.port_id}</span>
            </div>
          ))}
        </div>
      )}

      {/* ── Output ports ── */}
      {outputs.length > 0 && (
        <div style={{
          padding: '4px 8px',
          borderTop: inputs.length ? '1px solid #2d3748' : undefined,
        }}>
          {outputs.map(port => (
            <div key={port.port_id} style={{
              position: 'relative', padding: '2px 0',
              display: 'flex', alignItems: 'center',
              justifyContent: 'flex-end', gap: 4,
            }}>
              <span style={{ marginRight: 6, color: '#d1d5db' }}>{port.port_id}</span>
              <Handle
                type="source"
                position={Position.Right}
                id={port.port_id}
                title={`${port.port_id}: ${port.type ?? ''}`}
                style={sourceHandleStyle(port)}
                onClick={handlePortClick
                  ? (e) => handlePortClick(e, id, port.port_id, port.type, 'source')
                  : undefined}
              />
            </div>
          ))}
        </div>
      )}

      {/* ── Footer: status + drill-in button ── */}
      <div style={{
        borderTop: '1px solid #2d3748',
        padding: '3px 8px',
        display: 'flex', alignItems: 'center', gap: 6,
        borderRadius: '0 0 4px 4px',
        background: '#111827',
      }}>
        <span style={{
          color: statusStyle.background, fontSize: 10,
          animation: isRunning ? 'nf-spin 1s linear infinite' : 'none',
        }}>
          {statusStyle.label}
        </span>
        <span style={{ color: '#9ca3af', fontSize: 10, flex: 1 }}>{status}</span>
        <button
          title="Drill into subflow"
          onClick={(e) => {
            e.stopPropagation();
            onDrillIn?.(id, definition);
          }}
          style={{
            background: 'rgba(99,102,241,0.2)', border: '1px solid #6366f1',
            borderRadius: 3, color: '#a5b4fc', fontSize: 10,
            padding: '1px 6px', cursor: 'pointer',
          }}
          onMouseEnter={e => e.currentTarget.style.background = 'rgba(99,102,241,0.4)'}
          onMouseLeave={e => e.currentTarget.style.background = 'rgba(99,102,241,0.2)'}
        >
          ⊞ Drill in
        </button>
      </div>
    </div>
  );
}
