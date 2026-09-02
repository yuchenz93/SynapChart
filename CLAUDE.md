# SynapChart — working notes for Claude

Visual, node-based pipeline builder for neuroscience analysis ("ComfyUI for
spike trains / LFP"). **Frontend:** React + React Flow (Vite). **Backend:**
FastAPI (Python 3.10+). Values flowing between blocks are `NeuroData` envelopes
(numpy array + `sampling_rate`/`timestamps`/`channel_names`/`metadata`).

## Keep the docs in sync (important)

**After any major frontend/backend change, check whether the published docs also
need updating — proactively, without being asked.** Docs go stale silently and
make the project look narrow or unmaintained (e.g. Port Types v2 made
`data_type` free-form, but `docs/neurodata.md` / `docs/blocks/index.md` still
described a closed "registered types" list). When finishing a feature, grep
`docs/` for anything the change contradicts (type system, APIs, block lists, CLI
flags, screenshots) and offer to fix stale pages in the same effort.

## Running / building / testing

Use a Python 3.10+ environment with `pip install -r backend/requirements.txt`
(includes `h5py`, needed by the CRCNS loader / Tutorial 3).

- **Run the app** (serves the built frontend + API on one port):
  `python -m uvicorn main:app --app-dir backend --port 8000`
  (Use `--app-dir backend` — `backend/main.py` imports `from api import ...`, so
  `backend/` must be on the path.) Or the console script `synapchart`
  (`backend.cli:main`).
- **Frontend build:** `cd frontend && npm run build` → outputs to
  `backend/static/` (vite `outDir`; gitignored, regenerated). Dev server:
  `npm run dev` (Vite :5173, proxies `/api` → :8000).
- **Tests:** `pytest backend/tests` (needs `pytest` + `pytest-asyncio`). CI
  (`.github/workflows/test.yml`) runs on push to `main`/`dev` and PRs to `main`
  across Python 3.10/3.11/3.12.

## Documentation system

- Published site: **MkDocs Material**. Pages live under `docs/` and must be in
  the `nav:` in `mkdocs.yml`. Build/verify locally with
  `mkdocs build --strict` (`pip install -r requirements-docs.txt`).
- **Deploy:** pushing to `main` triggers `.github/workflows/docs.yml`
  (`mkdocs gh-deploy`), which publishes to the `gh-pages` branch →
  https://yuchenz93.github.io/SynapChart/. No version tag needed. Hard-refresh
  to bypass CDN/browser cache.
- **`docs/specs/` and `docs/progress/` are gitignored** local design/progress
  docs — *not* published and *not* committed. New feature specs go in
  `docs/specs/NN_*.md`; keep a `docs/progress/*_progress.md` log for multi-session
  work so it can stop/resume.
- Screenshots: `docs/assets/screenshots/` (a Playwright capture harness lives in
  the gitignored `_shots/`).

## Git conventions

- Commit or push **only when asked**. If on `main`, branch first. Use `gh` for
  PRs. End commit messages with the `Co-Authored-By: Claude ...` trailer.
- A release to PyPI happens **only on a version tag** (`release.yml`), never from
  a plain merge to `main`.

## Reference

- Port Type System v2 (structural type + advisory semantic role; three-state
  OK/WARN/ERROR validation): `docs/specs/12_port_type_system_v2.md`,
  implemented in `backend/neurodata/port_types.py`.
