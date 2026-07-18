import { useState, useEffect, useRef } from 'react';
import usePipelineStore from '../store/pipelineStore';
import FileBrowser from '../modals/FileBrowser';
import CodeConsentModal from '../modals/CodeConsentModal';
import {
  runPipeline, stepPipeline, stopPipeline,
  saveWorkflow, loadWorkflow,
  getTemplates, loadTemplate,
  getBlocks, updateCompositeBlock,
  packWorkflow,
} from '../api/client';

const BTN = {
  background: '#1f2937', border: '1px solid #374151',
  color: '#f9fafb', borderRadius: 4, padding: '4px 10px',
  fontSize: 12, cursor: 'pointer',
};

const STATUS_INDICATOR = {
  idle:     { color: '#6b7280', label: '●  Idle' },
  running:  { color: '#3b82f6', label: '⟳  Running' },
  done:     { color: '#22c55e', label: '✓  Done' },
  error:    { color: '#ef4444', label: '✕  Error' },
  stopped:  { color: '#f59e0b', label: '■  Stopped' },
  stopping: { color: '#f59e0b', label: '⏹  Stopping…' },
};

/**
 * Fixed top toolbar with file operations and pipeline execution controls.
 */
export default function TopToolbar() {
  const {
    serializeWorkflow, loadWorkflowIntoStore,
    currentFilePath, setCurrentFilePath,
    isDirty, setDirty,
    runStatus, setRunStatus,
    addTab, setActiveTabLabel, setActiveTabTemplateName, switchTab,
    compositeEditId, compositeMetadata,
    setBlockLibrary,
    nodes,
    loadedTemplateName, setLoadedTemplateName,
    loadedTemplatePath, setLoadedTemplatePath,
    clearTemplateState,
  } = usePipelineStore();

  // 'open' | 'save' | 'saveAs' | null
  const [browserMode, setBrowserMode] = useState(null);

  // Pending consent for opening a workflow that contains custom code.
  // { path, manifest } while the CodeConsentModal is shown, else null.
  const [consent, setConsent] = useState(null);

  const [templates, setTemplates] = useState([]);
  const [showTemplates, setShowTemplates] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [hoveredCategory, setHoveredCategory] = useState(null);
  const templatesRef = useRef(null);
  const loadingTemplatesRef = useRef(new Set()); // guards against concurrent duplicate loads

  // Group templates by their category field (from the backend)
  const groupedTemplates = (() => {
    const map = new Map();
    for (const { name, category } of templates) {
      if (!map.has(category)) map.set(category, []);
      map.get(category).push(name);
    }
    return Array.from(map.entries()).map(([label, items]) => ({ label, items }));
  })();

  // Close the dropdown when clicking outside it
  useEffect(() => {
    if (!showTemplates) return;
    const handler = (e) => {
      if (templatesRef.current && !templatesRef.current.contains(e.target)) {
        setShowTemplates(false);
        setHoveredCategory(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showTemplates]);

  const indicator = STATUS_INDICATOR[runStatus] ?? STATUS_INDICATOR.idle;

  // --- File operations ---

  const handleNew = () => {
    if (isDirty && !window.confirm('You have unsaved changes. Open a new tab anyway?')) return;
    clearTemplateState();
    addTab();
  };

  const handleOpen = () => {
    clearTemplateState();
    setBrowserMode('open');
  };

  const isTemplatePath = (path) =>
    path && (path.includes('/templates/') || path.includes('\\templates\\'));

  const confirmTemplateOverwrite = () =>
    window.confirm(
      `"${loadedTemplateName}" is a built-in template.\n\n` +
      'Saving here will overwrite it — it is recommended to save as a different copy instead.\n\n' +
      'Click OK to overwrite the template, or Cancel to save elsewhere.'
    );

  const handleSave = async () => {
    if (currentFilePath) {
      // Warn if saving back to the templates directory
      if (isTemplatePath(currentFilePath) && !confirmTemplateOverwrite()) {
        setBrowserMode('saveAs');
        return;
      }
      try {
        await saveWorkflow(serializeWorkflow(), currentFilePath);
        setLoadedTemplateName(null);
        setDirty(false);
      } catch (err) {
        alert(`Failed to save: ${err.response?.data?.message ?? err.message}`);
      }
    } else {
      // No saved path yet. If this workflow came from a template, offer to overwrite directly.
      if (loadedTemplateName && loadedTemplatePath) {
        const overwrite = window.confirm(
          `"${loadedTemplateName}" is a built-in template.\n\n` +
          'Click OK to overwrite the template, or Cancel to abort.\n' +
          '(Use "Save As" if you want to save as a different file.)'
        );
        if (!overwrite) return;
        try {
          await saveWorkflow(serializeWorkflow(), loadedTemplatePath);
          setCurrentFilePath(loadedTemplatePath);
          clearTemplateState();
          setDirty(false);
        } catch (err) {
          alert(`Failed to save: ${err.response?.data?.message ?? err.message}`);
        }
        return;
      }
      setBrowserMode('save');
    }
  };

  const handleSaveAs = () => setBrowserMode('saveAs');

  const handleSaveComposite = async () => {
    if (!compositeEditId || !compositeMetadata) return;
    const { nodes, edges, localBlocks, compositeBlocks } = usePipelineStore.getState();
    const updatedDefinition = {
      ...compositeMetadata,
      subflow: {
        ...(compositeMetadata.subflow ?? {}),
        nodes: nodes.map(n => ({
          node_id: n.id,
          block_type_id: n.data.block_type_id,
          position: n.position,
          parameters: n.data.parameters ?? {},
        })),
        edges: edges.map(e => ({
          edge_id: e.id,
          source_node_id: e.source,
          source_port_id: e.sourceHandle,
          target_node_id: e.target,
          target_port_id: e.targetHandle,
        })),
        local_blocks: localBlocks,
        composite_blocks: compositeBlocks,
      },
    };
    try {
      await updateCompositeBlock(compositeEditId, updatedDefinition);
      setDirty(false);
      const res = await getBlocks();
      setBlockLibrary(res.libraries ?? []);
    } catch (err) {
      alert(`Failed to save composite: ${err.response?.data?.detail?.message ?? err.message}`);
    }
  };

  // Pack workflow
  const [packMode, setPackMode] = useState(false);

  const handlePack = () => setPackMode(true);

  const handlePackSelect = async (path) => {
    setPackMode(false);
    if (!path) return;
    try {
      const res = await packWorkflow(serializeWorkflow(), path);
      alert(`Workflow packed successfully.\nEmbedded ${res.embedded_count} block(s) → ${res.file_path}`);
    } catch (err) {
      alert(`Pack failed: ${err.response?.data?.detail?.message ?? err.message}`);
    }
  };

  // Place a loaded workflow onto the canvas in a fresh tab.
  const applyLoadedWorkflow = (path, data) => {
    const { workflow, missing_libraries, conflicts, forwarding_redirects } = data;
    clearTemplateState();
    addTab();
    loadWorkflowIntoStore(workflow, {
      missingLibraries:    missing_libraries    ?? [],
      libraryConflicts:    conflicts            ?? [],
      forwardingRedirects: forwarding_redirects ?? [],
    });
    setCurrentFilePath(path);
  };

  // User confirmed the consent dialog — reload with trust so the backend
  // registers the embedded code, then render the workflow.
  const handleTrustAndLoad = async () => {
    const path = consent?.path;
    setConsent(null);
    if (!path) return;
    try {
      const res = await loadWorkflow(path, true);
      applyLoadedWorkflow(path, res.data);
    } catch (err) {
      alert(`Failed to load: ${err.response?.data?.message ?? err.message}`);
    }
  };

  // Called when the FileBrowser confirms a selection
  const handleBrowserSelect = async (path) => {
    setBrowserMode(null);
    if (browserMode === 'open') {
      try {
        // First load is untrusted: the backend returns a code manifest without
        // executing anything if the workflow contains custom code.
        const res = await loadWorkflow(path);
        if (res.data.requires_consent) {
          setConsent({ path, manifest: res.data.code_manifest ?? [] });
          return;   // nothing is loaded (and nothing can run) until consent
        }
        applyLoadedWorkflow(path, res.data);
      } catch (err) {
        alert(`Failed to load: ${err.response?.data?.message ?? err.message}`);
      }
    } else {
      // Warn if the user chose a path inside the templates directory
      if (isTemplatePath(path) && !confirmTemplateOverwrite()) return;
      try {
        await saveWorkflow(serializeWorkflow(), path);
        setCurrentFilePath(path);
        clearTemplateState();
        setDirty(false);
      } catch (err) {
        alert(`Failed to save: ${err.response?.data?.message ?? err.message}`);
      }
    }
  };

  const handleShowTemplates = async () => {
    // Toggle: if already open, just close it
    if (showTemplates) {
      setShowTemplates(false);
      setHoveredCategory(null);
      return;
    }
    // Open immediately so the user gets instant feedback, then populate
    setShowTemplates(true);
    setTemplatesLoading(true);
    try {
      const res = await getTemplates();
      setTemplates(res.templates ?? []);
    } catch (err) {
      console.error('Failed to load templates:', err);
      setTemplates([]);
    } finally {
      setTemplatesLoading(false);
    }
  };

  const handleLoadTemplate = async (name, category) => {
    // If a tab for this template already exists, switch to it
    const existingTab = usePipelineStore.getState().tabs.find(t => t.templateName === name);
    if (existingTab) {
      switchTab(existingTab.id);
      setShowTemplates(false);
      setHoveredCategory(null);
      return;
    }
    // Guard: if we're already in the middle of loading this template, do nothing
    if (loadingTemplatesRef.current.has(name)) return;
    loadingTemplatesRef.current.add(name);
    try {
      const res = await loadTemplate(category, name);
      const { workflow, missing_libraries, conflicts, forwarding_redirects } = res;
      addTab();                              // open in a new tab
      loadWorkflowIntoStore(workflow, {
        missingLibraries:    missing_libraries    ?? [],
        libraryConflicts:    conflicts            ?? [],
        forwardingRedirects: forwarding_redirects ?? [],
      });
      setActiveTabLabel(name);               // name the tab after the template
      setActiveTabTemplateName(name);        // tag tab so we can find it later
      setLoadedTemplateName(name);           // remember it came from a template
      setLoadedTemplatePath(res.template_path ?? null);  // store path for direct overwrite
      // currentFilePath stays null
      setShowTemplates(false);
      setHoveredCategory(null);
    } catch (err) {
      alert(`Failed to load template: ${err.response?.data?.message ?? err.message}`);
    } finally {
      loadingTemplatesRef.current.delete(name);
    }
  };

  // --- Execution controls ---

  const handleRun = async () => {
    if (runStatus === 'running' || runStatus === 'stopping') return;
    setRunStatus('running');
    try {
      await runPipeline(serializeWorkflow(), true);
    } catch (err) {
      setRunStatus('error');
    }
  };

  const handleRunNoCache = async () => {
    if (runStatus === 'running' || runStatus === 'stopping') return;
    setRunStatus('running');
    try {
      await runPipeline(serializeWorkflow(), false);
    } catch (err) {
      setRunStatus('error');
    }
  };

  const handleStep = async () => {
    if (runStatus === 'running' || runStatus === 'stopping') return;
    const sel = nodes.filter(n => n.selected);
    if (sel.length !== 1) return;
    setRunStatus('running');
    try {
      await stepPipeline(serializeWorkflow(), sel[0].id);
    } catch (err) {
      setRunStatus('error');
    }
  };

  const handleStop = async () => {
    try {
      setRunStatus('stopping');   // immediate visual feedback
      await stopPipeline();
      // Don't force-set to idle here — the WebSocket will deliver
      // {status: 'stopped'} once the current node finishes, and
      // App.jsx will call store.setRunStatus('stopped') at that point.
    } catch (err) {
      console.error(err);
      setRunStatus('idle');
    }
  };

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 4,
      padding: '6px 12px',
      background: '#0f172a', borderBottom: '1px solid #374151',
      flexShrink: 0, position: 'relative',
    }}>
      {browserMode && (
        <FileBrowser
          initialPath={currentFilePath ?? ''}
          onSelect={handleBrowserSelect}
          onClose={() => setBrowserMode(null)}
          placeholder={browserMode === 'open' ? 'File name…' : 'Workflow name…'}
          autoExt={browserMode !== 'open' ? '.json' : ''}
        />
      )}
      {packMode && (
        <FileBrowser
          initialPath={currentFilePath ?? ''}
          onSelect={handlePackSelect}
          onClose={() => setPackMode(false)}
          placeholder="Packed workflow name…"
          autoExt=".json"
        />
      )}
      {consent && (
        <CodeConsentModal
          filePath={consent.path}
          manifest={consent.manifest}
          onTrust={handleTrustAndLoad}
          onCancel={() => setConsent(null)}
        />
      )}
      {/* File ops */}
      <button style={BTN} onClick={handleNew}>New</button>
      {compositeEditId ? (
        <button
          style={{ ...BTN, background: '#1e3a5f', borderColor: '#3b82f6' }}
          onClick={handleSaveComposite}
        >
          💾 Save composite{isDirty ? ' *' : ''}
        </button>
      ) : (
        <>
          <button style={BTN} onClick={handleOpen}>Open</button>
          <button style={BTN} onClick={handleSave}>Save{isDirty ? ' *' : ''}</button>
          <button style={BTN} onClick={handleSaveAs}>Save As</button>
        </>
      )}
      <button style={BTN} onClick={handlePack} title="Pack workflow into a self-contained JSON">📦 Pack</button>

      <div ref={templatesRef} style={{ position: 'relative' }}>
        <button style={BTN} onClick={handleShowTemplates}>Templates ▾</button>
        {showTemplates && (
          <div style={{
            position: 'absolute', top: '100%', left: 0, zIndex: 999,
            background: '#1f2937', border: '1px solid #374151', borderRadius: 4,
            minWidth: 160, boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
          }}>
            {templatesLoading
              ? <div style={{ padding: '8px 12px', color: '#6b7280', fontSize: 12 }}>Loading…</div>
              : groupedTemplates.length === 0
                ? <div style={{ padding: '8px 12px', color: '#6b7280', fontSize: 12 }}>No templates found.</div>
                : groupedTemplates.map(group => (
                  <div
                    key={group.label}
                    style={{ position: 'relative' }}
                    onMouseEnter={() => setHoveredCategory(group.label)}
                  >
                    {/* Category row */}
                    <div style={{
                      padding: '7px 12px', cursor: 'default', fontSize: 12,
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16,
                      background: hoveredCategory === group.label ? '#374151' : 'transparent',
                      color: '#f9fafb', userSelect: 'none',
                    }}>
                      <span>{group.label}</span>
                      <span style={{ color: '#6b7280', fontSize: 10 }}>▸</span>
                    </div>

                    {/* Flyout submenu */}
                    {hoveredCategory === group.label && (
                      <div style={{
                        position: 'absolute', left: '100%', top: 0, zIndex: 1000,
                        background: '#1f2937', border: '1px solid #374151', borderRadius: 4,
                        minWidth: 220, boxShadow: '4px 4px 12px rgba(0,0,0,0.5)',
                      }}>
                        {group.items.map(t => (
                          <div
                            key={t}
                            onClick={() => handleLoadTemplate(t, group.label)}
                            style={{ padding: '7px 14px', cursor: 'pointer', fontSize: 12, color: '#f9fafb' }}
                            onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                            onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                          >
                            {t}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))
            }
          </div>
        )}
      </div>

      {/* Separator */}
      <div style={{ width: 1, height: 20, background: '#374151', margin: '0 4px' }} />

      {/* Execution controls */}
      <button style={{ ...BTN, background: '#166534', borderColor: '#22c55e' }} onClick={handleRun}>▶ Run</button>
      <button style={BTN} onClick={handleRunNoCache}>▶ Run (no cache)</button>
      {(() => {
        const sel = nodes.filter(n => n.selected);
        const ready = sel.length === 1;
        const label = ready ? sel[0].data?.label ?? sel[0].id : null;
        return (
          <button
            style={{ ...BTN, opacity: ready ? 1 : 0.45, cursor: ready ? 'pointer' : 'default' }}
            onClick={handleStep}
            title={ready ? `Step: ${label}` : 'Click a node on the canvas to select it, then step'}
          >⏭ Step{ready ? `: ${label}` : ''}</button>
        );
      })()}
      <button style={{ ...BTN, background: '#7f1d1d', borderColor: '#ef4444' }} onClick={handleStop}>■ Stop</button>

      {/* Status indicator */}
      <div style={{ marginLeft: 'auto', fontSize: 12, color: indicator.color, fontWeight: 600 }}>
        {indicator.label}
      </div>
    </div>
  );
}
