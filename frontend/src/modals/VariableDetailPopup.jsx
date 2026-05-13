import { useState, useRef, useEffect } from 'react';
import { getVariableDetail, getVariablePreview } from '../api/client';
import usePipelineStore from '../store/pipelineStore';

/** Resolve a node ID to a display name from the store. */
function resolveNodeName(nodeId) {
  const { nodes, blockIndex, localBlocks } = usePipelineStore.getState();
  const node = nodes.find(n => n.id === nodeId);
  if (!node) return nodeId;
  const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
  if (lb) return lb.display_name;
  return blockIndex[node.data.block_type_id]?.display_name ?? nodeId;
}

/**
 * Draggable floating popup showing Summary / Statistics / Value / Preview tabs
 * for one node output port.
 *
 * Props:
 *   nodeId        — node_id string
 *   portId        — port_id string
 *   summary       — variable summary object (already loaded)
 *   initialOffset — pixel offset for stacking
 *   onClose       — called when the popup is closed
 */
export default function VariableDetailPopup({ nodeId, portId, summary, initialOffset = 0, onClose }) {
  const [activeTab, setActiveTab] = useState('summary');
  const [pos, setPos] = useState({ x: 120 + initialOffset, y: 100 + initialOffset });

  // Value tab is shown when the array is 0-D, 1-D, or 2-D
  const showValueTab = summary?.shape != null && summary.shape.length <= 2;

  // Lazy-loaded detail (stats + rows) and preview
  const [detail, setDetail]         = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [preview, setPreview]       = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const dragging   = useRef(false);
  const dragOffset = useRef({ x: 0, y: 0 });

  const nodeName = resolveNodeName(nodeId);
  const title    = `${nodeName} → ${portId}`;

  // Load detail when Statistics or Value tab is first opened (shared response)
  useEffect(() => {
    if ((activeTab !== 'statistics' && activeTab !== 'value') || detail || detailLoading) return;
    setDetailLoading(true);
    getVariableDetail(nodeId, portId)
      .then(d => setDetail(d))
      .catch(() => setDetail({ error: 'Failed to load detail.' }))
      .finally(() => setDetailLoading(false));
  }, [activeTab, nodeId, portId, detail, detailLoading]);

  // Load preview when Preview tab is first opened
  useEffect(() => {
    if (activeTab !== 'preview' || preview || previewLoading) return;
    setPreviewLoading(true);
    getVariablePreview(nodeId, portId)
      .then(p => setPreview(p))
      .catch(() => setPreview({ error: 'Failed to load preview.' }))
      .finally(() => setPreviewLoading(false));
  }, [activeTab, nodeId, portId, preview, previewLoading]);

  // Keyboard close
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onClose]);

  const onTitleMouseDown = (e) => {
    if (e.button !== 0) return;
    dragging.current = true;
    dragOffset.current = { x: e.clientX - pos.x, y: e.clientY - pos.y };
    const onMove = (me) => {
      if (!dragging.current) return;
      setPos({ x: me.clientX - dragOffset.current.x, y: me.clientY - dragOffset.current.y });
    };
    const onUp = () => {
      dragging.current = false;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  };

  // Save preview image
  const handleSaveImage = () => {
    if (!preview?.image_b64) return;
    const a = document.createElement('a');
    a.href     = `data:image/png;base64,${preview.image_b64}`;
    a.download = `${nodeId}_${portId}_preview.png`;
    a.click();
  };

  return (
    <div style={{
      position: 'fixed',
      left: pos.x, top: pos.y,
      zIndex: 3000,
      width: 520,
      background: '#1f2937',
      border: '1px solid #374151',
      borderRadius: 8,
      boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
      display: 'flex', flexDirection: 'column',
      resize: 'both', overflow: 'auto',
      minWidth: 320, minHeight: 200,
    }}>

      {/* Title bar */}
      <div
        onMouseDown={onTitleMouseDown}
        style={{
          padding: '7px 12px',
          background: '#111827',
          borderRadius: '7px 7px 0 0',
          display: 'flex', alignItems: 'center', gap: 8,
          cursor: 'move', userSelect: 'none',
          borderBottom: '1px solid #374151',
          flexShrink: 0,
        }}
      >
        <span style={{ fontSize: 11, color: '#e5e7eb', fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {title}
        </span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 14, padding: '0 2px' }}
          onMouseEnter={e => e.currentTarget.style.color = '#f9fafb'}
          onMouseLeave={e => e.currentTarget.style.color = '#6b7280'}
        >
          ✕
        </button>
      </div>

      {/* Tab strip */}
      <div style={{
        display: 'flex', borderBottom: '1px solid #374151', flexShrink: 0,
        background: '#111827',
      }}>
        {['summary', 'statistics', ...(showValueTab ? ['value'] : []), 'preview'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              background: activeTab === tab ? '#1f2937' : 'none',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid #6366f1' : '2px solid transparent',
              color: activeTab === tab ? '#f9fafb' : '#6b7280',
              padding: '5px 14px', fontSize: 11, cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '10px 14px' }}>

        {/* ── Summary tab ── */}
        {activeTab === 'summary' && (
          <SummaryTab summary={summary} />
        )}

        {/* ── Statistics tab ── */}
        {activeTab === 'statistics' && (
          detailLoading
            ? <Spinner />
            : detail?.error
              ? <ErrorMsg msg={detail.error} />
              : detail?.statistics
                ? <StatsTab stats={detail.statistics} rows={detail?.rows} />
                : <div style={emptyStyle}>No statistics available for this type.</div>
        )}

        {/* ── Value tab ── */}
        {activeTab === 'value' && (
          detailLoading
            ? <Spinner />
            : detail?.error
              ? <ErrorMsg msg={detail.error} />
              : <ValueTab rows={detail?.rows} />
        )}

        {/* ── Preview tab ── */}
        {activeTab === 'preview' && (
          previewLoading
            ? <Spinner />
            : preview?.error
              ? <ErrorMsg msg={preview.error} />
              : preview?.image_b64
                ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <img
                      src={`data:image/png;base64,${preview.image_b64}`}
                      alt={`${portId} preview`}
                      style={{ width: '100%', borderRadius: 4 }}
                    />
                    <button
                      onClick={handleSaveImage}
                      style={{
                        alignSelf: 'flex-start',
                        background: '#1e293b', border: '1px solid #374151',
                        borderRadius: 4, color: '#9ca3af', fontSize: 11,
                        padding: '3px 10px', cursor: 'pointer',
                      }}
                      onMouseEnter={e => e.currentTarget.style.color = '#f9fafb'}
                      onMouseLeave={e => e.currentTarget.style.color = '#9ca3af'}
                    >
                      ⬇ Save image
                    </button>
                  </div>
                )
                : <div style={emptyStyle}>Loading preview…</div>
        )}

      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SummaryTab({ summary }) {
  if (!summary) return <div style={emptyStyle}>No summary available.</div>;

  const rows = [
    ['Data type',    summary.data_type],
    ['Shape',        summary.shape ? `[${summary.shape.join(', ')}]` : '—'],
    ['Size',         summary.size ?? '—'],
    ['dtype',        summary.dtype ?? '—'],
    ['Sampling rate', summary.sampling_rate != null ? `${summary.sampling_rate} Hz` : '—'],
    ['N channels',   summary.n_channels ?? '—'],
    ['N samples',    summary.n_samples ?? '—'],
    ['Timestamps',   summary.has_timestamps != null ? (summary.has_timestamps ? 'Yes' : 'No') : '—'],
    ['Channel names', summary.channel_names?.join(', ') ?? '—'],
    ['Metadata keys', summary.metadata_keys?.join(', ') ?? '—'],
    ...(summary.value_preview != null ? [['Value', summary.value_preview]] : []),
  ].filter(([, v]) => v !== '—' && v != null);

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label} style={{ borderBottom: '1px solid #1e293b' }}>
            <td style={{ padding: '4px 8px', color: '#9ca3af', fontWeight: 600, whiteSpace: 'nowrap', width: '40%' }}>{label}</td>
            <td style={{ padding: '4px 8px', color: '#e5e7eb', fontFamily: 'monospace', wordBreak: 'break-all' }}>{String(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StatsTab({ stats, rows }) {
  if (!stats?.length) return <div style={emptyStyle}>No statistics.</div>;
  const colTrunc = rows && rows.total_cols > 1 && rows.shown_cols < rows.total_cols;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 10, width: '100%' }}>
          <thead>
            <tr style={{ color: '#6b7280', borderBottom: '1px solid #374151' }}>
              {['Channel', 'Min', 'Max', 'Mean', 'Std', 'NaN', 'Inf'].map(h => (
                <th key={h} style={{ padding: '3px 8px', textAlign: 'right', fontWeight: 600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stats.map((s, i) => (
              <tr key={i} style={{ borderBottom: '1px solid #1e293b' }}>
                <td style={statCell}>{s.channel === 0 && stats.length === 1 ? 'value' : s.channel}</td>
                <td style={statCell}>{fmt(s.min)}</td>
                <td style={statCell}>{fmt(s.max)}</td>
                <td style={statCell}>{fmt(s.mean)}</td>
                <td style={statCell}>{fmt(s.std)}</td>
                <td style={statCell}>{s.n_nan}</td>
                <td style={statCell}>{s.n_inf}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {colTrunc && (
        <div style={{ padding: '5px 4px', fontSize: 10, color: '#6b7280', fontStyle: 'italic' }}>
          Showing first {rows.shown_cols} of {rows.total_cols} columns
        </div>
      )}
    </div>
  );
}

function ValueTab({ rows }) {
  if (!rows || typeof rows !== 'object' || !Array.isArray(rows.data)) {
    return <div style={emptyStyle}>No row data available.</div>;
  }
  const { data, shown_rows, total_rows } = rows;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ borderCollapse: 'collapse', fontSize: 10, width: '100%' }}>
          <tbody>
            {data.map((row, i) => {
              const cells = Array.isArray(row) ? row : [row];
              return (
                <tr key={i} style={{ borderBottom: '1px solid #1e293b' }}>
                  <td style={{ ...valueIdxCell }}>{i}</td>
                  {cells.map((v, j) => (
                    <td key={j} style={valueCell}>{fmtVal(v)}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {(shown_rows < total_rows || (rows.shown_cols != null && rows.shown_cols < rows.total_cols)) && (
        <div style={{ padding: '5px 4px', fontSize: 10, color: '#6b7280', fontStyle: 'italic' }}>
          {[
            shown_rows < total_rows && `first ${shown_rows} of ${total_rows} rows`,
            rows.shown_cols != null && rows.shown_cols < rows.total_cols && `first ${rows.shown_cols} of ${rows.total_cols} cols`,
          ].filter(Boolean).join(' · ')}
        </div>
      )}
    </div>
  );
}

const fmtVal = (v) => {
  if (v == null) return '—';
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toPrecision(6);
  return String(v);
};
const valueIdxCell = { padding: '2px 8px', textAlign: 'right', color: '#4b5563', fontFamily: 'monospace', userSelect: 'none', borderRight: '1px solid #1e293b' };
const valueCell    = { padding: '2px 8px', textAlign: 'right', color: '#d1d5db', fontFamily: 'monospace' };

const fmt = (v) => v == null ? '—' : v.toPrecision(5);
const statCell = { padding: '3px 8px', textAlign: 'right', color: '#d1d5db', fontFamily: 'monospace' };
const emptyStyle = { color: '#6b7280', fontSize: 11, padding: '8px 0' };

function Spinner() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 20, color: '#6b7280', fontSize: 12 }}>
      Loading…
    </div>
  );
}

function ErrorMsg({ msg }) {
  return <div style={{ color: '#f87171', fontSize: 11, padding: '8px 0' }}>{msg}</div>;
}
