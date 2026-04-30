# SynapChart — Doc 06: Packaging and Distribution

## Overview

SynapChart is distributed as a single pip-installable Python package. Users run one
command to install it and one command to launch it. They do not need Node.js, a
separate frontend server, or any manual configuration.

The frontend (React) is compiled into static files during development and bundled
inside the Python package. FastAPI serves those static files directly, so the entire
application ships as pure Python.

Distribution targets:
- pip (primary): `pip install synapchart`
- conda-forge (secondary, neuroscience standard): `conda install -c conda-forge synapchart`
- GitHub Releases: standalone zip with pre-built frontend for users who prefer manual install

---

## Repository Changes Required

Add the following files to the repository root:

```
synapchart/
├── pyproject.toml              ← NEW: Python package definition
├── MANIFEST.in                 ← NEW: include frontend build files
├── README.md                   ← NEW: user-facing readme
├── CHANGELOG.md                ← NEW: version history
├── .github/
│   └── workflows/
│       ├── test.yml            ← NEW: run tests on every push
│       └── release.yml         ← NEW: build and publish on git tag
├── backend/
│   ├── __init__.py             ← NEW: makes backend a proper package
│   ├── cli.py                  ← NEW: entry point for `synapchart` command
│   └── static/                 ← NEW: compiled frontend lives here (git-ignored)
│       └── .gitkeep
└── frontend/
    └── vite.config.js          ← MODIFY: change output dir to ../backend/static
```

---

## Python Package Definition — `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68", "setuptools-scm>=8"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "synapchart"
dynamic = ["version"]
description = "Visual pipeline builder for neuroscience data analysis"
readme = "README.md"
license = { text = "MIT" }
requires-python = ">=3.10"
authors = [
    { name = "Your Name", email = "you@example.com" }
]
keywords = ["neuroscience", "EEG", "LFP", "spike", "pipeline", "visualization"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Science/Research",
    "Topic :: Scientific/Engineering :: Bio-Informatics",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
    "numpy>=1.24",
    "scipy>=1.11",
    "matplotlib>=3.7",
    "websockets>=12.0",
    "pydantic>=2.0",
    "click>=8.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",       # for FastAPI test client
    "ruff>=0.4",         # linter
]

[project.urls]
Homepage = "https://github.com/your-org/synapchart"
Documentation = "https://github.com/your-org/synapchart/wiki"
Issues = "https://github.com/your-org/synapchart/issues"

[project.scripts]
synapchart = "backend.cli:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]

[tool.setuptools.package-data]
"backend" = ["static/**/*", "blocks/**/*.py", "workflows/templates/*.json"]

[tool.setuptools_scm]
# Version is derived automatically from git tags (e.g. tag v0.1.0 → version 0.1.0)
# No need to manually update version strings anywhere.
```

---

## CLI Entry Point — `backend/cli.py`

This is the script that runs when the user types `synapchart` in their terminal.

```python
# backend/cli.py
import os
import sys
import time
import webbrowser
import threading
from pathlib import Path

import click
import uvicorn


@click.command()
@click.option("--port", default=8000, show_default=True,
              help="Port to run the SynapChart server on.")
@click.option("--no-browser", is_flag=True, default=False,
              help="Start server without opening a browser tab.")
@click.option("--host", default="127.0.0.1", show_default=True,
              help="Host address to bind to. Use 0.0.0.0 to allow network access.")
def main(port: int, no_browser: bool, host: str):
    """
    SynapChart — visual pipeline builder for neuroscience.

    Starts the local server and opens the UI in your browser.
    Press Ctrl+C to stop.
    """
    click.echo(f"Starting SynapChart on http://{host}:{port}")
    click.echo("Press Ctrl+C to stop.\n")

    if not no_browser:
        # Open browser after a short delay to let the server start
        def _open():
            time.sleep(1.5)
            webbrowser.open(f"http://127.0.0.1:{port}")
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(
        "backend.main:app",
        host=host,
        port=port,
        log_level="warning",   # suppress uvicorn access logs in normal use
    )


if __name__ == "__main__":
    main()
```

---

## Serving the Frontend from FastAPI — `backend/main.py` additions

Add static file serving to the existing FastAPI app. The frontend build output is
placed in `backend/static/`. FastAPI serves it at the root URL so users just visit
`http://localhost:8000`.

