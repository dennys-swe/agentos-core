import os
import json
from fastapi import APIRouter, Request, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

from core.database import clinicas_collection
from services.ia_service import processar_mensagem_com_memoria
from services.whatsapp_service import enviar_mensagem_whatsapp

load_dotenv()

router = APIRouter()
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "agentos_secreto_123")


async def _get_clinica_por_phone_id(phone_number_id: str) -> dict | None:
    """
    Busca a clínica no banco de dados pelo phone_number_id da Meta.
    Retorna None se não encontrar (fallback para .env / simulador).
    """
    clinica = await clinicas_collection.find_one({"whatsapp_phone_id": phone_number_id})
    return clinica


# --- Nova Função Wrapper para Background ---
async def processar_e_responder(telefone_paciente: str, texto: str, clinica: dict | None):
    """
    Processa a mensagem e responde ao paciente.
    Se `clinica` for None, usa os valores padrão do .env (fallback para simulador).
    """
    try:
        resposta_ia = await processar_mensagem_com_memoria(telefone_paciente, texto, clinica)

        # 👇 Só envia se NÃO for silêncio (transbordo ativo)
        if resposta_ia != "_SILENCE_":
            # Usa os tokens da clínica, se disponíveis
            access_token = clinica.get("whatsapp_token") if clinica else None
            phone_id = clinica.get("whatsapp_phone_id") if clinica else None
            await enviar_mensagem_whatsapp(telefone_paciente, resposta_ia, access_token=access_token, phone_id=phone_id)
            print(f"✅ [AgentOS] Respondeu para {telefone_paciente}: {resposta_ia}\n")
        else:
            print(f"⏸️ [AgentOS] Transbordo ativo para {telefone_paciente}. Nenhuma mensagem enviada.\n")

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

            # ── ROTEAMENTO MULTI-TENANT ──
            # Descobre qual clínica recebeu a mensagem pelo phone_number_id da Meta
            phone_number_id = value.get("metadata", {}).get("phone_number_id")
            clinica = None
            if phone_number_id:
                clinica = await _get_clinica_por_phone_id(phone_number_id)
                if clinica:
                    print(f"🏥 [Webhook] Mensagem roteada para: {clinica.get('nome', 'N/A')}")
                else:
                    print(f"⚠️ [Webhook] phone_number_id '{phone_number_id}' não mapeado. Usando fallback do .env.")

            if texto and telefone_paciente:
                # Delega o processamento pesado para o background, passando o contexto da clínica
                background_tasks.add_task(processar_e_responder, telefone_paciente, texto, clinica)

        # O retorno é instantâneo, evitando que a Meta cancele o Webhook
        return {"status": "success"}

    except Exception as e:
        print(f"❌ Erro ao processar webhook: {e}")
        return {"status": "error"}
