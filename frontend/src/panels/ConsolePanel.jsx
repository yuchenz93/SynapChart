import { useState, useRef, useEffect, useCallback } from 'react';
import usePipelineStore from '../store/pipelineStore';
import WorkspacePanel from './WorkspacePanel';

const TYPE_META = {
  info:    { color: '#9ca3af', dot: '#9ca3af' },
  success: { color: '#22c55e', dot: '#22c55e' },
  warning: { color: '#eab308', dot: '#eab308' },
  error:   { color: '#f87171', dot: '#ef4444' },
};

const FILTERS = ['all', 'info', 'warning', 'error'];

/**
 * Collapsible console panel — shown at the bottom of the canvas area.
 *
 * Displays:
 *  - Connection validation results (info / warning / error)
 *  - Backend WebSocket execution logs (info / success / error)
 *  - "Save block to library" confirmations (success)
 *
 * Auto-expands on new error or warning messages.
 * Supports drag-to-resize, Clear, Copy all, and type filters.
 */
export default function ConsolePanel() {
  const consoleMessages      = usePipelineStore(s => s.consoleMessages);
  const clearConsoleMessages = usePipelineStore(s => s.clearConsoleMessages);
  const isPaused             = usePipelineStore(s => s.isPaused);
  const activeConsoleTab     = usePipelineStore(s => s.activeConsoleTab);
  const setActiveConsoleTab  = usePipelineStore(s => s.setActiveConsoleTab);

  const [collapsed, setCollapsed] = useState(true);
  const [height,    setHeight]    = useState(200);
  const [filter,    setFilter]    = useState('all');
  const [expanded,  setExpanded]  = useState(new Set()); // expanded traceback IDs

  // Auto-expand and switch to Workspace tab when paused
  useEffect(() => {
    if (isPaused) setCollapsed(false);
  }, [isPaused]);

  const listRef    = useRef(null);
  const isDragging = useRef(false);
  const dragStartY = useRef(0);
  const dragStartH = useRef(0);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (collapsed || !listRef.current) return;
    listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [consoleMessages, collapsed]);

  // Auto-expand panel on new errors / warnings
  useEffect(() => {
    const latest = consoleMessages[consoleMessages.length - 1];
    if (latest && (latest.type === 'error' || latest.type === 'warning')) {
      setCollapsed(false);
    }
  }, [consoleMessages]);

  // ── Drag-to-resize ────────────────────────────────────────────────────────
  const onDragStart = useCallback((e) => {
    e.preventDefault();
    isDragging.current = true;
    dragStartY.current = e.clientY;
    dragStartH.current = height;

    const onMove = (ev) => {
      if (!isDragging.current) return;
      const delta = dragStartY.current - ev.clientY;
      setHeight(Math.max(100, Math.min(600, dragStartH.current + delta)));
    };
    const onUp = () => {
      isDragging.current = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [height]);

  const toggleTraceback = useCallback((id) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const copyAll = useCallback(() => {
    const text = consoleMessages
      .map(m => `[${m.timestamp}] [${m.type.toUpperCase()}]${m.nodeId ? ` [${m.nodeId}]` : ''} ${m.text}`)
      .join('\n');
    navigator.clipboard.writeText(text).catch(() => {});
  }, [consoleMessages]);

  const latest  = consoleMessages[consoleMessages.length - 1];
  const dotColor = latest ? (TYPE_META[latest.type]?.dot ?? '#6b7280') : '#6b7280';

  const filtered = filter === 'all'
    ? consoleMessages
    : consoleMessages.filter(m => m.type === filter);

  return (
    <div style={{
      flexShrink: 0,
      background: '#0f172a',
      borderTop: '1px solid #374151',
      display: 'flex',
      flexDirection: 'column',
      height: collapsed ? 28 : height,
      overflow: 'hidden',
      transition: collapsed ? 'height 0.15s ease' : undefined,
    }}>

      {/* ── Drag handle (only when expanded) ── */}
      {!collapsed && (
        <div
          onMouseDown={onDragStart}
          style={{
            height: 5, flexShrink: 0, cursor: 'ns-resize',
            background: 'transparent',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = '#374151'; }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; }}
        />
      )}

      {/* ── Summary bar ── */}
      <div
        style={{
          display: 'flex', alignItems: 'center',
          padding: '0 10px', height: 28, flexShrink: 0,
          borderBottom: collapsed ? 'none' : '1px solid #1e293b',
          userSelect: 'none',
        }}
      >
        {/* Collapse toggle + label */}
        <div
          onClick={() => setCollapsed(c => !c)}
          style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', flex: 1, minWidth: 0 }}
        >
          <span style={{ fontSize: 10, color: '#6b7280', fontWeight: 700, letterSpacing: '0.06em' }}>
            CONSOLE
          </span>
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: dotColor, flexShrink: 0,
          }} />
          <span style={{
            fontSize: 11,
            color: latest ? (TYPE_META[latest.type]?.color ?? '#9ca3af') : '#4b5563',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            flex: 1,
          }}>
            {latest ? latest.text : 'No messages'}
          </span>
        </div>
        {/* Tab strip (always visible) */}
        <div style={{ display: 'flex', gap: 0, marginLeft: 8, flexShrink: 0 }}>
          {['logs', 'workspace'].map(tab => (
            <button
              key={tab}
              onClick={(e) => { e.stopPropagation(); setCollapsed(false); setActiveConsoleTab(tab); }}
              style={{
                background: activeConsoleTab === tab ? '#1e293b' : 'none',
                border: 'none',
                borderBottom: activeConsoleTab === tab ? '2px solid #6366f1' : '2px solid transparent',
                color: activeConsoleTab === tab ? '#f9fafb' : '#6b7280',
                padding: '0 10px', fontSize: 10, cursor: 'pointer',
                height: 28, display: 'flex', alignItems: 'center', gap: 4,
                textTransform: 'capitalize',
              }}
            >
              {tab}
              {tab === 'workspace' && isPaused && (
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: '#ef4444', display: 'inline-block',
                }} />
              )}
            </button>
          ))}
        </div>
        <span
          onClick={() => setCollapsed(c => !c)}
          style={{ fontSize: 10, color: '#6b7280', cursor: 'pointer', padding: '0 4px' }}
        >
          {collapsed ? '▲' : '▼'}
        </span>
      </div>

      {/* ── Logs tab: toolbar + message list ── */}
      {!collapsed && activeConsoleTab === 'logs' && (
        <>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 4,
            padding: '3px 10px', borderBottom: '1px solid #1e293b',
            flexShrink: 0,
          }}>
            {FILTERS.map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: '1px 8px', fontSize: 10, fontWeight: 600,
                  background: filter === f ? '#374151' : 'none',
                  border: `1px solid ${filter === f ? '#4b5563' : 'transparent'}`,
                  borderRadius: 3,
                  color: filter === f ? '#f9fafb' : '#6b7280',
                  cursor: 'pointer', textTransform: 'capitalize',
                }}
              >
                {f}
              </button>
            ))}
            <div style={{ flex: 1 }} />
            {['Copy all', 'Clear'].map((label) => (
              <button
                key={label}
                onClick={label === 'Clear' ? clearConsoleMessages : copyAll}
                style={{
                  padding: '1px 8px', fontSize: 10,
                  background: 'none', border: '1px solid transparent',
                  borderRadius: 3, color: '#6b7280', cursor: 'pointer',
                }}
                onMouseEnter={e => {
                  e.currentTarget.style.color = '#f9fafb';
                  e.currentTarget.style.borderColor = '#4b5563';
                }}
                onMouseLeave={e => {
                  e.currentTarget.style.color = '#6b7280';
                  e.currentTarget.style.borderColor = 'transparent';
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <div ref={listRef} style={{ flex: 1, overflowY: 'auto', padding: '3px 0' }}>
            {filtered.length === 0 ? (
              <div style={{ padding: '5px 12px', fontSize: 11, color: '#4b5563' }}>
                No messages
              </div>
            ) : filtered.map(msg => {
              const meta = TYPE_META[msg.type] ?? TYPE_META.info;
              const isExp = expanded.has(msg.id);
              return (
                <div key={msg.id} style={{ padding: '1px 12px', fontFamily: 'monospace' }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 5, flexWrap: 'wrap' }}>
                    <span style={{ color: '#4b5563', fontSize: 10, flexShrink: 0 }}>
                      {msg.timestamp}
                    </span>
                    {msg.nodeId && (
                      <span style={{ color: '#6b7280', fontSize: 10, flexShrink: 0 }}>
                        [{msg.nodeId}]
                      </span>
                    )}
                    <span style={{ color: meta.color, fontSize: 11, wordBreak: 'break-word', flex: 1 }}>
                      {msg.text}
                    </span>
                    {msg.traceback && (
                      <button
                        onClick={() => toggleTraceback(msg.id)}
                        style={{
                          fontSize: 10, color: '#6b7280',
                          background: 'none', border: 'none',
                          cursor: 'pointer', padding: '0 0 0 4px', flexShrink: 0,
                        }}
                      >
                        {isExp ? '▾ traceback' : '▸ traceback'}
                      </button>
                    )}
                  </div>
                  {msg.traceback && isExp && (
                    <pre style={{
                      margin: '2px 0 4px 0', padding: '4px 8px',
                      background: '#1e293b', borderRadius: 3,
                      color: '#f87171', fontSize: 10,
                      overflowX: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    }}>
                      {msg.traceback}
                    </pre>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* ── Workspace tab ── */}
      {!collapsed && activeConsoleTab === 'workspace' && (
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <WorkspacePanel />
        </div>
      )}
    </div>
  );
}
