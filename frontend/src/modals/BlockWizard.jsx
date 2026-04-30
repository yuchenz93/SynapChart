import { useState, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import usePipelineStore, { localBlockToDefinition } from '../store/pipelineStore';
import { getBlocks, getBlockSource, createBlock, updateBlock, testRunBlock, registerLocalBlocks } from '../api/client';

// ─── Constants ───────────────────────────────────────────────────────────────

const PORT_TYPES = [
  'NeuroData[raw_signal]', 'NeuroData[lfp]', 'NeuroData[spike_times]',
  'NeuroData[spike_matrix]', 'NeuroData[position]', 'NeuroData[tuning_curve]',
  'NeuroData[decoded]', 'NeuroData[any]',
  'float', 'int', 'str', 'bool',
];
const PARAM_TYPES = ['str', 'float', 'int', 'bool', 'enum'];

// ─── Template generator ───────────────────────────────────────────────────────
// Produces the body of run(self, inputs, parameters) in the same style as the
// built-in blocks: typed input unpacking, parameters.get() with explicit casts,
// and full NeuroData(...) construction preserving timestamps/channel_names/metadata.

function generateTemplate(inputs, outputs, params) {
  const lines = [
    '# numpy, NeuroData and disp() are always available.',
    '# disp(value) prints to the SynapChart console during execution.',
    '# Add any other imports here freely.',
    '# List extra pip packages in the "Extra dependencies" field below.',
    'import numpy as np',
    '',
  ];
  const neuroInputs  = inputs.filter(i => i.data_type.startsWith('NeuroData['));
  const scalarInputs = inputs.filter(i => !i.data_type.startsWith('NeuroData['));
  const firstNeuro   = neuroInputs[0] ?? null;

  // ── 1. Unpack NeuroData inputs ───────────────────────────────────────────
  neuroInputs.forEach(inp => {
    lines.push(`${inp.port_id}: NeuroData = inputs["${inp.port_id}"]`);
  });
  if (firstNeuro) {
    lines.push(`sr = ${firstNeuro.port_id}.sampling_rate or 1000.0`);
  }

  // ── 2. Unpack scalar inputs ──────────────────────────────────────────────
  scalarInputs.forEach(inp => {
    const casts = { float: 'float', int: 'int', bool: 'bool' };
    const cast  = casts[inp.data_type] ?? '';
    lines.push(cast
      ? `${inp.port_id} = ${cast}(inputs["${inp.port_id}"])`
      : `${inp.port_id} = inputs["${inp.port_id}"]`
    );
  });

  if (inputs.length > 0) lines.push('');

  // ── 3. Unpack parameters with type casts ────────────────────────────────
  params.forEach(p => {
    const raw = p.default ?? '';
    if (p.data_type === 'float') {
      const dv = parseFloat(raw);
      lines.push(`${p.name} = float(parameters.get("${p.name}", ${isNaN(dv) ? '0.0' : dv}))`);
    } else if (p.data_type === 'int') {
      const dv = parseInt(raw, 10);
      lines.push(`${p.name} = int(parameters.get("${p.name}", ${isNaN(dv) ? '0' : dv}))`);
    } else if (p.data_type === 'bool') {
      const dv = ['true', '1', 'yes'].includes(String(raw).toLowerCase()) ? 'True' : 'False';
      lines.push(`${p.name} = bool(parameters.get("${p.name}", ${dv}))`);
    } else {
      // str / enum
      lines.push(`${p.name} = str(parameters.get("${p.name}", "${raw}"))`);
    }
  });

  if (params.length > 0) lines.push('');

  // ── 4. Processing placeholder ────────────────────────────────────────────
  if (firstNeuro) {
    lines.push('# --- your processing logic here ---');
    lines.push(`processed = ${firstNeuro.port_id}.array  # TODO: apply your algorithm`);
    lines.push('');
  } else if (outputs.some(o => o.data_type.startsWith('NeuroData['))) {
    lines.push('# --- your processing logic here ---');
    lines.push('processed = None  # TODO');
    lines.push('');
  }

  // ── 5. Return dict ───────────────────────────────────────────────────────
  lines.push('return {');
  if (outputs.length === 0) {
    lines.push('    # No outputs defined');
  } else {
    outputs.forEach(o => {
      if (o.data_type.startsWith('NeuroData[')) {
        const dtype = o.data_type.slice(10, -1); // e.g. "lfp"
        if (firstNeuro) {
          lines.push(`    "${o.port_id}": NeuroData(`);
          lines.push(`        data_type="${dtype}",`);
          lines.push(`        array=processed,`);
          lines.push(`        sampling_rate=sr,`);
          lines.push(`        timestamps=${firstNeuro.port_id}.timestamps,`);
          lines.push(`        channel_names=${firstNeuro.port_id}.channel_names,`);
          lines.push(`        metadata={**${firstNeuro.port_id}.metadata},`);
          lines.push(`    ),`);
        } else {
          lines.push(`    "${o.port_id}": NeuroData(data_type="${dtype}", array=processed, sampling_rate=1.0),`);
        }
      } else if (o.data_type === 'float') {
        lines.push(`    "${o.port_id}": 0.0,  # TODO`);
      } else if (o.data_type === 'int') {
        lines.push(`    "${o.port_id}": 0,  # TODO`);
      } else {
        lines.push(`    "${o.port_id}": None,  # TODO: return ${o.data_type}`);
      }
    });
  }
  lines.push('}');

  return lines.join('\n');
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const toId = (name) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '');

const emptyInput  = () => ({ port_id: '', data_type: 'NeuroData[raw_signal]', description: '', required: true });
const emptyOutput = () => ({ port_id: '', data_type: 'NeuroData[raw_signal]', description: '' });
const emptyParam  = () => ({ name: '', data_type: 'float', default: '', description: '', enum_values: '' });

// Convert definition format (from API) → wizard row format
const defToWizardInputs  = (defPorts) => defPorts.map(p => ({
  port_id: p.port_id, data_type: p.type, description: p.description || '', required: p.required !== false,
}));
const defToWizardOutputs = (defPorts) => defPorts.map(p => ({
  port_id: p.port_id, data_type: p.type, description: p.description || '',
}));
const defToWizardParams  = (defParams) => defParams.map(p => ({
  name: p.name,
  data_type: p.type === 'enum' ? 'enum' : p.type,
  default: String(p.default ?? ''),
  description: p.description || '',
  enum_values: p.type === 'enum' ? (p.enum || []).join(',') : '',
}));

// ─── Shared input style ───────────────────────────────────────────────────────

const iS = {
  background: '#111827', border: '1px solid #374151', borderRadius: 3,
  color: '#f9fafb', padding: '3px 6px', fontSize: 12, width: '100%',
};
const btn = (color = '#374151') => ({
  background: color, border: 'none', borderRadius: 4,
  color: '#fff', padding: '6px 14px', cursor: 'pointer', fontSize: 12,
});

// ─── Step indicator ───────────────────────────────────────────────────────────

function StepDot({ n, label, active, done }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{
        width: 24, height: 24, borderRadius: '50%', fontSize: 12, fontWeight: 700,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: done ? '#22c55e' : active ? '#6366f1' : '#374151',
        color: '#fff', flexShrink: 0,
      }}>
        {done ? '✓' : n}
      </div>
      <span style={{ fontSize: 12, color: active ? '#f9fafb' : '#6b7280' }}>{label}</span>
    </div>
  );
}

