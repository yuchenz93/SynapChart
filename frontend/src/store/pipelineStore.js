import { create } from 'zustand';
import { applyNodeChanges, applyEdgeChanges } from 'reactflow';
import { setBreakpoint, clearBreakpoint } from '../api/client';

// ── Tab helpers ───────────────────────────────────────────────────────────────

/** Fields that belong to one workflow tab (everything except blockLibrary/blockIndex). */
function _captureSnapshot(state) {
  return {
    nodes:               state.nodes,
    edges:               state.edges,
    localBlocks:         state.localBlocks,
    compositeBlocks:     state.compositeBlocks,
    currentFilePath:     state.currentFilePath,
    isDirty:             state.isDirty,
    nodeStatuses:        state.nodeStatuses,
    runStatus:           state.runStatus,
    executionOrder:      state.executionOrder,
    undoStack:           state.undoStack,
    consoleMessages:     state.consoleMessages,
    vizResults:          state.vizResults,
    pipelineErrors:      state.pipelineErrors,
    activePopupNodeId:   state.activePopupNodeId,
    compositeEditId:     state.compositeEditId   ?? null,
    compositeMetadata:   state.compositeMetadata ?? null,
    workflowLibraries:   state.workflowLibraries ?? [{ id: 'synapchart_builtin', version: '1.0.0', priority: 1 }],
    missingLibraries:    state.missingLibraries   ?? [],
    libraryConflicts:    state.libraryConflicts   ?? [],
    forwardingRedirects: state.forwardingRedirects ?? [],
    loadedTemplateName:  state.loadedTemplateName  ?? null,
    loadedTemplatePath:  state.loadedTemplatePath  ?? null,
  };
}

function _emptySnapshot() {
  return {
    nodes: [], edges: [], localBlocks: [], compositeBlocks: [],
    currentFilePath: null, isDirty: false,
    nodeStatuses: {}, runStatus: 'idle', executionOrder: [],
    undoStack: [], consoleMessages: [], vizResults: {},
    pipelineErrors: [], activePopupNodeId: null,
    compositeEditId: null,
    compositeMetadata: null,
    workflowLibraries: [{ id: 'synapchart_builtin', version: '1.0.0', priority: 1 }],
    missingLibraries: [],
    libraryConflicts: [],
    forwardingRedirects: [],
    loadedTemplateName: null,
    loadedTemplatePath: null,
  };
}

/** Derive a short display label from a full file path. */
function _fileLabel(filePath) {
  if (!filePath) return null;
  return filePath.replace(/.*[/\\]/, '').replace(/\.[^.]+$/, '') || filePath;
}

let _tabCounter = 1;

/**
 * Converts a workflow JSON node to a React Flow node.
 * @param {object} wfNode - Workflow node from JSON.
 * @returns {object} React Flow node.
 */
export function workflowNodeToRFNode(wfNode) {
  return {
    id: wfNode.node_id,
    type: 'blockNode',
    position: wfNode.position ?? { x: 0, y: 0 },
    data: {
      block_type_id: wfNode.block_type_id,
      parameters:    wfNode.parameters  ?? {},
      portOrder:     wfNode.port_order  ?? undefined,
    },
  };
}

/**
 * Converts a workflow JSON edge to a React Flow edge.
 * @param {object} wfEdge - Workflow edge from JSON.
 * @returns {object} React Flow edge.
 */
export function workflowEdgeToRFEdge(wfEdge) {
  return {
    id:           wfEdge.edge_id,
    type:         'custom',
    source:       wfEdge.source_node_id,
    sourceHandle: wfEdge.source_port_id,
    target:       wfEdge.target_node_id,
    targetHandle: wfEdge.target_port_id,
    data:         wfEdge.data ?? {},
  };
}

/**
 * Converts React Flow nodes/edges back to workflow JSON format.
 * @param {object[]} nodes - React Flow nodes.
 * @param {object[]} edges - React Flow edges.
 * @param {object[]} localBlocks - Local block definitions (CreateBlockRequest format).
 * @param {object[]} compositeBlocks - Embedded composite block snapshots.
 * @returns {object} Workflow JSON object.
 */
