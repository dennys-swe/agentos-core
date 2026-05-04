import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

# Instancia o cliente global
client = AsyncIOMotorClient(MONGO_URI)

# Define o nome do seu banco de dados e a coleção (tabela)
db = client["agentos_db"]
sessions_collection = db["sessions"]

print("🔌 Conexão com o banco de dados 'agentos_db' instanciada.")