// ─── Dynamic row table ────────────────────────────────────────────────────────

function PortTable({ title, rows, setRows, withRequired }) {
  const update = (idx, field, val) =>
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: val } : r));

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{title}</span>
        <button onClick={() => setRows(r => [...r, withRequired ? emptyInput() : emptyOutput()])} style={{ ...btn('#4f46e5'), padding: '3px 10px' }}>+ Add</button>
      </div>
      {rows.length === 0
        ? <div style={{ fontSize: 11, color: '#4b5563', padding: '4px 0' }}>No {title.toLowerCase()} defined.</div>
        : (
          <>
            <div style={{ display: 'flex', gap: 6, marginBottom: 3 }}>
              {['Port name', 'Data type', 'Description', ...(withRequired ? ['Req'] : []), ''].map((h, i) => (
                <span key={i} style={{ flex: h === '' ? '0 0 22px' : h === 'Req' ? '0 0 30px' : i === 1 ? 3 : i === 0 ? 2 : 4, fontSize: 10, color: '#6b7280' }}>{h}</span>
              ))}
            </div>
            {rows.map((row, idx) => (
              <div key={idx} style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 4 }}>
                <input value={row.port_id} onChange={e => update(idx, 'port_id', e.target.value)} style={{ ...iS, flex: 2 }} placeholder="port_id" />
                <select value={row.data_type} onChange={e => update(idx, 'data_type', e.target.value)} style={{ ...iS, flex: 3 }}>
                  {PORT_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <input value={row.description} onChange={e => update(idx, 'description', e.target.value)} style={{ ...iS, flex: 4 }} placeholder="description" />
                {withRequired && (
                  <input type="checkbox" checked={row.required} onChange={e => update(idx, 'required', e.target.checked)} style={{ flex: '0 0 30px' }} />
                )}
                <button onClick={() => setRows(r => r.filter((_, i) => i !== idx))}
                  style={{ flex: '0 0 22px', background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 14, padding: 0 }}>✕</button>
              </div>
            ))}
          </>
        )
      }
    </div>
  );
}

