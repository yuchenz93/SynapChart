from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import pipeline, blocks, files, libraries

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from core.library_registry import discover_all_libraries
    from core.checkpoint import clear_cache
    discover_all_libraries()
    clear_cache()   # wipe stale checkpoints on every startup
    yield


app = FastAPI(title="SynapChart Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipeline.router,  prefix="/api/pipeline")
app.include_router(blocks.router,    prefix="/api/blocks")
app.include_router(files.router,     prefix="/api/files")
app.include_router(libraries.router, prefix="/api/libraries")

# --- Serve the compiled React frontend ---
# Only active after `npm run build` has populated backend/static/.
if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Catch-all: serve index.html for any path not matched by API routers."""
        file_path = STATIC_DIR / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
else:
    @app.get("/")
    async def serve_dev_notice() -> dict:
        return {
            "message": "SynapChart backend running. Frontend not built yet.",
            "hint": "Run `cd frontend && npm run build` to build the UI.",
        }
