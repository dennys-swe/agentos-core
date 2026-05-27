import httpx
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.database import sessions_collection
from services.whatsapp_service import formatar_numero_br, ACCESS_TOKEN, PHONE_ID, URL

router = APIRouter()


# --- Modelo de entrada ---
class RespostaHumana(BaseModel):
    mensagem: str


# --- GET: Lista todos os atendimentos humanos ativos ---
@router.get("/api/admin/atendimentos", tags=["Atendimento Humano"])
async def listar_atendimentos():
    """Retorna todas as sessões que estão sob controle de um atendente humano."""
    atendimentos = []
    cursor = sessions_collection.find({"owner": "human"}).sort("human_takeover_at", -1)

    async for sessao in cursor:
        atendimentos.append({
            "telefone": sessao.get("telefone"),
            "nome": sessao.get("nome"),
            "motivo": sessao.get("motivo"),
            "convenio": sessao.get("convenio"),
            "status": sessao.get("status"),
            "human_takeover_at": sessao.get("human_takeover_at"),
            "last_human_activity_at": sessao.get("last_human_activity_at"),
        })

    return atendimentos


# --- GET: Histórico completo de uma conversa ---
@router.get("/api/admin/atendimentos/{telefone}/historico", tags=["Atendimento Humano"])
async def obter_historico(telefone: str):
    """Retorna o histórico completo de mensagens de uma sessão."""
    sessao = await sessions_collection.find_one({"telefone": telefone})

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    return {"historico": sessao.get("historico", [])}


# --- POST: Envia resposta humana via WhatsApp ---
@router.post("/api/admin/atendimentos/{telefone}/responder", tags=["Atendimento Humano"])
async def responder_paciente(telefone: str, request: RespostaHumana):
    """Envia uma mensagem do atendente para o paciente via WhatsApp e salva no histórico."""
    sessao = await sessions_collection.find_one({"telefone": telefone})

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    # Atualiza o histórico com a mensagem do atendente
    historico = sessao.get("historico", [])
    historico.append({"role": "assistant", "content": request.mensagem})

    await sessions_collection.update_one(
        {"telefone": telefone},
        {"$set": {
            "historico": historico,
            "last_human_activity_at": datetime.utcnow()
        }}
    )

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
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Content-Type": "application/json"
            }
            response = await client.post(URL, json=data, headers=headers)

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
async def devolver_ao_bot(telefone: str):
    """Devolve o controle da conversa para o bot de IA."""
    sessao = await sessions_collection.find_one({"telefone": telefone})

    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada.")

    await sessions_collection.update_one(
        {"telefone": telefone},
        {"$set": {
            "owner": "bot",
            "human_takeover_at": None,
            "last_human_activity_at": None
        }}
    )

    print(f"🔁 [Atendimento] Sessão {telefone} devolvida ao bot.")
    return {"status": "sucesso", "mensagem": f"Sessão {telefone} devolvida ao bot."}
