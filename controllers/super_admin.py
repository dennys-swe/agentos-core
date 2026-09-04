from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from bson import ObjectId

from core.database import empresas_collection, users_collection, sessions_collection
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
    if "empresa_id" in doc and doc["empresa_id"]:
        doc["empresa_id"] = str(doc["empresa_id"])
    return doc


# ── Modelos de entrada ──

class EmpresaCreate(BaseModel):
    nome: str
    setor: str = "Outro"
    campos_extracao: list[str] = []
    whatsapp_phone_id: str
    whatsapp_token: str
    prompt_sistema: str
    horarios_funcionamento: str = "Segunda a Sexta, das 08h às 18h"

class EmpresaUpdate(BaseModel):
    nome: str | None = None
    setor: str | None = None
    campos_extracao: list[str] | None = None
    whatsapp_phone_id: str | None = None
    whatsapp_token: str | None = None
    prompt_sistema: str | None = None
    horarios_funcionamento: str | None = None

class UsuarioCreate(BaseModel):
    username: str
    password: str
    nome: str
    role: str = "atendente"  # "atendente" ou "super_admin"
    empresa_id: str | None = None  # Obrigatório para role=atendente

class UsuarioUpdate(BaseModel):
    nome: str | None = None
    password: str | None = None  # Se preenchido, troca a senha
    empresa_id: str | None = None


# ── ROTAS: Empresas ──

@router.get("/api/super-admin/empresas", tags=["Super Admin"])
async def listar_clinicas(current_user: dict = Depends(require_super_admin)):
    """Lista todas as clínicas cadastradas."""
    empresas = []
    async for empresa in empresas_collection.find():
        empresas.append(_serialize(empresa))
    return empresas


@router.post("/api/super-admin/empresas", tags=["Super Admin"])
async def criar_clinica(body: EmpresaCreate, current_user: dict = Depends(require_super_admin)):
    """Cadastra uma nova clínica no sistema."""
    # Verifica se o phone_id já existe
    existe = await empresas_collection.find_one({"whatsapp_phone_id": body.whatsapp_phone_id})
    if existe:
        raise HTTPException(status_code=409, detail=f"Já existe uma clínica com phone_id '{body.whatsapp_phone_id}'.")

    doc = {
        **body.model_dump(),
        "created_at": datetime.utcnow(),
        "ativa": True,
    }
    result = await empresas_collection.insert_one(doc)
    empresa = await empresas_collection.find_one({"_id": result.inserted_id})
    print(f"🏥 [SuperAdmin] Clínica criada: {body.nome}")
    return _serialize(empresa)


