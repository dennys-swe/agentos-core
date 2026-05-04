from fastapi import FastAPI
from controllers import webhook  # Importa o módulo que acabamos de criar

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
