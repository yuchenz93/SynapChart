# SynapChart — Doc 02: Frontend Canvas

## Overview

The frontend is a React application. It provides:
- A node canvas (React Flow) where users build pipelines visually
- A side panel for browsing and adding blocks
- A top toolbar for file operations
- A block editor popup (parameters + source code)
- Pop-out visualization windows

The frontend communicates with the FastAPI backend via the API client module. All global state is managed by Zustand.

---

## Bootstrap

```bash
npm create vite@latest frontend -- --template react
cd frontend
npm install react-flow-renderer zustand axios @monaco-editor/react
```

Use React Flow v11+. The canvas must fill the full browser viewport minus the top toolbar height.

---

## Global State — `store/pipelineStore.js`

All pipeline state lives in a single Zustand store. Components read from and write to this store; they do not maintain local copies of pipeline data.

```javascript
// store/pipelineStore.js
import { create } from 'zustand';

const usePipelineStore = create((set, get) => ({
  // Canvas state (fed directly to React Flow)
  nodes: [],
  edges: [],
  setNodes: (nodes) => set({ nodes }),
  setEdges: (edges) => set({ edges }),
  onNodesChange: (changes) => { /* apply React Flow node changes */ },
  onEdgesChange: (changes) => { /* apply React Flow edge changes */ },

  // Block library (fetched from backend on startup)
  blockLibrary: [],          // array of category objects from GET /api/blocks/
  setBlockLibrary: (lib) => set({ blockLibrary: lib }),

  // Execution state
  runStatus: 'idle',         // 'idle' | 'running' | 'paused' | 'error' | 'done'
  nodeStatuses: {},          // { node_id: 'pending' | 'running' | 'done' | 'cached' | 'error' }
  setRunStatus: (s) => set({ runStatus: s }),
  setNodeStatus: (id, s) => set(state => ({
    nodeStatuses: { ...state.nodeStatuses, [id]: s }
  })),

  // Currently open popup
  activePopupNodeId: null,
  setActivePopupNodeId: (id) => set({ activePopupNodeId: id }),

  // Workflow file metadata
  currentFilePath: null,
  isDirty: false,            // true if unsaved changes exist
  setCurrentFilePath: (p) => set({ currentFilePath: p }),
  setDirty: (v) => set({ isDirty: v }),
}));

export default usePipelineStore;
```

---

## Component: `canvas/Canvas.jsx`

This is the main React Flow canvas. It renders all nodes and edges, handles drag-drop from the side panel, and dispatches connection validation.

### Responsibilities
- Render `<ReactFlow>` with `nodes`, `edges`, `onNodesChange`, `onEdgesChange` from the Zustand store
- On new edge connection: call `POST /api/blocks/validate-connection` before accepting. If invalid, show a toast error and reject the connection
- On double-click on a node: open the block editor popup (`setActivePopupNodeId`)
- On right-click on a node: show a context menu with options: "Edit block", "Delete block", "Clear cache for this node"
- Accept drag-drop of blocks from the side panel: create a new node at the drop position with default parameters
- Display a small status badge on each node based on `nodeStatuses` from the store:
  - Gray = pending
  - Blue spinning = running
  - Green = done
  - Yellow = cached (loaded from checkpoint)
  - Red = error

### Node ID generation
New nodes get IDs of the form `{block_type_id}_{uuid4_short}`, e.g. `bandpass_filter_a3f2`.

### Canvas controls
Include React Flow's built-in `<MiniMap />`, `<Controls />`, and `<Background variant="dots" />`.

---

## Component: `canvas/BlockNode.jsx`

Custom React Flow node renderer. Every block on the canvas is rendered by this component.

### Visual structure
```
┌─────────────────────────────┐
│  [category color dot]  Name │  ← header (block display_name)
├─────────────────────────────┤
│  ● input_port_1             │  ← input handles on left edge
│  ● input_port_2             │
├─────────────────────────────┤
│             output_port_1 ● │  ← output handles on right edge
├─────────────────────────────┤
│  [status badge]             │  ← bottom: pending/running/done/cached/error
└─────────────────────────────┘
```

### Port handles
- Each input port renders a React Flow `<Handle type="target" position="Left" />`
- Each output port renders a React Flow `<Handle type="source" position="Right" />`
- Handle IDs must match the `port_id` from the block definition
- Port type is shown as a small tooltip on hover (e.g. "NeuroData[lfp]")

### Category color coding
Each block category maps to a header color:

| Category | Color |
|---|---|
| Data I/O | `#5DCAA5` (teal) |
| Behavior | `#EF9F27` (amber) |
| LFP / EEG | `#7F77DD` (purple) |
| Spikes | `#D85A30` (coral) |
| Visualization | `#378ADD` (blue) |

---

## Component: `panels/SidePanel.jsx`

A collapsible left-side panel showing the block library, grouped by category.

### Behavior
- On mount: fetch `GET /api/blocks/` and populate the store `blockLibrary`
- Render one accordion section per category
- Each block in the list is draggable onto the canvas
- Include a search/filter input at the top that filters blocks by name or description across all categories

### Drag protocol
When a block is dragged from the side panel onto the canvas:
1. `dragstart`: store `block_type_id` in `event.dataTransfer` as `application/synapchart-block`
2. Canvas `onDrop`: read the type, fetch the block definition, create a new node with default parameters at the drop coordinates

---

## Component: `panels/TopToolbar.jsx`

