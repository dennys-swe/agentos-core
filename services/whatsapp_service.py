import httpx
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
URL = f"https://graph.facebook.com/v25.0/{PHONE_ID}/messages"

def formatar_numero_br(telefone: str) -> str:
    """Garante o 9º dígito para números brasileiros."""
    num = ''.join(filter(str.isdigit, telefone))
    if num.startswith("55") and len(num) == 12:
        num = num[:4] + "9" + num[4:]
    return num

async def enviar_mensagem_whatsapp(telefone_destinatario: str, texto_total: str):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
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
                response = await client.post(URL, json=data, headers=headers)
                if response.status_code == 200:
                    print(f"✅ Balão enviado com sucesso.")
                else:
                    print(f"❌ Erro Meta: {response.text}")
            except Exception as e:
                print(f"❌ Falha crítica no envio: {e}")