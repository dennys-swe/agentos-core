import os
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from controllers import webhook
from services.ia_service import processar_mensagem_com_memoria

app = FastAPI(
    title="AgentOS API",
    description="Motor central para orquestração de agentes de IA na saúde.",
    version="1.0.0"
)

# Registra o router do webhook e define que o caminho base será /webhook
app.include_router(webhook.router, prefix="/webhook", tags=["WhatsApp Webhook"])

@app.get("/")
async def root():
    return {
        "status": "AgentOS is online",
        "message": "Bem-vindo ao motor central da API."
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok", 
        "service": "AgentOS Core",
        "database": "Configurado"
    }

class ChatRequest(BaseModel):
    telefone: str
    mensagem: str

@app.post("/api/simulator/chat", tags=["Simulador"])
async def simulator_chat(request: ChatRequest):
    resposta_ia = await processar_mensagem_com_memoria(request.telefone, request.mensagem)
    return {"resposta": resposta_ia}

@app.get("/chat", response_class=HTMLResponse, tags=["Simulador"])
async def chat_interface():
    html_path = os.path.join(os.path.dirname(__file__), "frontend", "chat.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()