A fixed top bar with file operations and pipeline execution controls.

### Buttons (left to right)

| Button | Action |
|---|---|
| New | Clear canvas (prompt if unsaved changes) |
| Open | Call `POST /api/files/load` with a file path from a browser file picker |
| Save | Call `POST /api/files/save` with current workflow JSON |
| Save As | Same, but always prompts for path |
| Templates | Dropdown: list from `GET /api/files/templates/`, load on select |
| --- separator --- | |
| Run | Call `POST /api/pipeline/run-from-cache` with current workflow |
| Run (no cache) | Call `POST /api/pipeline/run` |
| Step | Call `POST /api/pipeline/step` — prompts user to pick which node |
| Stop | Call `POST /api/pipeline/stop` |

### Execution status indicator
A small indicator on the right side of the toolbar shows the current `runStatus`:
- Idle: gray dot
- Running: animated blue spinner
- Done: green checkmark
- Error: red X with a clickable log viewer

---

## Component: `modals/BlockEditor.jsx`

A popup window that appears when the user double-clicks or right-clicks → "Edit block" on a node. This is the primary interface for configuring a block.

### Layout
The popup has two tabs:

**Tab 1: Parameters**
- Renders a form field for each parameter defined in the block's `parameters` array
- Field type is inferred from parameter `type`: `str` → text input, `float`/`int` → number input, `bool` → checkbox, enum → dropdown
- Each field shows its `description` as a tooltip
- Changes are applied to the node's `parameters` in the Zustand store on "Apply"

**Tab 2: Source code**
- Shows the block's Python source code in a Monaco editor (read-only for built-in blocks, editable for custom blocks)
- For custom blocks, a "Save & reload" button calls `POST /api/blocks/register-custom` with the updated source

### Opening/closing
- Opens when `activePopupNodeId` is set in the store
- Closes when the user presses Escape, clicks outside, or clicks the X button
- On close: set `activePopupNodeId` to null

---

## Component: `modals/VizWindow.jsx`

Pop-out windows spawned by visualization blocks. Each visualization block, when executed, may produce a plot image (PNG, served as a base64 string or file URL from the backend). This window displays that image.

### Behavior
- Multiple visualization windows can be open simultaneously
- Each window is draggable and resizable (use a lightweight library or CSS resize)
- Windows persist until the user closes them
- If the pipeline re-runs and the viz block produces a new image, the window updates automatically
- A "Save image" button downloads the PNG to disk

### Triggering
Visualization blocks include a `show_on_run` boolean parameter. If true, the VizWindow opens automatically when the block finishes executing. If false, the plot is saved to disk without display (path defined by a `save_path` parameter).

---

## API Client — `api/client.js`

All backend communication goes through this module. Components never call `fetch()` directly.

```javascript
// api/client.js
import axios from 'axios';

const BASE = 'http://localhost:8000';

export const getBlocks = () =>
  axios.get(`${BASE}/api/blocks/`).then(r => r.data);

export const validateConnection = (outputType, inputType) =>
  axios.post(`${BASE}/api/blocks/validate-connection`, { output_type: outputType, input_type: inputType });

export const runPipeline = (workflow, useCache = true) =>
  axios.post(`${BASE}/api/pipeline/${useCache ? 'run-from-cache' : 'run'}`, { workflow });

export const stepPipeline = (workflow, nodeId) =>
  axios.post(`${BASE}/api/pipeline/step`, { workflow, node_id: nodeId });

export const stopPipeline = () =>
  axios.post(`${BASE}/api/pipeline/stop`);

export const saveWorkflow = (workflow, filePath) =>
  axios.post(`${BASE}/api/files/save`, { workflow, file_path: filePath });

export const loadWorkflow = (filePath) =>
  axios.post(`${BASE}/api/files/load`, { file_path: filePath });

export const getTemplates = () =>
  axios.get(`${BASE}/api/files/templates`).then(r => r.data);

export const loadTemplate = (name) =>
  axios.get(`${BASE}/api/files/templates/${name}`).then(r => r.data);

export const openLogsSocket = (onMessage) => {
  const ws = new WebSocket(`ws://localhost:8000/api/pipeline/logs`);
  ws.onmessage = (e) => onMessage(JSON.parse(e.data));
  return ws;
};
```

---

## Workflow JSON → React Flow State Conversion

When a workflow is loaded from disk, it must be converted to React Flow's node/edge format. When saved, it must be converted back. This conversion lives in `store/pipelineStore.js`.

### Workflow node → React Flow node
```javascript
// workflow node (from JSON):
{ "node_id": "bandpass_filter_a3f2", "block_type_id": "bandpass_filter",
  "position": { "x": 200, "y": 150 }, "parameters": { "low_hz": 4, "high_hz": 12 } }

// React Flow node:
{ id: "bandpass_filter_a3f2", type: "blockNode", position: { x: 200, y: 150 },
  data: { block_type_id: "bandpass_filter", parameters: { low_hz: 4, high_hz: 12 } } }
```

### Workflow edge → React Flow edge
```javascript
// workflow edge (from JSON):
{ "edge_id": "e1", "source_node_id": "load_npy_x1a", "source_port_id": "data",
  "target_node_id": "bandpass_filter_a3f2", "target_port_id": "signal" }

// React Flow edge:
{ id: "e1", source: "load_npy_x1a", sourceHandle: "data",
  target: "bandpass_filter_a3f2", targetHandle: "signal" }
```
