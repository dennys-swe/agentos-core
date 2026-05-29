from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId

from core.database import clinicas_collection, users_collection, sessions_collection
from services.auth_service import get_current_user, hash_password

router = APIRouter()


# ── Guard: apenas Super Admins ──

async def require_super_admin(current_user: dict = Depends(get_current_user)):
    """Dependency que garante acesso exclusivo para role=super_admin."""
    if current_user.get("role") != "super_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito à equipe AgentOS.")
    return current_user


# ── Helpers ──

def _serialize(doc: dict) -> dict:
    """Serializa ObjectId para string."""
    doc["_id"] = str(doc["_id"])
    if "clinica_id" in doc and doc["clinica_id"]:
        doc["clinica_id"] = str(doc["clinica_id"])
    return doc


# ── Modelos de entrada ──

class ClinicaCreate(BaseModel):
    nome: str
    whatsapp_phone_id: str
    whatsapp_token: str
    prompt_sistema: str
    horarios_funcionamento: str = "Segunda a Sexta, das 08h às 18h"

class ClinicaUpdate(BaseModel):
    nome: str | None = None
    whatsapp_phone_id: str | None = None
    whatsapp_token: str | None = None
    prompt_sistema: str | None = None
    horarios_funcionamento: str | None = None

class UsuarioCreate(BaseModel):
    username: str
    password: str
    nome: str
    role: str = "atendente"  # "atendente" ou "super_admin"
    clinica_id: str | None = None  # Obrigatório para role=atendente


# ── ROTAS: Clínicas ──

@router.get("/api/super-admin/clinicas", tags=["Super Admin"])
async def listar_clinicas(current_user: dict = Depends(require_super_admin)):
    """Lista todas as clínicas cadastradas."""
    clinicas = []
    async for clinica in clinicas_collection.find():
        clinicas.append(_serialize(clinica))
    return clinicas


@router.post("/api/super-admin/clinicas", tags=["Super Admin"])
async def criar_clinica(body: ClinicaCreate, current_user: dict = Depends(require_super_admin)):
    """Cadastra uma nova clínica no sistema."""
    # Verifica se o phone_id já existe
    existe = await clinicas_collection.find_one({"whatsapp_phone_id": body.whatsapp_phone_id})
    if existe:
        raise HTTPException(status_code=409, detail=f"Já existe uma clínica com phone_id '{body.whatsapp_phone_id}'.")

    doc = {
        **body.model_dump(),
        "created_at": datetime.utcnow(),
        "ativa": True,
    }
    result = await clinicas_collection.insert_one(doc)
    clinica = await clinicas_collection.find_one({"_id": result.inserted_id})
    print(f"🏥 [SuperAdmin] Clínica criada: {body.nome}")
    return _serialize(clinica)


