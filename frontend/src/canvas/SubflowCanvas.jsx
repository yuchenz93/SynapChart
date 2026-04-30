/**
 * SubflowCanvas — a full React Flow canvas for viewing and editing a
 * composite block's internal subflow.
 *
 * Features:
 *  - Renders all subflow nodes and edges as a proper graph
 *  - Nodes are draggable for layout adjustment (positions are in-memory only)
 *  - Double-click a node to edit its parameters
 *  - Parameter changes are propagated to the host canvas via onParamsChange
 *  - No topology editing (connections / add-remove nodes are locked)
 */

import { useState, useCallback, useMemo } from 'react';
import ReactFlow, {
  Controls, Background, MiniMap,
  useNodesState, useEdgesState,
} from 'reactflow';
import 'reactflow/dist/style.css';
import BlockNode from './BlockNode';
import CompositeNode from './CompositeNode';
import { CanvasContext } from './CanvasContext';
import usePipelineStore, { localBlockToDefinition, compositeBlockToDefinition } from '../store/pipelineStore';
import FileBrowser from '../modals/FileBrowser';

// ── Node types ────────────────────────────────────────────────────────────────

const nodeTypes = { blockNode: BlockNode, compositeNode: CompositeNode };

// ── Neutral canvas context ────────────────────────────────────────────────────
// Disables click-to-connect and drill-in re-entry; nodes display in view-only mode.
const EMPTY_CTX = { pendingConnection: null, handlePortClick: null, onDrillIn: null };

// ── Helpers ───────────────────────────────────────────────────────────────────

function resolveDefinition(blockTypeId, blockLibrary, localBlocks, compositeBlocks, subflowLocalBlocks) {
  // Priority: subflow-embedded local blocks → workflow local blocks → global library → composites
  const sll = subflowLocalBlocks?.find(b => b.block_type_id === blockTypeId);
  if (sll) return localBlockToDefinition(sll);

  const lb = localBlocks.find(b => b.block_type_id === blockTypeId);
  if (lb) return localBlockToDefinition(lb);

  for (const cat of blockLibrary) {
    const found = cat.blocks?.find(b => b.block_type_id === blockTypeId);
    if (found) return found;
  }

  const cb = compositeBlocks.find(b => b.block_type_id === blockTypeId);
  if (cb) return compositeBlockToDefinition(cb);

  return null;
}

/**
 * Simple topological left-to-right auto-layout.
 * Used when all saved positions are identical (e.g. all at the origin).
 */
function autoLayout(rfNodes, rfEdges) {
  const inDegree = Object.fromEntries(rfNodes.map(n => [n.id, 0]));
  const adj = Object.fromEntries(rfNodes.map(n => [n.id, []]));

  rfEdges.forEach(e => {
    if (e.target in inDegree) inDegree[e.target]++;
    if (e.source in adj) adj[e.source].push(e.target);
  });

  // BFS column assignment
  const colOf = {};
  let queue = rfNodes.filter(n => inDegree[n.id] === 0).map(n => n.id);
  // Guard: if all nodes have incoming edges (cycle / disconnected) add everything
  if (queue.length === 0) queue = rfNodes.map(n => n.id);

  let col = 0;
  const remaining = new Set(rfNodes.map(n => n.id));
  while (queue.length > 0) {
    const next = [];
    queue.forEach(id => {
      if (!(id in colOf)) {
        colOf[id] = col;
        remaining.delete(id);
        adj[id].forEach(nxt => {
          inDegree[nxt]--;
          if (inDegree[nxt] === 0) next.push(nxt);
        });
      }
    });
    col++;
    queue = next;
    // Safety: if next is empty but remaining is not (disconnected nodes), seed remaining
    if (next.length === 0 && remaining.size > 0) {
      queue = [...remaining];
    }
  }

  // Assign rows within each column
  const colNodes = {};
  rfNodes.forEach(n => {
    const c = colOf[n.id] ?? 0;
    (colNodes[c] = colNodes[c] ?? []).push(n.id);
  });

  const COL_W = 260;
  const ROW_H = 130;

  return rfNodes.map(n => {
    const c = colOf[n.id] ?? 0;
    const row = (colNodes[c] ?? [n.id]).indexOf(n.id);
    return { ...n, position: { x: c * COL_W + 40, y: row * ROW_H + 40 } };
  });
}

