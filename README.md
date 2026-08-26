# AgentOS

Motor de orquestração de agentes de IA para atendimento no WhatsApp, construído em
**Python + FastAPI** com **MongoDB**. Um agente conversa com o paciente, coleta os dados
do lead e entrega o atendimento a um humano quando necessário — devolvendo a conversa ao
agente sozinho quando o atendimento esfria.

Arquitetura **multi-tenant**: uma única instância atende várias clínicas, cada uma com seu
próprio prompt, credenciais de WhatsApp e dados isolados.

> Projeto autoral, usado como base para implantações reais em clínicas.

---

## Stack

| Camada | Tecnologia |
| :--- | :--- |
| API | FastAPI (async), Pydantic v2 |
| Banco de dados | MongoDB — driver async **Motor**, conexão TLS |
| Autenticação | JWT (`python-jose`) em cookie, senhas com hash **bcrypt** |
| Motor de IA | LangChain + OpenRouter (padrão: `google/gemini-2.5-flash`) |
| Integração | WhatsApp Cloud API (Meta Graph v25) via `httpx` |
| Testes | pytest + pytest-asyncio |
| Painéis | HTML/JS servidos pela própria API |

---

## Como funciona

```
WhatsApp (Meta)  ──POST /webhook/whatsapp──►  FastAPI
                                               │
                        BackgroundTask ────────┤ resolve o tenant pelo phone_number_id
                                               │
                                   MongoDB ◄───┤ carrega sessão + histórico da conversa
                                               │
                              LangChain/LLM ◄──┤ gera resposta com o prompt daquela clínica
                                               │
                        WhatsApp API ◄─────────┘ responde ao paciente
```

Em paralelo, uma **task assíncrona no `lifespan` da aplicação** varre as sessões a cada 60
segundos e aplica as regras de inatividade do transbordo humano.

### Multi-tenant

O webhook identifica a clínica pelo `phone_number_id` que a Meta envia, e a partir daí tudo
é resolvido por tenant: prompt do sistema, credenciais de envio e filtro nas coleções. Cada
sessão é chaveada por `telefone + empresa_id`, de modo que o mesmo paciente pode falar com
duas clínicas sem colisão de histórico. Usuários comuns só alcançam os dados da própria
clínica (`get_empresa_filter`); o papel `super_admin` administra todas.

### Transbordo humano com retorno automático

Cada sessão tem um `owner`: `bot` ou `human`. Quando um atendente assume, o agente para de
responder (retorna `_SILENCE_`, e nada é enviado ao paciente). O `auto_return_service`
então cuida do ciclo de vida daquele atendimento:

- **5 min** sem resposta do paciente → aviso enviado a ele;
- **+5 min** de silêncio após o aviso → atendimento encerrado e sessão devolvida ao agente;
- **20 min** sem qualquer ação do atendente → sessão devolvida ao agente.

Isso evita o modo de falha mais comum desse tipo de sistema: a conversa fica presa com um
humano que não voltou, e o paciente deixa de ser atendido por qualquer um dos dois.

### Humanização das respostas

O agente devolve blocos separados por `|`, enviados como mensagens sucessivas com atraso
proporcional ao tamanho do texto (1,5 s a 4,0 s), simulando digitação em vez de despejar um
parágrafo único.

---

## Estrutura

```
main.py                      app FastAPI, lifespan, rotas públicas e painéis
controllers/
  webhook.py                 verificação e recebimento do webhook da Meta
  atendimento.py             fila de atendimento humano, responder, devolver ao bot
  auth.py                    login, logout, sessão atual
  super_admin.py             CRUD de clínicas e usuários, estatísticas
services/
  ia_service.py              montagem do prompt, memória da conversa, chamada ao LLM
  whatsapp_service.py        envio pela Graph API, formatação de número BR, humanização
  auth_service.py            hash bcrypt, emissão/validação de JWT, dependency de sessão
  auto_return_service.py     loop de inatividade e devolução ao agente
core/
  database.py                cliente Motor e coleções (sessions, users, empresas)
  config_empresa.py          horário comercial e configuração por clínica
  prompts.py                 prompt padrão (fallback do simulador)
frontend/                    painéis: login, atendimento, admin, super-admin
tests/                       testes de autenticação e do fluxo do webhook
scripts/criar_usuario.py     criação de atendentes e super admins
```

---

## Rodando localmente

Requer Python 3.11+ e uma instância de MongoDB.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # preencha as variáveis (ver abaixo)
python scripts/criar_usuario.py --super-admin   # cria o primeiro usuário (admin)

uvicorn main:app --reload
```

- API: <http://localhost:8000> · documentação automática: <http://localhost:8000/docs>
- `GET /health` responde o status do serviço
- Painéis: `/login`, `/atendimento`, `/admin`, `/super-admin`
- `/chat` é um simulador que conversa com o agente sem depender do WhatsApp real — dá para
  testar o agente de uma clínica específica passando `empresa_id`

### Variáveis de ambiente

Todas documentadas em [`.env.example`](.env.example): `MONGO_URI`, `JWT_SECRET_KEY`,
`JWT_EXPIRE_HOURS`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `WHATSAPP_ACCESS_TOKEN`,
`WHATSAPP_PHONE_ID`, `META_VERIFY_TOKEN` e `HUMAN_INACTIVITY_TIMEOUT_MINUTES`.

## Testes

```bash
pytest -v
```

15 testes cobrindo o handshake de verificação do webhook, o fluxo de recebimento de
mensagem e a autenticação (hash de senha, emissão e validação de JWT, isolamento por tenant).

---

## Principais rotas

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `GET` | `/webhook/whatsapp` | handshake de verificação da Meta |
| `POST` | `/webhook/whatsapp` | recebe mensagens e processa em background |
| `POST` | `/api/auth/login` | autentica e emite o JWT |
| `GET` | `/api/admin/atendimentos` | fila de atendimento da clínica |
| `POST` | `/api/admin/atendimentos/{telefone}/responder` | atendente humano responde |
| `POST` | `/api/admin/atendimentos/{telefone}/devolver` | devolve a sessão ao agente |
| `GET` | `/api/admin/leads` | leads captados pelo agente |
| `GET` | `/api/super-admin/empresas` | administração de clínicas (`super_admin`) |
| `POST` | `/api/simulator/chat` | conversa com o agente sem WhatsApp |

---

## Autor

**Dennys Alves Silva** — [github.com/dennys-swe](https://github.com/dennys-swe) ·
[linkedin.com/in/dennysdev](https://www.linkedin.com/in/dennysdev/)
