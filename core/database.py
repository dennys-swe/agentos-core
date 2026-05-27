import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

import certifi

client = AsyncIOMotorClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)

# Define o nome do seu banco de dados e a coleção (tabela)
db = client["agentos_db"]
sessions_collection = db["sessions"]

print("🔌 Conexão com o banco de dados 'agentos_db' instanciada.")
