import { useRef, useEffect, useState } from 'react';
import usePipelineStore from '../store/pipelineStore';

const STATUS_META = {
  pending: { icon: '○', color: '#4b5563' },
  running: { icon: '⟳', color: '#3b82f6' },
  done:    { icon: '✓', color: '#22c55e' },
  cached:  { icon: '⚡', color: '#eab308' },
  error:   { icon: '✕', color: '#ef4444' },
};

/**
 * Collapsible bottom tray that shows pipeline execution progress.
 * Appears automatically when a run starts; persists until manually dismissed.
 */
export default function RunProgress() {
  const { executionOrder, nodeStatuses, runStatus, nodes, blockIndex, pipelineErrors } = usePipelineStore();
  const [collapsed, setCollapsed] = useState(false);
  const listRef = useRef(null);

  // Show the panel whenever a run has been started or there are errors to report
  const visible = executionOrder.length > 0 || pipelineErrors.length > 0;

  const completed = executionOrder.filter(
    id => ['done', 'cached', 'error'].includes(nodeStatuses[id])
  ).length;
  const total = executionOrder.length;
  const pct = total ? (completed / total) * 100 : 0;

  const isRunning = runStatus === 'running';
  const barColor = runStatus === 'error' ? '#ef4444'
    : runStatus === 'done'  ? '#22c55e'
    : '#3b82f6';

  const headerLabel = isRunning
    ? `Running  ${completed} / ${total}`
    : runStatus === 'done'    ? `Done  ${total} / ${total}`
    : runStatus === 'error'   ? `Error  ${completed} / ${total}`
    : runStatus === 'stopped' ? `Stopped  ${completed} / ${total}`
    : `${completed} / ${total}`;

  // Auto-scroll to the currently running block
  useEffect(() => {
    if (collapsed || !listRef.current) return;
    const el = listRef.current.querySelector('[data-running="true"]');
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [nodeStatuses, collapsed]);

  // Auto-expand whenever a new run starts
  useEffect(() => {
    if (isRunning) setCollapsed(false);
  }, [isRunning]);

  const getDisplayName = (nodeId) => {
    const wfNode = nodes.find(n => n.id === nodeId);
    if (!wfNode) return nodeId;
    return blockIndex[wfNode.data.block_type_id]?.display_name ?? wfNode.data.block_type_id;
  };

  if (!visible) return null;

  return (
    <div style={{
      borderTop: '1px solid #374151',
      background: '#0f172a',
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      maxHeight: collapsed ? 36 : 200,
      transition: 'max-height 0.2s ease',
      overflow: 'hidden',
    }}>
      {/* Header row */}
      <div
        onClick={() => setCollapsed(c => !c)}
        style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '0 12px', height: 36, flexShrink: 0,
          cursor: 'pointer', userSelect: 'none',
          borderBottom: collapsed ? 'none' : '1px solid #1e293b',
        }}
      >
        {/* Spinner or status dot */}
        <span style={{
          fontSize: 13, color: barColor,
          display: 'inline-block',
          animation: isRunning ? 'nf-spin 1s linear infinite' : 'none',
        }}>
          {isRunning ? '⟳' : runStatus === 'done' ? '✓' : runStatus === 'error' ? '✕' : '■'}
        </span>

        {/* Label */}
        <span style={{ fontSize: 12, color: '#f9fafb', fontWeight: 600 }}>{headerLabel}</span>

        {/* Progress bar */}
        <div style={{ flex: 1, height: 4, background: '#1e293b', borderRadius: 2 }}>
          <div style={{
            height: '100%', width: `${pct}%`,
            background: barColor, borderRadius: 2,
            transition: 'width 0.3s ease',
          }} />
        </div>

        <span style={{ fontSize: 11, color: '#6b7280', minWidth: 34, textAlign: 'right' }}>
          {Math.round(pct)}%
        </span>

        {/* Collapse toggle */}
        <span style={{ fontSize: 11, color: '#6b7280', marginLeft: 4 }}>
          {collapsed ? '▲' : '▼'}
        </span>
      </div>

      {/* Error messages (e.g. validation failures) */}
      {!collapsed && pipelineErrors.length > 0 && (
        <div style={{ padding: '6px 12px', borderBottom: '1px solid #1e293b' }}>
          {pipelineErrors.map((err, i) => (
            <div key={i} style={{ fontSize: 11, color: '#f87171', display: 'flex', gap: 6, marginBottom: 2 }}>
              <span style={{ flexShrink: 0 }}>⚠</span>
              <span style={{ wordBreak: 'break-word' }}>{err}</span>
            </div>
          ))}
        </div>
      )}

      {/* Block list */}
      {!collapsed && (
        <div ref={listRef} style={{ flex: 1, overflowY: 'auto' }}>
          {executionOrder.map((nodeId) => {
            const status = nodeStatuses[nodeId] ?? 'pending';
            const meta = STATUS_META[status] ?? STATUS_META.pending;
            const isNodeRunning = status === 'running';
            const isDim = status === 'done' || status === 'cached';

            return (
              <div
                key={nodeId}
                data-running={isNodeRunning ? 'true' : undefined}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  padding: '3px 12px', fontSize: 12,
                  background: isNodeRunning ? 'rgba(59,130,246,0.1)' : 'transparent',
                  borderLeft: `3px solid ${isNodeRunning ? '#3b82f6' : 'transparent'}`,
                }}
              >
                <span style={{
                  color: meta.color, width: 14, textAlign: 'center', fontWeight: 600,
                  display: 'inline-block',
                  animation: isNodeRunning ? 'nf-spin 1s linear infinite' : 'none',
                }}>
                  {meta.icon}
                </span>

                <span style={{ color: isDim ? '#6b7280' : isNodeRunning ? '#93c5fd' : '#e5e7eb' }}>
                  {getDisplayName(nodeId)}
                </span>

                {status === 'cached' && (
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: '#eab308' }}>cached</span>
                )}
                {status === 'error' && (
                  <span style={{ marginLeft: 'auto', fontSize: 10, color: '#ef4444' }}>error</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
