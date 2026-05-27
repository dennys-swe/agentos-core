import os
import asyncio
from datetime import datetime, timedelta
from core.database import sessions_collection

# Timeout de inatividade em minutos (padrão: 15 minutos)
TIMEOUT_MINUTOS = int(os.getenv("HUMAN_INACTIVITY_TIMEOUT_MINUTES", "15"))


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


async def _verificar_sessoes_inativas():
    """Busca sessões com owner='human' e verifica se ultrapassaram o timeout."""
    cursor = sessions_collection.find({"owner": "human"})
    agora = datetime.utcnow()
    limite = timedelta(minutes=TIMEOUT_MINUTOS)

    async for sessao in cursor:
        telefone = sessao.get("telefone", "desconhecido")

        # Usa last_human_activity_at como referência; fallback para human_takeover_at
        ultima_atividade = sessao.get("last_human_activity_at") or sessao.get("human_takeover_at")

        if not ultima_atividade:
            # Sem timestamp de referência, ignora esta sessão
            continue

        tempo_inativo = agora - ultima_atividade

        if tempo_inativo > limite:
            print(f"⏰ [AutoReturn] Sessão {telefone} inativa há {tempo_inativo}. Devolvendo ao bot.")

            # Mensagem de sistema no histórico para registrar a devolução automática
            historico = sessao.get("historico", [])
            historico.append({
                "role": "system",
                "content": f"[Sistema] Sessão devolvida automaticamente ao bot após {TIMEOUT_MINUTOS} minutos de inatividade humana."
            })

            await sessions_collection.update_one(
                {"telefone": telefone},
                {"$set": {
                    "owner": "bot",
                    "historico": historico,
                    "human_takeover_at": None,
                    "last_human_activity_at": None
                }}
            )

            print(f"✅ [AutoReturn] Sessão {telefone} devolvida ao bot com sucesso.")
