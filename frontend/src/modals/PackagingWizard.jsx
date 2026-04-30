import { useState, useMemo, useEffect } from 'react';
import usePipelineStore, { compositeBlockToDefinition } from '../store/pipelineStore';
import { packageBlock, getBlocks, getLibraries } from '../api/client';

const OVERLAY = {
  position: 'fixed', inset: 0,
  background: 'rgba(0,0,0,0.7)',
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  zIndex: 10000,
};

const MODAL = {
  background: '#1f2937', border: '1px solid #374151',
  borderRadius: 8, padding: 24, minWidth: 640, maxWidth: 820,
  maxHeight: '90vh', overflowY: 'auto', color: '#f9fafb',
  boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
};

const LABEL = { fontSize: 11, color: '#9ca3af', marginBottom: 4, display: 'block' };

const INPUT = {
  width: '100%', background: '#111827', border: '1px solid #374151',
  borderRadius: 4, color: '#f9fafb', padding: '6px 8px',
  fontSize: 12, boxSizing: 'border-box',
};

const BTN = {
  background: '#374151', border: '1px solid #4b5563',
  color: '#f9fafb', borderRadius: 4, padding: '6px 14px',
  fontSize: 12, cursor: 'pointer',
};

const BTN_PRIMARY = {
  ...BTN,
  background: '#4f46e5', border: '1px solid #6366f1', color: '#fff',
};

// Heuristic: does this parameter look like a file path?
function isPathParam(name, value) {
  const nameLower = (name ?? '').toLowerCase();
  const val = String(value ?? '');
  if (/path|file|dir/.test(nameLower)) return true;
  if (/^(\/|\.\/|[A-Za-z]:[/\\])/.test(val)) return true;
  return false;
}

/**
 * Three-step wizard for packaging the current workflow as a composite block.
 *
 * Step 1: Promote file-path parameters to external input ports.
 * Step 2: Select which dangling ports to expose as external inputs/outputs.
 * Step 3: Fill in metadata (name, id, category, description).
 *
 * @param {function} onClose - Called when the wizard should close (cancel or success).
 * @param {function} onCreated - Called with the new composite block definition after save.
 */
