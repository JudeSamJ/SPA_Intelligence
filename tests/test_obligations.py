"""Obligation watcher: pure date logic with an injected as_of. Dates are worked out by hand in the comments."""
from datetime import date

import pytest

from app import config
from app import obligations as ob
from app.schema import DatedClause, Milestone
from tests.test_statute_gap import contract


def M(name, pct, d):
    return Milestone(name=name, percent=pct, due_date=d, source_page=1, source_quote=f"{name} row")


def make():
    c = contract(handover=date(2027, 6, 30), grace=60,
                 plan=[M("Booking", 20, date(2025, 3, 15)), M("First", 30, date(2025, 9, 15)), M("Undated", 50, None)])
    c.dated_clauses = [
        DatedClause(kind="notice_deadline", description="Inspection", amount=14, unit="days", anchor="notice_of_completion",
                    source_page=2, source_quote="Within fourteen (14) days"),
        DatedClause(kind="defect_liability", description="Defects period", amount=12, unit="months", anchor="notice_of_completion",
                    source_page=2, source_quote="twelve (12) months"),
        DatedClause(kind="other", description="Signing based", amount=10, unit="days", anchor="signing_date",
                    source_page=2, source_quote="ten days"),
    ]
    return c


def by_label(rows, text):
    return next(r for r in rows if text in r["label"])


def test_derivation_dates_by_hand():
    rows = ob.obligations_for(make(), "c1", "n", date(2025, 1, 1))
    # grace end = 2027-06-30 + 60 days = 2027-08-29 (July 31 + Aug 29 = 60)
    assert by_label(rows, "Grace period ends")["due_date"] == "2027-08-29"
    # inspection = handover + 14 days = 2027-07-14 ; defects = handover + 12 months = 2028-06-30
    assert by_label(rows, "Inspection")["due_date"] == "2027-07-14"
    assert by_label(rows, "Defects period")["due_date"] == "2028-06-30"
    assert by_label(rows, "Inspection")["assumed_anchor"]                       # flagged: real notice date unknown
    # signing-based: first payment date 2025-03-15 + 10 days = 2025-03-25
    assert by_label(rows, "Signing based")["due_date"] == "2025-03-25"
    assert not any("Undated" in r["label"] for r in rows)                       # undated milestone has no obligation
    assert all(r["evidence"]["quote"] for r in rows)


def test_add_months_end_of_month():
    assert ob.add_months(date(2025, 1, 31), 1) == date(2025, 2, 28)
    assert ob.add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert ob.add_months(date(2027, 11, 30), 3) == date(2028, 2, 29)


@pytest.mark.parametrize("as_of,label,event,days", [
    (date(2025, 3, 1), "Booking", "due_soon", 14),             # due 03-15, 14 days away -> boundary included
    (date(2025, 2, 28), "Booking", None, 15),                  # 15 days away -> not yet
    (date(2025, 3, 16), "Booking", "overdue", -1),
    (date(2025, 3, 15), "Booking", "due_soon", 0),             # due today
    (date(2027, 4, 1), "Contractual handover", "handover_approaching", 90),   # 04-01 -> 06-30 = 29+31+30 = 90
    (date(2027, 3, 31), "Contractual handover", None, 91),
    (date(2027, 7, 30), "Grace period ends", "grace_expiring", 30),            # 07-30 -> 08-29 = 30 days
    (date(2027, 6, 30), "Inspection", "notice_deadline", 14),
    (date(2027, 7, 15), "Inspection", None, -1),               # passed
])
def test_event_classification(as_of, label, event, days):
    r = by_label(ob.obligations_for(make(), "c1", "n", as_of), label)
    assert r["event_type"] == event and r["days_until"] == days
    if event is None:
        assert r["status"] in ("past", "upcoming") and r["severity"] == "none"


def test_filters():
    rows = ob.obligations_for(make(), "c1", "n", date(2025, 3, 10))
    soon = ob.filter_obligations(rows, within_days=30)
    assert {r["label"].split(" (")[0] for r in soon} >= {"Booking"} and all(r["days_until"] <= 30 for r in soon)
    assert [r["status"] for r in ob.filter_obligations(rows, status="due_soon")] == ["due_soon"]


@pytest.fixture
def alerts_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ALERTS_PATH", tmp_path / "alerts.json")
    sent = []

    class N:
        def notify(self, a):
            sent.append(a["id"])

    monkeypatch.setattr(ob, "NOTIFIER", N())
    return sent


def test_recompute_creates_acks_and_removes_stale(alerts_file):
    c = make()
    r1 = ob.recompute([("c1", "n", c)], date(2025, 3, 16))
    assert r1["new"] >= 1 and len(alerts_file) == r1["new"]
    alerts = ob.load_alerts()
    over = [a for a in alerts if a["event_type"] == "overdue"]
    assert over and over[0]["severity"] == "high" and "1 day(s) overdue" in over[0]["message"]
    # idempotent: same as_of again creates nothing new
    assert ob.recompute([("c1", "n", c)], date(2025, 3, 16))["new"] == 0
    # ack, then move far away: acked alert stays (history), unacked ones disappear
    ob.ack(over[0]["id"])
    ob.recompute([("c1", "n", c)], date(2026, 1, 1))
    left = ob.load_alerts()
    assert any(a["id"] == over[0]["id"] and a["acked"] for a in left)
    assert not any(a["event_type"] == "due_soon" for a in left)
    assert ob.ack("nope") is None


def test_logging_notifier_only_no_external_channel():
    import inspect
    src = inspect.getsource(ob)
    assert "smtp" not in src.lower() and "twilio" not in src.lower() and "whatsapp" not in src.lower().replace("whatsapp or", "")
    assert isinstance(ob.NOTIFIER, ob.LoggingNotifier)