function subflowToRF(subflow, blockLibrary, localBlocks, compositeBlocks) {
  const subflowLocalBlocks = subflow.local_blocks ?? [];

  let rfNodes = (subflow.nodes ?? []).map(n => {
    const def = resolveDefinition(n.block_type_id, blockLibrary, localBlocks, compositeBlocks, subflowLocalBlocks);
    const isComposite = def?.is_composite ?? false;
    return {
      id: n.node_id,
      type: isComposite ? 'compositeNode' : 'blockNode',
      position: n.position ?? { x: 0, y: 0 },
      data: {
        block_type_id: n.block_type_id,
        parameters: { ...(n.parameters ?? {}) },
        definition: def,
        is_composite: isComposite,
      },
    };
  });

  // If all positions are identical (e.g. all at origin), apply auto-layout
  const positions = rfNodes.map(n => `${n.position.x},${n.position.y}`);
  const allSame = positions.length > 1 && new Set(positions).size === 1;
  if (allSame || rfNodes.every(n => n.position.x === 0 && n.position.y === 0)) {
    rfNodes = autoLayout(rfNodes, rfEdgesFromSubflow(subflow));
  }

  const rfEdges = rfEdgesFromSubflow(subflow);
  return { rfNodes, rfEdges };
}

function rfEdgesFromSubflow(subflow) {
  return (subflow.edges ?? []).map((e, i) => ({
    id: e.edge_id ?? `sf_e_${i}`,
    source: e.source_node_id,
    sourceHandle: e.source_port_id,
    target: e.target_node_id,
    targetHandle: e.target_port_id,
    style: { stroke: '#4b5563', strokeWidth: 1.5 },
  }));
}

// ── SubflowParamEditor — inline parameter editing popup ───────────────────────

const inputStyle = {
  background: '#111827',
  border: '1px solid #374151',
  borderRadius: 3,
  color: '#f9fafb',
  padding: '4px 8px',
  fontSize: 12,
  width: '100%',
  boxSizing: 'border-box',
};

