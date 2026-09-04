import httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.database import sessions_collection, empresas_collection
from services.whatsapp_service import formatar_numero_br, DEFAULT_ACCESS_TOKEN, DEFAULT_PHONE_ID
from services.auth_service import get_current_user, get_empresa_filter

router = APIRouter()


# --- Helpers ---



async def _get_empresa_tokens(empresa_id: str) -> tuple[str, str]:
    """
    Retorna (access_token, phone_id) da clínica. Fallback para .env se não encontrar.
    """
    if empresa_id and empresa_id != "simulador":
        from bson import ObjectId
        try:
            empresa = await empresas_collection.find_one({"_id": ObjectId(empresa_id)})
            if empresa:
                return empresa.get("whatsapp_token"), empresa.get("whatsapp_phone_id")
        except Exception:
            pass
    return DEFAULT_ACCESS_TOKEN, DEFAULT_PHONE_ID


# --- Modelo de entrada ---
class RespostaHumana(BaseModel):
    mensagem: str


# --- GET: Lista todos os atendimentos humanos ativos ---
@router.get("/api/admin/atendimentos", tags=["Atendimento Humano"])
async def listar_atendimentos(current_user: dict = Depends(get_current_user)):
    """Retorna sessões com owner='human', filtradas pela clínica do usuário logado."""
    filtro = {"owner": "human", **get_empresa_filter(current_user)}
    atendimentos = []
    cursor = sessions_collection.find(filtro).sort("human_takeover_at", -1)

    async for sessao in cursor:
        atendimentos.append({
            "telefone": sessao.get("telefone"),
            "nome": sessao.get("nome"),
            "motivo": sessao.get("motivo"),
            "convenio": sessao.get("convenio"),
            "status": sessao.get("status"),
            "empresa_id": sessao.get("empresa_id"),
            "human_takeover_at": sessao.get("human_takeover_at"),
            "last_human_activity_at": sessao.get("last_human_activity_at"),
        })

    return atendimentos


# --- GET: Histórico completo de uma conversa ---
@router.get("/api/admin/atendimentos/{telefone}/historico", tags=["Atendimento Humano"])
async def obter_historico(telefone: str, current_user: dict = Depends(get_current_user)):
    """Retorna o histórico completo de mensagens de uma sessão (respeitando isolamento de tenant)."""
    filtro_empresa = get_empresa_filter(current_user)
    
    # Bypass para super admin testar o simulador
    if current_user.get("role") == "super_admin" and telefone.startswith("simulador_"):
        filtro_empresa = {} 
        
    filtro = {"telefone": telefone, **filtro_empresa}
    sessao = await sessions_collection.find_one(filtro)

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    return {"historico": sessao.get("historico", [])}


# --- POST: Envia resposta humana via WhatsApp ---
@router.post("/api/admin/atendimentos/{telefone}/responder", tags=["Atendimento Humano"])
async def responder_paciente(telefone: str, request: RespostaHumana, current_user: dict = Depends(get_current_user)):
    """Envia uma mensagem do atendente para o paciente via WhatsApp e salva no histórico."""
    filtro = {"telefone": telefone, **get_empresa_filter(current_user)}
    sessao = await sessions_collection.find_one(filtro)

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    # Atualiza o histórico com a mensagem do atendente
    historico = sessao.get("historico", [])
    historico.append({"role": "assistant", "content": request.mensagem})

    await sessions_collection.update_one(
        filtro,
        {"$set": {
            "historico": historico,
            "last_human_activity_at": datetime.utcnow(),
            "inactivity_warning_sent": False
        }}
    )

    # Busca os tokens corretos da clínica
    empresa_id = sessao.get("empresa_id", "simulador")
    access_token, phone_id = await _get_empresa_tokens(empresa_id)
    url = f"https://graph.facebook.com/v25.0/{phone_id}/messages"

    # Envia a mensagem diretamente via WhatsApp (sem split por |)
    try:
        async with httpx.AsyncClient() as client:
            telefone_ajustado = formatar_numero_br(telefone)
            data = {
                "messaging_product": "whatsapp",
                "to": telefone_ajustado,
                "type": "text",
                "text": {"body": request.mensagem}
            }
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            response = await client.post(url, json=data, headers=headers)

            if response.status_code == 200:
                print(f"✅ [Atendimento] Mensagem enviada para {telefone}.")
                return {"status": "sucesso", "mensagem": "Mensagem enviada com sucesso."}
            else:
                print(f"❌ [Atendimento] Erro ao enviar para {telefone}: {response.text}")
                return {"status": "erro", "detalhe": response.text}

    except Exception as e:
        print(f"❌ [Atendimento] Falha crítica no envio para {telefone}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar mensagem: {e}")


# --- POST: Devolve a sessão para o bot ---
@router.post("/api/admin/atendimentos/{telefone}/devolver", tags=["Atendimento Humano"])
async def devolver_ao_bot(telefone: str, current_user: dict = Depends(get_current_user)):
    """Devolve o controle da conversa para o bot de IA."""
    filtro = {"telefone": telefone, **get_empresa_filter(current_user)}
    sessao = await sessions_collection.find_one(filtro)

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    await sessions_collection.update_one(
        filtro,
        {"$set": {
            "owner": "bot",
            "human_takeover_at": None,
            "last_human_activity_at": None
        }}
    )

    print(f"🔁 [Atendimento] Sessão {telefone} devolvida ao bot.")
    return {"status": "sucesso", "mensagem": f"Sessão {telefone} devolvida ao bot."}
