import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
DB_PATH = DATA_DIR / "recipes.db"
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
# "mcp" drives the real Safeway site; "mock" returns fake products so the flow works offline.
SAFEWAY_MODE = os.environ.get("SAFEWAY_MODE", "mock")
SAFEWAY_EMAIL = os.environ.get("SAFEWAY_EMAIL", "")
SAFEWAY_PASSWORD = os.environ.get("SAFEWAY_PASSWORD", "")
SAFEWAY_MCP_COMMAND = os.environ.get("SAFEWAY_MCP_COMMAND", "striderlabs-mcp-safeway")
