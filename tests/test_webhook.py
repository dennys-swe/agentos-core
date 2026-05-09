import pytest
from httpx import AsyncClient, ASGITransport
from main import app
import asyncio

@pytest.mark.asyncio
async def test_webhook_verification():
    """Testa o 'aperto de mão' (GET) da Meta - ESSE JÁ PASSOU! ✅"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        params = {
            "hub.mode": "subscribe",
            "hub.verify_token": "agentos_secreto_123",
            "hub.challenge": "123456"
        }
        response = await ac.get("/webhook/whatsapp", params=params)
    
    assert response.status_code == 200
    assert response.text == "123456"

@pytest.mark.asyncio
async def test_receive_message_flow():
    """Simula o envio de uma mensagem de texto pelo usuário (POST)"""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "12345",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "55879..."},
                    "messages": [{
                        "from": "558791714659",
                        "id": "wamid.ID",
                        "timestamp": "123456",
                        "text": {"body": "Olá, meu nome é Dennys e quero agendar"},
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.post("/webhook/whatsapp", json=payload)
    
    # 1. Ajustado para 'success' conforme o seu código real
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    # 2. Como o processamento é em BackgroundTask, damos um pequeno tempo
    # Mas atenção: se o MongoDB der erro de SSL, essa parte pode falhar.
    await asyncio.sleep(2)