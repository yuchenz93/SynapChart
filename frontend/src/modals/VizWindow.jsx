import { useState, useRef } from 'react';
import usePipelineStore from '../store/pipelineStore';

/**
 * A single draggable, resizable, minimizable plot window.
 *
 * Minimize (–): collapses to title bar only; click title or (–) again to restore.
 * Close (✕):   removes the window entirely.
 * ⬇ Save:      downloads the image as PNG.
 */
export function VizWindowInstance({ nodeId, imageSrc, title, initialOffset, onClose }) {
  const [pos,       setPos]       = useState({ x: 80 + initialOffset, y: 80 + initialOffset });
  const [minimized, setMinimized] = useState(false);

  const dragging   = useRef(false);
  const dragOffset = useRef({ x: 0, y: 0 });

  const onMouseDown = (e) => {
    // Double-click on title toggles minimized
    if (e.detail === 2) {
      setMinimized(v => !v);
      return;
    }
    dragging.current = true;
    dragOffset.current = { x: e.clientX - pos.x, y: e.clientY - pos.y };
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup',   onMouseUp);
  };

  const onMouseMove = (e) => {
    if (!dragging.current) return;
    setPos({ x: e.clientX - dragOffset.current.x, y: e.clientY - dragOffset.current.y });
  };

  const onMouseUp = () => {
    dragging.current = false;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup',   onMouseUp);
  };

  const handleSave = () => {
    const a = document.createElement('a');
    a.href     = imageSrc;
    a.download = `${nodeId}_plot.png`;
    a.click();
  };

  return (
    <div style={{
      position:  'fixed',
      left: pos.x,
      top:  pos.y,
      zIndex:    2000,
      background: '#1f2937',
      border:    '1px solid #374151',
      borderRadius: 8,
      boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      minWidth:  360,
      // When minimized: only show title bar
      width:     minimized ? 360 : 520,
      height:    minimized ? 'auto' : 380,
      resize:    minimized ? 'none' : 'both',
      overflow:  minimized ? 'visible' : 'auto',
      display:   'flex',
      flexDirection: 'column',
    }}>

      {/* ── Title bar ── */}
      <div
        onMouseDown={onMouseDown}
        style={{
          padding:    '8px 12px',
          background: '#111827',
          borderRadius: minimized ? 7 : '7px 7px 0 0',
          display:    'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor:     'move',
          userSelect: 'none',
          borderBottom: minimized ? 'none' : '1px solid #374151',
          flexShrink: 0,
        }}
      >
        <span style={{ color: '#f9fafb', fontSize: 13, fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {title}
        </span>

        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          {/* Save — only when not minimized */}
          {!minimized && (
            <button
              onClick={handleSave}
              onMouseDown={e => e.stopPropagation()}
              style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 12 }}
              title="Save image as PNG"
            >
              ⬇ Save
            </button>
          )}

          {/* Minimize / Restore */}
          <button
            onClick={() => setMinimized(v => !v)}
            onMouseDown={e => e.stopPropagation()}
            style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 16, lineHeight: 1 }}
            title={minimized ? 'Restore' : 'Minimize'}
          >
            {minimized ? '▲' : '▼'}
          </button>

          {/* Close */}
          <button
            onClick={onClose}
            onMouseDown={e => e.stopPropagation()}
            style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 16 }}
            title="Close"
          >
            ✕
          </button>
        </div>
      </div>

      {/* ── Plot image — hidden when minimized ── */}
      {!minimized && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 8, overflow: 'hidden' }}>
          {imageSrc
            ? <img
                src={imageSrc}
                alt={`Plot: ${title}`}
                style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
              />
            : <span style={{ color: '#6b7280', fontSize: 12 }}>No image available.</span>
          }
        </div>
      )}
    </div>
  );
}

/**
 * Renders all open visualization windows.
 * Windows appear automatically when viz blocks complete during a pipeline run.
 */
export default function VizWindow() {
  const { vizResults, removeVizResult, nodes, blockIndex } = usePipelineStore();

  const getDisplayName = (nodeId) => {
    const wfNode = nodes.find(n => n.id === nodeId);
    if (!wfNode) return nodeId;
    return blockIndex[wfNode.data.block_type_id]?.display_name ?? wfNode.data.block_type_id;
  };

  const entries = Object.entries(vizResults);
  if (entries.length === 0) return null;

  return (
    <>
      {entries.map(([nodeId, data], i) => (
        <VizWindowInstance
          key={nodeId}
          nodeId={nodeId}
          imageSrc={data.imageSrc}
          title={getDisplayName(nodeId)}
          initialOffset={i * 28}
          onClose={() => removeVizResult(nodeId)}
        />
      ))}
    </>
  );
}
