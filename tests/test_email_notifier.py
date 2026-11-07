"""Direct email over SMTP (no Power Automate). The SMTP server is a recording fake; the message is a real, parsed email."""
import pytest

from app import notifiers
from app.notifiers import EmailNotifier, configured_hook, email_notifier_from_env

CONTRACT = {"contract": {"contract_id": "a" * 64, "contract_name": "sample_a.pdf", "unit_id": "MCR-1204", "buyer": "Sample Buyer",
                         "currency": "AED", "price": 2450000, "handover_date": "2027-06-30", "jurisdiction": "ae_dubai",
                         "milestones": 5, "payment_plan_percent_sum": 100.0, "warnings": 0, "needs_review": 1,
                         "plan": [{"name": "Booking", "percent": 20, "due_date": "2025-03-15"}]}}
ALERT = {"alert": {"id": "x", "contract_id": "a" * 64, "contract_name": "sample_a.pdf", "event_type": "overdue", "severity": "high",
                   "message": "Overdue", "due_date": "2026-03-15", "days_until": -10, "label": "Second Instalment", "page": 6}}


class FakeSMTP:
    log: list = []
    fail_login = False

    def __init__(self, host, port, timeout=0):
        self.host, self.port = host, port
        FakeSMTP.log.append(("connect", host, port))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        FakeSMTP.log.append(("starttls",))

    def login(self, user, password):
        if FakeSMTP.fail_login:
            raise RuntimeError("535 bad credentials for secret-user")
        FakeSMTP.log.append(("login", user, password))

    def send_message(self, msg):
        FakeSMTP.log.append(("send", msg))


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeSMTP.log, FakeSMTP.fail_login = [], False
    monkeypatch.setattr(EmailNotifier, "smtp_factory", FakeSMTP)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://spa.example.com")
    monkeypatch.setenv("ALERT_WEBHOOK_SECRET", "s" * 24)
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_SECURITY", "ALERT_EMAIL_TO"):
        monkeypatch.delenv(k, raising=False)


def sent():
    return [x[1] for x in FakeSMTP.log if x[0] == "send"]


def test_sends_a_multipart_designed_email_with_starttls_and_login():
    n = EmailNotifier("smtp.example.com", 587, "u@example.com", "pw", "u@example.com", ["a@x.co", "b@x.co"])
    assert n.post("contract_ready", CONTRACT) is True
    assert [x[0] for x in FakeSMTP.log] == ["connect", "starttls", "login", "send"]
    m = sent()[0]
    assert m["To"] == "a@x.co, b@x.co" and "MCR-1204" in m["Subject"] and "u@example.com" in m["From"]
    assert m.is_multipart()
    html = m.get_body(preferencelist=("html",)).get_content()
    text = m.get_body(preferencelist=("plain",)).get_content()
    assert "With regards" in html and "https://spa.example.com/api/card.png?d=" in html and "MCR-1204" in text


def test_every_event_kind_builds_an_email():
    n = EmailNotifier("h", 587, "", "", "from@x.co", ["to@x.co"], security="none")
    assert n.post("alert", ALERT) and n.post("review_needed", {"review": {"contract_id": "a" * 64, "contract_name": "s.pdf", "field": "price",
                                                                           "status": "partial", "confidence": 0.8, "page": 3}})
    assert [x[0] for x in FakeSMTP.log].count("starttls") == 0 and [x[0] for x in FakeSMTP.log].count("login") == 0
    assert len(sent()) == 2 and n.post("unknown_kind", {}) is False


def test_failure_returns_false_and_never_leaks_the_reason(caplog):
    FakeSMTP.fail_login = True
    n = EmailNotifier("h", 587, "secret-user", "pw", "f@x.co", ["t@x.co"])
    with caplog.at_level("WARNING"):
        assert n.post("alert", ALERT) is False
    assert "secret-user" not in caplog.text and "RuntimeError" in caplog.text and not sent()


def test_no_recipients_is_rejected():
    with pytest.raises(ValueError):
        EmailNotifier("h", 587, "", "", "f@x.co", [])


def test_env_configuration(monkeypatch):
    assert email_notifier_from_env() is None and configured_hook() is None
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    assert email_notifier_from_env() is None                     # no recipients yet
    monkeypatch.setenv("ALERT_EMAIL_TO", "a@x.co; b@x.co ,c@x.co")
    monkeypatch.setenv("SMTP_USER", "me@x.co")
    n = email_notifier_from_env()
    assert n.recipients == ["a@x.co", "b@x.co", "c@x.co"] and n.port == 587 and n.sender == "me@x.co" and n.security == "starttls"
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    assert email_notifier_from_env().port == 465
    monkeypatch.setenv("SMTP_SECURITY", "bogus")
    assert email_notifier_from_env().security == "starttls"


def test_contract_ready_goes_out_by_email_alone(monkeypatch):
    from datetime import date
    from app.extract import extract_contract
    from tests.fakes import FakeClient, oracle_input
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "samples" / "sample_a.pdf"
    c = extract_contract(p.read_bytes(), p.name, client=FakeClient(oracle_input(p)), use_cache=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ALERT_EMAIL_TO", "a@x.co")
    assert notifiers.notify_contract_ready("a" * 64, p.name, c) is True
    assert len(sent()) == 1 and c.unit_id.value in sent()[0]["Subject"]


def test_webhook_and_email_both_fire_and_one_failing_does_not_stop_the_other(monkeypatch):
    class Boom:
        def post(self, kind, data):
            return False
    hooks = notifiers.Hooks([Boom(), EmailNotifier("h", 587, "", "", "f@x.co", ["t@x.co"], security="none")])
    assert hooks.post("alert", ALERT) is True and len(sent()) == 1
