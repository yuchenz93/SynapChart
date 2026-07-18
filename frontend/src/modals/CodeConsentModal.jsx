import { useState } from 'react';

/**
 * Blocking consent dialog shown before a workflow that contains custom code is
 * loaded onto the canvas.  SynapChart blocks execute arbitrary Python, so
 * opening a workflow from an untrusted source is equivalent to running an
 * unknown script.  The user must explicitly confirm before any code runs.
 *
 * Props:
 *   filePath  — path of the workflow being opened (shown for context)
 *   manifest  — array of { block_type_id, kind, library_id, line_count, source }
 *   onTrust   — called when the user confirms (loads + executes the code)
 *   onCancel  — called when the user declines (nothing is loaded)
 */

const KIND_LABEL = {
  local_block:     'Local block',
  embedded_python: 'Embedded library block',
};

const OVERLAY = {
  position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
};

const PANEL = {
  width: 'min(720px, 92vw)', maxHeight: '86vh', display: 'flex', flexDirection: 'column',
  background: '#0f172a', border: '1px solid #374151', borderRadius: 8,
  color: '#f9fafb', fontSize: 13, boxShadow: '0 10px 40px rgba(0,0,0,0.5)',
};

const BTN = {
  borderRadius: 4, padding: '7px 14px', fontSize: 13, cursor: 'pointer',
  border: '1px solid #374151',
};

export default function CodeConsentModal({ filePath, manifest = [], onTrust, onCancel }) {
  const [expanded, setExpanded] = useState({});
  const toggle = (key) => setExpanded((e) => ({ ...e, [key]: !e[key] }));

  const fileName = filePath ? filePath.replace(/.*[/\\]/, '') : 'this workflow';

  return (
    <div style={OVERLAY} onMouseDown={onCancel}>
      <div style={PANEL} onMouseDown={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={{ padding: '14px 18px', borderBottom: '1px solid #374151' }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#fbbf24' }}>
            ⚠ This workflow contains custom code
          </div>
          <div style={{ marginTop: 6, color: '#cbd5e1', lineHeight: 1.5 }}>
            <strong style={{ wordBreak: 'break-all' }}>{fileName}</strong> includes{' '}
            {manifest.length} custom code block{manifest.length === 1 ? '' : 's'} that will run
            on your machine with your permissions. Only continue if you trust the source of
            this file. Review the code below before deciding.
          </div>
        </div>

        {/* Manifest list */}
        <div style={{ overflowY: 'auto', padding: '8px 18px', flex: 1 }}>
          {manifest.map((item) => {
            const key = `${item.kind}:${item.block_type_id}`;
            const isOpen = !!expanded[key];
            return (
              <div
                key={key}
                style={{
                  border: '1px solid #1f2937', borderRadius: 6,
                  margin: '8px 0', background: '#111827',
                }}
              >
                <div
                  onClick={() => toggle(key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 10px', cursor: 'pointer',
                  }}
                >
                  <span style={{ color: '#64748b', width: 12 }}>{isOpen ? '▾' : '▸'}</span>
                  <span style={{
                    fontSize: 11, padding: '1px 6px', borderRadius: 3,
                    background: item.kind === 'embedded_python' ? '#3b0764' : '#1e3a5f',
                    color: '#e9d5ff',
                  }}>
                    {KIND_LABEL[item.kind] ?? item.kind}
                  </span>
                  <span style={{ fontFamily: 'monospace', color: '#f9fafb' }}>
                    {item.block_type_id}
                  </span>
                  {item.library_id && (
                    <span style={{ color: '#64748b', fontSize: 11 }}>({item.library_id})</span>
                  )}
                  <span style={{ marginLeft: 'auto', color: '#64748b', fontSize: 11 }}>
                    {item.line_count} line{item.line_count === 1 ? '' : 's'}
                  </span>
                </div>
                {isOpen && (
                  <pre style={{
                    margin: 0, padding: '10px 12px', borderTop: '1px solid #1f2937',
                    background: '#0b1120', color: '#e2e8f0', fontSize: 12,
                    overflowX: 'auto', whiteSpace: 'pre', maxHeight: 280,
                  }}>
                    {item.source || '(no source available)'}
                  </pre>
                )}
              </div>
            );
          })}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 18px', borderTop: '1px solid #374151',
          display: 'flex', justifyContent: 'flex-end', gap: 10,
        }}>
          <button
            style={{ ...BTN, background: '#1f2937', color: '#f9fafb' }}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            style={{ ...BTN, background: '#b45309', borderColor: '#f59e0b', color: '#fff' }}
            onClick={onTrust}
          >
            Trust &amp; Load
          </button>
        </div>
      </div>
    </div>
  );
}