```python
# Add to backend/main.py (after the existing router includes)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"

# Serve the React app's static assets (JS, CSS, images)
if STATIC_DIR.exists() and any(STATIC_DIR.iterdir()):
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        Catch-all route: serves index.html for any path not matched by the API.
        This is required for React Router (client-side routing) to work correctly.
        Must be defined AFTER all API routers.
        """
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    async def serve_dev_notice():
        return {
            "message": "SynapChart backend running. Frontend not built yet.",
            "hint": "Run `cd frontend && npm run build` to build the UI."
        }
```

---

## Frontend Build Configuration — `frontend/vite.config.js`

Change the build output directory so compiled files land in `backend/static/`,
where the Python package can find them.

```javascript
// frontend/vite.config.js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  build: {
    // Output goes into the Python package's static folder
    outDir: path.resolve(__dirname, '../backend/static'),
    emptyOutDir: true,
  },
  server: {
    // During development, proxy API calls to the FastAPI backend
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
```

---

## `.gitignore` additions

```
# Compiled frontend — always regenerated from source, never committed
backend/static/

# Python build artifacts
dist/
build/
*.egg-info/
__pycache__/
.synapchart_cache/

# Node
frontend/node_modules/
frontend/dist/
```

---

## `MANIFEST.in`

Tells setuptools to include non-Python files when building a source distribution.

```
include README.md
include CHANGELOG.md
include LICENSE
recursive-include backend/static *
recursive-include backend/blocks *.py
recursive-include workflows/templates *.json
```

---

## Development Workflow (for you, building the project)

```bash
# 1. Build the frontend once (or after any UI changes)
cd frontend
npm run build          # outputs to backend/static/

# 2. Run the backend in dev mode (hot-reload on Python changes)
cd backend
uvicorn main:app --reload --port 8000

# 3. OR run the frontend dev server separately for UI development
#    (hot module replacement, no need to rebuild on every change)
cd frontend
npm run dev            # runs on http://localhost:5173, proxies API to :8000
```

---

## User Install Workflow

Once published to PyPI, this is all a user needs:

```bash
# Recommended: install in a virtual environment
python -m venv synapchart-env
source synapchart-env/bin/activate   # on Windows: synapchart-env\Scripts\activate

pip install synapchart

# Launch
synapchart
# Browser opens automatically at http://localhost:8000
```

For conda users (common in neuroscience):

```bash
conda create -n synapchart python=3.11
conda activate synapchart
pip install synapchart    # until a conda-forge recipe is submitted
synapchart
```

---

## GitHub Actions: Test on Every Push — `.github/workflows/test.yml`

```yaml
name: Tests

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        run: |
          pytest backend/tests/ -v
```

---

## GitHub Actions: Build and Publish on Release — `.github/workflows/release.yml`

This workflow triggers when you push a git tag like `v0.1.0`. It builds the
frontend, bundles it into the Python package, and publishes to PyPI automatically.

```yaml
name: Release

on:
  push:
    tags:
      - "v*.*.*"

jobs:
  build-and-publish:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0    # required for setuptools-scm to read git tags

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Build frontend
        run: |
          cd frontend
          npm ci
          npm run build
          # Compiled output now in backend/static/

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install build tools
        run: pip install build twine

      - name: Build Python package
        run: python -m build
        # Creates dist/synapchart-X.Y.Z.tar.gz and dist/synapchart-X.Y.Z-py3-none-any.whl

      - name: Publish to PyPI
        env:
          TWINE_USERNAME: __token__
          TWINE_PASSWORD: ${{ secrets.PYPI_API_TOKEN }}
        run: twine upload dist/*

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: dist/*
          generate_release_notes: true
```

To use this workflow:
1. Create a PyPI account at pypi.org
2. Generate an API token in your PyPI account settings
3. Add it to your GitHub repository: Settings → Secrets → `PYPI_API_TOKEN`
4. To release: `git tag v0.1.0 && git push origin v0.1.0`

---

## Versioning Convention

Use semantic versioning: `MAJOR.MINOR.PATCH`

- `v0.x.x` — pre-release / alpha (you are here)
- `v1.0.0` — first stable public release (after demo workflow runs end-to-end)
- `v1.x.0` — new block categories or features
- `v1.x.x` — bug fixes

Version numbers are derived automatically from git tags by `setuptools-scm`.
You never manually edit a version string anywhere in the codebase.

---

## Checklist Before First Public Release (v0.1.0)

- [ ] Demo workflow (Doc 05) runs end-to-end on synthetic test data
- [ ] `pip install -e .` works on a clean Python 3.10 environment
- [ ] `synapchart` command opens the UI and the canvas loads
- [ ] At least one built-in block from each category works
- [ ] README has screenshots and a 2-minute quickstart section
- [ ] License file is present (MIT recommended for research tools)
- [ ] PyPI token is set in GitHub secrets