export function rfStateToWorkflow(
  nodes,
  edges,
  localBlocks = [],
  compositeBlocks = [],
  workflowLibraries = [{ id: 'synapchart_builtin', version: '1.0.0', priority: 1 }],
) {
  return {
    schema_version:  '2.0',
    libraries:       workflowLibraries,
    local_blocks:    localBlocks,
    composite_blocks: compositeBlocks,
    nodes: nodes.map(n => ({
      node_id:       n.id,
      block_type_id: n.data.block_type_id,
      position:      n.position,
      parameters:    n.data.parameters ?? {},
      // Visual-only: port display order (does not affect execution)
      ...(n.data.portOrder ? { port_order: n.data.portOrder } : {}),
    })),
    edges: edges.map(e => ({
      edge_id:        e.id,
      source_node_id: e.source,
      source_port_id: e.sourceHandle,
      target_node_id: e.target,
      target_port_id: e.targetHandle,
      // Visual-only: edge control-point bend data
      ...(e.data && Object.keys(e.data).length > 0 ? { data: e.data } : {}),
    })),
  };
}

/**
 * Convert a local block definition (workflow JSON / CreateBlockRequest format,
 * using data_type) into the block definition format BlockNode expects (using type).
 * @param {object} lb - Local block definition from local_blocks array.
 * @returns {object} Block definition in BlockNode format.
 */
export function localBlockToDefinition(lb) {
  return {
    block_type_id:  lb.block_type_id,
    display_name:   lb.display_name,
    category:       lb.category || 'local',
    description:    lb.description || '',
    is_custom:      true,
    is_local:       true,
    source_snippet: lb.source_snippet ?? '',
    dependencies:   lb.dependencies   ?? [],
    inputs:  (lb.inputs  ?? []).map(p => ({
      port_id: p.port_id, type: p.data_type, description: p.description ?? '', required: p.required !== false,
    })),
    outputs: (lb.outputs ?? []).map(p => ({
      port_id: p.port_id, type: p.data_type, description: p.description ?? '',
    })),
    parameters: (lb.parameters ?? []).map(p => ({
      name: p.name, type: p.data_type, default: p.default, description: p.description ?? '',
    })),
  };
}

/**
 * Convert a composite block full definition into the format BlockNode/CompositeNode expects.
 * @param {object} cb - Full composite block definition (from composite_blocks array).
 * @returns {object} Block definition in BlockNode format.
 */
export function compositeBlockToDefinition(cb) {
  return {
    block_type_id: cb.block_type_id,
    display_name:  cb.display_name,
    category:      cb.category || 'Composite',
    description:   cb.description || '',
    is_custom:     false,
    is_composite:  true,
    inputs:  (cb.inputs  ?? []).map(p => ({
      port_id: p.port_id, type: p.data_type, description: p.description ?? '', required: true,
    })),
    outputs: (cb.outputs ?? []).map(p => ({
      port_id: p.port_id, type: p.data_type, description: p.description ?? '',
    })),
    parameters: [],
    subflow: cb.subflow,
  };
}

