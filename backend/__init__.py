import sys
from pathlib import Path

# When SynapChart is installed as a package and uvicorn loads "backend.main:app"
# from the project root, the submodules inside backend/ (api, core, blocks,
# neurodata) are not on sys.path.  Adding backend/ here ensures that
# "from api import ..." works identically in both dev and installed modes.
_backend_dir = str(Path(__file__).parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
