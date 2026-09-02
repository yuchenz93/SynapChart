import { useCallback, useRef, useEffect, useLayoutEffect, useState } from 'react';
import ReactFlow, {
  MiniMap,
  Controls,
  Background,
  addEdge,
} from 'reactflow';
import 'reactflow/dist/style.css';
import BlockNode from './BlockNode';
import CompositeNode from './CompositeNode';
import CustomEdge from './CustomEdge';
import SubflowCanvas from './SubflowCanvas';
import BlockWizard from '../modals/BlockWizard';
import PackagingWizard from '../modals/PackagingWizard';
import { CanvasContext, isCompatible } from './CanvasContext';
import usePipelineStore, { localBlockToDefinition, compositeBlockToDefinition } from '../store/pipelineStore';
import { validateConnection, clearCache, createBlock, getBlocks, getBlockSource, getCompositeBlock } from '../api/client';

const nodeTypes = { blockNode: BlockNode, compositeNode: CompositeNode };
const edgeTypes = { custom: CustomEdge };

/**
 * Main React Flow canvas.
 *
 * Handles:
 *  - Drag-drop from side panel
 *  - Connection validation (drag-to-connect + click-to-connect)
 *  - Pending connection SVG overlay (click-to-connect wire)
 *  - Node and edge selection, deletion, right-click menus
 *  - Keyboard shortcuts: Delete/Backspace, Ctrl+Z, Escape
 *  - Local-block promotion to global library
 */