export default function PackagingWizard({ onClose, onCreated }) {
  const { nodes, edges, blockIndex, localBlocks, compositeBlocks, serializeWorkflow } = usePipelineStore();

  // ── Step tracking ─────────────────────────────────────────────────────────
  const [step, setStep] = useState(1);

  // ── Step 1: Promoted parameters ───────────────────────────────────────────
  // Scan all nodes for str parameters that look like file paths.
  const candidatePromotions = useMemo(() => {
    const rows = [];
    for (const node of nodes) {
      const bid = node.data.block_type_id;
      let def = node.data.definition ?? null;
      if (!def) {
        const lb = localBlocks.find(b => b.block_type_id === bid);
        if (lb) def = { display_name: lb.display_name, parameters: lb.parameters?.map(p => ({ name: p.name, type: p.data_type, default: p.default })) ?? [] };
      }
      if (!def) def = blockIndex[bid] ?? null;
      if (!def) continue;

      const nodeName = def.display_name ?? bid;
      const currentParams = node.data.parameters ?? {};

      for (const param of (def.parameters ?? [])) {
        // Only str parameters
        if (param.type !== 'str' && param.data_type !== 'str') continue;
        const currentValue = currentParams[param.name] ?? param.default ?? '';
        if (!isPathParam(param.name, currentValue)) continue;
        rows.push({
          nodeId:        node.id,
          nodeName,
          paramName:     param.name,
          currentValue:  String(currentValue),
          externalLabel: param.name,
          promote:       true,
        });
      }
    }
    return rows;
  }, [nodes, blockIndex, localBlocks]);

  const [promotionRows, setPromotionRows] = useState(() => candidatePromotions);

  const togglePromote   = (i) => setPromotionRows(rows => rows.map((r, idx) => idx === i ? { ...r, promote: !r.promote } : r));
  const setPromoLabel   = (i, v) => setPromotionRows(rows => rows.map((r, idx) => idx === i ? { ...r, externalLabel: v } : r));

  // ── Step 2: Port selection ─────────────────────────────────────────────────
  // Detect dangling ports (same as before)
  const { candidateInputs, candidateOutputs } = useMemo(() => {
    // port id sets that have connections
    const connectedTargets = new Set(edges.map(e => `${e.target}::${e.targetHandle}`));
    const connectedSources = new Set(edges.map(e => `${e.source}::${e.sourceHandle}`));

    const candIn  = [];
    const candOut = [];

    for (const node of nodes) {
      // Resolve definition
      const bid = node.data.block_type_id;
      let def = node.data.definition ?? null;
      if (!def) {
        const lb = localBlocks.find(b => b.block_type_id === bid);
        if (lb) {
          def = { inputs: lb.inputs?.map(p => ({ port_id: p.port_id, type: p.data_type })) ?? [],
                  outputs: lb.outputs?.map(p => ({ port_id: p.port_id, type: p.data_type })) ?? [],
                  display_name: lb.display_name };
        }
      }
      if (!def) def = blockIndex[bid] ?? null;
      if (!def) continue;

      const nodeName = def.display_name ?? bid;

      for (const port of (def.inputs ?? [])) {
        const key = `${node.id}::${port.port_id}`;
        if (!connectedTargets.has(key)) {
          candIn.push({
            nodeId: node.id, nodeName, portId: port.port_id,
            portType: port.type ?? '', externalLabel: port.port_id,
            include: true,
          });
        }
      }
      for (const port of (def.outputs ?? [])) {
        const key = `${node.id}::${port.port_id}`;
        if (!connectedSources.has(key)) {
          // Uncheck visualization dead-ends by default (category === 'Visualization')
          const cat = def.category ?? '';
          candOut.push({
            nodeId: node.id, nodeName, portId: port.port_id,
            portType: port.type ?? '', externalLabel: port.port_id,
            include: cat !== 'Visualization',
          });
        }
      }
    }
    return { candidateInputs: candIn, candidateOutputs: candOut };
  }, [nodes, edges, blockIndex, localBlocks]);

  const [inputRows,  setInputRows]  = useState(() => candidateInputs);
  const [outputRows, setOutputRows] = useState(() => candidateOutputs);

  // ── Step 3 state (metadata) ───────────────────────────────────────────────
  const [displayName,      setDisplayName]      = useState('');
  const [blockTypeId,      setBlockTypeId]      = useState('');
  const [category,         setCategory]         = useState('Composite');
  const [description,      setDescription]      = useState('');
  const [targetLibraryId,  setTargetLibraryId]  = useState('user_blocks');
  const [writableLibraries, setWritableLibraries] = useState([]);
  const [saving,           setSaving]           = useState(false);
  const [error,            setError]            = useState('');

  // Load writable libraries for the target selector
  useEffect(() => {
    getLibraries()
      .then(res => {
        const writable = (res.libraries ?? []).filter(l => !l.is_builtin);
        setWritableLibraries(writable);
        if (writable.length > 0 && !writable.find(l => l.id === targetLibraryId)) {
          setTargetLibraryId(writable[0].id);
        }
      })
      .catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-generate block_type_id from display name
  const autoId = (name) =>
    name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '');

  const handleNameChange = (v) => {
    setDisplayName(v);
    if (!blockTypeId || blockTypeId === autoId(displayName)) {
      setBlockTypeId(autoId(v));
    }
  };

  // Toggle include on a row
  const toggleInput  = (i) => setInputRows(rows  => rows.map((r, idx) => idx === i ? { ...r, include: !r.include } : r));
  const toggleOutput = (i) => setOutputRows(rows => rows.map((r, idx) => idx === i ? { ...r, include: !r.include } : r));

  // Edit label
  const setInputLabel  = (i, v) => setInputRows(rows  => rows.map((r, idx) => idx === i ? { ...r, externalLabel: v } : r));
  const setOutputLabel = (i, v) => setOutputRows(rows => rows.map((r, idx) => idx === i ? { ...r, externalLabel: v } : r));

  // ── Save ─────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!blockTypeId.trim()) { setError('Block ID is required.'); return; }
    if (!displayName.trim()) { setError('Block name is required.'); return; }

    const workflow = serializeWorkflow();
    const promotedMappings = promotionRows.filter(r => r.promote).map(r => ({
      external_port_id: r.externalLabel || r.paramName,
      node_id:          r.nodeId,
      parameter:        r.paramName,
      default:          r.currentValue,
    }));
    const inputMappings  = inputRows.filter(r => r.include).map(r => ({
      external_port_id: r.externalLabel || r.portId,
      node_id:  r.nodeId,
      port_id:  r.portId,
      data_type: r.portType,
    }));
    const outputMappings = outputRows.filter(r => r.include).map(r => ({
      external_port_id: r.externalLabel || r.portId,
      node_id:  r.nodeId,
      port_id:  r.portId,
      data_type: r.portType,
    }));

    setSaving(true);
    setError('');
    try {
      const result = await packageBlock({
        workflow,
        metadata: {
          block_type_id: blockTypeId.trim(),
          display_name:  displayName.trim(),
          category:      category.trim() || 'Composite',
          description:   description.trim(),
        },
        promoted_parameters: promotedMappings,
        input_mappings:  inputMappings,
        output_mappings: outputMappings,
        library_id:      targetLibraryId,
      });
      // Fetch updated block library so new composite shows in side panel
      const libData = await getBlocks();
      usePipelineStore.getState().setBlockLibrary(libData.libraries ?? []);
      onCreated?.(result.definition);
      onClose();
    } catch (err) {
      setError(err.response?.data?.detail?.message ?? err.message ?? 'Unknown error');
    } finally {
      setSaving(false);
    }
  };

  // ── Table helpers ─────────────────────────────────────────────────────────
  const tableStyle = {
    width: '100%', borderCollapse: 'collapse', fontSize: 11, marginBottom: 12,
  };
  const th = {
    textAlign: 'left', padding: '4px 8px',
    color: '#9ca3af', borderBottom: '1px solid #374151', fontWeight: 600,
  };
  const td = {
    padding: '4px 8px', borderBottom: '1px solid #1f2937',
    verticalAlign: 'middle',
  };

  const PortTable = ({ rows, onToggle, onLabelChange, title }) => (
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#a5b4fc', marginBottom: 6 }}>{title}</div>
      {rows.length === 0
        ? <div style={{ color: '#6b7280', fontSize: 11, padding: '8px 0' }}>No dangling {title.toLowerCase()}.</div>
        : (
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={th}>Include</th>
                <th style={th}>Node</th>
                <th style={th}>Port</th>
                <th style={th}>Type</th>
                <th style={th}>External label</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} style={{ background: row.include ? 'rgba(99,102,241,0.07)' : 'transparent' }}>
                  <td style={td}>
                    <input type="checkbox" checked={row.include}
                      onChange={() => onToggle(i)} />
                  </td>
                  <td style={{ ...td, color: '#d1d5db' }}>{row.nodeName}</td>
                  <td style={{ ...td, color: '#d1d5db', fontFamily: 'monospace' }}>{row.portId}</td>
                  <td style={{ ...td, color: '#6b7280', fontFamily: 'monospace', fontSize: 10 }}>{row.portType}</td>
                  <td style={td}>
                    <input
                      value={row.externalLabel}
                      onChange={e => onLabelChange(i, e.target.value)}
                      disabled={!row.include}
                      style={{
                        ...INPUT, padding: '2px 6px', fontSize: 11,
                        opacity: row.include ? 1 : 0.4,
                      }}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      }
    </div>
  );

  return (
    <div style={OVERLAY} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div style={MODAL}>
        {/* Title */}
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
          <span style={{ fontSize: 16, fontWeight: 700, flex: 1 }}>
            ⊞ Package as composite block
          </span>
          <span style={{ color: '#6b7280', fontSize: 12 }}>
            Step {step} of 3
          </span>
          <button onClick={onClose} style={{ ...BTN, marginLeft: 12, padding: '3px 10px' }}>✕</button>
        </div>

        {/* Step indicator */}
        <div style={{ display: 'flex', gap: 0, marginBottom: 20 }}>
          {[1, 2, 3].map(s => (
            <div key={s} style={{
              flex: 1, height: 3, borderRadius: 2,
              background: step >= s ? '#6366f1' : '#374151',
              marginRight: s < 3 ? 4 : 0,
            }} />
          ))}
        </div>

        {/* ── Step 1: Promoted parameters ── */}
        {step === 1 && (
          <>
            <p style={{ color: '#9ca3af', fontSize: 12, marginBottom: 16 }}>
              The following <strong style={{ color: '#f9fafb' }}>file path parameters</strong> were
              detected across your workflow nodes. Promoting a parameter converts it into an
              external input port of type <code style={{ color: '#a5b4fc' }}>str</code> on the
              composite block, so callers can pass different paths without editing the subflow.
              The current value is kept as the default.
            </p>

            {promotionRows.length === 0 ? (
              <div style={{
                color: '#6b7280', fontSize: 12, padding: '12px 0', fontStyle: 'italic',
              }}>
                No file path parameters found. You can still expose data ports in the next step.
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11, marginBottom: 12 }}>
                <thead>
                  <tr>
                    <th style={th}>Promote</th>
                    <th style={th}>Node</th>
                    <th style={th}>Parameter</th>
                    <th style={th}>Current value</th>
                    <th style={th}>External port label</th>
                  </tr>
                </thead>
                <tbody>
                  {promotionRows.map((row, i) => (
                    <tr key={i} style={{ background: row.promote ? 'rgba(99,102,241,0.07)' : 'transparent' }}>
                      <td style={td}>
                        <input type="checkbox" checked={row.promote}
                          onChange={() => togglePromote(i)} />
                      </td>
                      <td style={{ ...td, color: '#d1d5db' }}>{row.nodeName}</td>
                      <td style={{ ...td, color: '#d1d5db', fontFamily: 'monospace' }}>{row.paramName}</td>
                      <td style={{ ...td, color: '#6b7280', fontFamily: 'monospace', fontSize: 10,
                        maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {row.currentValue || <em style={{ color: '#4b5563' }}>empty</em>}
                      </td>
                      <td style={td}>
                        <input
                          value={row.externalLabel}
                          onChange={e => setPromoLabel(i, e.target.value)}
                          disabled={!row.promote}
                          style={{
                            ...INPUT, padding: '2px 6px', fontSize: 11,
                            opacity: row.promote ? 1 : 0.4,
                          }}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 8 }}>
              <button style={BTN} onClick={onClose}>Cancel</button>
              <button style={BTN_PRIMARY} onClick={() => setStep(2)}>Next →</button>
            </div>
          </>
        )}

        {/* ── Step 2: Port selection ── */}
        {step === 2 && (
          <>
            <p style={{ color: '#9ca3af', fontSize: 12, marginBottom: 16 }}>
              Select which dangling ports to expose as external inputs and outputs of this composite block.
              Assign a clear external label for each selected port.
            </p>
            <div style={{ display: 'flex', gap: 16 }}>
              <PortTable
                rows={inputRows}
                onToggle={toggleInput}
                onLabelChange={setInputLabel}
                title="Inputs"
              />
              <PortTable
                rows={outputRows}
                onToggle={toggleOutput}
                onLabelChange={setOutputLabel}
                title="Outputs"
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginTop: 8 }}>
              <button style={BTN} onClick={() => setStep(1)}>← Back</button>
              <button style={BTN_PRIMARY} onClick={() => setStep(3)}>Next →</button>
            </div>
          </>
        )}

        {/* ── Step 3: Metadata ── */}
        {step === 3 && (
          <>
            <p style={{ color: '#9ca3af', fontSize: 12, marginBottom: 16 }}>
              Describe the composite block. The block will be saved to the library and can be reused in other workflows.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <label style={LABEL}>Block name *</label>
                <input
                  style={INPUT}
                  value={displayName}
                  onChange={e => handleNameChange(e.target.value)}
                  placeholder="LFP preprocessing pipeline"
                  autoFocus
                />
              </div>
              <div>
                <label style={LABEL}>Block ID * (snake_case, unique)</label>
                <input
                  style={INPUT}
                  value={blockTypeId}
                  onChange={e => setBlockTypeId(e.target.value)}
                  placeholder="lfp_preprocessing_pipeline"
                />
              </div>
              <div>
                <label style={LABEL}>Category</label>
                <input
                  style={INPUT}
                  value={category}
                  onChange={e => setCategory(e.target.value)}
                  placeholder="Composite"
                />
              </div>
              <div>
                <label style={LABEL}>Description</label>
                <input
                  style={INPUT}
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="Bandpass filter and phase extraction for LFP signals."
                />
              </div>
            </div>

            {/* Library selector */}
            <div style={{ marginBottom: 16 }}>
              <label style={LABEL}>Save to library</label>
              <select
                style={INPUT}
                value={targetLibraryId}
                onChange={e => setTargetLibraryId(e.target.value)}
              >
                {writableLibraries.length === 0
                  ? <option value="user_blocks">User Blocks (default)</option>
                  : writableLibraries.map(l => (
                    <option key={l.id} value={l.id}>{l.name} ({l.id})</option>
                  ))
                }
              </select>
              <div style={{ fontSize: 10, color: '#4b5563', marginTop: 4 }}>
                Only writable (non-built-in) libraries are listed.
              </div>
            </div>

            {/* Port summary */}
            <div style={{
              background: '#111827', borderRadius: 6, padding: '10px 14px',
              fontSize: 11, color: '#6b7280', marginBottom: 16,
            }}>
              <strong style={{ color: '#9ca3af' }}>Port summary: </strong>
              {promotionRows.filter(r => r.promote).length > 0 && (
                <span>
                  {promotionRows.filter(r => r.promote).length} promoted param(s)
                  {promotionRows.filter(r => r.promote).map(r => ` "${r.externalLabel}"`).join(',')}
                  {' · '}
                </span>
              )}
              {inputRows.filter(r => r.include).length} data input(s)
              {inputRows.filter(r => r.include).map(r => ` "${r.externalLabel}"`).join(',')}
              {' · '}
              {outputRows.filter(r => r.include).length} output(s)
              {outputRows.filter(r => r.include).map(r => ` "${r.externalLabel}"`).join(',')}
            </div>

            {error && (
              <div style={{
                background: '#7f1d1d', border: '1px solid #ef4444',
                borderRadius: 4, padding: '8px 12px', color: '#fca5a5',
                fontSize: 12, marginBottom: 12,
              }}>
                {error}
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
              <button style={BTN} onClick={() => setStep(2)}>← Back</button>
              <div style={{ display: 'flex', gap: 8 }}>
                <button style={BTN} onClick={onClose}>Cancel</button>
                <button
                  style={{ ...BTN_PRIMARY, opacity: saving ? 0.6 : 1 }}
                  onClick={handleSave}
                  disabled={saving}
                >
                  {saving ? 'Saving…' : '⊞ Save composite block'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
