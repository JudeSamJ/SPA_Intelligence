"""Designed HTML emails and image cards for the Power Automate webhook.

The server builds the whole email (subject + table-based HTML that email clients can render + a hosted hero image), so the flow only
needs ONE "Send an email" action. Nothing here reads contract text: cards show headline facts (unit, price, dates, plan percentages),
never quotes.

Image cards are drawn with Pillow from a SMALL SIGNED payload carried in the URL (HMAC with ALERT_WEBHOOK_SECRET, 30-day expiry):
stateless (survives Render restarts), public (an email client cannot log in) and not abusable (nobody can make the server draw arbitrary
images without the secret).

Settings: PUBLIC_BASE_URL (links, logo and image host), ALERT_WEBHOOK_SECRET (signs card URLs), EMAIL_SENDER_NAME, EMAIL_SENDER_TITLE.
"""
from __future__ import annotations

import base64
import functools
import hashlib
import hmac
import html
import io
import json
import os
import random
import re
import time
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import config

ASSETS = config.ROOT / "assets"
NAVY, VIOLET, PLUM, WARM, GOLD, TERRA = "#0b1b2b", "#2d2a5a", "#6b3a68", "#f0a35a", "#d4a24c", "#b5532e"
CREAM, INK, MUTED, OK, WARN_C, DANGER, BLUE = "#f3ead3", "#1f1912", "#7a6f5d", "#2e7d5b", "#b7791f", "#b03a2e", "#2d78c0"
SEG = ["#d4a24c", "#b5532e", "#6b3a68", "#2d78c0", "#2e7d5b", "#8a6d3b", "#4a4f8a", "#a8584a"]
SEVERITY = {"high": (("#5c1624", "#b03a2e", "#e0703a"), "HIGH"), "medium": (("#5a3d0e", "#b7791f", "#f0a35a"), "MEDIUM"),
            "low": (("#1b3a66", "#2d78c0", "#7fb3e6"), "LOW")}
EVENTS = {"overdue": "OVERDUE", "due_soon": "DUE SOON", "grace_expiring": "GRACE ENDING", "handover_approaching": "HANDOVER SOON",
          "notice_deadline": "NOTICE DEADLINE"}
JURISDICTIONS = {"ae_dubai": "Dubai (UAE)", "in_rera": "India (RERA)"}
S = 2                                     # supersampling factor for smooth edges
CARD_DAYS = 30


class CardError(ValueError):
    pass


# ------------------------------------------------------------------ settings
def settings() -> dict:
    return {"base": os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/"), "secret": os.environ.get("ALERT_WEBHOOK_SECRET", ""),
            "name": os.environ.get("EMAIL_SENDER_NAME", "").strip() or "The SPA Intelligence team",
            "title": os.environ.get("EMAIL_SENDER_TITLE", "").strip() or "Unlimited Innovations India Pvt. Ltd"}


# ------------------------------------------------------------------ signed card URLs
def _key(secret: str) -> bytes:
    return hmac.new(secret.encode(), b"spa-card-v1", hashlib.sha256).digest()


def sign(secret: str, d: str) -> str:
    return hmac.new(_key(secret), d.encode(), hashlib.sha256).hexdigest()[:32]


def card_params(secret: str, payload: dict, now: float | None = None) -> tuple[str, str]:
    p = {**payload, "exp": int((now or time.time()) + CARD_DAYS * 86400)}
    d = base64.urlsafe_b64encode(json.dumps(p, separators=(",", ":"), ensure_ascii=False).encode()).rstrip(b"=").decode()
    return d, sign(secret, d)


def decode_card(d: str, sig: str, secret: str, now: float | None = None) -> dict:
    if not secret:
        raise CardError("cards are not enabled")
    if not hmac.compare_digest(sign(secret, d), sig or ""):
        raise CardError("bad signature")
    try:
        p = json.loads(base64.urlsafe_b64decode(d + "=" * (-len(d) % 4)))
    except (ValueError, UnicodeDecodeError):
        raise CardError("bad payload") from None
    if not isinstance(p, dict) or p.get("k") not in ("c", "a", "r"):
        raise CardError("bad payload")
    if (now or time.time()) > float(p.get("exp", 0)):
        raise CardError("expired")
    return p


