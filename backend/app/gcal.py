"""Google Calendar: meals go out to a dedicated "Meals" calendar, and the week's busy times come in for the chef.

Auth reuses an existing token file (Task_Chore_Syncing's token_jake.pickle). It is mounted read-only, refreshed in
memory and never written back, exactly like the Kindle dashboard does. Meals never go on the "Care Tasks" calendar:
the chore sync turns events there into tasks and deletes them.
"""
import pickle
import time
from datetime import date, datetime, timedelta

import google_auth_httplib2
import httplib2
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from . import config, store

TOWN_TZ = "America/Los_Angeles"
MARK = "sous=1"  # private extended property on every event we create, so we only ever touch our own


class CalendarUnavailable(Exception):
    pass


def configured() -> bool:
    return bool(config.GOOGLE_TOKEN_PATH)


def _service():
    if not configured():
        raise CalendarUnavailable("Google Calendar is not set up (GOOGLE_TOKEN_PATH)")
    try:
        with open(config.GOOGLE_TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
    except Exception as e:  # missing, empty or unreadable file
        raise CalendarUnavailable(f"Couldn't read the Google token: {e}") from e
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise CalendarUnavailable("The Google token is invalid. Re-authenticate in Task_Chore_Syncing.")
        try:
            creds.refresh(Request())  # in memory only
        except Exception as e:
            raise CalendarUnavailable(f"Google token refresh failed: {e}") from e
    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=15))
    return build("calendar", "v3", http=http, cache_discovery=False)


def _meals_calendar_id(svc) -> str:
    known = store.get_setting("meals_calendar_id")
    entries = svc.calendarList().list(minAccessRole="writer").execute().get("items", [])
    ids = {e["id"] for e in entries}
    if known in ids:
        return known
    for e in entries:
        if e.get("summary") == config.MEALS_CALENDAR_NAME:
            store.set_setting("meals_calendar_id", e["id"])
            return e["id"]
    made = svc.calendars().insert(body={"summary": config.MEALS_CALENDAR_NAME, "timeZone": TOWN_TZ,
                                        "description": "Meals planned in Sous"}).execute()
    store.set_setting("meals_calendar_id", made["id"])
    return made["id"]


def dinner_time() -> str:
    return store.get_setting("dinner_time") or config.DEFAULT_DINNER_TIME


def event_body(item: dict) -> dict:
    """The calendar event for one planned meal: 'Cook: <title>' at its time, with a link to cook mode."""
    r = item["recipe"]
    hhmm = item.get("cook_time") or dinner_time()
    start = datetime.fromisoformat(f"{item['cook_date']}T{hhmm}:00")
    minutes = min(180, max(60, (r.get("prep_min") or 0) + (r.get("cook_min") or 0)))
    end = start + timedelta(minutes=minutes)
    link = f"{config.SOUS_URL.rstrip('/')}/cook/{r['id']}?servings={item['servings']}"
    return {
        "summary": f"Cook: {r['title']}",
        "description": f"Serves {item['servings']}\nCook mode: {link}\nRecipe: {config.SOUS_URL.rstrip('/')}/recipes/{r['id']}",
        "start": {"dateTime": start.isoformat(), "timeZone": TOWN_TZ},
        "end": {"dateTime": end.isoformat(), "timeZone": TOWN_TZ},
        "extendedProperties": {"private": {"sous": "1", "sous_item": str(item["id"])}},
    }


def _same(existing: dict, wanted: dict) -> bool:
    return (existing.get("summary") == wanted["summary"] and existing.get("description") == wanted["description"]
            and existing["start"].get("dateTime", "")[:16] == wanted["start"]["dateTime"][:16]
            and existing["end"].get("dateTime", "")[:16] == wanted["end"]["dateTime"][:16])


def sync_week(week_start: str, svc=None) -> dict:
    """Make the Meals calendar match this week's plan. Touches only events Sous created."""
    svc = svc or _service()
    cal = _meals_calendar_id(svc)
    start = datetime.fromisoformat(f"{week_start}T00:00:00")
    window = {"timeMin": start.isoformat() + "-12:00", "timeMax": (start + timedelta(days=8)).isoformat() + "+12:00"}
    existing = {}
    token = None
    while True:
        page = svc.events().list(calendarId=cal, singleEvents=True, privateExtendedProperty=MARK, pageToken=token, **window).execute()
        for e in page.get("items", []):
            existing[e["extendedProperties"]["private"].get("sous_item")] = e
        token = page.get("nextPageToken")
        if not token:
            break
    wanted = {str(i["id"]): i for i in store.plan_items(week_start) if i["cook_date"] and i["recipe"]}
    out = {"created": 0, "updated": 0, "deleted": 0, "unchanged": 0}
    for item_id, item in wanted.items():
        body = event_body(item)
        have = existing.get(item_id)
        if not have:
            svc.events().insert(calendarId=cal, body=body).execute()
            out["created"] += 1
        elif _same(have, body):
            out["unchanged"] += 1
        else:
            svc.events().patch(calendarId=cal, eventId=have["id"], body=body).execute()
            out["updated"] += 1
    for item_id, e in existing.items():
        if item_id not in wanted:
            svc.events().delete(calendarId=cal, eventId=e["id"]).execute()
            out["deleted"] += 1
    return out


_busy_cache: dict[str, tuple[float, dict]] = {}


def busy_by_day(week_start: str, svc=None, ttl: int = 300) -> dict[str, list[str]]:
    """What is already on the household's calendars each day (everything except the Meals calendar)."""
    hit = _busy_cache.get(week_start)
    if hit and time.time() - hit[0] < ttl and svc is None:
        return hit[1]
    svc = svc or _service()
    meals = store.get_setting("meals_calendar_id")
    start = datetime.fromisoformat(f"{week_start}T00:00:00")
    window = {"timeMin": start.isoformat() + "-12:00", "timeMax": (start + timedelta(days=7)).isoformat() + "+12:00"}
    days: dict[str, list[str]] = {d: [] for d in store.week_days(week_start)}
    for cal in svc.calendarList().list().execute().get("items", []):
        if cal["id"] == meals or cal.get("selected") is False:
            continue
        for e in svc.events().list(calendarId=cal["id"], singleEvents=True, orderBy="startTime", maxResults=100, **window).execute().get("items", []):
            if e.get("status") == "cancelled" or e.get("transparency") == "transparent":
                continue
            s = e["start"]
            if "dateTime" in s:
                dt = datetime.fromisoformat(s["dateTime"])
                day, label = dt.date().isoformat(), f"{dt.strftime('%-I:%M %p')} {e.get('summary', 'busy')}"
            else:
                day, label = s["date"], f"all day: {e.get('summary', 'busy')}"
            if day in days and len(days[day]) < 6:
                days[day].append(label)
    _busy_cache[week_start] = (time.time(), days)
    return days
