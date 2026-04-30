import { useEffect, useRef, useState } from 'react';
import Canvas from './canvas/Canvas';
import SidePanel from './panels/SidePanel';
import TopToolbar from './panels/TopToolbar';
import TabBar from './panels/TabBar';
import BlockEditor from './modals/BlockEditor';
import VizWindow from './modals/VizWindow';
import RunProgress from './panels/RunProgress';
import ConsolePanel from './panels/ConsolePanel';
import usePipelineStore from './store/pipelineStore';
import { getBlocks, openLogsSocket } from './api/client';

/** Resolve a node ID to its display name using current store state. */
function getNodeName(nodeId) {
  const { nodes, blockIndex, localBlocks } = usePipelineStore.getState();
  const node = nodes.find(n => n.id === nodeId);
  if (!node) return nodeId;
  const lb = localBlocks.find(b => b.block_type_id === node.data.block_type_id);
  if (lb) return lb.display_name;
  const found = blockIndex[node.data.block_type_id];
  return found?.display_name ?? node.data.block_type_id;
}

/** Root application component. Bootstraps the block library and lays out the UI. */
export default function App() {
  const { setBlockLibrary, missingLibraries, clearLoadWarnings } = usePipelineStore(s => ({
    setBlockLibrary:  s.setBlockLibrary,
    missingLibraries: s.missingLibraries,
    clearLoadWarnings: s.clearLoadWarnings,
  }));

  const [showMissingBanner, setShowMissingBanner] = useState(false);

  // Show banner whenever missingLibraries becomes non-empty
  useEffect(() => {
    if (missingLibraries.length > 0) setShowMissingBanner(true);
  }, [missingLibraries]);

  // Load block library on startup
  useEffect(() => {
    getBlocks()
      .then(data => setBlockLibrary(data.libraries ?? []))
      .catch(err => console.error('Failed to load block library:', err));
  }, [setBlockLibrary]);

  // WebSocket: connect once and reconnect if dropped.
  const wsRef = useRef(null);
  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const ws = openLogsSocket((msg) => {
        const store = usePipelineStore.getState();

        if (msg.status === 'plan' && Array.isArray(msg.order)) {
          const initial = {};
          msg.order.forEach(id => { initial[id] = 'pending'; });
          store.setNodeStatuses(initial);
          store.setExecutionOrder(msg.order);
          store.setRunStatus('running');
          store.clearVizResults();
          store.clearPipelineErrors();
          store.addConsoleMessage({ type: 'info', text: `Pipeline started (${msg.order.length} nodes)` });
          return;
        }

        if (msg.status === 'viz_result' && msg.node_id && msg.image_b64) {
          store.addVizResult(msg.node_id, { imageSrc: msg.image_b64 });
          return;
        }

        if (msg.level === 'error' && !msg.node_id) {
          store.addPipelineError(msg.message);
          store.setRunStatus('error');
          store.addConsoleMessage({ type: 'error', text: msg.message });
          return;
        }

        if (msg.status === 'disp' && msg.node_id) {
          const name = getNodeName(msg.node_id);
          store.addConsoleMessage({ type: 'info', text: `${name}: ${msg.message}`, nodeId: msg.node_id });
          return;
        }

        if (msg.node_id && msg.status) {
          store.setNodeStatus(msg.node_id, msg.status);
          const name = getNodeName(msg.node_id);
          if (msg.status === 'running') {
            store.addConsoleMessage({ type: 'info', text: `${name}: running...`, nodeId: msg.node_id });
          } else if (msg.status === 'done') {
            store.addConsoleMessage({ type: 'info', text: `${name}: done`, nodeId: msg.node_id });
          } else if (msg.status === 'cached') {
            store.addConsoleMessage({ type: 'info', text: `${name}: loaded from cache`, nodeId: msg.node_id });
          } else if (msg.status === 'error') {
            store.addConsoleMessage({
              type: 'error',
              text: `${name} failed: ${msg.message ?? 'unknown error'}`,
              nodeId: msg.node_id,
              traceback: msg.traceback ?? null,
            });
          }
        }

        if (!msg.node_id && msg.status && ['done', 'error', 'stopped'].includes(msg.status)) {
          store.setRunStatus(msg.status);
          if (msg.status === 'done') {
            store.addConsoleMessage({ type: 'success', text: 'Pipeline complete' });
          } else if (msg.status === 'stopped') {
            store.addConsoleMessage({ type: 'info', text: 'Pipeline stopped' });
          }
        }
      });

      ws.onclose = () => { if (!cancelled) setTimeout(connect, 2000); };
      wsRef.current = ws;
    };

    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  const handleOpenLibraryFolder = () => {
    // Best-effort: tell the user where to drop library folders
    alert(
      'Drop your library folder (containing library.json) into:\n' +
      '  ~/.synapchart/blocklibrary/\n\n' +
      'Then click "Refresh libraries" in the side panel, or restart the server.'
    );
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <TopToolbar />
      <TabBar />

      {/* Missing library warning banner */}
      {showMissingBanner && missingLibraries.length > 0 && (
        <div style={{
          background: '#7c2d12', borderBottom: '1px solid #ea580c',
          color: '#fed7aa', fontSize: 12, padding: '6px 16px',
          display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
        }}>
          <span style={{ fontWeight: 700 }}>⚠ Missing libraries:</span>
          <span>{missingLibraries.map(l => `${l.name ?? l.id} (v${l.version})`).join(', ')}</span>
          <span style={{ color: '#fdba74' }}>— Affected blocks are unavailable.</span>
          <button
            onClick={handleOpenLibraryFolder}
            style={{ background: '#9a3412', border: '1px solid #ea580c', borderRadius: 3,
              color: '#fed7aa', padding: '2px 8px', cursor: 'pointer', fontSize: 11, marginLeft: 4 }}
          >
            Where to install?
          </button>
          <button
            onClick={() => { setShowMissingBanner(false); clearLoadWarnings(); }}
            style={{ marginLeft: 'auto', background: 'none', border: 'none',
              color: '#fed7aa', cursor: 'pointer', fontSize: 14 }}
          >
            ✕
          </button>
        </div>
      )}

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <SidePanel />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <Canvas />
          <ConsolePanel />
        </div>
      </div>
      <RunProgress />
      <BlockEditor />
      <VizWindow />
    </div>
  );
}