@router.get("/api/super-admin/empresas/{empresa_id}", tags=["Super Admin"])
async def obter_clinica(empresa_id: str, current_user: dict = Depends(require_super_admin)):
    """Retorna os detalhes de uma clínica."""
    try:
        empresa = await empresas_collection.find_one({"_id": ObjectId(empresa_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="empresa_id inválido.")
    if not empresa:
        raise HTTPException(status_code=404, detail="Clínica não encontrada.")
    return _serialize(empresa)


@router.put("/api/super-admin/empresas/{empresa_id}", tags=["Super Admin"])
async def atualizar_clinica(empresa_id: str, body: EmpresaUpdate, current_user: dict = Depends(require_super_admin)):
    """Atualiza as configurações de uma clínica (prompt, token, horários, etc.)."""
    try:
        oid = ObjectId(empresa_id)
    except Exception:
        raise HTTPException(status_code=400, detail="empresa_id inválido.")

    campos = {k: v for k, v in body.model_dump().items() if v is not None}
    if not campos:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    campos["updated_at"] = datetime.utcnow()
    result = await empresas_collection.update_one({"_id": oid}, {"$set": campos})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Clínica não encontrada.")

    empresa = await empresas_collection.find_one({"_id": oid})
    print(f"✏️ [SuperAdmin] Clínica {empresa_id} atualizada.")
    return _serialize(empresa)


@router.delete("/api/super-admin/empresas/{empresa_id}", tags=["Super Admin"])
async def deletar_clinica(empresa_id: str, current_user: dict = Depends(require_super_admin)):
    """Remove uma clínica e todos os seus dados (usuários e sessões)."""
    try:
        oid = ObjectId(empresa_id)
    except Exception:
        raise HTTPException(status_code=400, detail="empresa_id inválido.")

    # Remove clínica
    result = await empresas_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Clínica não encontrada.")

    # Limpa usuários e sessões vinculados
    await users_collection.delete_many({"empresa_id": empresa_id})
    await sessions_collection.delete_many({"empresa_id": empresa_id})

    print(f"🗑️ [SuperAdmin] Clínica {empresa_id} e seus dados foram removidos.")
    return {"status": "sucesso", "mensagem": f"Clínica {empresa_id} removida com todos os seus dados."}


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

    if body.role == "atendente" and not body.empresa_id:
        raise HTTPException(status_code=400, detail="empresa_id é obrigatório para o role 'atendente'.")

    doc = {
        "username": body.username,
        "password_hash": hash_password(body.password),
        "nome": body.nome,
        "role": body.role,
        "empresa_id": body.empresa_id,
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


@router.patch("/api/super-admin/usuarios/{username}", tags=["Super Admin"])
async def atualizar_usuario(username: str, body: UsuarioUpdate, current_user: dict = Depends(require_super_admin)):
    """Atualiza nome, senha ou clínica de um usuário."""
    user = await users_collection.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=404, detail=f"Usuário '{username}' não encontrado.")

    campos = {}
    if body.nome:
        campos["nome"] = body.nome
    if body.password:
        if len(body.password) < 4:
            raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 4 caracteres.")
        campos["password_hash"] = hash_password(body.password)
    if body.empresa_id is not None:  # Permite setar como None (desvincular)
        campos["empresa_id"] = body.empresa_id if body.empresa_id else None

    if not campos:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar.")

    campos["updated_at"] = datetime.utcnow()
    await users_collection.update_one({"username": username}, {"$set": campos})

    user = await users_collection.find_one({"username": username})
    user.pop("password_hash", None)
    print(f"✏️ [SuperAdmin] Usuário {username} atualizado.")
    return _serialize(user)


# ── ROTAS: Dashboard / Estatísticas ──

@router.get("/api/super-admin/stats", tags=["Super Admin"])
async def obter_stats(current_user: dict = Depends(require_super_admin)):
    """Retorna estatísticas gerais + resumo por clínica para o dashboard."""
    total_clinicas = await empresas_collection.count_documents({})
    total_empresas = await empresas_collection.count_documents({})
    total_usuarios = await users_collection.count_documents({})
    total_sessoes = await sessions_collection.count_documents({})
    sessoes_ativas_humano = await sessions_collection.count_documents({"owner": "human"})
    sessoes_bot = await sessions_collection.count_documents({"owner": "bot"})

    # Resumo por clínica: nome + contagem de sessões
    empresas_resumo = []
    async for empresa in empresas_collection.find():
        cid = str(empresa["_id"])
        total = await sessions_collection.count_documents({"empresa_id": cid})
        humanos = await sessions_collection.count_documents({"empresa_id": cid, "owner": "human"})
        empresas_resumo.append({
            "_id": cid,
            "nome": empresa.get("nome"),
            "total_sessoes": total,
            "sessoes_humano": humanos,
            "ativa": empresa.get("ativa", True),
        })

    # Últimas sessões em atendimento humano (para o feed de atividade)
    recentes = []
    cursor = sessions_collection.find(
        {"owner": "human"},
        {"telefone": 1, "nome": 1, "empresa_id": 1, "human_takeover_at": 1}
    ).sort("human_takeover_at", -1).limit(5)
    async for s in cursor:
        recentes.append({
            "telefone": s.get("telefone"),
            "nome": s.get("nome") or "Pac. desconhecido",
            "empresa_id": s.get("empresa_id"),
            "human_takeover_at": s.get("human_takeover_at").isoformat() if s.get("human_takeover_at") else None,
        })

    return {
        "total_empresas": total_empresas,
        "total_usuarios": total_usuarios,
        "total_sessoes": total_sessoes,
        "sessoes_em_atendimento_humano": sessoes_ativas_humano,
        "sessoes_com_bot": sessoes_bot,
        "empresas_resumo": empresas_resumo,
        "atividade_recente": recentes,
    }
