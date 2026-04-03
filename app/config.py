import os
from pathlib import Path

# In Docker the env var is not set and /app/data is used via the volume.
# Locally it defaults to <project_root>/data so no extra setup is needed.
_default = Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.environ.get("DATA_DIR", _default))
