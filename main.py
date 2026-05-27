import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from controllers import webhook
from controllers import atendimento
from services.ia_service import processar_mensagem_com_memoria
from services.auto_return_service import iniciar_verificacao_inatividade
from core.database import sessions_collection

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Executado na inicialização
    asyncio.create_task(iniciar_verificacao_inatividade())
    yield

app = FastAPI(
    title="AgentOS API",
    description="Motor central para orquestração de agentes de IA na saúde.",
    version="1.0.0",
    lifespan=lifespan
)

# Registra o router do webhook e define que o caminho base será /webhook
app.include_router(webhook.router, prefix="/webhook", tags=["WhatsApp Webhook"])
app.include_router(atendimento.router, prefix="", tags=["Atendimento Humano"])

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

@app.get("/api/admin/leads", tags=["Admin"])
async def get_admin_leads():
    leads = []
    async for session in sessions_collection.find():
        leads.append({
            "telefone": session.get("telefone"),
            "nome": session.get("nome"),
            "motivo": session.get("motivo"),
            "convenio": session.get("convenio"),
            "status": session.get("status", "desconhecido")
        })
    return leads

@app.get("/admin", response_class=HTMLResponse, tags=["Admin"])
async def admin_interface():
    html_path = os.path.join(os.path.dirname(__file__), "frontend", "admin.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/atendimento", response_class=HTMLResponse, tags=["Atendimento Humano"])
async def atendimento_interface():
    html_path = os.path.join(os.path.dirname(__file__), "frontend", "atendimento.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

