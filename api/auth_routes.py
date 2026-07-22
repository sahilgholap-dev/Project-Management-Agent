"""Login / logout / whoami. First successful login flips invite_status
'invited' -> 'active' (PRD section 4's invite acceptance, without any send)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from api import security
from api.deps import SESSION_COOKIE, Conn, User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


def _user_info(user) -> dict:
    return {
        "user_id": user["user_id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "invite_status": user["invite_status"],
    }


@router.post("/login")
def login(body: LoginBody, response: Response, conn: Conn) -> dict:
    user = conn.execute(
        "SELECT u.user_id, u.email, u.display_name, u.role, u.invite_status,"
        "       c.password_hash"
        " FROM users u JOIN auth_credentials c ON c.user_id = u.user_id"
        " WHERE LOWER(u.email) = LOWER(?)",
        (body.email,),
    ).fetchone()
    if (
        user is None
        or user["invite_status"] == "disabled"
        or not security.verify_password(body.password, user["password_hash"])
    ):
        raise HTTPException(status_code=401, detail="invalid credentials")

    if user["invite_status"] == "invited":
        conn.execute(
            "UPDATE users SET invite_status = 'active' WHERE user_id = ?",
            (user["user_id"],),
        )
        conn.commit()

    response.set_cookie(
        SESSION_COOKIE, security.make_session(user["user_id"]),
        httponly=True, samesite="lax",
        max_age=security.SESSION_TTL_HOURS * 3600,
    )
    info = _user_info(user)
    info["invite_status"] = "active"
    return info


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: User) -> dict:
    return _user_info(user)
