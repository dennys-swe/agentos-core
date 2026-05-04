import os
import json
from fastapi import APIRouter, Request, HTTPException, Query, Body
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from services.ia_service import processar_mensagem_com_memoria

load_dotenv()

# Instancia o roteador para esse módulo
router = APIRouter()

# Token de verificação que você vai cadastrar no painel da Meta
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "agentos_secreto_123")

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
async def receive_message(payload: dict = Body(...)):
    try:
        entry = payload.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            message = value["messages"][0]
            telefone_paciente = message.get("from")
            texto = message.get("text", {}).get("body")
            
            if texto and telefone_paciente:
                # Dispara a inteligência da AgentOS!
                resposta_ia = await processar_mensagem_com_memoria(telefone_paciente, texto)
                
                print(f"✅ [AgentOS] Respondeu para {telefone_paciente}: {resposta_ia}\n")

        return {"status": "success"} 
        
    except Exception as e:
        print(f"❌ Erro ao processar webhook: {e}")
        return {"status": "error"} # O WhatsApp prefere que você não estoure erro 500
