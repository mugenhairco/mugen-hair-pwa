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


# REVISI UI/UX: preferensi Dark/Light Mode per akun -- endpoint ini bisa
# dipanggil siapa pun yang sudah login (admin maupun barber), HANYA
# mengubah tema milik akun itu sendiri (user_id dari token, bukan dari
# parameter apa pun yang bisa dimanipulasi lewat client).
class TemaBody(BaseModel):
    tema: str


@router.put("/tema")
def simpan_tema(body: TemaBody, user: dict = Depends(get_current_user)):
    try:
        auth_db.set_tema_user(user["id"], body.tema)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    diperbarui = auth_db.get_user(user["id"])
    diperbarui.pop("password_hash", None)
    return diperbarui
