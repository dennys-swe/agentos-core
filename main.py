import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from controllers import webhook
from controllers import atendimento
from controllers import auth
from controllers import super_admin
from services.ia_service import processar_mensagem_com_memoria
from services.auto_return_service import iniciar_verificacao_inatividade
from services.auth_service import get_current_user, get_empresa_filter
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

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    # Se der erro 401 em rotas de páginas (que não são da API), redireciona para o login
    if exc.status_code == 401 and not request.url.path.startswith("/api/"):
        return RedirectResponse(url="/login", status_code=303)
        
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# Registra os routers
app.include_router(webhook.router, prefix="/webhook", tags=["WhatsApp Webhook"])
app.include_router(atendimento.router, prefix="", tags=["Atendimento Humano"])
app.include_router(auth.router, prefix="", tags=["Autenticação"])
app.include_router(super_admin.router, prefix="", tags=["Super Admin"])


# ── Rotas Públicas ──

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


# ── Rotas Protegidas ──

class ChatRequest(BaseModel):
    telefone: str
    mensagem: str
    empresa_id: str | None = None  # Opcional: testa o agente de uma clínica específica

@app.post("/api/simulator/chat", tags=["Simulador"])
async def simulator_chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Simulador de chat. Se empresa_id for passado, usa o prompt e config daquela clínica.
    Útil para o Super Admin testar o agente de um cliente sem precisar do WhatsApp real.
    """
    empresa = None
    if request.empresa_id:
        from bson import ObjectId
        from core.database import empresas_collection
        try:
            empresa = await empresas_collection.find_one({"_id": ObjectId(request.empresa_id)})
        except Exception:
            pass

    resposta_ia = await processar_mensagem_com_memoria(request.telefone, request.mensagem, empresa)
    return {"resposta": resposta_ia}

@app.delete("/api/simulator/chat/{telefone}", tags=["Simulador"])
async def limpar_chat_simulador(telefone: str, current_user: dict = Depends(get_current_user)):
    """Remove a sessão do simulador para reiniciar o teste do zero."""
    if not telefone.startswith("simulador_"):
        raise HTTPException(status_code=400, detail="Apenas sessões do simulador podem ser apagadas por esta rota.")
    from core.database import sessions_collection
    result = await sessions_collection.delete_one({"telefone": telefone})
    return {"sucesso": True, "apagado": result.deleted_count > 0}

@app.get("/chat", response_class=HTMLResponse, tags=["Simulador"])
async def chat_interface(current_user: dict = Depends(get_current_user)):
    html_path = os.path.join(os.path.dirname(__file__), "frontend", "chat.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/admin/leads", tags=["Admin"])
async def get_admin_leads(current_user: dict = Depends(get_current_user)):
    leads = []
    filtro = get_empresa_filter(current_user)
    async for session in sessions_collection.find(filtro):
        leads.append({
            "telefone": session.get("telefone"),
            "nome": session.get("nome"),
            "motivo": session.get("motivo"),
            "convenio": session.get("convenio"),
            "status": session.get("status", "desconhecido")
        })
    return leads

@app.get("/admin", response_class=HTMLResponse, tags=["Admin"])
async def admin_interface(current_user: dict = Depends(get_current_user)):
    html_path = os.path.join(os.path.dirname(__file__), "frontend", "admin.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/atendimento", response_class=HTMLResponse, tags=["Atendimento Humano"])
async def atendimento_interface(current_user: dict = Depends(get_current_user)):
    html_path = os.path.join(os.path.dirname(__file__), "frontend", "atendimento.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


@app.get("/super-admin", response_class=HTMLResponse, tags=["Super Admin"])
async def super_admin_interface(current_user: dict = Depends(get_current_user)):
    """Painel exclusivo da AgentOS para gerenciar clínicas e usuários. Requer role=super_admin."""
    if current_user.get("role") != "super_admin":
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/atendimento", status_code=303)
    html_path = os.path.join(os.path.dirname(__file__), "frontend", "super-admin.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()
