"""Administrator: see who has signed up and give them a role (staff, reviewer or buyer)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import users
from backend.api import auth
from backend.api.deps import ApiError

router = APIRouter(prefix="/users", tags=["users"])


class RoleChange(BaseModel):
    role: Optional[str] = Field(None, description="staff | reviewer | buyer, or null to remove access.")


@router.get("")
def list_users():
    return {"users": users.list_users()}


@router.put("/{user_id}/role")
def set_role(user_id: str, body: RoleChange, request: Request):
    try:
        return users.set_role(user_id, body.role, auth.actor(request))
    except users.UserError as e:
        raise ApiError(404 if "not found" in str(e) else 422, "user_error", str(e)) from None