# ------------------------------------------------------------------ small helpers
def _s(v, n=60) -> str:
    return str(v if v is not None else "")[:n]


def money(cur, v) -> str:
    try:
        return f"{cur or ''} {float(v):,.0f}".strip()
    except (TypeError, ValueError):
        return "not stated"


def short_date(iso) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
        return f"{d.day} {d.strftime('%b %Y')}"
    except ValueError:
        return "not stated" if not iso else _s(iso, 14)


def pretty_field(f) -> str:
    return _s(f, 40).replace("_", " ").replace(".", " #").strip().capitalize()


def _f(v, default=0.0) -> float:
    try:
        x = float(v)
        return x if x == x and abs(x) != float("inf") else default      # NaN / inf are not drawable
    except (TypeError, ValueError, OverflowError):
        return default


def _d(x) -> dict:
    return x if isinstance(x, dict) else {}


def _i(v, default=0) -> int:
    try:
        return int(_f(v, default))
    except (TypeError, ValueError, OverflowError):
        return default


def pct(v) -> str:
    try:
        return f"{float(v):g}%"
    except (TypeError, ValueError):
        return "-"


# ------------------------------------------------------------------ drawing
@functools.lru_cache(maxsize=64)
def font(face: str, size: int, wght: int) -> ImageFont.FreeTypeFont:
    name = "fraunces" if face == "serif" else "inter"
    try:
        f = ImageFont.truetype(str(ASSETS / "fonts" / f"{name}-latin-wght-normal.woff2"), size * S)
        f.set_variation_by_axes([wght])
        return f
    except Exception:  # noqa: BLE001  (fall back rather than failing to send an email)
        try:                                              # reportlab ships the Bitstream Vera fonts, so this is always present
            import reportlab
            vera = Path(reportlab.__file__).parent / "fonts" / ("VeraBd.ttf" if wght >= 600 else "Vera.ttf")
            return ImageFont.truetype(str(vera), size * S)
        except Exception:  # noqa: BLE001
            return ImageFont.load_default()


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def gradient(draw: ImageDraw.ImageDraw, box, stops):
    x0, y0, x1, y1 = [v * S for v in box]
    cols = [_rgb(c) for c in stops]
    h = max(1, y1 - y0)
    for y in range(h):
        t = y / h * (len(cols) - 1)
        i = min(int(t), len(cols) - 2)
        draw.line([(x0, y0 + y), (x1, y0 + y)], fill=_lerp(cols[i], cols[i + 1], t - i))


def rr(draw, box, r, fill, outline=None, width=0):
    draw.rounded_rectangle([v * S for v in box], radius=r * S, fill=fill, outline=outline, width=width * S)


def text(draw, xy, s, f, fill, anchor="la"):
    draw.text((xy[0] * S, xy[1] * S), s, font=f, fill=fill, anchor=anchor)


def fit(s: str, f, max_w: int) -> str:
    """Truncate with an ellipsis so text never overflows its tile."""
    if f.getlength(s) <= max_w * S:
        return s
    while s and f.getlength(s + "...") > max_w * S:
        s = s[:-1]
    return s.rstrip() + "..."


def pill(draw, x, y, label, fill, fg, size=20, pad=18, h=40, right=False):
    f = font("sans", size, 700)
    w = int(f.getlength(label) / S) + pad * 2
    x0 = x - w if right else x
    rr(draw, (x0, y, x0 + w, y + h), h // 2, fill)
    text(draw, (x0 + w / 2, y + h / 2 + 1), label, f, fg, "mm")
    return w


def dot(draw, cx, cy, r, fill):
    draw.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S], fill=fill)


