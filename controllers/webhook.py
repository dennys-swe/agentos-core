import os
import json
from fastapi import APIRouter, Request, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from services.ia_service import processar_mensagem_com_memoria
from services.whatsapp_service import enviar_mensagem_whatsapp

load_dotenv()

router = APIRouter()
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "agentos_secreto_123")

# --- Nova Função Wrapper para Background ---
async def processar_e_responder(telefone_paciente: str, texto: str):
    try:
        resposta_ia = await processar_mensagem_com_memoria(telefone_paciente, texto)
        await enviar_mensagem_whatsapp(telefone_paciente, resposta_ia)
        print(f"✅ [AgentOS] Respondeu para {telefone_paciente}: {resposta_ia}\n")
    except Exception as e:
        print(f"❌ Erro na task de background: {e}")

@router.get("/whatsapp")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token")
):
    """
    Rota GET: A Meta faz uma requisição aqui para confirmar que a URL é sua.
    """
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        print("✅ Webhook verificado com sucesso pela Meta!")
        # A Meta exige que o desafio (challenge) seja retornado em texto puro
        return PlainTextResponse(content=hub_challenge)
    
    print("❌ Falha na verificação do Webhook. Token incorreto.")
    raise HTTPException(status_code=403, detail="Token de verificação inválido")


@router.post("/whatsapp")
async def receive_message(background_tasks: BackgroundTasks, payload: dict = Body(...)):
    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            message = value["messages"][0]
            telefone_paciente = message.get("from")
            texto = message.get("text", {}).get("body")
            
            if texto and telefone_paciente:
                # Delega o processamento pesado para o background
                background_tasks.add_task(processar_e_responder, telefone_paciente, texto)

        # O retorno é instantâneo, evitando que a Meta cancele o Webhook
        return {"status": "success"} 
        
    except Exception as e:
        print(f"❌ Erro ao processar webhook: {e}")
        return {"status": "error"}
