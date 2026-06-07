"""Make the `app` package (api/app) importable without a uv workspace install.

Mirrors how scripts/run_brief.py puts `engine` on the path. The api package is not
pip-installed in the dev env, so prepend api/ to sys.path for these tests.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_DIR = _REPO_ROOT / "api"
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))
