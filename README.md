# AgentOS

AI-agent orchestration backend for WhatsApp customer service, built with **Python + FastAPI**
and **MongoDB**. An agent talks to the patient, collects the lead's data, and hands the
conversation to a human when needed — automatically returning it to the agent once the
human interaction goes cold.

**Multi-tenant** architecture: a single instance serves many clinics, each with its own
system prompt, WhatsApp credentials, and isolated data.

> Original project, used as the base for real clinic deployments.

---

## Screenshots

<!--
Add real screenshots here. Easiest way:
1. Run the app (see "Running locally").
2. Capture the chat simulator (/chat), the human-handoff queue (/atendimento), and /super-admin.
3. Drag them into a GitHub issue comment to get hosted URLs, or commit them to docs/img/.
4. Replace the lines below.
-->

| Chat simulator | Handoff queue | Super-admin |
| :---: | :---: | :---: |
| _screenshot pending_ | _screenshot pending_ | _screenshot pending_ |

---

## Stack

| Layer | Technology |
| :--- | :--- |
| API | FastAPI (async), Pydantic v2 |
| Database | MongoDB — async **Motor** driver, TLS connection |
| Auth | JWT (`python-jose`) in a cookie, passwords hashed with **bcrypt** |
| AI engine | LangChain + OpenRouter (default: `google/gemini-2.5-flash`) |
| Integration | WhatsApp Cloud API (Meta Graph v25) via `httpx` |
| Tests | pytest + pytest-asyncio |
| Panels | HTML/JS served by the API itself |

---

## How it works

```
WhatsApp (Meta)  ──POST /webhook/whatsapp──►  FastAPI
                                               │
                        BackgroundTask ────────┤ resolves the tenant by phone_number_id
                                               │
                                   MongoDB ◄───┤ loads the session + conversation history
                                               │
                              LangChain/LLM ◄──┤ generates a reply with that clinic's prompt
                                               │
                        WhatsApp API ◄─────────┘ replies to the patient
```

In parallel, an **async task on the application `lifespan`** scans the sessions every 60
seconds and applies the human-handoff inactivity rules.

### Multi-tenant

The webhook identifies the clinic by the `phone_number_id` that Meta sends, and from there
everything is resolved per tenant: system prompt, sending credentials, and collection
filters. Each session is keyed by `phone + empresa_id`, so the same patient can talk to two
clinics with no history collision. Regular users only reach their own clinic's data
(`get_empresa_filter`); the `super_admin` role administers all of them.

### Human handoff with automatic return

Each session has an `owner`: `bot` or `human`. When an agent takes over, the AI stops
replying (returns `_SILENCE_`, and nothing is sent to the patient). The `auto_return_service`
then manages that interaction's lifecycle:

- **5 min** without a patient reply → a notice is sent to them;
- **+5 min** of silence after the notice → interaction closed, session returned to the AI;
- **20 min** without any action from the agent → session returned to the AI.

This avoids the most common failure mode of this kind of system: the conversation gets stuck
with a human who never came back, and the patient stops being served by either side.

### Response humanization

The agent returns blocks separated by `|`, sent as successive messages with a delay
proportional to the text length (1.5 s to 4.0 s), simulating typing instead of dumping a
single paragraph.

---

## Structure

```
main.py                      FastAPI app, lifespan, public routes and panels
controllers/
  webhook.py                 Meta webhook verification and message intake
  atendimento.py             human-service queue: reply, return to bot
  auth.py                    login, logout, current session
  super_admin.py             clinic and user CRUD, statistics
services/
  ia_service.py              prompt assembly, conversation memory, LLM call
  whatsapp_service.py        Graph API sending, BR phone formatting, humanization
  auth_service.py            bcrypt hashing, JWT issue/validate, session dependency
  auto_return_service.py     inactivity loop and return-to-agent logic
core/
  database.py                Motor client and collections (sessions, users, empresas)
  config_empresa.py          business hours and per-clinic configuration
  prompts.py                 default prompt (simulator fallback)
frontend/                    panels: login, atendimento, admin, super-admin
tests/                       auth and webhook-flow tests
scripts/criar_usuario.py     create agents and super admins
```

---

## Running locally

Requires Python 3.11+ and a MongoDB instance.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # fill in the variables (see below)
python scripts/criar_usuario.py --super-admin   # create the first user (admin)

uvicorn main:app --reload
```

- API: <http://localhost:8000> · auto docs: <http://localhost:8000/docs>
- `GET /health` returns the service status
- Panels: `/login`, `/atendimento`, `/admin`, `/super-admin`
- `/chat` is a simulator that talks to the agent without depending on real WhatsApp — you can
  test a specific clinic's agent by passing `empresa_id`

### Environment variables

All documented in [`.env.example`](.env.example): `MONGO_URI`, `JWT_SECRET_KEY`,
`JWT_EXPIRE_HOURS`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `WHATSAPP_ACCESS_TOKEN`,
`WHATSAPP_PHONE_ID`, `META_VERIFY_TOKEN` and `HUMAN_INACTIVITY_TIMEOUT_MINUTES`.

## Tests

```bash
pytest -v
```

15 tests covering the webhook verification handshake, the message-intake flow, and
authentication (password hashing, JWT issue/validation, per-tenant isolation).

---

## Main routes

| Method | Route | Description |
| :--- | :--- | :--- |
| `GET` | `/webhook/whatsapp` | Meta verification handshake |
| `POST` | `/webhook/whatsapp` | receives messages, processes in background |
| `POST` | `/api/auth/login` | authenticates and issues the JWT |
| `GET` | `/api/admin/atendimentos` | the clinic's service queue |
| `POST` | `/api/admin/atendimentos/{phone}/responder` | human agent replies |
| `POST` | `/api/admin/atendimentos/{phone}/devolver` | returns the session to the agent |
| `GET` | `/api/admin/leads` | leads captured by the agent |
| `GET` | `/api/super-admin/empresas` | clinic administration (`super_admin`) |
| `POST` | `/api/simulator/chat` | talk to the agent without WhatsApp |

---

## Author

**Dennys Alves Silva** — [github.com/dennys-swe](https://github.com/dennys-swe) ·
[linkedin.com/in/dennysdev](https://www.linkedin.com/in/dennysdev/)
