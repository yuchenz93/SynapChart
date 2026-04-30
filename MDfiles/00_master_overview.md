# SynapChart — Master Overview

## Project Vision

SynapChart is an open-source, web-based visual programming environment for neuroscience data analysis. Users build analysis pipelines by connecting blocks on a canvas — similar in style to ComfyUI or Simulink — with a Python backend executing the actual computation.

The primary audience is neuroscience researchers. The initial focus is EEG/LFP and spike train analysis. The architecture is designed to grow: blocks and workflows can be shared by the community, and a future AI-assisted block/workflow design layer should require no structural changes to achieve.

---

## Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | React + React Flow | Mature node-canvas library, large ecosystem |
| Backend | FastAPI (Python) | Async, researcher-friendly, easy to extend |
| Frontend–backend comms | REST + WebSocket | REST for control, WebSocket for live log streaming |
| Visualization | matplotlib (server-side, saved to file or shown via popup) | Familiar to neuroscience users |
| Data interchange | `NeuroData` (custom numpy wrapper, see Doc 03) | Typed, metadata-bearing, no external deps |
| Workflow persistence | JSON (schema defined in Doc 03) | Human-readable, git-friendly, registry-ready |
| Package manager | pip + `requirements.txt` | Standard Python tooling |

---

## Repository Structure

```
synapchart/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── api/
│   │   ├── pipeline.py          # Pipeline run/step/stop endpoints
│   │   ├── blocks.py            # Block registry endpoints
│   │   └── files.py             # Workflow save/load endpoints
│   ├── core/
│   │   ├── executor.py          # Pipeline execution engine
│   │   ├── graph.py             # DAG resolution and topological sort
│   │   ├── checkpoint.py        # Per-node result cache
│   │   └── validator.py         # Port type validation
│   ├── blocks/
│   │   ├── base.py              # BlockBase class definition
│   │   ├── io/                  # Data loading/saving blocks
│   │   ├── behavior/            # Behavioral processing blocks
│   │   ├── lfp/                 # LFP/EEG processing blocks
│   │   ├── spikes/              # Spike train processing blocks
│   │   └── visualization/       # Visualization blocks
│   ├── neurodata/
│   │   └── types.py             # NeuroData wrapper and type definitions
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Root component
│   │   ├── canvas/
│   │   │   ├── Canvas.jsx       # React Flow canvas
│   │   │   ├── BlockNode.jsx    # Individual block rendering
│   │   │   └── ConnectionLine.jsx
│   │   ├── panels/
│   │   │   ├── SidePanel.jsx    # Block library browser
│   │   │   └── TopToolbar.jsx   # File operations toolbar
│   │   ├── modals/
│   │   │   ├── BlockEditor.jsx  # Popup: params + source code editor
│   │   │   └── VizWindow.jsx    # Pop-out visualization window
│   │   ├── api/
│   │   │   └── client.js        # All backend API calls
│   │   └── store/
│   │       └── pipelineStore.js # Global state (Zustand)
│   ├── package.json
│   └── vite.config.js
├── workflows/
│   └── templates/
│       └── theta_phase_precession.json   # Demo template workflow
└── docs/
    ├── 00_master_overview.md
    ├── 01_backend_core.md
    ├── 02_frontend_canvas.md
    ├── 03_block_system.md
    ├── 04_execution_engine.md
    └── 05_demo_workflow.md
```

---

## Coding Conventions

### Python (backend)
- Python 3.10+
- Type hints on all function signatures
- Docstrings on all public classes and methods (Google style)
- Block implementations must inherit from `BlockBase` (see Doc 03)
- No global mutable state outside of the FastAPI app instance
- All file paths use `pathlib.Path`

### JavaScript (frontend)
- React functional components only (no class components)
- Zustand for global state management
- All backend calls go through `src/api/client.js` — no inline `fetch()` elsewhere
- Component files use PascalCase; utility files use camelCase
- Props are documented with JSDoc comments on each component

### JSON Workflow Files
- All workflow files must validate against the schema defined in Doc 03
- Field names use `snake_case`
- Version field must be present: `"schema_version": "1.0"`

---

## Design Principles for Future AI Assistance (v2 Target)

The following constraints are intentionally applied now to make a future AI assistant layer easy to add:

1. **Block schema is self-describing.** Every block's JSON definition includes human-readable `description` and `parameter_descriptions` fields. An LLM can read a block definition and understand what it does without executing it.

2. **Workflow JSON is flat and annotated.** Nodes and edges are stored as simple lists. Each node carries its block type, parameters, and an optional `user_notes` field. No nested execution state is mixed into the workflow file.

3. **Block source code is stored alongside metadata.** Custom blocks store their Python source as a string in the block package. An LLM can read, modify, and regenerate this source.

4. **No magic or implicit behavior.** All port types, parameter defaults, and execution order are explicit in the JSON. An LLM generating or modifying a workflow should never need to infer implicit rules.

---

## Running the Project (Development)

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # runs on http://localhost:5173
```

---

## v1 Scope Boundaries

The following are explicitly OUT of scope for v1 and should not be implemented:

- Real-time / streaming data execution
- Community registry server (block packages are designed to be registry-ready, but no server exists yet)
- Multi-user / collaborative editing
- fMRI-specific blocks (architecture supports them; blocks not included)
- AI-assisted block writing or workflow design (architecture is ready; feature not included)