function SubflowParamEditor({ node, onSave, onClose }) {
  const definition = node.data.definition;
  const paramDefs  = definition?.parameters ?? [];

  const [params, setParams] = useState({ ...(node.data.parameters ?? {}) });
  const [fileBrowserParam, setFileBrowserParam] = useState(null);

  const update = (name, val) => setParams(prev => ({ ...prev, [name]: val }));

  const renderField = (param) => {
    const val = params[param.name] ?? param.default ?? '';

    if (param.type === 'bool') {
      return (
        <input
          type="checkbox"
          checked={!!val}
          onChange={e => update(param.name, e.target.checked)}
          style={{ cursor: 'pointer' }}
        />
      );
    }
    if (param.type === 'float' || param.type === 'int') {
      return (
        <input
          type="number"
          value={val}
          step={param.type === 'float' ? 'any' : 1}
          onChange={e => update(param.name, param.type === 'float' ? parseFloat(e.target.value) : parseInt(e.target.value, 10))}
          style={inputStyle}
        />
      );
    }
    if (Array.isArray(param.enum)) {
      return (
        <select value={val} onChange={e => update(param.name, e.target.value)} style={inputStyle}>
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
          <input
            type="text"
            value={val}
            onChange={e => update(param.name, e.target.value)}
            style={{ ...inputStyle, flex: 1 }}
          />
          <button
            onClick={() => setFileBrowserParam(param.name)}
            style={{
              background: '#374151', border: 'none', borderRadius: 3,
              color: '#d1d5db', padding: '4px 8px', cursor: 'pointer', fontSize: 11,
            }}
          >
            Browse…
          </button>
        </div>
      );
    }

    return (
      <input
        type="text"
        value={val}
        onChange={e => update(param.name, e.target.value)}
        style={inputStyle}
      />
    );
  };

  return (
    <>
      {fileBrowserParam && (
        <FileBrowser
          initialPath={params[fileBrowserParam] ?? ''}
          onSelect={(path) => {
            update(fileBrowserParam, path);
            setFileBrowserParam(null);
          }}
          onClose={() => setFileBrowserParam(null)}
        />
      )}

      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'absolute', inset: 0,
          background: 'rgba(0,0,0,0.45)', zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        <div
          onClick={e => e.stopPropagation()}
          style={{
            background: '#1f2937', border: '1px solid #374151',
            borderRadius: 8, width: 500, maxHeight: '70vh',
            display: 'flex', flexDirection: 'column',
            color: '#f9fafb', boxShadow: '0 8px 32px rgba(0,0,0,0.7)',
          }}
        >
          {/* Header */}
          <div style={{
            display: 'flex', alignItems: 'center',
            justifyContent: 'space-between',
            padding: '10px 14px', borderBottom: '1px solid #374151',
          }}>
            <div>
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                {definition?.display_name ?? node.data.block_type_id}
              </span>
              <span style={{
                marginLeft: 8, fontSize: 10, color: '#6b7280',
                background: '#111827', borderRadius: 3, padding: '1px 6px',
              }}>
                {node.id}
              </span>
            </div>
            <button
              onClick={onClose}
              style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: 16 }}
            >
              ✕
            </button>
          </div>

          {/* Body */}
          <div style={{ flex: 1, overflow: 'auto', padding: 14 }}>
            {paramDefs.length === 0 ? (
              <p style={{ color: '#6b7280', fontSize: 12, margin: 0 }}>
                This block has no configurable parameters.
              </p>
            ) : (
              paramDefs.map(param => (
                <div key={param.name} style={{ marginBottom: 12 }}>
                  <label
                    title={param.description}
                    style={{ display: 'block', fontSize: 11, color: '#9ca3af', marginBottom: 3 }}
                  >
                    {param.name}
                    {param.description && <span style={{ marginLeft: 5, cursor: 'help' }}>ⓘ</span>}
                  </label>
                  {renderField(param)}
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div style={{
            padding: '10px 14px', borderTop: '1px solid #374151',
            display: 'flex', justifyContent: 'flex-end', gap: 8,
          }}>
            <button
              onClick={onClose}
              style={{
                background: '#374151', border: 'none', borderRadius: 4,
                color: '#d1d5db', padding: '6px 14px', cursor: 'pointer', fontSize: 12,
              }}
            >
              Cancel
            </button>
            <button
              onClick={() => onSave(params)}
              style={{
                background: '#166534', border: 'none', borderRadius: 4,
                color: '#f0fdf4', padding: '6px 14px', cursor: 'pointer', fontSize: 12,
                fontWeight: 600,
              }}
            >
              ✓ Apply
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

// ── SubflowCanvas — main export ───────────────────────────────────────────────

/**
 * Full React Flow canvas for a composite block's subflow.
 *
 * @param {object} props
 * @param {object} props.definition    — Full composite block definition (includes .subflow).
 * @param {function} props.onParamsChange(subflowNodeId, newParams) — Called when a node's params are saved.
 */
export default function SubflowCanvas({ definition, onParamsChange }) {
  const { blockLibrary, localBlocks, compositeBlocks } = usePipelineStore();

  // Convert once on mount; after that node dragging is handled locally by useNodesState
  const { rfNodes: initNodes, rfEdges: initEdges } = useMemo(
    () => subflowToRF(definition.subflow ?? {}, blockLibrary, localBlocks, compositeBlocks),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes);
  const [edges, , onEdgesChange] = useEdgesState(initEdges);

  const [editingNodeId, setEditingNodeId] = useState(null);
  const editingNode = nodes.find(n => n.id === editingNodeId) ?? null;

  const onNodeDoubleClick = useCallback((_evt, node) => {
    setEditingNodeId(node.id);
  }, []);

  const handleSaveParams = useCallback((newParams) => {
    // Update the RF node so re-opening the editor shows the new values
    setNodes(nds => nds.map(n =>
      n.id === editingNodeId ? { ...n, data: { ...n.data, parameters: newParams } } : n
    ));
    onParamsChange(editingNodeId, newParams);
    setEditingNodeId(null);
  }, [editingNodeId, onParamsChange, setNodes]);

  if (!definition?.subflow) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#6b7280', fontSize: 13 }}>
        No subflow data available for this composite block.
      </div>
    );
  }

  return (
    <CanvasContext.Provider value={EMPTY_CTX}>
      <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeDoubleClick={onNodeDoubleClick}
          nodesConnectable={false}
          deleteKeyCode={null}
          fitView
          fitViewOptions={{ padding: 0.15 }}
        >
          <Controls />
          <Background variant="dots" />
          <MiniMap />
        </ReactFlow>

        {/* Hint overlay */}
        <div style={{
          position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)',
          background: 'rgba(17,24,39,0.85)', border: '1px solid #374151',
          borderRadius: 4, padding: '3px 10px',
          fontSize: 10, color: '#6b7280', pointerEvents: 'none', zIndex: 10,
        }}>
          Double-click a node to edit its parameters · Connections are read-only
        </div>

        {/* Parameter editor popup */}
        {editingNode && (
          <SubflowParamEditor
            node={editingNode}
            onSave={handleSaveParams}
            onClose={() => setEditingNodeId(null)}
          />
        )}
      </div>
    </CanvasContext.Provider>
  );
}