function ParamTable({ params, setParams }) {
  const update = (idx, field, val) =>
    setParams(prev => prev.map((r, i) => i === idx ? { ...r, [field]: val } : r));

  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: '#9ca3af', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Parameters</span>
        <button onClick={() => setParams(p => [...p, emptyParam()])} style={{ ...btn('#4f46e5'), padding: '3px 10px' }}>+ Add</button>
      </div>
      {params.length === 0
        ? <div style={{ fontSize: 11, color: '#4b5563', padding: '4px 0' }}>No parameters defined.</div>
        : params.map((p, idx) => (
          <div key={idx} style={{ marginBottom: 8, background: '#0f172a', borderRadius: 4, padding: '6px 8px' }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: p.data_type === 'enum' ? 6 : 0 }}>
              <input value={p.name} onChange={e => update(idx, 'name', e.target.value)} style={{ ...iS, flex: 2 }} placeholder="param_name" />
              <select value={p.data_type} onChange={e => update(idx, 'data_type', e.target.value)} style={{ ...iS, flex: 2 }}>
                {PARAM_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
              <input value={p.default} onChange={e => update(idx, 'default', e.target.value)} style={{ ...iS, flex: 2 }} placeholder="default" />
              <input value={p.description} onChange={e => update(idx, 'description', e.target.value)} style={{ ...iS, flex: 4 }} placeholder="description" />
              <button onClick={() => setParams(ps => ps.filter((_, i) => i !== idx))}
                style={{ flex: '0 0 22px', background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', fontSize: 14, padding: 0 }}>✕</button>
            </div>
            {p.data_type === 'enum' && (
              <input value={p.enum_values} onChange={e => update(idx, 'enum_values', e.target.value)}
                style={{ ...iS }} placeholder="Comma-separated values, e.g. mean,median,max" />
            )}
          </div>
        ))
      }
    </div>
  );
}

// ─── Main wizard ──────────────────────────────────────────────────────────────

/**
 * 3-step block creation / editing wizard.
 *
 * Props:
 *   editBlock  – block definition to pre-fill (null = new block)
 *   onClose()  – called when wizard is dismissed or saved
 */
/**
 * saveToLibrary – when true, a *new* block is saved to the global disk library
 *                 (used for "Duplicate to library"). Default false = local block.
 */
export default function BlockWizard({ editBlock = null, onClose, saveToLibrary = false }) {
  const { blockLibrary, blockIndex, setBlockLibrary, localBlocks, addLocalBlock, updateLocalBlock, setDirty } = usePipelineStore();
  const existingCategories = [...new Set(
    blockLibrary.flatMap(lib => (lib.categories ?? []).map(c => c.name))
  )].sort();

  const isEdit      = Boolean(editBlock?.is_custom);
  // Local edit: editing a block that lives in the workflow's local_blocks array,
  // not yet promoted to the global library.
  const isLocalEdit = isEdit && Boolean(editBlock?.is_local);

  // ── Step state ──
  const [step, setStep] = useState(1);

  // Whether the category field should be shown:
  // - Always shown when editing an existing global block (isEdit && !isLocalEdit)
  // - Always shown when saving to library (saveToLibrary)
  // - Hidden for new local blocks and local-block edits (category is always 'local')
  const showCategory = (isEdit && !isLocalEdit) || saveToLibrary;

  // ── Step 1 ──
  // Strip any library prefix (e.g. "synapchart_builtin.") from the pre-filled
  // block_type_id so that duplicating a built-in block doesn't inherit its
  // namespace — local variants must have a flat, unprefixed ID.
  const rawId = editBlock?.block_type_id ?? '';
  const strippedId = !isEdit && rawId.includes('.') ? rawId.split('.').pop() : rawId;

  const [meta, setMeta] = useState({
    display_name:  editBlock?.display_name  ?? '',
    block_type_id: strippedId,
    // New local blocks always use 'local'; only editable for global blocks.
    category:      editBlock?.category ?? (showCategory ? '' : 'local'),
    description:   editBlock?.description  ?? '',
  });
  const [idWarning, setIdWarning] = useState('');

  // ── Step 2 ──
  const [inputs,  setInputs]  = useState(defToWizardInputs (editBlock?.inputs      ?? []));
  const [outputs, setOutputs] = useState(defToWizardOutputs(editBlock?.outputs     ?? []));
  const [params,  setParams]  = useState(defToWizardParams (editBlock?.parameters  ?? []));

  // ── Step 3 ──
  const [snippet,      setSnippet]      = useState('');
  const [snippetReady, setSnippetReady] = useState(false);
  const [depsText,     setDepsText]     = useState((editBlock?.dependencies ?? []).join('\n'));
  const [testResult,   setTestResult]   = useState(null);
  const [testing,      setTesting]      = useState(false);
  const [saving,       setSaving]       = useState(false);
  const [saveError,    setSaveError]    = useState('');

  // Auto-generate block_type_id from display name (only while field is "clean")
  const handleNameChange = (name) => {
    setMeta(prev => ({
      ...prev,
      display_name: name,
      block_type_id:
        !prev.block_type_id || prev.block_type_id === toId(prev.display_name)
          ? toId(name)
          : prev.block_type_id,
    }));
  };

  // Warn if block_type_id collides with a library block or an existing local block
  useEffect(() => {
    if (isEdit) { setIdWarning(''); return; }
    const inLibrary = !!blockIndex[meta.block_type_id];
    const inLocal   = localBlocks.some(lb => lb.block_type_id === meta.block_type_id);
    setIdWarning(
      (inLibrary || inLocal) && meta.block_type_id
        ? `'${meta.block_type_id}' already exists — saving will overwrite it.`
        : ''
    );
  }, [meta.block_type_id, blockIndex, localBlocks, isEdit]);

  // Load snippet (and dependencies) when entering Step 3
  useEffect(() => {
    if (step !== 3 || snippetReady) return;
    if (isLocalEdit) {
      // Local blocks carry their snippet and dependencies directly.
      setSnippet(editBlock.source_snippet ?? generateTemplate(inputs, outputs, params));
      setDepsText((editBlock.dependencies ?? []).join('\n'));
      setSnippetReady(true);
    } else if (isEdit) {
      getBlockSource(editBlock.block_type_id)
        .then(res => {
          setSnippet(res.source_snippet ?? generateTemplate(inputs, outputs, params));
          setDepsText((res.dependencies ?? []).join('\n'));
        })
        .catch(() => setSnippet(generateTemplate(inputs, outputs, params)))
        .finally(() => setSnippetReady(true));
    } else if (editBlock?.block_type_id && !editBlock?.source_snippet) {
      // New local variant created from a built-in block — fetch the parent's run() body
      // so the variant starts with working code and all necessary imports intact.
      getBlockSource(editBlock.block_type_id)
        .then(res => {
          setSnippet(res.source_snippet ?? generateTemplate(inputs, outputs, params));
          setDepsText((res.dependencies ?? []).join('\n'));
        })
        .catch(() => setSnippet(generateTemplate(inputs, outputs, params)))
        .finally(() => setSnippetReady(true));
    } else {
      // Prefer a pre-supplied snippet (e.g. from a duplicate action) over the template.
      setSnippet(editBlock?.source_snippet ?? generateTemplate(inputs, outputs, params));
      setDepsText((editBlock?.dependencies ?? []).join('\n'));
      setSnippetReady(true);
    }
  }, [step, snippetReady]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTestRun = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await testRunBlock({
        source_snippet: snippet,
        inputs:     inputs.map(i => ({ port_id: i.port_id, data_type: i.data_type })),
        outputs:    outputs.map(o => ({ port_id: o.port_id, data_type: o.data_type })),
        parameters: params.map(p => ({ name: p.name, data_type: p.data_type, default: p.default, enum_values: p.enum_values })),
      });
      setTestResult(res);
    } catch (err) {
      setTestResult({ status: 'error', error_type: 'network', message: err.message });
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaveError('');
    const payload = {
      block_type_id: meta.block_type_id,
      display_name:  meta.display_name,
      category:      meta.category,
      description:   meta.description,
      inputs:     inputs.map(i => ({ port_id: i.port_id, data_type: i.data_type, description: i.description, required: i.required })),
      outputs:    outputs.map(o => ({ port_id: o.port_id, data_type: o.data_type, description: o.description })),
      parameters: params.map(p => ({ name: p.name, data_type: p.data_type, default: p.default, description: p.description, enum_values: p.enum_values })),
      source_snippet: snippet,
      dependencies: depsText.split('\n').map(s => s.trim()).filter(Boolean),
    };
    try {
      if (isLocalEdit) {
        // Editing a workflow-local block — update in-memory only.
        await registerLocalBlocks([payload]);
        updateLocalBlock(payload);
        // Refresh the embedded definition on every canvas node that uses this block.
        const updatedDef = localBlockToDefinition(payload);
        usePipelineStore.setState(state => ({
          nodes: state.nodes.map(n =>
            n.data.block_type_id === payload.block_type_id
              ? { ...n, data: { ...n.data, definition: updatedDef, is_local: true } }
              : n
          ),
        }));
        setDirty(true);
      } else if (isEdit) {
        // Editing an existing global custom block — save to disk and refresh library.
        await updateBlock(meta.block_type_id, payload);
        const data = await getBlocks();
        setBlockLibrary(data.libraries ?? []);
      } else if (saveToLibrary) {
        await createBlock(payload);
        const libData = await getBlocks();
        setBlockLibrary(libData.libraries ?? []);
      } else {
        // New block → workflow-local: register in-memory on backend, store locally,
        // and drop a node directly onto the canvas.
        await registerLocalBlocks([payload]);
        addLocalBlock(payload);

        const definition = localBlockToDefinition(payload);
        const nodeId = `${payload.block_type_id}_${Math.random().toString(36).slice(2, 6)}`;
        const existingCount = usePipelineStore.getState().nodes.length;
        const position = {
          x: 150 + (existingCount % 5) * 220,
          y: 100 + Math.floor(existingCount / 5) * 180,
        };
        const newNode = {
          id:       nodeId,
          type:     'blockNode',
          position,
          data: {
            block_type_id: payload.block_type_id,
            parameters:    Object.fromEntries(payload.parameters.map(p => [p.name, p.default ?? ''])),
            definition,
            is_local: true,
          },
        };
        usePipelineStore.setState(state => ({ nodes: [...state.nodes, newNode] }));
        setDirty(true);
      }
      onClose();
    } catch (err) {
      setSaveError(err.response?.data?.detail?.message ?? err.message);
    } finally {
      setSaving(false);
    }
  };

  // ── Step validation ──
  const step1Valid = meta.display_name.trim() && meta.block_type_id.trim() &&
    (!showCategory || meta.category.trim());
  const step2Valid = true; // ports are optional
  const canSave    = step1Valid && !saving;

  // ── Render ──
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1200,
      background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: '#1f2937', border: '1px solid #374151', borderRadius: 10,
        width: 820, maxHeight: '90vh',
        display: 'flex', flexDirection: 'column',
        color: '#f9fafb', boxShadow: '0 16px 48px rgba(0,0,0,0.7)',
      }}>

        {/* ── Header ── */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', borderBottom: '1px solid #374151' }}>
          <span style={{ fontWeight: 700, fontSize: 15 }}>
            {isEdit
              ? `Edit block: ${editBlock.display_name}`
              : (editBlock ? `Duplicate: ${editBlock.display_name}` : 'New custom block')}
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>

        {/* ── Step indicator ── */}
        <div style={{ display: 'flex', gap: 28, padding: '10px 20px', borderBottom: '1px solid #1e293b', alignItems: 'center' }}>
          <StepDot n={1} label="Metadata"          active={step === 1} done={step > 1} />
          <div style={{ flex: 1, height: 1, background: '#374151' }} />
          <StepDot n={2} label="Ports & parameters" active={step === 2} done={step > 2} />
          <div style={{ flex: 1, height: 1, background: '#374151' }} />
          <StepDot n={3} label="Source code"        active={step === 3} done={false} />
        </div>

        {/* ── Body ── */}
        <div style={{ flex: 1, overflow: 'auto', padding: '18px 24px' }}>

          {/* ══ Step 1: Metadata ══ */}
          {step === 1 && (
            <div style={{ maxWidth: 520 }}>
              <Field label="Block name *">
                <input value={meta.display_name} onChange={e => handleNameChange(e.target.value)}
                  style={iS} placeholder="e.g. Theta cycle detector" autoFocus />
              </Field>

              <Field label="block_type_id *" hint="Unique snake_case identifier">
                <input value={meta.block_type_id}
                  onChange={e => setMeta(m => ({ ...m, block_type_id: e.target.value }))}
                  style={iS} placeholder="e.g. theta_cycle_detector" />
                {idWarning && <div style={{ fontSize: 11, color: '#f59e0b', marginTop: 3 }}>⚠ {idWarning}</div>}
              </Field>

              {showCategory && (
                <Field label="Category *">
                  <input
                    list="wizard-categories"
                    value={meta.category}
                    onChange={e => setMeta(m => ({ ...m, category: e.target.value }))}
                    style={iS}
                    placeholder="Select or type a category"
                  />
                  <datalist id="wizard-categories">
                    {existingCategories.map(c => <option key={c} value={c} />)}
                  </datalist>
                </Field>
              )}

              <Field label="Description">
                <textarea value={meta.description}
                  onChange={e => setMeta(m => ({ ...m, description: e.target.value }))}
                  style={{ ...iS, height: 68, resize: 'vertical' }}
                  placeholder="One or two sentences describing this block." />
              </Field>
            </div>
          )}

          {/* ══ Step 2: Ports & Parameters ══ */}
          {step === 2 && (
            <>
              <PortTable  title="Inputs"     rows={inputs}  setRows={setInputs}  withRequired />
              <PortTable  title="Outputs"    rows={outputs} setRows={setOutputs} />
              <ParamTable params={params} setParams={setParams} />
            </>
          )}

          {/* ══ Step 3: Source Code ══ */}
          {step === 3 && (
            <div style={{ display: 'flex', flexDirection: 'column', height: 520 }}>
              <div style={{ flex: 1, minHeight: 0 }}>
                {!snippetReady
                  ? <div style={{ color: '#6b7280', fontSize: 12, padding: 8 }}>Loading…</div>
                  : <Editor
                      height="100%"
                      defaultLanguage="python"
                      value={snippet}
                      onChange={v => setSnippet(v ?? '')}
                      options={{ minimap: { enabled: false }, fontSize: 12, scrollBeyondLastLine: false, lineNumbers: 'on' }}
                      theme="vs-dark"
                    />
                }
              </div>

              {/* Extra dependencies */}
              <div style={{ marginTop: 10 }}>
                <label style={{ display: 'block', fontSize: 11, color: '#9ca3af', marginBottom: 4 }}>
                  Extra dependencies
                  <span style={{ color: '#4b5563', marginLeft: 6, fontWeight: 400 }}>
                    — pip package names, one per line (e.g. <code style={{ color: '#818cf8' }}>elephant</code>, <code style={{ color: '#818cf8' }}>mne&gt;=1.6</code>)
                  </span>
                </label>
                <textarea
                  value={depsText}
                  onChange={e => setDepsText(e.target.value)}
                  placeholder={'elephant\nmne>=1.6\npynapple'}
                  spellCheck={false}
                  style={{
                    ...iS,
                    height: 64,
                    resize: 'vertical',
                    fontFamily: 'monospace',
                    fontSize: 12,
                  }}
                />
              </div>

              {/* Test result */}
              {testResult && (
                <div style={{
                  marginTop: 8, padding: '8px 12px', borderRadius: 4, fontSize: 12,
                  background: testResult.status === 'ok'
                    ? (testResult.warnings?.length ? '#422006' : '#052e16')
                    : testResult.status === 'warning'
                      ? '#422006'
                      : '#450a0a',
                  border: `1px solid ${
                    testResult.status === 'ok'
                      ? (testResult.warnings?.length ? '#d97706' : '#16a34a')
                      : testResult.status === 'warning'
                        ? '#d97706'
                        : '#dc2626'
                  }`,
                  maxHeight: 160, overflow: 'auto',
                }}>
                  {testResult.status === 'ok' ? (
                    <>
                      <div style={{ color: testResult.warnings?.length ? '#fbbf24' : '#4ade80', fontWeight: 600, marginBottom: 4 }}>
                        {testResult.warnings?.length ? '⚠ Test passed with warnings' : `✓ Test passed  (${testResult.execution_time_ms} ms)`}
                      </div>
                      <div style={{ color: '#d1d5db' }}>
                        {Object.entries(testResult.output_types).map(([k, v]) => (
                          <div key={k}><code>{k}</code> → <code style={{ color: '#818cf8' }}>{v}</code></div>
                        ))}
                        {testResult.warnings?.map((w, i) => <div key={i} style={{ color: '#fbbf24', marginTop: 3 }}>{w}</div>)}
                      </div>
                    </>
                  ) : testResult.status === 'warning' ? (
                    <>
                      <div style={{ color: '#fbbf24', fontWeight: 600, marginBottom: 4 }}>
                        ⚠ Runtime error with dummy data — block can still be saved
                      </div>
                      <div style={{ color: '#fde68a', marginBottom: 4, whiteSpace: 'pre-wrap' }}>{testResult.message}</div>
                      {testResult.traceback && (
                        <pre style={{ fontSize: 10, color: '#fcd34d', margin: 0, whiteSpace: 'pre-wrap' }}>{testResult.traceback}</pre>
                      )}
                    </>
                  ) : (
                    <>
                      <div style={{ color: '#f87171', fontWeight: 600, marginBottom: 4 }}>
                        ✕ {testResult.message}
                      </div>
                      {testResult.traceback && (
                        <pre style={{ fontSize: 10, color: '#fca5a5', margin: 0, whiteSpace: 'pre-wrap' }}>{testResult.traceback}</pre>
                      )}
                    </>
                  )}
                </div>
              )}

              {saveError && (
                <div style={{ marginTop: 6, fontSize: 12, color: '#f87171' }}>⚠ {saveError}</div>
              )}
            </div>
          )}
        </div>

        {/* ── Footer ── */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 20px', borderTop: '1px solid #374151' }}>
          <button onClick={() => step > 1 ? setStep(s => s - 1) : onClose()} style={btn()}>
            {step === 1 ? 'Cancel' : '← Back'}
          </button>

          <div style={{ display: 'flex', gap: 8 }}>
            {step === 3 && (
              <button onClick={handleTestRun} disabled={testing} style={{ ...btn('#0f766e'), opacity: testing ? 0.6 : 1 }}>
                {testing ? 'Testing…' : '▶ Test run'}
              </button>
            )}
            {step < 3 && (
              <button
                onClick={() => setStep(s => s + 1)}
                disabled={step === 1 && !step1Valid}
                style={{ ...btn('#4f46e5'), opacity: (step === 1 && !step1Valid) ? 0.5 : 1 }}
              >
                Next →
              </button>
            )}
            {step === 3 && (
              <button onClick={handleSave} disabled={!canSave} style={{ ...btn('#166534'), opacity: !canSave ? 0.5 : 1 }}>
                {saving ? 'Saving…' : (isEdit ? '✓ Update block' : '✓ Save block')}
              </button>
            )}
          </div>
        </div>

      </div>
    </div>
  );
}

// ─── Helper component ─────────────────────────────────────────────────────────

function Field({ label, hint, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: 'block', fontSize: 12, color: '#9ca3af', marginBottom: 4 }}>
        {label}
        {hint && <span style={{ color: '#4b5563', marginLeft: 6, fontWeight: 400 }}>— {hint}</span>}
      </label>
      {children}
    </div>
  );
}
