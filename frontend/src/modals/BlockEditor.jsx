/**
 * BlockEditor — floating, draggable and resizable popup for editing block
 * parameters and viewing / editing block source code.
 *
 * UI behaviour:
 *  - Opens as a floating panel (not a blocking modal).
 *  - Drag by the title bar to reposition anywhere on screen.
 *  - Drag the ⤡ handle at the bottom-right corner to resize.
 *  - Minimum size: 400 × 300 px.
 *  - A dim backdrop sits behind the panel; clicking it closes the editor.
 *  - Press Escape to close.
 *  - Position and size persist for the session (not reset between opens).
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import Editor from '@monaco-editor/react';
import usePipelineStore, { localBlockToDefinition } from '../store/pipelineStore';
import { getBlockSource, registerCustomBlock, registerLocalBlocks, saveLocalToLibrary, getLibraries, getBlocks } from '../api/client';
import FileBrowser from './FileBrowser';

const MIN_W = 400;
const MIN_H = 300;
const INIT_W = 620;
const INIT_H = 540;

export default function BlockEditor() {
  const {
    activePopupNodeId, setActivePopupNodeId,
    nodes, setNodes,
    blockIndex,
    localBlocks,
  } = usePipelineStore();

  // ── Window position / size ─────────────────────────────────────────────────
  const [pos,  setPos]  = useState(() => ({
    x: Math.max(0, Math.round((window.innerWidth  - INIT_W) / 2)),
    y: Math.max(0, Math.round((window.innerHeight - INIT_H) / 2)),
  }));
  const [size, setSize] = useState({ w: INIT_W, h: INIT_H });

  // ── Tabs / edit state ──────────────────────────────────────────────────────
  const [activeTab,      setActiveTab]      = useState('parameters');
  const [params,         setParams]         = useState({});
  const [fileBrowserParam, setFileBrowserParam] = useState(null);

  const [sourceLoading,  setSourceLoading]  = useState(false);
  const [editedSource,   setEditedSource]   = useState('');
  const [editableSource, setEditableSource] = useState(false);
  const [savingSource,   setSavingSource]   = useState(false);

  // Save-to-library state
  const [writableLibraries,  setWritableLibraries]  = useState([]);
  const [selectedLibId,      setSelectedLibId]      = useState('user_blocks');
  const [savingToLib,        setSavingToLib]        = useState(false);
  const [saveToLibStatus,    setSaveToLibStatus]    = useState(null); // null | 'ok' | 'err'
  const [saveToLibMessage,   setSaveToLibMessage]   = useState('');

  const node = nodes.find(n => n.id === activePopupNodeId);

  const definition = (() => {
    if (!node) return null;
    const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
    if (lb) return localBlockToDefinition(lb);
    return blockIndex[node.data.block_type_id] ?? node.data.definition ?? null;
  })();

  // Reset params when the popup opens for a new node
  useEffect(() => {
    if (node) {
      setParams({ ...(node.data.parameters ?? {}) });
      setActiveTab('parameters');
      setEditableSource(false);
      setEditedSource('');
    }
  }, [activePopupNodeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch source code when Source tab is activated
  useEffect(() => {
    if (activeTab !== 'source' || !node) return;

    // Local blocks: source lives in the store — no API call needed
    const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
    if (lb) {
      setEditedSource(lb.source_snippet ?? '# No source snippet stored for this local block.');
      setSourceLoading(false);
      return;
    }

    // Library / global blocks: fetch from server
    setSourceLoading(true);
    setEditableSource(false);
    getBlockSource(node.data.block_type_id)
      .then(res => setEditedSource(res.source_code ?? '# Source code not available.'))
      .catch(() => setEditedSource('# Failed to load source code.'))
      .finally(() => setSourceLoading(false));
  }, [activeTab, activePopupNodeId, localBlocks]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load writable libraries when source tab opens for a local block
  useEffect(() => {
    if (activeTab !== 'source' || !node) return;
    const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
    if (!lb) return;
    getLibraries()
      .then(res => {
        const writable = (res.libraries ?? []).filter(l => !l.is_builtin);
        setWritableLibraries(writable);
        if (writable.length > 0 && !writable.find(l => l.id === selectedLibId)) {
          setSelectedLibId(writable[0].id);
        }
      })
      .catch(() => {});
  }, [activeTab, activePopupNodeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSaveToLibrary = async () => {
    if (!node) return;
    const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
    if (!lb) return;
    setSavingToLib(true);
    setSaveToLibStatus(null);
    setSaveToLibMessage('');
    try {
      const result = await saveLocalToLibrary(lb, selectedLibId);
      // Refresh sidebar so the new permanent block appears
      const libData = await getBlocks();
      usePipelineStore.getState().setBlockLibrary(libData.libraries ?? []);
      setSaveToLibStatus('ok');
      setSaveToLibMessage(`Saved as ${result.block_type_id} in ${selectedLibId}.`);
    } catch (err) {
      setSaveToLibStatus('err');
      setSaveToLibMessage(err.response?.data?.detail?.message ?? err.message ?? 'Unknown error');
    } finally {
      setSavingToLib(false);
    }
  };

  // ── Drag title bar ─────────────────────────────────────────────────────────
  const dragStart = useRef(null); // { mouseX, mouseY, startX, startY }

  const onTitleMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    dragStart.current = { mouseX: e.clientX, mouseY: e.clientY, startX: pos.x, startY: pos.y };

    const onMove = (me) => {
      const dx = me.clientX - dragStart.current.mouseX;
      const dy = me.clientY - dragStart.current.mouseY;
      setPos({
        x: Math.max(0, dragStart.current.startX + dx),
        y: Math.max(0, dragStart.current.startY + dy),
      });
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  }, [pos]);

  // ── Resize handle (bottom-right corner) ───────────────────────────────────
  const resizeStart = useRef(null); // { mouseX, mouseY, startW, startH }

  const onResizeMouseDown = useCallback((e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    resizeStart.current = { mouseX: e.clientX, mouseY: e.clientY, startW: size.w, startH: size.h };

    const onMove = (me) => {
      const dw = me.clientX - resizeStart.current.mouseX;
      const dh = me.clientY - resizeStart.current.mouseY;
      setSize({
        w: Math.max(MIN_W, resizeStart.current.startW + dw),
        h: Math.max(MIN_H, resizeStart.current.startH + dh),
      });
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup',   onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
  }, [size]);

  if (!activePopupNodeId || !node) return null;

  const close = () => setActivePopupNodeId(null);

  const applyParams = () => {
    setNodes(nodes.map(n =>
      n.id === node.id
        ? { ...n, data: { ...n.data, parameters: { ...params } } }
        : n
    ));
    usePipelineStore.getState().setDirty(true);
    close();
  };

  const handleSaveSource = async () => {
    setSavingSource(true);
    try {
      const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
      if (lb) {
        // Local block: update snippet in store and re-register on server for this session
        const updated = { ...lb, source_snippet: editedSource };
        usePipelineStore.getState().updateLocalBlock(updated);
        await registerLocalBlocks([updated]);
        usePipelineStore.getState().setDirty(true);
        setEditableSource(false);
        alert('Block saved. Changes are active now and will be preserved when you save the workflow.');
      } else {
        // Library / global block: register as a custom override for this session
        await registerCustomBlock(editedSource);
        setEditableSource(false);
        alert('Block registered for this session. Changes take effect on the next run.\n\nNote: overrides are lost when the server restarts.');
      }
    } catch (err) {
      alert(`Failed to save: ${err.response?.data?.detail?.message ?? err.message}`);
    } finally {
      setSavingSource(false);
    }
  };

  // ── Parameter field renderer ───────────────────────────────────────────────
  const renderField = (param) => {
    const val    = params[param.name] ?? param.default ?? '';
    const update = (v) => setParams(prev => ({ ...prev, [param.name]: v }));

    if (param.type === 'bool') {
      return (
        <input type="checkbox" checked={!!val}
          onChange={e => update(e.target.checked)} />
      );
    }
    if (param.type === 'float' || param.type === 'int') {
      return (
        <input type="number" value={val}
          step={param.type === 'float' ? 'any' : 1}
          onChange={e => update(param.type === 'float'
            ? parseFloat(e.target.value)
            : parseInt(e.target.value, 10))}
          style={inputStyle} />
      );
    }
    if (Array.isArray(param.enum)) {
      return (
        <select value={val} onChange={e => update(e.target.value)} style={inputStyle}>
          {param.enum.map(opt => <option key={opt} value={opt}>{opt}</option>)}
        </select>
      );
    }
    const isPath = param.type === 'str' && (
      param.name.endsWith('_path') || param.name.endsWith('_file') || param.name === 'filename'
    );
    if (isPath) {
      return (
        <div style={{ display: 'flex', gap: 4 }}>
          <input type="text" value={val} onChange={e => update(e.target.value)}
            style={{ ...inputStyle, flex: 1 }} />
          <button onClick={() => setFileBrowserParam(param.name)}
            style={btnSecondary} title="Browse filesystem">
            Browse…
          </button>
        </div>
      );
    }
    return (
      <input type="text" value={val} onChange={e => update(e.target.value)}
        style={inputStyle} />
    );
  };

  // Source editor height = panel height minus fixed chrome (header 45 + tabs 38 + toolbar 32 + footer 52 + padding)
  const sourceEditorH = Math.max(160, size.h - 200);

  return (
    <>
      {/* File browser — always on top */}
      {fileBrowserParam && (
        <FileBrowser
          initialPath={params[fileBrowserParam] ?? ''}
          onSelect={(path) => {
            setParams(prev => ({ ...prev, [fileBrowserParam]: path }));
            setFileBrowserParam(null);
          }}
          onClose={() => setFileBrowserParam(null)}
        />
      )}

      {/* Dim backdrop — click to close but does NOT block the canvas */}
      <div
        onClick={close}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.25)',
          zIndex: 1000,
        }}
      />

      {/* ── Floating panel ── */}
      <div
        onClick={e => e.stopPropagation()}
        onKeyDown={e => e.key === 'Escape' && close()}
        style={{
          position: 'fixed',
          left: pos.x,
          top:  pos.y,
          width:  size.w,
          height: size.h,
          zIndex: 1001,
          background: '#1f2937',
          border: '1px solid #374151',
          borderRadius: 8,
          display: 'flex',
          flexDirection: 'column',
          color: '#f9fafb',
          boxShadow: '0 12px 40px rgba(0,0,0,0.7)',
          overflow: 'hidden',   // children clip to rounded corners
          userSelect: 'none',   // prevent text selection while dragging
        }}
      >
        {/* ── Draggable title bar ── */}
        <div
          onMouseDown={onTitleMouseDown}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '10px 14px',
            borderBottom: '1px solid #374151',
            cursor: 'move',
            background: '#111827',
            flexShrink: 0,
            userSelect: 'none',
          }}
        >
          {/* Grab indicator dots */}
          <span style={{ color: '#4b5563', fontSize: 11, letterSpacing: 2, marginRight: 8, flexShrink: 0 }}>
            ⠿
          </span>
          <span style={{ fontWeight: 600, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {definition?.display_name ?? node.data.block_type_id}
          </span>
          <button
            onClick={close}
            onMouseDown={e => e.stopPropagation()} // don't start a drag on ✕ click
            style={{
              background: 'none', border: 'none', color: '#9ca3af',
              cursor: 'pointer', fontSize: 16, padding: '0 0 0 8px',
              flexShrink: 0,
            }}
            title="Close (Esc)"
          >
            ✕
          </button>
        </div>

        {/* ── Tab bar ── */}
        <div style={{ display: 'flex', borderBottom: '1px solid #374151', flexShrink: 0 }}>
          {['parameters', 'source'].map(tab => (
            <button
              key={tab}
              onMouseDown={e => e.stopPropagation()}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: '8px 16px', border: 'none', cursor: 'pointer',
                background: activeTab === tab ? '#374151' : 'transparent',
                color: activeTab === tab ? '#f9fafb' : '#9ca3af',
                borderBottom: activeTab === tab ? '2px solid #6366f1' : '2px solid transparent',
                fontSize: 13, textTransform: 'capitalize',
                userSelect: 'none',
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* ── Scrollable body ── */}
        <div style={{ flex: 1, overflow: 'auto', padding: 16 }}
          onMouseDown={e => e.stopPropagation()}>

          {/* Parameters tab */}
          {activeTab === 'parameters' && (
            <div>
              {(definition?.parameters ?? []).length === 0 && (
                <p style={{ color: '#6b7280', fontSize: 13 }}>
                  This block has no configurable parameters.
                </p>
              )}
              {(definition?.parameters ?? []).map(param => (
                <div key={param.name} style={{ marginBottom: 12 }}>
                  <label
                    title={param.description}
                    style={{ display: 'block', fontSize: 12, color: '#9ca3af', marginBottom: 4 }}
                  >
                    {param.name}
                    {param.description && (
                      <span style={{ marginLeft: 6, cursor: 'help' }}>ⓘ</span>
                    )}
                  </label>
                  {renderField(param)}
                </div>
              ))}
            </div>
          )}

          {/* Source tab */}
          {activeTab === 'source' && (
            <div style={{ display: 'flex', flexDirection: 'column', height: sourceEditorH + 60 }}>
              {/* Toolbar */}
              <div style={{
                display: 'flex', alignItems: 'center',
                justifyContent: 'space-between', marginBottom: 8,
              }}>
                <span style={{ fontSize: 11, color: '#6b7280' }}>
                  {sourceLoading
                    ? 'Loading…'
                    : editableSource
                      ? 'Editing — changes override the built-in block at runtime'
                      : 'Read-only'}
                </span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
                  <span style={{ fontSize: 12, color: '#9ca3af' }}>Editable</span>
                  <div
                    onClick={() => !sourceLoading && setEditableSource(v => !v)}
                    style={{
                      width: 38, height: 22, borderRadius: 11, position: 'relative',
                      background: editableSource ? '#4f46e5' : '#374151',
                      cursor: sourceLoading ? 'default' : 'pointer',
                      transition: 'background 0.2s', flexShrink: 0,
                    }}
                  >
                    <div style={{
                      width: 18, height: 18, borderRadius: 9, background: '#fff',
                      position: 'absolute', top: 2,
                      left: editableSource ? 18 : 2,
                      transition: 'left 0.15s',
                    }} />
                  </div>
                </label>
              </div>

              {/* Monaco editor */}
              <div style={{ flex: 1 }}>
                {sourceLoading
                  ? <div style={{ color: '#6b7280', fontSize: 12, paddingTop: 8 }}>
                      Loading source code…
                    </div>
                  : <Editor
                      height={sourceEditorH}
                      defaultLanguage="python"
                      value={editedSource}
                      onChange={v => editableSource && setEditedSource(v ?? '')}
                      options={{
                        readOnly: !editableSource,
                        minimap: { enabled: false },
                        fontSize: 12,
                        lineNumbers: 'on',
                        scrollBeyondLastLine: false,
                      }}
                      theme="vs-dark"
                    />
                }
              </div>

              {editableSource && (
                <button
                  style={{ ...btnPrimary, marginTop: 8, opacity: savingSource ? 0.6 : 1 }}
                  onClick={handleSaveSource}
                  disabled={savingSource}
                >
                  {savingSource ? 'Saving…' : 'Save & Reload'}
                </button>
              )}

              {/* Save to Library — only for local blocks */}
              {localBlocks.find(b => b.block_type_id === node.data.block_type_id) && (
                <div style={{
                  marginTop: 16, padding: '10px 12px',
                  background: '#111827', borderRadius: 6, border: '1px solid #374151',
                }}>
                  <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 8, fontWeight: 600 }}>
                    Save to Library
                  </div>
                  <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 8 }}>
                    Promote this local block to a permanent library block so it's available in all future workflows.
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select
                      value={selectedLibId}
                      onChange={e => setSelectedLibId(e.target.value)}
                      style={{ ...inputStyle, flex: 1 }}
                      disabled={savingToLib}
                    >
                      {writableLibraries.length === 0
                        ? <option value="user_blocks">User Blocks (default)</option>
                        : writableLibraries.map(l => (
                          <option key={l.id} value={l.id}>{l.name} ({l.id})</option>
                        ))
                      }
                    </select>
                    <button
                      style={{ ...btnPrimary, whiteSpace: 'nowrap', opacity: savingToLib ? 0.6 : 1 }}
                      onClick={handleSaveToLibrary}
                      disabled={savingToLib}
                    >
                      {savingToLib ? 'Saving…' : 'Save to Library'}
                    </button>
                  </div>
                  {saveToLibStatus && (
                    <div style={{
                      marginTop: 8, fontSize: 11,
                      color: saveToLibStatus === 'ok' ? '#22c55e' : '#ef4444',
                    }}>
                      {saveToLibStatus === 'ok' ? '✓ ' : '✕ '}{saveToLibMessage}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Footer — parameters only ── */}
        {activeTab === 'parameters' && (
          <div
            onMouseDown={e => e.stopPropagation()}
            style={{
              padding: '10px 14px', borderTop: '1px solid #374151',
              display: 'flex', justifyContent: 'flex-end', gap: 8,
              flexShrink: 0, background: '#111827',
            }}
          >
            <button onClick={close}       style={btnSecondary}>Cancel</button>
            <button onClick={applyParams} style={btnPrimary}>Apply</button>
          </div>
        )}

        {/* ── Resize handle (bottom-right corner) ── */}
        <div
          onMouseDown={onResizeMouseDown}
          title="Drag to resize"
          style={{
            position: 'absolute', bottom: 0, right: 0,
            width: 18, height: 18,
            cursor: 'se-resize',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#4b5563', fontSize: 12,
            userSelect: 'none',
          }}
        >
          ⤡
        </div>
      </div>
    </>
  );
}

// ── Shared style constants ─────────────────────────────────────────────────────

const inputStyle = {
  background: '#111827', border: '1px solid #374151',
  borderRadius: 4, color: '#f9fafb',
  padding: '4px 8px', fontSize: 12, width: '100%',
};

const btnPrimary = {
  background: '#4f46e5', border: 'none', borderRadius: 4,
  color: '#fff', padding: '6px 14px', cursor: 'pointer', fontSize: 13,
};

const btnSecondary = {
  background: '#374151', border: 'none', borderRadius: 4,
  color: '#f9fafb', padding: '6px 14px', cursor: 'pointer', fontSize: 13,
};
