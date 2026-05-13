import { useState } from 'react';
import usePipelineStore from '../store/pipelineStore';
import { continueExecution } from '../api/client';
import VariableDetailPopup from '../modals/VariableDetailPopup';

/** Resolve a node ID to a display name from the store. */
function useNodeName(nodeId) {
  const nodes      = usePipelineStore(s => s.nodes);
  const blockIndex = usePipelineStore(s => s.blockIndex);
  const localBlocks = usePipelineStore(s => s.localBlocks);
  if (!nodeId) return nodeId;
  const node = nodes.find(n => n.id === nodeId);
  if (!node) return nodeId;
  const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
  if (lb) return lb.display_name;
  return blockIndex[node.data.block_type_id]?.display_name ?? nodeId;
}

/** One expandable node row in the workspace list. */
function WorkspaceNodeRow({ nodeId, variables, isPausedHere, onVarClick }) {
  const nodeName = useNodeName(nodeId);
  const [expanded, setExpanded] = useState(isPausedHere);

  // Filter out internal _viz port
  const displayVars = (variables ?? []).filter(v => v.port_id !== '_viz');

  return (
    <div style={{ borderBottom: '1px solid #1e293b' }}>
      {/* Node header row */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 10px', cursor: 'pointer', userSelect: 'none',
          background: isPausedHere ? 'rgba(99,102,241,0.12)' : 'transparent',
        }}
        onMouseEnter={e => { if (!isPausedHere) e.currentTarget.style.background = '#1e293b'; }}
        onMouseLeave={e => { if (!isPausedHere) e.currentTarget.style.background = 'transparent'; }}
      >
        <span style={{ color: '#6b7280', fontSize: 11, width: 10 }}>
          {expanded ? '▼' : '▶'}
        </span>
        <span style={{ fontSize: 11, color: isPausedHere ? '#a5b4fc' : '#e5e7eb', fontWeight: isPausedHere ? 700 : 400 }}>
          {nodeName}
        </span>
        {isPausedHere && (
          <span style={{
            fontSize: 9, color: '#ef4444', fontWeight: 700,
            background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)',
            borderRadius: 3, padding: '0 4px', marginLeft: 2,
          }}>
            paused here
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#4b5563' }}>
          {displayVars.length} var{displayVars.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Expanded variable table */}
      {expanded && (
        <div style={{ paddingLeft: 20, paddingBottom: 4 }}>
          {displayVars.length === 0 ? (
            <div style={{ fontSize: 10, color: '#4b5563', padding: '3px 10px' }}>No outputs</div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
              <thead>
                <tr style={{ color: '#6b7280' }}>
                  <th style={thStyle}>Name</th>
                  <th style={thStyle}>Type</th>
                  <th style={thStyle}>Shape</th>
                  <th style={thStyle}>Size</th>
                </tr>
              </thead>
              <tbody>
                {displayVars.map(v => (
                  <tr
                    key={v.port_id}
                    onClick={() => onVarClick(nodeId, v)}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={e => e.currentTarget.style.background = '#1e293b'}
                    onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                  >
                    <td style={tdStyle}>{v.port_id}</td>
                    <td style={{ ...tdStyle, color: '#a5b4fc' }}>{v.data_type}</td>
                    <td style={tdStyle}>{v.shape ? `[${v.shape.join(', ')}]` : '—'}</td>
                    <td style={tdStyle}>{v.size ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

const thStyle = {
  textAlign: 'left', padding: '2px 6px',
  fontWeight: 600, letterSpacing: '0.04em',
  borderBottom: '1px solid #1e293b',
};

const tdStyle = {
  padding: '2px 6px', color: '#d1d5db',
  fontFamily: 'monospace',
};

/** Workspace tab content panel. */
export default function WorkspacePanel() {
  const isPaused       = usePipelineStore(s => s.isPaused);
  const pausedAtNodeId = usePipelineStore(s => s.pausedAtNodeId);
  const workspaceData  = usePipelineStore(s => s.workspaceData);
  const clearWorkspace = usePipelineStore(s => s.clearWorkspace);
  const pausedNodeName = useNodeName(pausedAtNodeId);

  const [openPopups, setOpenPopups] = useState([]);

  const handleContinue = async () => {
    try { await continueExecution(); } catch { /* ignore */ }
    clearWorkspace();
    setOpenPopups([]);
  };

  const handleVarClick = (nodeId, varSummary) => {
    const key = `${nodeId}::${varSummary.port_id}`;
    setOpenPopups(prev => {
      if (prev.find(p => p.key === key)) return prev;
      return [...prev, { key, nodeId, portId: varSummary.port_id, summary: varSummary }];
    });
  };

  const closePopup = (key) => setOpenPopups(prev => prev.filter(p => p.key !== key));

  if (!isPaused) {
    return (
      <div style={{ padding: '20px 16px', color: '#4b5563', fontSize: 12, textAlign: 'center', lineHeight: 1.7 }}>
        Set a breakpoint on any node<br />
        <span style={{ color: '#6b7280', fontSize: 11 }}>
          Right-click a node → "Set breakpoint"
        </span><br />
        <span style={{ color: '#6b7280', fontSize: 11 }}>
          then run the pipeline. Execution will pause here.
        </span>
      </div>
    );
  }

  const nodeIds = Object.keys(workspaceData);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Header bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '5px 10px', borderBottom: '1px solid #1e293b',
        flexShrink: 0, background: '#0f172a',
      }}>
        <span style={{ fontSize: 10, fontWeight: 700, color: '#6b7280', letterSpacing: '0.06em' }}>
          WORKSPACE
        </span>
        <span style={{ fontSize: 11, color: '#9ca3af' }}>·</span>
        <span style={{ fontSize: 11, color: '#a5b4fc' }}>
          Paused at: {pausedNodeName ?? pausedAtNodeId}
        </span>
        <div style={{ marginLeft: 'auto' }}>
          <button
            onClick={handleContinue}
            style={{
              background: '#1d4ed8', border: '1px solid #3b82f6',
              borderRadius: 4, color: '#eff6ff',
              padding: '3px 10px', fontSize: 11, cursor: 'pointer',
              fontWeight: 600,
            }}
            onMouseEnter={e => e.currentTarget.style.background = '#2563eb'}
            onMouseLeave={e => e.currentTarget.style.background = '#1d4ed8'}
          >
            Continue ▶
          </button>
        </div>
      </div>

      {/* Node list */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        {nodeIds.length === 0 ? (
          <div style={{ padding: '12px', color: '#4b5563', fontSize: 11 }}>
            Loading workspace data…
          </div>
        ) : nodeIds.map(nid => (
          <WorkspaceNodeRow
            key={nid}
            nodeId={nid}
            variables={workspaceData[nid]}
            isPausedHere={nid === pausedAtNodeId}
            onVarClick={handleVarClick}
          />
        ))}
      </div>

      {/* Variable detail popups */}
      {openPopups.map((p, i) => (
        <VariableDetailPopup
          key={p.key}
          nodeId={p.nodeId}
          portId={p.portId}
          summary={p.summary}
          initialOffset={i * 30}
          onClose={() => closePopup(p.key)}
        />
      ))}
    </div>
  );
}
