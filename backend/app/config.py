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
# Google Calendar: path to an existing authorized-user token (read-only copy; refreshed in memory, never written back).
GOOGLE_TOKEN_PATH = os.environ.get("GOOGLE_TOKEN_PATH", "")
# Where recipe links in calendar events point (the app's address as the household reaches it).
SOUS_URL = os.environ.get("SOUS_URL", "http://localhost:3100")
MEALS_CALENDAR_NAME = os.environ.get("MEALS_CALENDAR_NAME", "Meals")
DEFAULT_DINNER_TIME = os.environ.get("DEFAULT_DINNER_TIME", "17:30")
# Who is in the household: each person rates what they cook, so the chef learns each person's taste.
HOUSEHOLD_MEMBERS = [m.strip() for m in os.environ.get("HOUSEHOLD_MEMBERS", "Jake,Kadie").split(",") if m.strip()]
