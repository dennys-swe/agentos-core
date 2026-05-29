"""
Script para criar usuários no AgentOS (Atendentes ou Super Admins).

Uso:
    # Criar Super Admin da agência:
    python scripts/criar_usuario.py --super-admin

    # Criar atendente de clínica:
    python scripts/criar_usuario.py
"""
import asyncio
import sys
import os
import getpass
import argparse

# Adiciona o diretório raiz do projeto ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.database import users_collection
from services.auth_service import hash_password


async def criar_usuario(is_super_admin: bool = False):
    print("=" * 55)
    if is_super_admin:
        print("  ⭐ AgentOS — Criar Super Admin (Agência)")
    else:
        print("  👤 AgentOS — Criar Usuário Atendente")
    print("=" * 55)
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

    # Define role e clinica_id
    role = "super_admin" if is_super_admin else "atendente"
    clinica_id = None

    if not is_super_admin:
        print()
        clinica_id = input("  ID da Clínica (clinica_id do MongoDB): ").strip()
        if not clinica_id:
            print("  ❌ clinica_id é obrigatório para atendentes.")
            return

    # Cria o documento
    from datetime import datetime, timezone
    user_doc = {
        "nome": nome,
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "clinica_id": clinica_id,
        "created_at": datetime.now(timezone.utc),
    }

    await users_collection.insert_one(user_doc)
    print()
    print(f"  ✅ Usuário '{username}' criado com sucesso!")
    print(f"  📝 Nome: {nome}")
    print(f"  🎭 Role: {role}")
    if clinica_id:
        print(f"  🏥 Clínica ID: {clinica_id}")
    if is_super_admin:
        print(f"  🚀 Acesse o painel em /super-admin")
    else:
        print(f"  🔑 Faça login em /login com essas credenciais.")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Criar usuário no AgentOS")
    parser.add_argument("--super-admin", action="store_true", help="Criar um Super Admin da agência")
    args = parser.parse_args()

    asyncio.run(criar_usuario(is_super_admin=args.super_admin))