const usePipelineStore = create((set, get) => ({
  // ── Tab management ──────────────────────────────────────────────────────────
  // Each entry: { id, label, filePath, isDirty }
  // The active tab's full state lives at the top level (nodes/edges/…).
  // Inactive tabs are serialised into _snapshots keyed by tab id.
  tabs: [{ id: 'tab_1', label: 'Untitled 1', filePath: null, isDirty: false, compositeEditId: null, templateName: null }],
  activeTabId: 'tab_1',
  _snapshots: {},

  addTab: () => {
    const state = get();
    const snapshot = _captureSnapshot(state);
    const newId = `tab_${Date.now()}`;
    const n = ++_tabCounter;
    set({
      _snapshots: { ...state._snapshots, [state.activeTabId]: snapshot },
      tabs: [...state.tabs, { id: newId, label: `Untitled ${n}`, filePath: null, isDirty: false, compositeEditId: null, templateName: null }],
      activeTabId: newId,
      ..._emptySnapshot(),
    });
  },

  /** Open a composite block's subflow as a fully-editable canvas in a new tab. */
  openCompositeForEdit: (definition) => {
    const state = get();
    const snapshot = _captureSnapshot(state);
    const newId = `tab_${Date.now()}`;
    const subflow = definition.subflow ?? {};

    const localBlocks    = subflow.local_blocks    ?? [];
    const compositeBlocks = subflow.composite_blocks ?? [];

    const localDefMap = {};
    for (const lb of localBlocks) localDefMap[lb.block_type_id] = localBlockToDefinition(lb);
    const compositeDefMap = {};
    for (const cb of compositeBlocks) {
      const def = compositeBlockToDefinition(cb);
      compositeDefMap[cb.block_type_id] = def;
      if (!cb.block_type_id.includes('.')) {
        compositeDefMap[`user_blocks.${cb.block_type_id}`] = def;
      }
    }

    const nodes = (subflow.nodes ?? []).map(wfNode => {
      const rfNode = workflowNodeToRFNode(wfNode);
      const localDef = localDefMap[wfNode.block_type_id];
      if (localDef) { rfNode.data.definition = localDef; rfNode.data.is_local = true; }
      const compositeDef = compositeDefMap[wfNode.block_type_id];
      if (compositeDef) { rfNode.type = 'compositeNode'; rfNode.data.definition = compositeDef; rfNode.data.is_composite = true; }
      return rfNode;
    });
    const edges = (subflow.edges ?? []).map(workflowEdgeToRFEdge);

    set({
      _snapshots: { ...state._snapshots, [state.activeTabId]: snapshot },
      tabs: [...state.tabs, {
        id: newId,
        label: definition.display_name ?? definition.block_type_id,
        filePath: null,
        isDirty: false,
        compositeEditId: definition.block_type_id,
      }],
      activeTabId: newId,
      nodes, edges, localBlocks, compositeBlocks,
      currentFilePath: null, isDirty: false,
      nodeStatuses: {}, runStatus: 'idle', executionOrder: [],
      undoStack: [], consoleMessages: [], vizResults: {},
      pipelineErrors: [], activePopupNodeId: null,
      compositeEditId: definition.block_type_id,
      compositeMetadata: definition,
    });
  },

  switchTab: (id) => {
    const state = get();
    if (id === state.activeTabId) return;
    const snapshot = _captureSnapshot(state);
    const target = state._snapshots[id] ?? _emptySnapshot();
    const newSnapshots = { ...state._snapshots, [state.activeTabId]: snapshot };
    delete newSnapshots[id]; // active state lives at top level, not in snapshots
    set({ _snapshots: newSnapshots, activeTabId: id, ...target });
  },

  closeTab: (id) => {
    const state = get();
    const newTabs = state.tabs.filter(t => t.id !== id);
    const newSnapshots = { ...state._snapshots };
    delete newSnapshots[id];

    if (id !== state.activeTabId) {
      set({ tabs: newTabs, _snapshots: newSnapshots });
      return;
    }

    // Closing the active tab — switch to an adjacent one
    if (newTabs.length === 0) {
      const newId = `tab_${Date.now()}`;
      _tabCounter++;
      set({
        tabs: [{ id: newId, label: 'Untitled 1', filePath: null, isDirty: false, compositeEditId: null }],
        activeTabId: newId,
        _snapshots: {},
        ..._emptySnapshot(),
      });
      return;
    }

    const oldIdx = state.tabs.findIndex(t => t.id === id);
    const nextTab = newTabs[Math.min(oldIdx, newTabs.length - 1)];
    const target = newSnapshots[nextTab.id] ?? _emptySnapshot();
    const finalSnapshots = { ...newSnapshots };
    delete finalSnapshots[nextTab.id];
    set({ tabs: newTabs, _snapshots: finalSnapshots, activeTabId: nextTab.id, ...target });
  },

  // ── Canvas state (fed directly to React Flow) ───────────────────────────────
  nodes: [],
  edges: [],
  setNodes: (updaterOrValue) =>
    typeof updaterOrValue === 'function'
      ? set(state => ({ nodes: updaterOrValue(state.nodes) }))
      : set({ nodes: updaterOrValue }),
  setEdges: (updaterOrValue) =>
    typeof updaterOrValue === 'function'
      ? set(state => ({ edges: updaterOrValue(state.edges) }))
      : set({ edges: updaterOrValue }),
  onNodesChange: (changes) =>
    set(state => ({ nodes: applyNodeChanges(changes, state.nodes) })),
  onEdgesChange: (changes) =>
    set(state => ({ edges: applyEdgeChanges(changes, state.edges) })),

  // Block library (fetched from backend on startup)
  // Shape: [{id, name, version, is_builtin, categories: [{name, blocks:[...]}]}]
  blockLibrary: [],
  // Flat map: block_type_id → definition (rebuilt whenever blockLibrary changes)
  blockIndex: {},
  setBlockLibrary: (libraries) => {
    // libraries can be the new [{id,name,categories}] array from GET /api/blocks/.libraries
    const blockIndex = {};
    for (const lib of (libraries ?? [])) {
      for (const cat of (lib.categories ?? [])) {
        for (const block of (cat.blocks ?? [])) {
          blockIndex[block.block_type_id] = block;
        }
      }
    }
    set({ blockLibrary: libraries ?? [], blockIndex });
  },

  // Libraries declared in the current workflow JSON
  workflowLibraries: [{ id: 'synapchart_builtin', version: '1.0.0', priority: 1 }],
  setWorkflowLibraries: (libs) => set({ workflowLibraries: libs }),

  // Populated from the last load response
  missingLibraries:    [],
  libraryConflicts:    [],
  forwardingRedirects: [],
  setLoadWarnings: ({ missingLibraries = [], libraryConflicts = [], forwardingRedirects = [] } = {}) =>
    set({ missingLibraries, libraryConflicts, forwardingRedirects }),
  clearLoadWarnings: () => set({ missingLibraries: [], libraryConflicts: [], forwardingRedirects: [] }),

  // Workflow-local block definitions (not saved to disk or global registry).
  // Each entry is a CreateBlockRequest-format object (uses data_type, not type).
  localBlocks: [],
  addLocalBlock:    (blockDef) => set(state => ({ localBlocks: [...state.localBlocks, blockDef] })),
  updateLocalBlock: (blockDef) => set(state => ({
    localBlocks: state.localBlocks.map(b => b.block_type_id === blockDef.block_type_id ? blockDef : b),
  })),
  removeLocalBlock: (blockTypeId) => set(state => ({
    localBlocks: state.localBlocks.filter(b => b.block_type_id !== blockTypeId),
  })),

  // Composite block snapshots embedded in this workflow (copy semantics).
  // Each entry is the full composite block JSON definition.
  compositeBlocks: [],
  addCompositeBlock: (definition) => set(state => {
    // If already embedded, update the snapshot; otherwise append.
    const exists = state.compositeBlocks.some(b => b.block_type_id === definition.block_type_id);
    return {
      compositeBlocks: exists
        ? state.compositeBlocks.map(b => b.block_type_id === definition.block_type_id ? definition : b)
        : [...state.compositeBlocks, definition],
    };
  }),
  removeCompositeBlock: (blockTypeId) => set(state => ({
    compositeBlocks: state.compositeBlocks.filter(b => b.block_type_id !== blockTypeId),
  })),

  // Called after a local block is saved to the global library.
  // Strips the is_local flag (and embedded definition) from every canvas node that
  // uses this block so the "local" badge disappears and BlockNode falls back to the
  // global library definition.  The localBlocks entry is intentionally kept so the
  // workflow JSON remains self-contained.
  promoteLocalBlock: (blockTypeId) => set(state => ({
    nodes: state.nodes.map(n => {
      if (n.data.block_type_id !== blockTypeId) return n;
      const { definition: _def, is_local: _loc, ...restData } = n.data;
      return { ...n, data: restData };
    }),
  })),

  // Execution state
  runStatus: 'idle',         // 'idle' | 'running' | 'paused' | 'error' | 'done'
  nodeStatuses: {},          // { node_id: 'pending' | 'running' | 'done' | 'cached' | 'error' }
  executionOrder: [],        // node_ids in topological run order (set by backend plan message)
  setRunStatus: (s) => set({ runStatus: s }),
  setNodeStatus: (id, s) => set(state => ({
    nodeStatuses: { ...state.nodeStatuses, [id]: s },
  })),
  setNodeStatuses: (statuses) => set({ nodeStatuses: statuses }),
  setExecutionOrder: (order) => set({ executionOrder: order }),

  // Visualization results: node_id -> { imageSrc }
  vizResults: {},
  addVizResult: (nodeId, data) => set(state => ({
    vizResults: { ...state.vizResults, [nodeId]: data },
  })),
  removeVizResult: (nodeId) => set(state => {
    const { [nodeId]: _, ...rest } = state.vizResults;
    return { vizResults: rest };
  }),
  clearVizResults: () => set({ vizResults: {} }),

  // Pipeline-level error messages (e.g. validation failures)
  pipelineErrors: [],
  addPipelineError: (msg) => set(state => ({ pipelineErrors: [...state.pipelineErrors, msg] })),
  clearPipelineErrors: () => set({ pipelineErrors: [] }),

  // Currently open popup
  activePopupNodeId: null,
  setActivePopupNodeId: (id) => set({ activePopupNodeId: id }),

  // Composite editor mode (null = normal workflow tab)
  compositeEditId: null,       // block_type_id being edited
  compositeMetadata: null,     // full original definition (ports, metadata)

  // Undo stack for canvas operations (each entry: { nodes, edges } to restore)
  undoStack: [],
  pushUndo: (entry) => set(state => ({ undoStack: [...state.undoStack, entry] })),
  popUndo: () => {
    const stack = get().undoStack;
    if (!stack.length) return null;
    const entry = stack[stack.length - 1];
    set({ undoStack: stack.slice(0, -1) });
    return entry;
  },

  // Console messages
  consoleMessages: [],
  addConsoleMessage: ({ type, text, nodeId = null, traceback = null }) =>
    set(state => ({
      consoleMessages: [
        ...state.consoleMessages,
        {
          id: Math.random().toString(36).slice(2, 9),
          type,   // 'info' | 'success' | 'warning' | 'error'
          timestamp: new Date().toLocaleTimeString('en-US', { hour12: false }),
          text,
          nodeId,
          traceback,
        },
      ],
    })),
  clearConsoleMessages: () => set({ consoleMessages: [] }),

  // Template metadata (per-tab: which built-in template this workflow came from)
  loadedTemplateName: null,
  loadedTemplatePath: null,
  setLoadedTemplateName: (name) => set({ loadedTemplateName: name }),
  setLoadedTemplatePath: (path) => set({ loadedTemplatePath: path }),
  clearTemplateState: () => set({ loadedTemplateName: null, loadedTemplatePath: null }),

  // Workflow file metadata
  currentFilePath: null,
  isDirty: false,            // true if unsaved changes exist
  setCurrentFilePath: (p) => set(state => ({
    currentFilePath: p,
    tabs: state.tabs.map(t => t.id === state.activeTabId
      ? { ...t, filePath: p, label: _fileLabel(p) ?? t.label }
      : t
    ),
  })),
  setActiveTabLabel: (label) => set(state => ({
    tabs: state.tabs.map(t =>
      t.id === state.activeTabId ? { ...t, label } : t
    ),
  })),
  setActiveTabTemplateName: (name) => set(state => ({
    tabs: state.tabs.map(t =>
      t.id === state.activeTabId ? { ...t, templateName: name } : t
    ),
  })),
  setDirty: (v) => set(state => ({
    isDirty: v,
    tabs: state.tabs.map(t => t.id === state.activeTabId ? { ...t, isDirty: v } : t),
  })),

  // Load a full workflow JSON into the canvas state.
  // Accepts an optional loadMeta object with {missing_libraries, conflicts, forwarding_redirects}
  // from the POST /api/files/load response.
  loadWorkflowIntoStore: (workflow, loadMeta = {}) => {
    const localBlocks     = workflow.local_blocks ?? [];
    const compositeBlocks = workflow.composite_blocks ?? [];
    const workflowLibraries = workflow.libraries ?? [{ id: 'synapchart_builtin', version: '1.0.0', priority: 1 }];

    const localDefMap = {};
    for (const lb of localBlocks) {
      localDefMap[lb.block_type_id] = localBlockToDefinition(lb);
    }
    const compositeDefMap = {};
    for (const cb of compositeBlocks) {
      const def = compositeBlockToDefinition(cb);
      compositeDefMap[cb.block_type_id] = def;
      // Nodes reference composites as "user_blocks.<id>" but composite_blocks
      // stores them without the namespace prefix — index both so the lookup works.
      if (!cb.block_type_id.includes('.')) {
        compositeDefMap[`user_blocks.${cb.block_type_id}`] = def;
      }
    }
    const nodes = (workflow.nodes ?? []).map(wfNode => {
      const rfNode = workflowNodeToRFNode(wfNode);
      const localDef = localDefMap[wfNode.block_type_id];
      if (localDef) {
        rfNode.data.definition = localDef;
        rfNode.data.is_local   = true;
      }
      const compositeDef = compositeDefMap[wfNode.block_type_id];
      if (compositeDef) {
        rfNode.type              = 'compositeNode';
        rfNode.data.definition   = compositeDef;
        rfNode.data.is_composite = true;
      }
      return rfNode;
    });
    const edges = (workflow.edges ?? []).map(workflowEdgeToRFEdge);
    set(state => ({
      nodes, edges, localBlocks, compositeBlocks,
      workflowLibraries,
      missingLibraries:    loadMeta.missingLibraries    ?? [],
      libraryConflicts:    loadMeta.libraryConflicts    ?? [],
      forwardingRedirects: loadMeta.forwardingRedirects ?? [],
      nodeStatuses: {}, runStatus: 'idle', isDirty: false, undoStack: [],
      tabs: state.tabs.map(t => t.id === state.activeTabId ? { ...t, isDirty: false } : t),
    }));
  },

  // Serialize current canvas state to workflow JSON
  serializeWorkflow: () => {
    const { nodes, edges, localBlocks, compositeBlocks, workflowLibraries } = get();
    return rfStateToWorkflow(nodes, edges, localBlocks, compositeBlocks, workflowLibraries);
  },

  // ── Debugger state (session-global, not per workflow-tab) ─────────────────

  // node_ids that have a breakpoint set (session-only, not saved to workflow JSON)
  breakpointNodeIds: new Set(),
  // true while execution is paused at a breakpoint
  isPaused: false,
  pausedAtNodeId: null,
  // { node_id: [variable summary objects] } populated on breakpoint_hit
  workspaceData: {},
  // which console tab is active: 'logs' | 'workspace'
  activeConsoleTab: 'logs',

  toggleBreakpoint: (nodeId) => set(state => {
    const next = new Set(state.breakpointNodeIds);
    if (next.has(nodeId)) {
      next.delete(nodeId);
      clearBreakpoint(nodeId).catch(() => {});
    } else {
      next.add(nodeId);
      setBreakpoint(nodeId).catch(() => {});
    }
    return { breakpointNodeIds: next };
  }),

  setPaused: (paused, nodeId = null) => set({
    isPaused: paused,
    pausedAtNodeId: nodeId,
  }),

  setWorkspaceNodeData: (nodeId, variables) => set(state => ({
    workspaceData: { ...state.workspaceData, [nodeId]: variables },
  })),

  clearWorkspace: () => set({ workspaceData: {}, isPaused: false, pausedAtNodeId: null }),

  setActiveConsoleTab: (tab) => set({ activeConsoleTab: tab }),
}));

export default usePipelineStore;
