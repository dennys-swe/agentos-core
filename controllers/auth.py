import os
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from core.database import users_collection
from services.auth_service import (
    verify_password,
    create_access_token,
    get_current_user,
)

router = APIRouter()


# ── Modelo de entrada ──
class LoginRequest(BaseModel):
    username: str
    password: str


# ── GET /login — Serve a página de login ──
@router.get("/login", response_class=HTMLResponse, tags=["Autenticação"])
async def login_page():
    """Serve a página HTML de login."""
    html_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "login.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


# ── POST /api/auth/login — Autentica o usuário ──
@router.post("/api/auth/login", tags=["Autenticação"])
async def login(request: LoginRequest):
    """Valida credenciais e retorna JWT via cookie httpOnly."""
    user = await users_collection.find_one({"username": request.username})

    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos")

    token = create_access_token(data={"sub": user["username"]})

    response = JSONResponse(content={
        "status": "sucesso",
        "nome": user.get("nome", user["username"]),
    })

    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,       # Impede acesso via JavaScript (proteção XSS)
        samesite="lax",      # Proteção CSRF básica
        secure=False,        # Mudar para True em produção (HTTPS)
        max_age=8 * 60 * 60, # 8 horas em segundos
        path="/",
    )

    print(f"🔐 Login bem-sucedido: {user['username']}")
    return response


# ── POST /api/auth/logout — Remove o cookie JWT ──
@router.post("/api/auth/logout", tags=["Autenticação"])
async def logout():
    """Limpa o cookie de autenticação."""
    response = JSONResponse(content={"status": "sucesso", "mensagem": "Logout realizado"})
    response.delete_cookie(key="access_token", path="/")
    return response


# ── GET /api/auth/me — Retorna dados do usuário logado ──
@router.get("/api/auth/me", tags=["Autenticação"])
async def me(current_user: dict = Depends(get_current_user)):
    """Retorna informações do usuário autenticado."""
    return {
        "username": current_user["username"],
        "nome": current_user.get("nome", current_user["username"]),
    }