def sky_header(img, draw, w, h, stops, seed=7):
    """Dusk gradient, stars and the stepped-tower skyline, like the site's hero."""
    gradient(draw, (0, 0, w, h), stops)
    r = random.Random(seed)
    for _ in range(46):
        sx, sy, sr = r.random() * w, r.random() * h * 0.55, r.choice((1, 1, 1.5, 2))
        dot(draw, sx, sy, sr, (255, 244, 220, int(80 + r.random() * 120)))
    base = h
    x = -20
    while x < w:                                              # generic towers
        bw, bh = r.randint(46, 98), r.randint(26, 92)
        rr(draw, (x, base - bh, x + bw, base + 10), 2, (21, 15, 36, 205))
        x += bw + r.randint(4, 14)
    tx = int(w * 0.8)                                         # the stepped tapering tower
    tiers = [(60, 52), (46, 52), (36, 50), (26, 50), (16, 46), (8, 40)]
    y = base
    for tw, th in tiers:
        y -= th
        rr(draw, (tx - tw // 2, y, tx + tw // 2, y + th + 2), 1, (21, 15, 36, 245))
    draw.rectangle([(tx - 1) * S, (y - 54) * S, (tx + 1) * S, y * S], fill=(21, 15, 36, 245))
    for i in range(7):                                        # a few lit windows
        wy = base - 30 - i * 26
        if i % 2 == 0:
            draw.rectangle([(tx - 4) * S, wy * S, (tx + 4) * S, (wy + 4) * S], fill=(246, 213, 138, 220))


def new_canvas(w, h):
    img = Image.new("RGBA", (w * S, h * S), (255, 255, 255, 255))
    return img, ImageDraw.Draw(img, "RGBA")


def finish(img) -> bytes:
    out = img.convert("RGB").resize((img.width // S, img.height // S), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def brand(draw, w, light=True):
    dot(draw, 70, 56, 9, GOLD)
    dot(draw, 70, 56, 4, NAVY)
    text(draw, (92, 56), "SPA Intelligence", font("serif", 32, 700), CREAM, "lm")


def footer(draw, w, y):
    text(draw, (w / 2, y), "Decision support, not legal advice.", font("sans", 18, 500), MUTED, "mm")


def tile(draw, x, y, w, label, value, sub=""):
    text(draw, (x, y), label.upper(), font("sans", 17, 700), MUTED)
    f = font("sans", 31, 700)
    text(draw, (x, y + 30), fit(value, f, w), f, NAVY)
    if sub:
        text(draw, (x, y + 76), fit(sub, font("sans", 18, 500), w), font("sans", 18, 500), MUTED)


# ------------------------------------------------------------------ the three cards
def render_contract(d: dict) -> bytes:
    W, H = 1200, 640
    img, draw = new_canvas(W, H)
    sky_header(img, draw, W, 300, (VIOLET, PLUM, WARM), 11)
    brand(draw, W)
    pill(draw, W - 56, 36, "CONTRACT READY", GOLD, INK, 21, right=True)
    text(draw, (56, 118), fit(_s(d.get("u"), 30) or "Contract", font("serif", 96, 800), 760), font("serif", 96, 800), CREAM)
    sub = " · ".join(x for x in (_s(d.get("b"), 40), _s(d.get("n"), 40)) if x)
    text(draw, (58, 236), fit(sub, font("sans", 28, 500), 1050), font("sans", 28, 500), (243, 234, 211, 215))
    rr(draw, (24, 276, W - 24, H - 22), 30, "#fffdf8", "#e8dfc9", 2)
    cur = d.get("cur")
    cols = [("Price", money(cur, d.get("p")), ""), ("Handover", short_date(d.get("h")), ""),
            ("Jurisdiction", JURISDICTIONS.get(d.get("j"), _s(d.get("j"), 20) or "Not stated"), ""),
            ("Milestones", f"{_i(d.get('m'))}", f"plan totals {pct(d.get('s'))}")]
    cw = (W - 112) // 4
    for i, (lab, val, sub_) in enumerate(cols):
        tile(draw, 56 + i * cw, 306, cw - 24, lab, val, sub_)
    # payment plan bar
    plan = [p for p in (d.get("pl") or []) if isinstance(p, list) and len(p) >= 2][:10]
    text(draw, (56, 418), "PAYMENT PLAN", font("sans", 17, 700), MUTED)
    bx0, bx1, by, bh = 56, W - 56, 448, 46
    rr(draw, (bx0, by, bx1, by + bh), 14, "#efe7d4")
    total_w, x = bx1 - bx0, bx0
    for i, p in enumerate(plan):
        sw = max(0, total_w * min(max(_f(p[1]), 0), 100) / 100)
        if sw < 1:
            continue
        seg = (x, by, x + sw - 3, by + bh)
        rr(draw, seg, 12 if sw > 30 else 4, SEG[i % len(SEG)])
        if sw > 78:
            text(draw, ((seg[0] + seg[2]) / 2, by + bh / 2 + 1), pct(p[1]), font("sans", 22, 700), "#ffffff", "mm")
        if sw > 120:
            text(draw, (x + 4, by + bh + 12), short_date(p[2] if len(p) > 2 else ""), font("sans", 17, 500), MUTED)
        x += sw
    w_, r_ = _i(d.get("w")), _i(d.get("r"))
    y = H - 82
    pill(draw, 56, y, f"{w_} warning{'s' if w_ != 1 else ''}", "#e5f2ea" if not w_ else "#fbecd6", OK if not w_ else WARN_C, 19, 16, 38)
    pill(draw, 56 + 190, y, f"{r_} to review", "#e5f2ea" if not r_ else "#fbecd6", OK if not r_ else WARN_C, 19, 16, 38)
    text(draw, (W - 56, y + 19), "Decision support, not legal advice.", font("sans", 18, 500), MUTED, "rm")
    return finish(img)


def render_alert(d: dict) -> bytes:
    W, H = 1200, 470
    stops, sev_label = SEVERITY.get(d.get("sev"), SEVERITY["medium"])
    img, draw = new_canvas(W, H)
    sky_header(img, draw, W, 220, stops, 5)
    brand(draw, W)
    pill(draw, W - 56, 36, EVENTS.get(d.get("ev"), "ALERT"), "#fffdf8", INK, 21, right=True)
    tf = font("serif", 60, 700)
    text(draw, (56, 104), fit(_s(d.get("lab"), 70) or "Obligation", tf, 1090), tf, CREAM)
    rr(draw, (24, 196, W - 24, H - 22), 30, "#fffdf8", "#e8dfc9", 2)
    days = d.get("d")
    if isinstance(days, (int, float)):
        big, cap = (str(abs(_i(days))), "days overdue" if days < 0 else "days left") if days != 0 else ("0", "due today")
    else:
        big, cap = "-", ""
    col = DANGER if (isinstance(days, (int, float)) and days < 0) else WARN_C
    text(draw, (60, 222), big, font("serif", 128, 800), col)
    bw = font("serif", 128, 800).getlength(big) / S
    text(draw, (60 + bw + 18, 318), cap, font("sans", 30, 600), MUTED)
    rows = [("Contract", _s(d.get("n"), 36)), ("Due date", short_date(d.get("due"))), ("Severity", sev_label.capitalize()),
            ("Source page", _s(d.get("pg"), 6) or "-")]
    for i, (k, v) in enumerate(rows):
        yy = 232 + i * 46
        text(draw, (700, yy), k.upper(), font("sans", 16, 700), MUTED)
        text(draw, (880, yy - 3), fit(v, font("sans", 27, 600), 270), font("sans", 27, 600), NAVY)
    footer(draw, W, H - 52)
    return finish(img)


def render_review(d: dict) -> bytes:
    W, H = 1200, 480
    img, draw = new_canvas(W, H)
    sky_header(img, draw, W, 210, (NAVY, VIOLET, PLUM), 3)
    brand(draw, W)
    pill(draw, W - 56, 36, "REVIEW NEEDED", WARM, INK, 21, right=True)
    tf = font("serif", 64, 800)
    text(draw, (56, 100), fit(pretty_field(d.get("f")), tf, 1090), tf, CREAM)
    rr(draw, (24, 186, W - 24, H - 22), 30, "#fffdf8", "#e8dfc9", 2)
    text(draw, (56, 214), fit(_s(d.get("n"), 60), font("sans", 26, 600), 1080), font("sans", 26, 600), MUTED)
    cf = d.get("cf")
    try:
        c = max(0.0, min(1.0, float(cf)))
    except (TypeError, ValueError):
        c = None
    st = _s(d.get("st"), 20) or "unverified"
    pill(draw, 56, 266, st.upper(), "#fbecd6" if st != "ungrounded" else "#f8dedb", WARN_C if st != "ungrounded" else DANGER, 20)
    text(draw, (W - 56, 286), f"Source page {_s(d.get('pg'), 6) or '-'}", font("sans", 26, 600), NAVY, "rm")
    text(draw, (56, 334), "CONFIDENCE", font("sans", 17, 700), MUTED)
    rr(draw, (56, 362, 656, 390), 14, "#efe7d4")
    if c is not None:
        rr(draw, (56, 362, 56 + max(16, 600 * c), 390), 14, OK if c >= 0.85 else WARN_C if c >= 0.5 else DANGER)
        text(draw, (680, 376), f"{c * 100:.0f}%", font("sans", 28, 700), NAVY, "lm")
    text(draw, (W - 56, 326), "Open the contract to see the highlighted source", font("sans", 20, 500), MUTED, "rm")
    footer(draw, W, H - 50)
    return finish(img)


RENDERERS = {"c": render_contract, "a": render_alert, "r": render_review}


STR_KEYS = {"u": 30, "b": 40, "n": 60, "cur": 4, "j": 20, "lab": 70, "ev": 24, "sev": 8, "f": 40, "st": 20, "due": 12, "h": 12, "pg": 6}
FLOAT_KEYS = ("p", "s", "cf")
INT_KEYS = ("m", "w", "r")


def clean_payload(p: dict) -> dict:
    """Coerce every field to a safe type and length, so nothing odd can break the drawing (or an email)."""
    out = {"k": p.get("k")}
    for k, n in STR_KEYS.items():
        v = p.get(k)
        out[k] = _s(v, n) if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ""
    for k in FLOAT_KEYS:
        out[k] = _f(p.get(k), None) if p.get(k) is not None else None
    for k in INT_KEYS:
        out[k] = _i(p.get(k))
    d = p.get("d")
    out["d"] = _i(d, None) if isinstance(d, (int, float)) and not isinstance(d, bool) and _f(d, None) is not None else None
    pl = p.get("pl") if isinstance(p.get("pl"), list) else []
    out["pl"] = [[_s(x[0], 24) if isinstance(x[0], (str, int, float)) else "", _f(x[1]), _s(x[2], 12) if isinstance(x[2], (str, int, float)) else ""]
                 for x in pl[:10] if isinstance(x, list) and len(x) >= 3]
    return out


def render_card(payload: dict) -> bytes:
    return RENDERERS[payload["k"]](clean_payload(payload))


# ------------------------------------------------------------------ event -> card payload
def card_payload(kind: str, data: dict) -> dict:
    if kind == "contract_ready":
        c = _d(data.get("contract"))
        return {"k": "c", "u": _s(c.get("unit_id"), 30), "b": _s(c.get("buyer"), 40), "n": _s(c.get("contract_name"), 40),
                "cur": _s(c.get("currency"), 4), "p": c.get("price"), "h": c.get("handover_date"), "j": _s(c.get("jurisdiction"), 20),
                "m": c.get("milestones"), "s": c.get("payment_plan_percent_sum"), "w": c.get("warnings"), "r": c.get("needs_review"),
                "pl": [[_s(p.get("name"), 24), p.get("percent"), p.get("due_date")] for p in (c.get("plan") if isinstance(c.get("plan"), list) else [])[:10] if isinstance(p, dict)]}
    if kind == "alert":
        a = _d(data.get("alert"))
        return {"k": "a", "n": _s(a.get("contract_name"), 40), "lab": _s(a.get("label"), 70), "ev": _s(a.get("event_type"), 24),
                "sev": _s(a.get("severity"), 8), "due": a.get("due_date"), "d": a.get("days_until"), "pg": a.get("page")}
    if kind == "review_needed":
        r = _d(data.get("review"))
        return {"k": "r", "n": _s(r.get("contract_name"), 60), "f": _s(r.get("field"), 40), "st": _s(r.get("status"), 20),
                "cf": r.get("confidence"), "pg": r.get("page")}
    raise CardError("unknown event")


# ------------------------------------------------------------------ HTML email
def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _row(label, value) -> str:
    return (f'<tr><td style="padding:9px 0;border-bottom:1px solid #eee6d2;font:600 12px Arial,Helvetica,sans-serif;color:#7a6f5d;'
            f'text-transform:uppercase;letter-spacing:.06em;width:38%;">{esc(label)}</td>'
            f'<td style="padding:9px 0;border-bottom:1px solid #eee6d2;font:600 15px Arial,Helvetica,sans-serif;color:#0b1b2b;">{esc(value)}</td></tr>')


def _button(href, label) -> str:
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:22px 0 4px;"><tr>'
            f'<td bgcolor="#b5532e" style="border-radius:999px;"><a href="{esc(href)}" target="_blank" '
            f'style="display:inline-block;padding:14px 30px;font:700 15px Arial,Helvetica,sans-serif;color:#ffffff;text-decoration:none;'
            f'border-radius:999px;">{esc(label)}</a></td></tr></table>')


def build_email(kind: str, data: dict, st: dict | None = None, local_dir: str | None = None) -> dict:
    """-> {subject, html, text, preheader, image_url}. `local_dir` makes image/logo references relative (for offline previews)."""
    st = st or settings()
    p = card_payload(kind, data)
    base, secret = st["base"], st["secret"]
    if local_dir is not None:
        image_url, logo_url = f"{local_dir}card_{kind}.png", f"{local_dir}logo.png"
    else:
        image_url = ""
        if base and secret:
            d, sig = card_params(secret, p)
            image_url = f"{base}/api/card.png?d={d}&sig={sig}"
        logo_url = f"{base}/api/brand/logo.png" if base else ""
    cid = ""
    if kind == "contract_ready":
        c = _d(data.get("contract"))
        cid = str(c.get("contract_id") or "")
        subject = f"Contract ready · {p['u'] or p['n']} · {p['n']}"
        preheader = f"{p['b']} · {money(p['cur'], p['p'])} · handover {short_date(p['h'])}"
        heading, intro = "Your contract has been read", ("The contract was extracted and every value is linked to the page and the text it came from. "
                                                           "Anything uncertain is queued for a human to review.")
        rows = [("Unit", p["u"]), ("Buyer", p["b"]), ("Price", money(p["cur"], p["p"])), ("Handover", short_date(p["h"])),
                ("Jurisdiction", JURISDICTIONS.get(p["j"], p["j"] or "Not stated")),
                ("Payment plan", f"{_i(p['m'])} milestones, totals {pct(p['s'])}"),
                ("Checks", f"{_i(p['w'])} warning(s), {_i(p['r'])} field(s) to review")]
        path, cta, alt = "terms", "Open the contract", f"Contract summary for {p['u']}: {money(p['cur'], p['p'])}, handover {short_date(p['h'])}"
        callout = None
    elif kind == "alert":
        a = _d(data.get("alert"))
        cid = str(a.get("contract_id") or "")
        ev = EVENTS.get(p["ev"], "ALERT").title()
        subject = f"{SEVERITY.get(p['sev'], SEVERITY['medium'])[1]} · {p['lab']} · {ev.lower()}"
        preheader = _s(a.get("message"), 110)
        heading, intro = f"{ev}: {p['lab']}", "A dated obligation in this contract needs attention."
        days = p["d"]
        when = ("due today" if days == 0 else f"{abs(_i(days))} day(s) overdue" if isinstance(days, (int, float)) and days < 0 else
                f"due in {_i(days)} day(s)" if isinstance(days, (int, float)) else "")
        rows = [("Contract", p["n"]), ("Obligation", p["lab"]), ("Due date", short_date(p["due"])), ("Status", when),
                ("Severity", SEVERITY.get(p["sev"], SEVERITY["medium"])[1].capitalize()), ("Source", f"page {p['pg']}" if p["pg"] else "")]
        path, cta, alt = "obligations", "View obligations", f"{ev}: {p['lab']}, {when}"
        callout = ("This tool cannot see whether a payment was made. “Overdue” means the due date has passed. "
                   "Acknowledge the alert once it is handled.")
    else:
        r = _d(data.get("review"))
        cid = str(r.get("contract_id") or "")
        subject = f"Review needed · {pretty_field(p['f'])} · {p['n']}"
        preheader = f"{pretty_field(p['f'])} is {p['st'] or 'unverified'}"
        heading, intro = f"{pretty_field(p['f'])} needs a human decision", "The system is not certain about this value, so it asks you to check it against the source."
        try:
            conf = f"{float(p['cf']) * 100:.0f}%"
        except (TypeError, ValueError):
            conf = "n/a"
        rows = [("Contract", p["n"]), ("Field", pretty_field(p["f"])), ("Status", p["st"] or "unverified"), ("Confidence", conf),
                ("Source", f"page {p['pg']}" if p["pg"] else "")]
        path, cta, alt = "terms", "Review in the app", f"Review needed: {pretty_field(p['f'])}"
        callout = "Accept, correct or reject the value. Your decision is stored with your name and the time."
    link = f"{base}/app/contracts/{cid}/{path}" if base and re.fullmatch(r"[0-9a-f]{64}", cid or "") else (f"{base}/app" if base else "")
    hero = (f'<tr><td style="padding:0;line-height:0;font-size:0;"><img src="{esc(image_url)}" width="600" alt="{esc(alt)}" '
            f'style="display:block;width:100%;max-width:600px;height:auto;border:0;"></td></tr>') if image_url else ""
    logo = (f'<img src="{esc(logo_url)}" width="230" alt="Unlimited Innovations India Pvt. Ltd" '
            f'style="display:block;width:230px;max-width:100%;height:auto;border:0;margin-top:18px;">') if logo_url else ""
    call = (f'<div style="margin:18px 0 0;padding:12px 14px;background:#fbf4e3;border-left:4px solid #d4a24c;border-radius:6px;'
            f'font:14px/1.5 Arial,Helvetica,sans-serif;color:#4a4032;">{esc(callout)}</div>') if callout else ""
    rows_html = "".join(_row(k, v) for k, v in rows if v not in ("", None))
    body = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>{esc(subject)}</title></head>
<body style="margin:0;padding:0;background:#efe9dc;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#efe9dc;">{esc(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#efe9dc"><tr><td align="center" style="padding:26px 12px;">
<!--[if mso]><table role="presentation" width="600" align="center" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#ffffff;border-radius:18px;overflow:hidden;">
{hero}
<tr><td style="padding:30px 34px 6px;">
<h1 style="margin:0 0 10px;font:700 26px/1.2 Georgia,'Times New Roman',serif;color:#0b1b2b;">{esc(heading)}</h1>
<p style="margin:0 0 18px;font:15px/1.55 Arial,Helvetica,sans-serif;color:#4a4032;">{esc(intro)}</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{rows_html}</table>
{call}{_button(link, cta) if link else ""}
</td></tr>
<tr><td style="padding:22px 34px 8px;">
<div style="border-top:1px solid #eee6d2;padding-top:22px;font:15px/1.6 Arial,Helvetica,sans-serif;color:#1f1912;">
With regards,<br><strong style="font-size:16px;">{esc(st['name'])}</strong><br><span style="color:#7a6f5d;font-size:13px;">{esc(st['title'])}</span>
{logo}
</div></td></tr>
<tr><td style="padding:18px 34px 26px;font:12px/1.5 Arial,Helvetica,sans-serif;color:#8b8068;">
<strong style="color:#4a4032;">Decision support, not legal advice.</strong> Figures come from the extracted contract and from rules that may not yet have been reviewed by a lawyer.
Links open SPA Intelligence and ask you to sign in with GitHub.</td></tr>
</table>
<!--[if mso]></td></tr></table><![endif]-->
</td></tr></table></body></html>"""
    text_alt = "\n".join([heading, intro, ""] + [f"{k}: {v}" for k, v in rows if v not in ("", None)] +
                         ([f"\n{cta}: {link}"] if link else []) + ["", "With regards,", st["name"], st["title"], "", "Decision support, not legal advice."])
    return {"subject": subject[:200], "html": body, "text": text_alt, "preheader": preheader[:140], "image_url": image_url}