@router.get("/api/super-admin/clinicas/{clinica_id}", tags=["Super Admin"])
async def obter_clinica(clinica_id: str, current_user: dict = Depends(require_super_admin)):
    """Retorna os detalhes de uma clínica."""
    try:
        clinica = await clinicas_collection.find_one({"_id": ObjectId(clinica_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="clinica_id inválido.")
    if not clinica:
        raise HTTPException(status_code=404, detail="Clínica não encontrada.")
    return _serialize(clinica)


@router.put("/api/super-admin/clinicas/{clinica_id}", tags=["Super Admin"])
async def atualizar_clinica(clinica_id: str, body: ClinicaUpdate, current_user: dict = Depends(require_super_admin)):
    """Atualiza as configurações de uma clínica (prompt, token, horários, etc.)."""
    try:
        oid = ObjectId(clinica_id)
    except Exception:
        raise HTTPException(status_code=400, detail="clinica_id inválido.")

    campos = {k: v for k, v in body.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    campos["updated_at"] = datetime.utcnow()
    result = await clinicas_collection.update_one({"_id": oid}, {"$set": campos})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Clínica não encontrada.")

    clinica = await clinicas_collection.find_one({"_id": oid})
    print(f"✏️ [SuperAdmin] Clínica {clinica_id} atualizada.")
    return _serialize(clinica)


@router.delete("/api/super-admin/clinicas/{clinica_id}", tags=["Super Admin"])
async def deletar_clinica(clinica_id: str, current_user: dict = Depends(require_super_admin)):
    """Remove uma clínica e todos os seus dados (usuários e sessões)."""
    try:
        oid = ObjectId(clinica_id)
    except Exception:
        raise HTTPException(status_code=400, detail="clinica_id inválido.")

    # Remove clínica
    result = await clinicas_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Clínica não encontrada.")

    # Limpa usuários e sessões vinculados
    await users_collection.delete_many({"clinica_id": clinica_id})
    await sessions_collection.delete_many({"clinica_id": clinica_id})

    print(f"🗑️ [SuperAdmin] Clínica {clinica_id} e seus dados foram removidos.")
    return {"status": "sucesso", "mensagem": f"Clínica {clinica_id} removida com todos os seus dados."}


# ── ROTAS: Usuários / Atendentes ──

@router.get("/api/super-admin/usuarios", tags=["Super Admin"])
async def listar_usuarios(current_user: dict = Depends(require_super_admin)):
    """Lista todos os usuários do sistema."""
    usuarios = []
    async for u in users_collection.find():
        u.pop("password_hash", None)  # Nunca retornar a senha
        usuarios.append(_serialize(u))
    return usuarios


@router.post("/api/super-admin/usuarios", tags=["Super Admin"])
async def criar_usuario(body: UsuarioCreate, current_user: dict = Depends(require_super_admin)):
    """Cria um novo usuário (atendente ou super_admin) no sistema."""
    existe = await users_collection.find_one({"username": body.username})
    if existe:
        raise HTTPException(status_code=409, detail=f"Usuário '{body.username}' já existe.")

    if body.role == "atendente" and not body.clinica_id:
        raise HTTPException(status_code=400, detail="clinica_id é obrigatório para o role 'atendente'.")

    doc = {
        "username": body.username,
        "password_hash": hash_password(body.password),
        "nome": body.nome,
        "role": body.role,
        "clinica_id": body.clinica_id,
        "created_at": datetime.utcnow(),
    }
    result = await users_collection.insert_one(doc)
    user = await users_collection.find_one({"_id": result.inserted_id})
    user.pop("password_hash", None)
    print(f"👤 [SuperAdmin] Usuário criado: {body.username} ({body.role})")
    return _serialize(user)


@router.delete("/api/super-admin/usuarios/{username}", tags=["Super Admin"])
async def deletar_usuario(username: str, current_user: dict = Depends(require_super_admin)):
    """Remove um usuário do sistema."""
    if username == current_user.get("username"):
        raise HTTPException(status_code=400, detail="Você não pode remover sua própria conta.")

    result = await users_collection.delete_one({"username": username})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"Usuário '{username}' não encontrado.")

    print(f"🗑️ [SuperAdmin] Usuário {username} removido.")
    return {"status": "sucesso", "mensagem": f"Usuário '{username}' removido."}


# ── ROTAS: Dashboard / Estatísticas ──

@router.get("/api/super-admin/stats", tags=["Super Admin"])
async def obter_stats(current_user: dict = Depends(require_super_admin)):
    """Retorna estatísticas gerais do sistema para o dashboard."""
    total_clinicas = await clinicas_collection.count_documents({})
    total_usuarios = await users_collection.count_documents({})
    total_sessoes = await sessions_collection.count_documents({})
    sessoes_ativas_humano = await sessions_collection.count_documents({"owner": "human"})
    sessoes_bot = await sessions_collection.count_documents({"owner": "bot"})

    return {
        "total_clinicas": total_clinicas,
        "total_usuarios": total_usuarios,
        "total_sessoes": total_sessoes,
        "sessoes_em_atendimento_humano": sessoes_ativas_humano,
        "sessoes_com_bot": sessoes_bot,
    }
