"""
Script para criar usuários administradores no AgentOS.

Uso:
    python scripts/criar_usuario.py
"""
import asyncio
import sys
import os
import getpass

# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.database import users_collection
from services.auth_service import hash_password


async def criar_usuario():
    print("=" * 50)
    print("  🔐 AgentOS — Criar Usuário Admin")
    print("=" * 50)
    print()

    nome = input("  Nome completo: ").strip()
    if not nome:
        print("  ❌ Nome não pode ser vazio.")
        return

    username = input("  Usuário (login): ").strip().lower()
    if not username:
        print("  ❌ Usuário não pode ser vazio.")
        return

    # Verifica se já existe
    existente = await users_collection.find_one({"username": username})
    if existente:
        print(f"  ❌ O usuário '{username}' já existe.")
        return

    password = getpass.getpass("  Senha: ").strip()
    if len(password) < 4:
        print("  ❌ A senha precisa ter pelo menos 4 caracteres.")
        return

    password_confirm = getpass.getpass("  Confirme a senha: ").strip()
    if password != password_confirm:
        print("  ❌ As senhas não coincidem.")
        return

    # Cria o documento
    from datetime import datetime, timezone
    user_doc = {
        "nome": nome,
        "username": username,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc),
    }

    await users_collection.insert_one(user_doc)
    print()
    print(f"  ✅ Usuário '{username}' criado com sucesso!")
    print(f"  📝 Nome: {nome}")
    print(f"  🔑 Faça login em /login com essas credenciais.")
    print()


if __name__ == "__main__":
    asyncio.run(criar_usuario())
