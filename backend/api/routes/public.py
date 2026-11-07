"""Public, unauthenticated resources an email client must be able to load: the signed image card and the logo.
The card is drawn only from a payload signed with ALERT_WEBHOOK_SECRET (see app/emailcards.py): nobody can make the server
draw anything else, and a bad, expired or unsigned request is answered with a plain 404."""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, Response

from app import emailcards as ec
from backend.api.deps import ApiError

router = APIRouter(tags=["public"])
CACHE = {"Cache-Control": "public, max-age=86400"}


@router.get("/card.png", include_in_schema=False)
def card(d: str = Query(..., max_length=3000), sig: str = Query(..., max_length=64)):
    try:
        payload = ec.decode_card(d, sig, ec.settings()["secret"])
        png = ec.render_card(payload)
    except ec.CardError:
        raise ApiError(404, "not_found", "Not found.") from None
    return Response(png, media_type="image/png", headers=CACHE)


@router.get("/brand/logo.png", include_in_schema=False)
def logo():
    return FileResponse(ec.ASSETS / "brand" / "email-logo.png", media_type="image/png", headers=CACHE)
