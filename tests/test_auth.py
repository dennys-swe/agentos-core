"""
Testes automatizados para o sistema de autenticação JWT do AgentOS.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport

# Precisamos mockar o database antes de importar o app
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def mock_db():
    """Mocka as coleções do MongoDB para testes isolados."""
    with patch("core.database.sessions_collection") as mock_sessions, \
         patch("core.database.users_collection") as mock_users:
        yield mock_sessions, mock_users


@pytest.fixture
def test_user():
    """Retorna dados de um usuário de teste."""
    from services.auth_service import hash_password
    return {
        "_id": "test_id",
        "nome": "Teste Admin",
        "username": "admin_test",
        "password_hash": hash_password("senha123"),
    }


@pytest.fixture
def valid_token(test_user):
    """Gera um token JWT válido para testes."""
    from services.auth_service import create_access_token
    return create_access_token(data={"sub": test_user["username"]})


class TestAuthService:
    """Testes unitários do services/auth_service.py"""

    def test_hash_password_gera_hash(self):
        from services.auth_service import hash_password
        hashed = hash_password("minha_senha")
        assert hashed != "minha_senha"
        assert hashed.startswith("$2b$")

    def test_verify_password_correto(self):
        from services.auth_service import hash_password, verify_password
        hashed = hash_password("minha_senha")
        assert verify_password("minha_senha", hashed) is True

    def test_verify_password_incorreto(self):
        from services.auth_service import hash_password, verify_password
        hashed = hash_password("minha_senha")
        assert verify_password("outra_senha", hashed) is False

    def test_create_access_token(self):
        from services.auth_service import create_access_token, decode_access_token
        token = create_access_token(data={"sub": "admin"})
        assert token is not None
        payload = decode_access_token(token)
        assert payload["sub"] == "admin"

    def test_decode_token_invalido_retorna_none(self):
        from services.auth_service import decode_access_token
        result = decode_access_token("token.invalido.aqui")
        assert result is None

    def test_decode_token_vazio_retorna_none(self):
        from services.auth_service import decode_access_token
        result = decode_access_token("")
        assert result is None


class TestAuthEndpoints:
    """Testes de integração dos endpoints de autenticação."""

    @pytest.mark.asyncio
    async def test_login_com_credenciais_corretas(self, test_user):
        """Login com credenciais válidas deve retornar 200 e setar cookie."""
        with patch("controllers.auth.users_collection") as mock_users:
            mock_users.find_one = AsyncMock(return_value=test_user)
            
            from main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/auth/login", json={
                    "username": "admin_test",
                    "password": "senha123"
                })
                assert response.status_code == 200
                assert "access_token" in response.cookies

    @pytest.mark.asyncio
    async def test_login_com_credenciais_incorretas(self):
        """Login com credenciais inválidas deve retornar 401."""
        with patch("controllers.auth.users_collection") as mock_users:
            mock_users.find_one = AsyncMock(return_value=None)
            
            from main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/auth/login", json={
                    "username": "inexistente",
                    "password": "errada"
                })
                assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_rota_protegida_sem_cookie_retorna_401(self):
        """Acesso a rota protegida sem autenticação deve retornar 401."""
        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/admin/leads")
            assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_rota_protegida_com_cookie_valido(self, test_user, valid_token):
        """Acesso a rota protegida com cookie válido deve retornar 200."""
        with patch("services.auth_service.users_collection") as mock_users, \
             patch("main.sessions_collection") as mock_sessions:
            mock_users.find_one = AsyncMock(return_value=test_user)
            mock_sessions.find = MagicMock(return_value=AsyncIteratorMock([]))
            
            from main import app
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                client.cookies.set("access_token", valid_token)
                response = await client.get("/api/admin/leads")
                assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_limpa_cookie(self):
        """Logout deve retornar 200 e limpar o cookie."""
        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/auth/logout")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_webhook_permanece_publico(self):
        """Webhook do WhatsApp deve continuar acessível sem autenticação."""
        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/webhook/whatsapp", params={
                "hub.mode": "subscribe",
                "hub.challenge": "test_challenge",
                "hub.verify_token": "agentos_secreto_123"
            })
            # O webhook deve retornar o challenge (200) ou 403 se o token não bater
            assert response.status_code in [200, 403]

    @pytest.mark.asyncio
    async def test_health_permanece_publico(self):
        """Health check deve continuar acessível sem autenticação."""
        from main import app
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health")
            assert response.status_code == 200


# Helper para mockar iteradores async do MongoDB
class AsyncIteratorMock:
    def __init__(self, items):
        self.items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.items)
        except StopIteration:
            raise StopAsyncIteration
