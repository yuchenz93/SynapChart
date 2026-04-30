import { useState, useEffect, useCallback } from 'react';
import { getLibraries, refreshLibraries, getLibraryConflicts } from '../api/client';
import usePipelineStore from '../store/pipelineStore';

/**
 * Modal for managing the loaded block libraries.
 *
 * Left panel  — Available libraries: priority order, remove/add buttons.
 * Right panel — Conflicts: short IDs that appear in >1 loaded library.
 */
export default function LibraryManager({ onClose }) {
  const { blockLibrary, setBlockLibrary } = usePipelineStore(s => ({
    blockLibrary: s.blockLibrary,
    setBlockLibrary: s.setBlockLibrary,
  }));

  // All libraries known to the server (including ones not currently loaded)
  const [allLibraries, setAllLibraries]   = useState([]);
  const [conflicts, setConflicts]         = useState([]);
  const [loading, setLoading]             = useState(true);
  const [refreshing, setRefreshing]       = useState(false);
  const [error, setError]                 = useState(null);

  // IDs currently shown in the side panel (in order)
  const loadedIds = blockLibrary.map(l => l.id);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getLibraries();
      setAllLibraries(data.libraries ?? []);
      if (loadedIds.length > 0) {
        const cdata = await getLibraryConflicts(loadedIds);
        setConflicts(cdata.conflicts ?? []);
      }
    } catch (e) {
      setError('Failed to load library information.');
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => { load(); }, [load]);

  // ── Actions ──────────────────────────────────────────────────────────────

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const data = await refreshLibraries();
      setAllLibraries(data.libraries ?? []);
      // Also update blockLibrary in store with refreshed data from server
      // (keep current order, just update metadata)
      const newMap = Object.fromEntries((data.libraries ?? []).map(l => [l.id, l]));
      setBlockLibrary(blockLibrary.map(l => newMap[l.id] ? { ...l, ...newMap[l.id] } : l));
    } catch {
      setError('Refresh failed.');
    } finally {
      setRefreshing(false);
    }
  };

  const handleMoveUp = (idx) => {
    if (idx <= 0) return;
    const next = [...blockLibrary];
    [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
    setBlockLibrary(next);
  };

  const handleMoveDown = (idx) => {
    if (idx >= blockLibrary.length - 1) return;
    const next = [...blockLibrary];
    [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
    setBlockLibrary(next);
  };

  const handleRemove = (libId) => {
    // Built-in library cannot be removed
    const lib = blockLibrary.find(l => l.id === libId);
    if (lib?.is_builtin) return;
    setBlockLibrary(blockLibrary.filter(l => l.id !== libId));
  };

  const handleAdd = (lib) => {
    if (loadedIds.includes(lib.id)) return;
    // Add at end with empty categories placeholder — user must refresh to get blocks
    setBlockLibrary([...blockLibrary, { ...lib, categories: lib.categories ?? [] }]);
  };

  // ── Styles ────────────────────────────────────────────────────────────────

  const panelStyle = {
    background: '#111827',
    border: '1px solid #374151',
    borderRadius: 6,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    flex: 1,
  };

  const rowStyle = (highlight = false) => ({
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '5px 10px',
    background: highlight ? 'rgba(59,130,246,0.08)' : 'transparent',
    borderBottom: '1px solid #1e293b',
  });

  const btnStyle = (variant = 'default') => ({
    background: 'none',
    border: `1px solid ${variant === 'danger' ? '#991b1b' : variant === 'add' ? '#166534' : '#374151'}`,
    borderRadius: 4,
    color: variant === 'danger' ? '#f87171' : variant === 'add' ? '#86efac' : '#9ca3af',
    cursor: 'pointer',
    fontSize: 11,
    padding: '2px 7px',
    lineHeight: '18px',
    whiteSpace: 'nowrap',
  });

  const iconBtnStyle = {
    background: 'none',
    border: '1px solid #374151',
    borderRadius: 4,
    color: '#9ca3af',
    cursor: 'pointer',
    fontSize: 12,
    width: 22,
    height: 22,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  };

  return (
    /* Backdrop */
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.6)',
        zIndex: 3000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      {/* Dialog */}
      <div style={{
        background: '#1f2937',
        border: '1px solid #374151',
        borderRadius: 10,
        boxShadow: '0 16px 48px rgba(0,0,0,0.7)',
        width: 720,
        maxWidth: '95vw',
        maxHeight: '80vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '14px 18px',
          borderBottom: '1px solid #374151',
          flexShrink: 0,
        }}>
          <span style={{ color: '#f9fafb', fontSize: 14, fontWeight: 700 }}>
            📚 Library Manager
          </span>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              style={{ ...btnStyle(), opacity: refreshing ? 0.6 : 1 }}
            >
              {refreshing ? '⟳ Refreshing…' : '↺ Refresh libraries'}
            </button>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 18 }}
            >
              ✕
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: '8px 18px', background: '#450a0a', color: '#f87171', fontSize: 12 }}>
            {error}
          </div>
        )}

        {/* Body: two panels */}
        <div style={{
          display: 'flex', gap: 12,
          padding: 14,
          flex: 1,
          overflow: 'hidden',
          minHeight: 0,
        }}>
          {/* ── Left: Loaded libraries ────────────────────────────── */}
          <div style={{ ...panelStyle, flex: '0 0 55%' }}>
            <div style={{
              padding: '7px 10px',
              background: '#0f172a',
              borderBottom: '1px solid #374151',
              fontSize: 11,
              color: '#9ca3af',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              flexShrink: 0,
            }}>
              Loaded libraries (priority order ↑ = higher)
            </div>

            <div style={{ flex: 1, overflowY: 'auto' }}>
              {loading ? (
                <div style={{ padding: 12, color: '#6b7280', fontSize: 12 }}>Loading…</div>
              ) : blockLibrary.length === 0 ? (
                <div style={{ padding: 12, color: '#6b7280', fontSize: 12 }}>No libraries loaded.</div>
              ) : (
                blockLibrary.map((lib, idx) => (
                  <div key={lib.id} style={rowStyle()}>
                    {/* Reorder buttons */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                      <button style={iconBtnStyle} onClick={() => handleMoveUp(idx)} disabled={idx === 0}
                        title="Move up (higher priority)" aria-label="Move up">
                        ↑
                      </button>
                      <button style={iconBtnStyle} onClick={() => handleMoveDown(idx)} disabled={idx === blockLibrary.length - 1}
                        title="Move down (lower priority)" aria-label="Move down">
                        ↓
                      </button>
                    </div>

                    {/* Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ color: '#f9fafb', fontSize: 12, fontWeight: 600,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {lib.name}
                        </span>
                        {lib.is_builtin && (
                          <span style={{
                            fontSize: 9, background: '#1e3a5f', color: '#93c5fd',
                            borderRadius: 3, padding: '1px 5px', flexShrink: 0,
                          }}>built-in</span>
                        )}
                      </div>
                      <div style={{ color: '#6b7280', fontSize: 10, marginTop: 1 }}>
                        {lib.id}
                        {lib.version ? ` · v${lib.version}` : ''}
                        {' · '}
                        {(lib.categories ?? []).reduce((n, c) => n + (c.blocks?.length ?? 0), 0)} blocks
                      </div>
                    </div>

                    {/* Remove */}
                    <button
                      style={{ ...btnStyle('danger'), opacity: lib.is_builtin ? 0.3 : 1 }}
                      disabled={lib.is_builtin}
                      title={lib.is_builtin ? 'Built-in library cannot be removed' : 'Remove from side panel'}
                      onClick={() => handleRemove(lib.id)}
                    >
                      Remove
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* ── Right: Available + Conflicts ─────────────────────── */}
          <div style={{ ...panelStyle, flex: 1, minWidth: 0 }}>
            {/* Available (not loaded) */}
            <div style={{
              padding: '7px 10px',
              background: '#0f172a',
              borderBottom: '1px solid #374151',
              fontSize: 11,
              color: '#9ca3af',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              flexShrink: 0,
            }}>
              Available (not loaded)
            </div>

            <div style={{ flex: '0 0 auto', overflowY: 'auto', maxHeight: '45%' }}>
              {loading ? (
                <div style={{ padding: 10, color: '#6b7280', fontSize: 12 }}>Loading…</div>
              ) : (
                allLibraries
                  .filter(l => !loadedIds.includes(l.id))
                  .map(lib => (
                    <div key={lib.id} style={rowStyle()}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ color: '#d1d5db', fontSize: 12, fontWeight: 500,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {lib.name}
                        </div>
                        <div style={{ color: '#6b7280', fontSize: 10 }}>
                          {lib.id}{lib.version ? ` · v${lib.version}` : ''}
                        </div>
                      </div>
                      <button style={btnStyle('add')} onClick={() => handleAdd(lib)}>
                        + Add
                      </button>
                    </div>
                  ))
              )}
              {!loading && allLibraries.filter(l => !loadedIds.includes(l.id)).length === 0 && (
                <div style={{ padding: '8px 10px', color: '#4b5563', fontSize: 11 }}>
                  All discovered libraries are already loaded.
                </div>
              )}
            </div>

            {/* Divider */}
            <div style={{ height: 1, background: '#374151', flexShrink: 0 }} />

            {/* Conflicts */}
            <div style={{
              padding: '7px 10px',
              background: '#0f172a',
              borderBottom: '1px solid #374151',
              fontSize: 11,
              color: '#9ca3af',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              flexShrink: 0,
            }}>
              Block ID conflicts
            </div>

            <div style={{ flex: 1, overflowY: 'auto' }}>
              {loading ? (
                <div style={{ padding: 10, color: '#6b7280', fontSize: 12 }}>Loading…</div>
              ) : conflicts.length === 0 ? (
                <div style={{ padding: '8px 10px', color: '#4b5563', fontSize: 11 }}>
                  No conflicts detected.
                </div>
              ) : (
                conflicts.map((shortId) => (
                  <div key={shortId} style={{
                    ...rowStyle(true),
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    gap: 2,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ color: '#fbbf24', fontSize: 11 }}>⚠</span>
                      <span style={{ color: '#fcd34d', fontSize: 12, fontWeight: 600 }}>{shortId}</span>
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: 10, paddingLeft: 18 }}>
                      Appears in multiple loaded libraries — higher-priority library takes precedence.
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          borderTop: '1px solid #374151',
          padding: '10px 18px',
          display: 'flex',
          justifyContent: 'flex-end',
          flexShrink: 0,
        }}>
          <button
            onClick={onClose}
            style={{
              background: '#3b82f6',
              border: 'none',
              borderRadius: 6,
              color: '#fff',
              cursor: 'pointer',
              fontSize: 13,
              padding: '6px 18px',
              fontWeight: 600,
            }}
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