export default function Canvas() {
  const {
    nodes, edges,
    setEdges,
    onNodesChange, onEdgesChange,
    setActivePopupNodeId,
    setDirty,
    pushUndo, popUndo,
    setBlockLibrary,
    promoteLocalBlock,
    addCompositeBlock,
    activeTabId,
    breakpointNodeIds,
    toggleBreakpoint,
  } = usePipelineStore();

  const reactFlowWrapper = useRef(null);
  const [reactFlowInstance, setReactFlowInstance] = usePipelineStore(
    s => [s.rfInstance, s.setRfInstance ?? (() => {})]
  );

  // Node context menu: { x, y, nodeId, isLocal } | null
  const [contextMenu, setContextMenu] = useState(null);
  const contextMenuRef = useRef(null);

  // Edge context menu: { x, y, edgeId } | null
  const [edgeContextMenu, setEdgeContextMenu] = useState(null);
  const edgeContextMenuRef = useRef(null);

  // Flip context menus toward screen center when they'd extend off-screen
  useLayoutEffect(() => {
    if (!contextMenuRef.current || !contextMenu) return;
    const rect = contextMenuRef.current.getBoundingClientRect();
    let { x, y } = contextMenu;
    if (rect.bottom > window.innerHeight) y = Math.max(0, window.innerHeight - rect.height - 4);
    if (rect.right  > window.innerWidth)  x = Math.max(0, window.innerWidth  - rect.width  - 4);
    if (x !== contextMenu.x || y !== contextMenu.y) setContextMenu(m => ({ ...m, x, y }));
  }, [contextMenu]);

  useLayoutEffect(() => {
    if (!edgeContextMenuRef.current || !edgeContextMenu) return;
    const rect = edgeContextMenuRef.current.getBoundingClientRect();
    let { x, y } = edgeContextMenu;
    if (rect.bottom > window.innerHeight) y = Math.max(0, window.innerHeight - rect.height - 4);
    if (rect.right  > window.innerWidth)  x = Math.max(0, window.innerWidth  - rect.width  - 4);
    if (x !== edgeContextMenu.x || y !== edgeContextMenu.y) setEdgeContextMenu(m => ({ ...m, x, y }));
  }, [edgeContextMenu]);

  // Pending connection (click-to-connect):
  // { sourceNodeId, sourcePortId, sourcePortType, sx, sy } | null
  const [pendingConnection, setPendingConnection] = useState(null);
  const pendingRef = useRef(null); // mirror of pendingConnection, always current in closures

  // Cursor position relative to the canvas wrapper (for the pending wire endpoint)
  const [cursorPos, setCursorPos] = useState(null);

  // BlockWizard opened from the canvas (local-block editing only)
  const [wizardEditBlock, setWizardEditBlock] = useState(null);

  // Packaging wizard state
  const [showPackagingWizard, setShowPackagingWizard] = useState(false);

  // Drill-in tabs: [{ id, label, definition }]
  // 'main' is the always-present root tab.
  const [drillTabs, setDrillTabs] = useState([]);
  // Currently active tab: 'main' | node_id of composite block
  const [activeTab, setActiveTab] = useState('main');

  // Reset drill-in state whenever the user switches workflow tabs
  useEffect(() => {
    setDrillTabs([]);
    setActiveTab('main');
  }, [activeTabId]);

  // Toast notification
  const [toast, setToast] = useState(null);
  const toastTimer = useRef(null);

  const showToast = useCallback((message) => {
    clearTimeout(toastTimer.current);
    setToast(message);
    toastTimer.current = setTimeout(() => setToast(null), 3500);
  }, []);

  // Keep the ref in sync with state so async callbacks and effects read the latest value
  useEffect(() => { pendingRef.current = pendingConnection; }, [pendingConnection]);

  // ── Cancel pending connection ────────────────────────────────────────────
  const cancelPending = useCallback(() => {
    setPendingConnection(null);
    setCursorPos(null);
  }, []);

  // ── Close context menus on outside click ─────────────────────────────────
  useEffect(() => {
    if (!contextMenu && !edgeContextMenu) return;
    const handler = (e) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(e.target)) {
        setContextMenu(null);
      }
      if (edgeContextMenuRef.current && !edgeContextMenuRef.current.contains(e.target)) {
        setEdgeContextMenu(null);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [contextMenu, edgeContextMenu]);

  // ── Cursor tracking for pending wire — active only while connecting ───────
  const hasPending = pendingConnection !== null;
  useEffect(() => {
    if (!hasPending) return;
    const onMove = (e) => {
      const wrapperRect = reactFlowWrapper.current?.getBoundingClientRect();
      if (!wrapperRect) return;
      setCursorPos({
        x: e.clientX - wrapperRect.left,
        y: e.clientY - wrapperRect.top,
      });
    };
    document.addEventListener('mousemove', onMove);
    return () => document.removeEventListener('mousemove', onMove);
  }, [hasPending]);

  // ── Delete node(s) by ID ─────────────────────────────────────────────────
  const deleteNodes = useCallback((nodeIds) => {
    const { nodes: allNodes, edges: allEdges } = usePipelineStore.getState();
    const deletedNodes = allNodes.filter(n => nodeIds.includes(n.id));
    const deletedEdges = allEdges.filter(
      e => nodeIds.includes(e.source) || nodeIds.includes(e.target)
    );
    if (deletedNodes.length === 0) return;

    pushUndo({ nodes: deletedNodes, edges: deletedEdges });

    usePipelineStore.setState(state => ({
      nodes: state.nodes.filter(n => !nodeIds.includes(n.id)),
      edges: state.edges.filter(
        e => !nodeIds.includes(e.source) && !nodeIds.includes(e.target)
      ),
    }));
    setDirty(true);
    setContextMenu(null);
    clearCache().catch(() => {});
  }, [pushUndo, setDirty]);

  // ── Delete edge(s) by ID ─────────────────────────────────────────────────
  const deleteEdges = useCallback((edgeIds) => {
    usePipelineStore.setState(state => ({
      edges: state.edges.filter(e => !edgeIds.includes(e.id)),
    }));
    setDirty(true);
    setEdgeContextMenu(null);
  }, [setDirty]);

  // ── Save local block to global library ────────────────────────────────────
  const saveToLibrary = useCallback(async (nodeId) => {
    setContextMenu(null);
    const { nodes: allNodes, localBlocks } = usePipelineStore.getState();
    const node = allNodes.find(n => n.id === nodeId);
    if (!node) return;
    const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
    if (!lb) return;

    try {
      await createBlock(lb);
      const data = await getBlocks();
      setBlockLibrary(data.libraries ?? []);
      promoteLocalBlock(lb.block_type_id);
      showToast('Block saved to library. Workflow remains self-contained.');
      usePipelineStore.getState().addConsoleMessage({
        type: 'success',
        text: `Block saved to library. Workflow remains self-contained.`,
      });
    } catch (err) {
      const msg = err.response?.data?.detail?.message ?? err.message;
      usePipelineStore.getState().addConsoleMessage({
        type: 'error',
        text: `Failed to save block to library: ${msg}`,
      });
      alert(`Failed to save block to library: ${msg}`);
    }
  }, [setBlockLibrary, promoteLocalBlock, showToast]);

  // ── Open BlockWizard for editing a local block ───────────────────────────
  const openLocalEdit = useCallback((nodeId) => {
    setContextMenu(null);
    const { nodes: allNodes, localBlocks } = usePipelineStore.getState();
    const node = allNodes.find(n => n.id === nodeId);
    if (!node) return;
    const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
    if (!lb) return;
    setWizardEditBlock({ ...localBlockToDefinition(lb), source_snippet: lb.source_snippet });
  }, []);

  // ── Duplicate node: same block type + same params, placed offset ──────────
  const duplicateNode = useCallback((nodeId) => {
    setContextMenu(null);
    const { nodes: allNodes } = usePipelineStore.getState();
    const node = allNodes.find(n => n.id === nodeId);
    if (!node) return;
    const newNode = {
      ...node,
      id: `${node.data.block_type_id}_${Math.random().toString(36).slice(2, 6)}`,
      position: { x: node.position.x + 30, y: node.position.y + 30 },
      selected: false,
    };
    usePipelineStore.setState(state => ({ nodes: [...state.nodes, newNode] }));
    usePipelineStore.getState().setDirty(true);
  }, []);

  // ── Create local variant: opens wizard pre-filled, saves as new local block ─
  const createLocalVariant = useCallback(async (nodeId) => {
    setContextMenu(null);
    const { nodes: allNodes, localBlocks, blockIndex } = usePipelineStore.getState();
    const node = allNodes.find(n => n.id === nodeId);
    if (!node) return;

    // Local block: definition + snippet are already in store
    const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
    if (lb) {
      setWizardEditBlock({
        ...localBlockToDefinition(lb),
        is_custom:      false,
        source_snippet: lb.source_snippet ?? null,
        display_name:   `${lb.display_name} (variant)`,
        block_type_id:  `${lb.block_type_id}_variant`,
      });
      return;
    }

    // Global block: look up definition and fetch source snippet
    const def = blockIndex[node.data.block_type_id] ?? null;
    if (!def) return;
    try {
      const res = await getBlockSource(node.data.block_type_id);
      setWizardEditBlock({
        ...def,
        is_custom:      false,
        source_snippet: res.source_snippet ?? null,
        display_name:   `${def.display_name} (variant)`,
        block_type_id:  `${def.block_type_id}_variant`,
      });
    } catch (err) {
      alert(`Could not load block source: ${err.message}`);
    }
  }, []);

  // ── Drill-in: open subflow in a nested tab ───────────────────────────────
  const onDrillIn = useCallback((nodeId, definition) => {
    if (!definition?.subflow) return;
    setDrillTabs(tabs => {
      if (tabs.find(t => t.id === nodeId)) return tabs;
      return [...tabs, { id: nodeId, label: definition.display_name ?? nodeId, definition }];
    });
    setActiveTab(nodeId);
  }, []);

  const closeDrillTab = useCallback((tabId) => {
    setDrillTabs(tabs => tabs.filter(t => t.id !== tabId));
    setActiveTab(prev => prev === tabId ? 'main' : prev);
  }, []);

  // ── Subflow parameter change: propagate to host canvas node ──────────────
  const onSubflowParamsChange = useCallback((subflowNodeId, newParams) => {
    setDrillTabs(tabs => tabs.map(t => {
      if (t.id !== activeTab) return t;

      // Update the parameter in the subflow's node list
      const updatedSubflowNodes = (t.definition.subflow?.nodes ?? []).map(n =>
        n.node_id === subflowNodeId ? { ...n, parameters: newParams } : n
      );
      const updatedDefinition = {
        ...t.definition,
        subflow: { ...t.definition.subflow, nodes: updatedSubflowNodes },
      };

      // Update the composite node in the main canvas
      usePipelineStore.setState(state => ({
        nodes: state.nodes.map(n =>
          n.id === activeTab
            ? { ...n, data: { ...n.data, definition: updatedDefinition } }
            : n
        ),
      }));
      usePipelineStore.getState().setDirty(true);

      return { ...t, definition: updatedDefinition };
    }));
  }, [activeTab]);

  // ── Port click handler (click-to-connect) ────────────────────────────────
  const handlePortClick = useCallback(async (event, nodeId, portId, portType, direction) => {
    const pending = pendingRef.current;

    if (direction === 'source') {
      if (pending?.sourceNodeId === nodeId && pending?.sourcePortId === portId) {
        // Clicking the same source port again → cancel
        cancelPending();
      } else {
        // Start a new pending connection from this output port
        const wrapperRect = reactFlowWrapper.current?.getBoundingClientRect();
        const handleRect = event.currentTarget.getBoundingClientRect();
        const sx = handleRect.left + handleRect.width / 2 - (wrapperRect?.left ?? 0);
        const sy = handleRect.top + handleRect.height / 2 - (wrapperRect?.top ?? 0);
        setPendingConnection({ sourceNodeId: nodeId, sourcePortId: portId, sourcePortType: portType, sx, sy });
        setCursorPos({ x: sx, y: sy });
      }
      return;
    }

    // direction === 'target': attempt to complete the pending connection
    if (!pending) return;

    // Prevent connecting a node to itself
    if (pending.sourceNodeId === nodeId) {
      cancelPending();
      return;
    }

    // Reject if the input port already has a connection
    const { edges: currentEdges } = usePipelineStore.getState();
    if (currentEdges.some(e => e.target === nodeId && e.targetHandle === portId)) {
      cancelPending();
      return;
    }

    const connection = {
      id: `e_${Math.random().toString(36).slice(2, 9)}`,
      type: 'custom',
      source: pending.sourceNodeId,
      sourceHandle: pending.sourcePortId,
      target: nodeId,
      targetHandle: portId,
    };

    cancelPending();

    let edgeData = {};
    try {
      const srcType = pending.sourcePortType ?? 'NeuroData[any]';
      const tgtType = portType ?? 'NeuroData[any]';
      const res = await validateConnection(srcType, tgtType);
      const { nodes: allNodes, blockIndex, localBlocks } = usePipelineStore.getState();

      const resolveName = (nid) => {
        const node = allNodes.find(n => n.id === nid);
        if (!node) return nid;
        const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
        if (lb) return lb.display_name;
        return blockIndex[node.data.block_type_id]?.display_name ?? node.data.block_type_id;
      };

      const srcName = resolveName(pending.sourceNodeId);
      const tgtName = resolveName(nodeId);

      // ERROR (structural) is blocked; WARN (role mismatch) is allowed and
      // flagged with a persisted ⚠ badge on the edge (Port Types v2).
      if (!res.data.valid) {
        usePipelineStore.getState().addConsoleMessage({
          type: 'error',
          text: `Connection rejected: ${srcName} → ${tgtName} — ${res.data.message}`,
        });
        return;
      }

      if (res.data.status === 'warn') {
        edgeData = { warn: true, warnMsg: res.data.message };
        usePipelineStore.getState().addConsoleMessage({
          type: 'warning',
          text: `Connected with warning: ${srcName} → ${tgtName} — ${res.data.message}`,
        });
      } else {
        usePipelineStore.getState().addConsoleMessage({
          type: 'info',
          text: `Connected: ${srcName} → ${tgtName}`,
        });
      }
    } catch {
      // Allow connection if validation endpoint is unreachable during development
    }

    setEdges(eds => addEdge({ ...connection, data: edgeData }, eds));
    setDirty(true);
  }, [cancelPending, setEdges, setDirty]);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  useEffect(() => {
    const isEditableTarget = (el) =>
      ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable;

    const handler = (e) => {
      if (isEditableTarget(e.target)) return;

      // Escape → cancel pending connection
      if (e.key === 'Escape') {
        if (pendingRef.current) {
          e.preventDefault();
          cancelPending();
        }
        return;
      }

      // Delete / Backspace → delete selected nodes and/or edges
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const state = usePipelineStore.getState();
        const selectedNodes = state.nodes.filter(n => n.selected);
        const selectedEdges = state.edges.filter(ed => ed.selected);
        if (selectedNodes.length > 0 || selectedEdges.length > 0) {
          e.preventDefault();
          if (selectedNodes.length > 0) deleteNodes(selectedNodes.map(n => n.id));
          if (selectedEdges.length > 0) deleteEdges(selectedEdges.map(ed => ed.id));
        }
        return;
      }

      // Ctrl+Z / Cmd+Z → undo last deletion
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        const entry = popUndo();
        if (entry) {
          e.preventDefault();
          usePipelineStore.setState(state => ({
            nodes: [...state.nodes, ...entry.nodes],
            edges: [...state.edges, ...entry.edges],
          }));
          setDirty(true);
        }
      }
    };

    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [cancelPending, deleteNodes, deleteEdges, popUndo, setDirty]);

  // ── Connection validation (drag-to-connect) ───────────────────────────────
  const onConnect = useCallback(async (connection) => {
    let edgeData = {};
    try {
      // React Flow passes handle IDs (port_ids) in sourceHandle/targetHandle,
      // not port types. Resolve the actual type from the block definition.
      const { nodes: allNodes, blockIndex, localBlocks } = usePipelineStore.getState();

      const resolvePortType = (nodeId, portId, direction) => {
        const node = allNodes.find(n => n.id === nodeId);
        if (!node) return 'NeuroData[any]';
        const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
        const def = lb ? localBlockToDefinition(lb) : (blockIndex[node.data.block_type_id] ?? null);
        if (!def) return 'NeuroData[any]';
        const ports = direction === 'source' ? (def.outputs ?? []) : (def.inputs ?? []);
        return ports.find(p => p.port_id === portId)?.type ?? 'NeuroData[any]';
      };

      const srcType = resolvePortType(connection.source, connection.sourceHandle, 'source');
      const tgtType = resolvePortType(connection.target, connection.targetHandle, 'target');
      const res = await validateConnection(srcType, tgtType);

      const resolveName = (nodeId) => {
        const node = allNodes.find(n => n.id === nodeId);
        if (!node) return nodeId;
        const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
        if (lb) return lb.display_name;
        return blockIndex[node.data.block_type_id]?.display_name ?? node.data.block_type_id;
      };

      const srcName = resolveName(connection.source);
      const tgtName = resolveName(connection.target);

      // ERROR (structural) is blocked; WARN (role mismatch) is allowed and
      // flagged with a persisted ⚠ badge on the edge (Port Types v2).
      if (!res.data.valid) {
        usePipelineStore.getState().addConsoleMessage({
          type: 'error',
          text: `Connection rejected: ${srcName} → ${tgtName} — ${res.data.message}`,
        });
        return;
      }

      if (res.data.status === 'warn') {
        edgeData = { warn: true, warnMsg: res.data.message };
        usePipelineStore.getState().addConsoleMessage({
          type: 'warning',
          text: `Connected with warning: ${srcName} → ${tgtName} — ${res.data.message}`,
        });
      } else {
        usePipelineStore.getState().addConsoleMessage({
          type: 'info',
          text: `Connected: ${srcName} → ${tgtName}`,
        });
      }
    } catch {
      // Allow if validation endpoint is unreachable during development
    }

    // Enforce single-source-per-input-port: reject if the target port already
    // has an incoming edge. Fan-out (one output → many inputs) is fine; fan-in
    // (many outputs → one input) is ambiguous and not supported.
    const { edges: currentEdges } = usePipelineStore.getState();
    if (currentEdges.some(
      e => e.target === connection.target && e.targetHandle === connection.targetHandle
    )) {
      usePipelineStore.getState().addConsoleMessage({
        type: 'error',
        text: `Connection rejected: input port "${connection.targetHandle}" already has a source. Each input port accepts only one connection.`,
      });
      return;
    }

    setEdges(eds => addEdge({ ...connection, type: 'custom', data: edgeData }, eds));
    setDirty(true);
  }, [setEdges, setDirty]);

  // ── Node interaction ──────────────────────────────────────────────────────
  const onNodeDoubleClick = useCallback((_event, node) => {
    setActivePopupNodeId(node.id);
  }, [setActivePopupNodeId]);

  const onNodeContextMenu = useCallback((event, node) => {
    event.preventDefault();
    cancelPending();
    setEdgeContextMenu(null);
    setContextMenu({
      x: event.clientX,
      y: event.clientY,
      nodeId: node.id,
      isLocal: node.data.is_local ?? false,
      isComposite: node.data.is_composite ?? false,
    });
  }, [cancelPending]);

  // ── Edge interaction ──────────────────────────────────────────────────────
  const onEdgeContextMenu = useCallback((event, edge) => {
    event.preventDefault();
    cancelPending();
    setContextMenu(null);
    setEdgeContextMenu({ x: event.clientX, y: event.clientY, edgeId: edge.id });
  }, [cancelPending]);

  // ── Pane interaction ──────────────────────────────────────────────────────
  const onPaneClick = useCallback(() => {
    setContextMenu(null);
    setEdgeContextMenu(null);
    cancelPending();
  }, [cancelPending]);

  const onPaneContextMenu = useCallback((event) => {
    event.preventDefault();
    cancelPending();
  }, [cancelPending]);

  // ── Drag-drop from side panel ─────────────────────────────────────────────
  const onDrop = useCallback(async (event) => {
    event.preventDefault();
    const blockTypeId = event.dataTransfer.getData('application/synapchart-block');
    const isComposite = event.dataTransfer.getData('application/synapchart-composite') === 'true';
    if (!blockTypeId) return;

    const bounds = reactFlowWrapper.current.getBoundingClientRect();
    const position = {
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    };

    if (isComposite) {
      // Fetch full definition and embed snapshot in the workflow
      try {
        const fullDef = await getCompositeBlock(blockTypeId);
        const def = compositeBlockToDefinition(fullDef);
        addCompositeBlock(fullDef);  // embed snapshot (copy semantics)
        const newNode = {
          id: `${blockTypeId}_${Math.random().toString(36).slice(2, 6)}`,
          type: 'compositeNode',
          position,
          data: { block_type_id: blockTypeId, parameters: {}, definition: def, is_composite: true },
        };
        usePipelineStore.setState(state => ({ nodes: [...state.nodes, newNode] }));
        setDirty(true);
      } catch (err) {
        console.error('Failed to load composite block:', err);
        usePipelineStore.getState().addConsoleMessage({
          type: 'error',
          text: `Failed to load composite block "${blockTypeId}": ${err.message}`,
        });
      }
      return;
    }

    const newNode = {
      id: `${blockTypeId}_${Math.random().toString(36).slice(2, 6)}`,
      type: 'blockNode',
      position,
      data: { block_type_id: blockTypeId, parameters: {} },
    };

    usePipelineStore.setState(state => ({ nodes: [...state.nodes, newNode] }));
    setDirty(true);
  }, [setDirty, addCompositeBlock]);

  const onDragOver = useCallback((event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  // ── Shared menu-item style helper ─────────────────────────────────────────
  const menuItem = (color = '#f9fafb') => ({
    display: 'block', width: '100%', textAlign: 'left',
    background: 'none', border: 'none',
    color, padding: '6px 16px',
    fontSize: 12, cursor: 'pointer',
  });

  // ── Context value for BlockNode / CompositeNode ──────────────────────────
  const canvasCtx = { pendingConnection, handlePortClick, onDrillIn };

  // ── Pending wire bezier path ──────────────────────────────────────────────
  const pendingPath = pendingConnection && cursorPos ? (() => {
    const { sx, sy } = pendingConnection;
    const { x: cx, y: cy } = cursorPos;
    const dx = Math.max(60, Math.abs(cx - sx) * 0.5);
    return `M ${sx} ${sy} C ${sx + dx} ${sy}, ${cx - dx} ${cy}, ${cx} ${cy}`;
  })() : null;

  // Find the active drill-in tab definition
  const activeDrillTab = drillTabs.find(t => t.id === activeTab);

  return (
    <CanvasContext.Provider value={canvasCtx}>
      <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>

        {/* ── Canvas tabs bar — always visible ── */}
        <div style={{
          display: 'flex', alignItems: 'center',
          background: '#111827', borderBottom: '1px solid #1f2937',
          flexShrink: 0, gap: 0, padding: '0 8px',
          minHeight: 32,
        }}>
          {drillTabs.length > 0 && (
            <>
              <button
                onClick={() => setActiveTab('main')}
                style={{
                  background: activeTab === 'main' ? '#1f2937' : 'transparent',
                  border: 'none', borderBottom: activeTab === 'main' ? '2px solid #6366f1' : '2px solid transparent',
                  color: activeTab === 'main' ? '#f9fafb' : '#9ca3af',
                  padding: '6px 14px', fontSize: 12, cursor: 'pointer',
                }}
              >
                Main workflow
              </button>
              {drillTabs.map(tab => (
                <div key={tab.id} style={{ display: 'flex', alignItems: 'center' }}>
                  <button
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      background: activeTab === tab.id ? '#1f2937' : 'transparent',
                      border: 'none', borderBottom: activeTab === tab.id ? '2px solid #6366f1' : '2px solid transparent',
                      color: activeTab === tab.id ? '#f9fafb' : '#9ca3af',
                      padding: '6px 14px', fontSize: 12, cursor: 'pointer',
                    }}
                  >
                    ⊞ {tab.label}
                  </button>
                  <button
                    onClick={() => closeDrillTab(tab.id)}
                    style={{
                      background: 'transparent', border: 'none',
                      color: '#6b7280', fontSize: 10, cursor: 'pointer', padding: '0 4px',
                    }}
                    title="Close tab"
                  >
                    ✕
                  </button>
                </div>
              ))}
            </>
          )}
          {/* Package as block button — always accessible */}
          <button
            onClick={() => setShowPackagingWizard(true)}
            title="Package this workflow as a reusable composite block"
            style={{
              marginLeft: 'auto',
              background: 'rgba(99,102,241,0.15)', border: '1px solid #4f46e5',
              borderRadius: 4, color: '#a5b4fc', fontSize: 11,
              padding: '3px 10px', cursor: 'pointer',
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(99,102,241,0.3)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(99,102,241,0.15)'}
          >
            ⊞ Package as block
          </button>
        </div>

        {/* ── Drill-in subflow canvas ── */}
        {activeTab !== 'main' && activeDrillTab && (
          <div style={{
            flex: 1, minHeight: 0, background: '#0f172a',
            display: 'flex', flexDirection: 'column',
          }}>
            {/* Breadcrumb */}
            <div style={{
              padding: '6px 16px', fontSize: 11, color: '#6b7280',
              borderBottom: '1px solid #1f2937', flexShrink: 0,
              display: 'flex', alignItems: 'center', gap: 4,
            }}>
              <span
                onClick={() => setActiveTab('main')}
                style={{ cursor: 'pointer', color: '#a5b4fc' }}
              >
                Main workflow
              </span>
              <span style={{ color: '#374151' }}>›</span>
              <span style={{ color: '#e5e7eb' }}>
                ⊞ {activeDrillTab.label}
              </span>
              <span style={{
                marginLeft: 8, fontSize: 10, color: '#4b5563',
                background: '#1f2937', border: '1px solid #374151',
                borderRadius: 3, padding: '1px 6px',
              }}>
                {(activeDrillTab.definition?.subflow?.nodes ?? []).length} nodes ·{' '}
                {(activeDrillTab.definition?.subflow?.edges ?? []).length} edges
              </span>
            </div>

            {/* Full React Flow canvas for the subflow */}
            <SubflowCanvas
              definition={activeDrillTab.definition}
              onParamsChange={onSubflowParamsChange}
            />
          </div>
        )}

      {/* ── Main canvas (hidden when a drill-in tab is active) ── */}
      <div
        ref={reactFlowWrapper}
        style={{
          flex: activeTab === 'main' ? 1 : 0,
          minHeight: 0,
          position: 'relative',
          cursor: pendingConnection ? 'crosshair' : undefined,
          display: activeTab === 'main' ? undefined : 'none',
        }}
      >
        {/* ── Packaging wizard ── */}
        {showPackagingWizard && (
          <PackagingWizard
            onClose={() => setShowPackagingWizard(false)}
            onCreated={(_def) => {
              showToast('Composite block saved to library.');
            }}
          />
        )}

        {/* ── BlockWizard for canvas-level local-block editing ── */}
        {wizardEditBlock && (
          <BlockWizard
            editBlock={wizardEditBlock}
            onClose={() => setWizardEditBlock(null)}
          />
        )}

        {/* ── Toast notification ── */}
        {toast && (
          <div style={{
            position: 'absolute', bottom: 40, left: '50%', transform: 'translateX(-50%)',
            background: '#166534', border: '1px solid #22c55e', borderRadius: 6,
            color: '#f0fdf4', padding: '8px 18px', fontSize: 12, fontWeight: 600,
            zIndex: 9998, pointerEvents: 'none',
            boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
          }}>
            ✓ {toast}
          </div>
        )}

        {/* ── Pending connection wire SVG overlay ── */}
        {pendingPath && (
          <svg style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            pointerEvents: 'none', zIndex: 9990,
            overflow: 'visible',
          }}>
            <path
              d={pendingPath}
              fill="none"
              stroke="#818cf8"
              strokeWidth={2}
              strokeDasharray="7 4"
              strokeLinecap="round"
            />
            {/* Animated dot at cursor end */}
            <circle cx={cursorPos.x} cy={cursorPos.y} r={4} fill="#818cf8" opacity={0.8} />
          </svg>
        )}

        {/* ── Node context menu ── */}
        {contextMenu && (
          <div
            ref={contextMenuRef}
            style={{
              position: 'fixed',
              top: contextMenu.y, left: contextMenu.x,
              background: '#1f2937', border: '1px solid #374151',
              borderRadius: 6, boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
              zIndex: 9999, minWidth: 190, padding: '4px 0',
            }}
          >
            {/* Drill in — composite blocks only */}
            {contextMenu.isComposite && (
              <button
                onClick={() => {
                  setContextMenu(null);
                  const { nodes: allNodes, compositeBlocks } = usePipelineStore.getState();
                  const node = allNodes.find(n => n.id === contextMenu.nodeId);
                  if (!node) return;
                  const def = node.data.definition ?? compositeBlocks.find(
                    b => b.block_type_id === node.data.block_type_id
                  );
                  if (def) onDrillIn(contextMenu.nodeId, def.subflow ? def : compositeBlockToDefinition?.(def));
                }}
                style={menuItem('#a5b4fc')}
                onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}
              >
                ⊞ Drill in
              </button>
            )}
            {/* Duplicate node — always available */}
            <button
              onClick={() => duplicateNode(contextMenu.nodeId)}
              style={menuItem()}
              onMouseEnter={e => e.currentTarget.style.background = '#374151'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              ⧉ Duplicate
            </button>
            {/* Create local variant — composite blocks don't support this */}
            {!contextMenu.isComposite && (
              <button
                onClick={() => createLocalVariant(contextMenu.nodeId)}
                style={menuItem('#a5b4fc')}
                onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}
              >
                ✦ Create local variant…
              </button>
            )}
            <div style={{ height: 1, background: '#374151', margin: '4px 0' }} />
            {contextMenu.isLocal && (
              <>
                <button
                  onClick={() => openLocalEdit(contextMenu.nodeId)}
                  style={menuItem()}
                  onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                  onMouseLeave={e => e.currentTarget.style.background = 'none'}
                >
                  ✏ Edit block definition
                </button>
                <button
                  onClick={() => saveToLibrary(contextMenu.nodeId)}
                  style={menuItem('#818cf8')}
                  onMouseEnter={e => e.currentTarget.style.background = '#374151'}
                  onMouseLeave={e => e.currentTarget.style.background = 'none'}
                >
                  ↑ Save block to library
                </button>
              </>
            )}
            <div style={{ height: 1, background: '#374151', margin: '4px 0' }} />
            <button
              onClick={() => { toggleBreakpoint(contextMenu.nodeId); setContextMenu(null); }}
              style={menuItem(breakpointNodeIds.has(contextMenu.nodeId) ? '#f87171' : '#fbbf24')}
              onMouseEnter={e => e.currentTarget.style.background = '#374151'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              {breakpointNodeIds.has(contextMenu.nodeId) ? '● Remove breakpoint' : '○ Set breakpoint'}
            </button>
            <div style={{ height: 1, background: '#374151', margin: '4px 0' }} />
            <button
              onClick={() => deleteNodes([contextMenu.nodeId])}
              style={menuItem('#f87171')}
              onMouseEnter={e => e.currentTarget.style.background = '#374151'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              ✕ Delete block
            </button>
          </div>
        )}

        {/* ── Edge context menu ── */}
        {edgeContextMenu && (
          <div
            ref={edgeContextMenuRef}
            style={{
              position: 'fixed',
              top: edgeContextMenu.y, left: edgeContextMenu.x,
              background: '#1f2937', border: '1px solid #374151',
              borderRadius: 6, boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
              zIndex: 9999, minWidth: 160, padding: '4px 0',
            }}
          >
            <button
              onClick={() => deleteEdges([edgeContextMenu.edgeId])}
              style={menuItem('#f87171')}
              onMouseEnter={e => e.currentTarget.style.background = '#374151'}
              onMouseLeave={e => e.currentTarget.style.background = 'none'}
            >
              ✕ Delete connection
            </button>
          </div>
        )}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeDoubleClick={onNodeDoubleClick}
          onNodeContextMenu={onNodeContextMenu}
          onEdgeContextMenu={onEdgeContextMenu}
          onPaneClick={onPaneClick}
          onPaneContextMenu={onPaneContextMenu}
          onDrop={onDrop}
          onDragOver={onDragOver}
          onInit={setReactFlowInstance}
          deleteKeyCode={null}
          fitView
        >
          <MiniMap />
          <Controls />
          <Background variant="dots" />
        </ReactFlow>
      </div>
      </div>
    </CanvasContext.Provider>
  );
}

