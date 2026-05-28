import os
from datetime import datetime, timedelta, timezone

from fastapi import Request, HTTPException
from jose import JWTError, jwt
import bcrypt
from dotenv import load_dotenv

from core.database import users_collection

load_dotenv()

# ── Configuração ──
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "8"))

if not JWT_SECRET_KEY:
    import secrets
    JWT_SECRET_KEY = secrets.token_hex(32)
    print("⚠️  JWT_SECRET_KEY não definida no .env. Usando chave temporária (tokens invalidados ao reiniciar).")

# ── Hashing de senhas ──

def hash_password(password: str) -> str:
    """Gera o hash bcrypt de uma senha em texto plano."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto plano corresponde ao hash armazenado."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# ── JWT ──
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Cria um token JWT assinado com os dados fornecidos."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=JWT_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decodifica e valida um token JWT. Retorna None se inválido."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


# ── FastAPI Dependency ──
async def get_current_user(request: Request):
    """
    Dependency do FastAPI que extrai o JWT do cookie 'access_token',
    valida e retorna o documento do usuário do MongoDB.
    Levanta HTTPException(401) se o token for inválido ou ausente.
    """
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Não autenticado")

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado")

    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Token inválido")

    user = await users_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")

    return user
