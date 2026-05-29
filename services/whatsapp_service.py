import httpx
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Valores padrão do .env (usados como fallback para o simulador e testes locais)
DEFAULT_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
DEFAULT_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")

def formatar_numero_br(telefone: str) -> str:
    """Garante o 9º dígito para números brasileiros."""
    num = ''.join(filter(str.isdigit, telefone))
    if num.startswith("55") and len(num) == 12:
        num = num[:4] + "9" + num[4:]
    return num

async def enviar_mensagem_whatsapp(
    telefone_destinatario: str,
    texto_total: str,
    access_token: str = None,
    phone_id: str = None,
):
    """
    Envia mensagem via WhatsApp API.
    Se access_token e phone_id não forem fornecidos, usa o fallback do .env.
    Isso permite que cada clínica use seus próprios tokens (Multi-Tenant).
    """
    token = access_token or DEFAULT_ACCESS_TOKEN
    pid = phone_id or DEFAULT_PHONE_ID
    url = f"https://graph.facebook.com/v25.0/{pid}/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    telefone_ajustado = formatar_numero_br(telefone_destinatario)

    # Divide o texto pelo separador '|' definido no prompt
    partes = [p.strip() for p in texto_total.split('|') if p.strip()]

    async with httpx.AsyncClient() as client:
        for mensagem in partes:
            # --- LÓGICA DE HUMANIZAÇÃO ---
            # Tempo base de 1.5s + 0.06s por caractere (simula velocidade de digitação humana)
            # Limitamos entre 1.5 e 4.0 segundos para não ficar lento demais
            tempo_espera = max(1.5, min(len(mensagem) * 0.06, 4.0))

            print(f"⏳ Simulando digitação: {tempo_espera:.1f}s para a frase: '{mensagem[:20]}...'")
            await asyncio.sleep(tempo_espera)

            data = {
                "messaging_product": "whatsapp",
                "to": telefone_ajustado,
                "type": "text",
                "text": {"body": mensagem}
            }

            try:
                response = await client.post(url, json=data, headers=headers)
                if response.status_code == 200:
                    print(f"✅ Balão enviado com sucesso.")
                else:
                    print(f"❌ Erro Meta: {response.text}")
            except Exception as e:
                print(f"❌ Falha crítica no envio: {e}")