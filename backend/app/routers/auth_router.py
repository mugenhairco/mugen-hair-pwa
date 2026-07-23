"""routers/auth_router.py — /api/auth/*: login & data akun sendiri."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

import auth_db
from auth import buat_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginBody):
    user = auth_db.autentikasi(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Username atau password salah.")
    if not user.get("aktif"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Akun tidak aktif, hubungi Owner.")
    token = buat_token(user["id"])
    return {"token": token, "user": user}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
