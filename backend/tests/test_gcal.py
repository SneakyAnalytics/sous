from app import config, gcal, store


class Exec:
    def __init__(self, value=None, fn=None):
        self.value, self.fn = value, fn

    def execute(self):
        return self.fn() if self.fn else self.value


class FakeEvents:
    def __init__(self, svc):
        self.svc = svc

    def list(self, calendarId, **kw):
        store_ = self.svc.events_by_cal.setdefault(calendarId, {})
        items = list(store_.values())
        if kw.get("privateExtendedProperty"):
            items = [e for e in items if e.get("extendedProperties", {}).get("private", {}).get("sous")]
        return Exec({"items": items})

    def insert(self, calendarId, body):
        self.svc.n += 1
        e = {**body, "id": f"e{self.svc.n}"}
        self.svc.events_by_cal.setdefault(calendarId, {})[e["id"]] = e
        self.svc.calls.append(("insert", e["id"]))
        return Exec(e)

    def patch(self, calendarId, eventId, body):
        self.svc.events_by_cal[calendarId][eventId].update(body)
        self.svc.calls.append(("patch", eventId))
        return Exec({})

    def delete(self, calendarId, eventId):
        del self.svc.events_by_cal[calendarId][eventId]
        self.svc.calls.append(("delete", eventId))
        return Exec({})


class FakeService:
    def __init__(self, calendars=None):
        self.calendars_ = calendars if calendars is not None else [{"id": "primary", "summary": "Jake"}]
        self.events_by_cal, self.calls, self.n = {}, [], 0

    def calendarList(self):
        outer = self
        return type("CL", (), {"list": lambda s, **kw: Exec({"items": outer.calendars_})})()

    def calendars(self):
        outer = self

        def insert(body):
            def go():
                outer.calendars_.append({"id": "meals-id", "summary": body["summary"]})
                return {"id": "meals-id"}
            return Exec(fn=go)
        return type("C", (), {"insert": staticmethod(lambda body: insert(body))})()

    def events(self):
        return FakeEvents(self)


def plan_one(client, day_index=3):
    rid = client.post("/recipes", json={"title": "Chili Mac", "servings": 4, "prep_min": 15, "cook_min": 35,
                                        "ingredients": [], "steps": []}).json()["id"]
    week = store.planning_week_start()
    day = store.week_days(week)[day_index]
    client.post(f"/plan/{week}/items", json={"recipe_id": rid, "cook_date": day})
    return week, day, rid


def test_sync_creates_updates_and_removes_only_our_events(client):
    week, day, rid = plan_one(client)
    svc = FakeService()
    # an unrelated event on the Meals calendar must never be touched
    assert gcal.sync_week(week, svc) == {"created": 1, "updated": 0, "deleted": 0, "unchanged": 0}
    svc.events_by_cal["meals-id"]["foreign"] = {"id": "foreign", "summary": "Not ours", "start": {}, "end": {}}
    ev = next(e for e in svc.events_by_cal["meals-id"].values() if e["id"] != "foreign")
    # dinner at 5:30 PM and 50 minutes of work: the event runs from the start-by time to half an hour after eating
    assert ev["summary"] == "Cook: Chili Mac" and ev["start"]["dateTime"].startswith(f"{day}T16:40")
    assert f"/cook/{rid}?servings=4" in ev["description"] and "Start by 4:40 PM, eat at 5:30 PM" in ev["description"]
    assert ev["end"]["dateTime"].startswith(f"{day}T18:00")
    assert ev["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}

    assert gcal.sync_week(week, svc)["unchanged"] == 1
    item = store.plan_items(week)[0]
    store.update_plan_item(item["id"], {"cook_time": "18:45"})
    assert gcal.sync_week(week, svc)["updated"] == 1
    assert ev["start"]["dateTime"].startswith(f"{day}T17:55")  # eat at 6:45 PM now, so start 50 minutes earlier

    store.remove_plan_item(item["id"])
    assert gcal.sync_week(week, svc)["deleted"] == 1
    assert "foreign" in svc.events_by_cal["meals-id"] and len(svc.events_by_cal["meals-id"]) == 1


def test_meals_calendar_is_reused_not_recreated(client):
    week, *_ = plan_one(client)
    svc = FakeService(calendars=[{"id": "existing", "summary": config.MEALS_CALENDAR_NAME}])
    gcal.sync_week(week, svc)
    gcal.sync_week(week, svc)
    assert store.get_setting("meals_calendar_id") == "existing"
    assert [c["summary"] for c in svc.calendars_] == [config.MEALS_CALENDAR_NAME]


def test_busy_times_skip_the_meals_calendar(client):
    week = store.planning_week_start()
    day = store.week_days(week)[2]
    svc = FakeService(calendars=[{"id": "primary", "summary": "Jake"}, {"id": "meals-id", "summary": "Meals"}])
    store.set_setting("meals_calendar_id", "meals-id")
    svc.events_by_cal["primary"] = {
        "a": {"id": "a", "summary": "Kadie yoga", "start": {"dateTime": f"{day}T18:00:00-08:00"}, "end": {}},
        "b": {"id": "b", "summary": "Holiday", "start": {"date": day}, "end": {}},
        "c": {"id": "c", "summary": "Free-ish", "transparency": "transparent", "start": {"date": day}, "end": {}}}
    svc.events_by_cal["meals-id"] = {"m": {"id": "m", "summary": "Cook: X", "start": {"date": day}, "end": {}}}
    assert gcal.busy_by_day(week, svc)[day] == ["6:00 PM Kadie yoga", "all day: Holiday"]


def test_endpoints_when_not_configured(client):
    week, *_ = plan_one(client)
    assert client.get("/calendar/status").json()["configured"] is False
    assert client.post(f"/plan/{week}/calendar-sync").status_code == 503
    item = client.get(f"/plan/{week}").json()["items"][0]
    assert client.patch(f"/plan/items/{item['id']}", json={"cook_time": "7pm"}).status_code == 422
    assert client.patch(f"/plan/items/{item['id']}", json={"cook_time": "19:00"}).status_code == 200
