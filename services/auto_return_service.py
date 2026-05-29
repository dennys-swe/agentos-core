import os
import asyncio
from datetime import datetime, timedelta
from bson import ObjectId

from core.database import sessions_collection, clinicas_collection
from services.whatsapp_service import DEFAULT_ACCESS_TOKEN, DEFAULT_PHONE_ID

# Timeout de inatividade em minutos (padrão: 15 minutos)
TIMEOUT_MINUTOS = int(os.getenv("HUMAN_INACTIVITY_TIMEOUT_MINUTES", "15"))


async def _get_tokens_da_clinica(clinica_id: str) -> tuple[str, str]:
    """
    Busca os tokens WhatsApp da clínica pelo ID.
    Retorna fallback do .env se não encontrar (simulador/testes).
    """
    if clinica_id and clinica_id != "simulador":
        try:
            clinica = await clinicas_collection.find_one({"_id": ObjectId(clinica_id)})
            if clinica:
                return clinica.get("whatsapp_token"), clinica.get("whatsapp_phone_id")
        except Exception:
            pass
    return DEFAULT_ACCESS_TOKEN, DEFAULT_PHONE_ID


async def iniciar_verificacao_inatividade():
    """Loop de background que verifica sessões humanas inativas e as devolve ao bot."""
    print(f"🔄 [AutoReturn] Serviço iniciado. Timeout de inatividade: {TIMEOUT_MINUTOS} minutos.")

    while True:
        try:
            await _verificar_sessoes_inativas()
        except Exception as e:
            print(f"❌ [AutoReturn] Erro na verificação: {e}")

        # Aguarda 60 segundos antes da próxima verificação
        await asyncio.sleep(60)


from services.whatsapp_service import enviar_mensagem_whatsapp

async def _verificar_sessoes_inativas():
    """Busca sessões com owner='human' e aplica regras de inatividade (foco no paciente)."""
    cursor = sessions_collection.find({"owner": "human"})
    agora = datetime.utcnow()

    # Timeouts
    TIMEOUT_AVISO_PACIENTE = timedelta(minutes=5)
    TIMEOUT_ENCERRA_PACIENTE = timedelta(minutes=5)  # 5 minutos APÓS o aviso
    TIMEOUT_SILENCIOSO_HUMANO = timedelta(minutes=20)

    async for sessao in cursor:
        telefone = sessao.get("telefone", "desconhecido")
        clinica_id = sessao.get("clinica_id", "simulador")
        historico = sessao.get("historico", [])

        if not historico:
            continue

        last_msg = historico[-1]

        # --- TURNO DO PACIENTE (aguardando resposta do paciente) ---
        if last_msg["role"] == "assistant":
            ultima_atividade = sessao.get("last_human_activity_at") or sessao.get("human_takeover_at")
            if not ultima_atividade:
                continue

            tempo_inativo = agora - ultima_atividade
            aviso_enviado = sessao.get("inactivity_warning_sent", False)

            # Estágio 2: Encerramento (passou mais 5 min desde o aviso)
            if aviso_enviado:
                if tempo_inativo > (TIMEOUT_AVISO_PACIENTE + TIMEOUT_ENCERRA_PACIENTE):
                    print(f"⏰ [AutoReturn] Paciente {telefone} inativo há >10min. Encerrando.")

                    msg_encerramento = "Como não tivemos retorno, estou encerrando este atendimento humano por enquanto. Qualquer dúvida, é só me chamar!"

                    if not telefone.startswith("simulador_"):
                        access_token, phone_id = await _get_tokens_da_clinica(clinica_id)
                        await enviar_mensagem_whatsapp(telefone, msg_encerramento, access_token=access_token, phone_id=phone_id)

                    historico.append({"role": "assistant", "content": msg_encerramento})
                    historico.append({"role": "system", "content": "[Sistema] Atendimento humano encerrado por inatividade do paciente."})

                    await sessions_collection.update_one(
                        {"telefone": telefone, "clinica_id": clinica_id},
                        {"$set": {
                            "owner": "bot",
                            "historico": historico,
                            "human_takeover_at": None,
                            "last_human_activity_at": None,
                            "last_patient_activity_at": None,
                            "inactivity_warning_sent": False
                        }}
                    )

            # Estágio 1: Aviso de 5 min (se ainda não foi enviado)
            elif tempo_inativo > TIMEOUT_AVISO_PACIENTE:
                print(f"⏰ [AutoReturn] Paciente {telefone} inativo há >5min. Enviando aviso.")

                msg_aviso = "Ainda está aí? Podemos continuar o atendimento?"

                if not telefone.startswith("simulador_"):
                    access_token, phone_id = await _get_tokens_da_clinica(clinica_id)
                    await enviar_mensagem_whatsapp(telefone, msg_aviso, access_token=access_token, phone_id=phone_id)

                historico.append({"role": "assistant", "content": msg_aviso})

                await sessions_collection.update_one(
                    {"telefone": telefone, "clinica_id": clinica_id},
                    {"$set": {
                        "historico": historico,
                        "inactivity_warning_sent": True
                    }}
                )

        # --- TURNO DO ATENDENTE (aguardando resposta do humano) ---
        elif last_msg["role"] == "user":
            ultima_atividade = sessao.get("last_patient_activity_at") or sessao.get("human_takeover_at")
            if not ultima_atividade:
                continue

            tempo_inativo = agora - ultima_atividade

            if tempo_inativo > TIMEOUT_SILENCIOSO_HUMANO:
                print(f"⏰ [AutoReturn] Atendente inativo há >20min para {telefone}. Devolvendo ao bot.")

                historico.append({
                    "role": "system",
                    "content": "[Sistema] Sessão devolvida ao bot após 20 minutos de inatividade do atendente."
                })

                await sessions_collection.update_one(
                    {"telefone": telefone, "clinica_id": clinica_id},
                    {"$set": {
                        "owner": "bot",
                        "historico": historico,
                        "human_takeover_at": None,
                        "last_human_activity_at": None,
                        "last_patient_activity_at": None,
                        "inactivity_warning_sent": False
                    }}
                )
