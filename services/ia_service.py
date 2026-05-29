import os
import json
import re
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv

# Importa nossa coleção de sessões do MongoDB
from core.database import sessions_collection
# Importa configurações e prompt padrão (fallback para simulador/testes)
from core.config_empresa import esta_em_horario_comercial
from core.prompts import PROMPT_SISTEMA as PROMPT_SISTEMA_PADRAO

load_dotenv()

def get_model():
    provider = os.getenv("MODEL_PROVIDER", "gemini").lower()

    if provider == "groq":
        print("🚀 [AgentOS] Usando motor Groq (Llama 3.1)")
        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.1
        )
    else:
        print("🧠 [AgentOS] Usando motor Google (Gemini)")
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.1
        )

# Inicialização do LLM é feita uma única vez no startup
llm = get_model()


async def processar_mensagem_com_memoria(
    telefone_paciente: str,
    texto_usuario: str,
    empresa: dict | None = None,
) -> str:
    """
    Processa a mensagem do paciente e gera uma resposta via IA.

    Args:
        telefone_paciente: Número do paciente.
        texto_usuario: Texto enviado pelo paciente.
        empresa: Documento da clínica do MongoDB. Se None, usa os padrões do .env (simulador/fallback).
    """
    # Extrai o contexto da clínica ou usa os defaults
    empresa_id = str(empresa["_id"]) if empresa else "simulador"
    prompt_sistema = empresa.get("prompt_sistema", PROMPT_SISTEMA_PADRAO) if empresa else PROMPT_SISTEMA_PADRAO
    empresa_nome = empresa.get("nome", "Clínica AgentOS") if empresa else "Clínica AgentOS"

    # 1. Busca a sessão no banco (filtrando pela clínica para evitar colisão entre tenants)
    sessao = await sessions_collection.find_one({
        "telefone": telefone_paciente,
        "empresa_id": empresa_id
    })

    # 👇 A TRAVA DEVE FICAR AQUI, LOGO APÓS A BUSCA 👇
    if sessao and sessao.get("owner") == "human":
        print(f"⏸️ [Transbordo] Conversa com {telefone_paciente} ({empresa_nome}) pausada. IA silenciada.")

        # Apenas guarda a mensagem nova do paciente para a recepcionista ler depois
        novo_historico = sessao.get("historico", []) + [{"role": "user", "content": texto_usuario}]
        await sessions_collection.update_one(
            {"telefone": telefone_paciente, "empresa_id": empresa_id},
            {"$set": {
                "historico": novo_historico,
                "last_patient_activity_at": datetime.utcnow(),
                "inactivity_warning_sent": False
            }}
        )
        return "_SILENCE_"
    # --------------------------------------------------

    historico_bd = []
    if sessao:
        historico_bd = sessao.get("historico", [])
    else:
        print(f"🆕 Nova sessão criada para o paciente {telefone_paciente} na clínica '{empresa_nome}'")
        await sessions_collection.insert_one({
            "telefone": telefone_paciente,
            "empresa_id": empresa_id,
            "historico": [],
            "nome": None,
            "motivo": None,
            "convenio": None,
            "status": "triagem_iniciada",
            "owner": "bot"
        })

    # 2. Monta o Prompt de Sistema DINÂMICO (substituindo placeholder do telefone se existir)
    prompt_conteudo = prompt_sistema
    if "{telefone_paciente}" in prompt_conteudo:
        prompt_conteudo = prompt_conteudo.replace("{telefone_paciente}", telefone_paciente)

    # 3. Garante o bloco de instruções JSON — SEMPRE necessário para o parser funcionar.
    #    Se o prompt da empresa não contiver as instruções de saída JSON, injetamos automaticamente.
    #    Isso libera o admin de precisar conhecer detalhes técnicos ao escrever o prompt.
    campos_extracao = empresa.get("campos_extracao", ["nome", "motivo", "convenio"]) if empresa else ["nome", "motivo", "convenio"]
    
    # Monta a estrutura JSON dinamicamente baseada nos campos solicitados pela equipe AgentOS
    if not campos_extracao:
        json_keys = '"extraido": "nenhum campo solicitado"'
    else:
        json_keys = ",\n    ".join([f'"{campo}": "valor ou null"' for campo in campos_extracao])

    JSON_FORMAT_BLOCK = f"""

====================================
INSTRUÇÃO CRÍTICA DO SISTEMA:
====================================
Você NÃO é um chatbot comum respondendo texto. Você é um microsserviço que processa dados para uma API.
Você DEVE OBRIGATORIAMENTE formatar SUA RESPOSTA INTEIRA como um ÚNICO bloco JSON válido.
NÃO retorne texto puro, apenas o JSON.

Estrutura JSON EXATA que você deve retornar (preencha os valores):
```json
{{
  "resposta_para_paciente": "Sua resposta final aqui. Use o caractere | para separar múltiplos balões de mensagem.",
  "dados_extraidos": {{
    {json_keys}
  }},
  "necessita_humano": false
}}
```
Regra: Marque "necessita_humano": true SOMENTE SE o paciente pedir explicitamente para falar com um atendente humano ou relatar emergência.
"""

    if "necessita_humano" not in prompt_conteudo:
        prompt_conteudo += JSON_FORMAT_BLOCK

    prompt_personalizado = SystemMessage(content=prompt_conteudo)

    # 3. Monta a lista de mensagens para o LLM
    mensagens_langchain = [prompt_personalizado]
    for msg in historico_bd:
        if msg["role"] == "user":
            mensagens_langchain.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            mensagens_langchain.append(AIMessage(content=msg["content"]))
        # Mensagens de sistema (role: "system") são ignoradas no histórico do LLM

    mensagens_langchain.append(HumanMessage(content=texto_usuario))

    try:
        print(f"🧠 [AgentOS] Gerando resposta para {telefone_paciente} ({empresa_nome})...")
        resposta = await llm.ainvoke(mensagens_langchain)
        conteudo_bruto = resposta.content

        # --- LÓGICA DE LIMPEZA E EXTRAÇÃO ROBUSTA ---
        try:
            match = re.search(r'\{.*\}', conteudo_bruto, re.DOTALL)

            if match:
                conteudo_limpo = match.group(0)
            else:
                conteudo_limpo = conteudo_bruto

            parsed_response = json.loads(conteudo_limpo)
            texto_resposta = parsed_response.get("resposta_para_paciente", "Desculpe, pode repetir?")
            dados_extraidos = parsed_response.get("dados_extraidos", {})

            # Verifica se a IA pediu ajuda humana
            necessita_humano = parsed_response.get("necessita_humano", False)

            if necessita_humano:
                if esta_em_horario_comercial():
                    print(f"🚨 [Transbordo] Transferindo {telefone_paciente} ({empresa_nome}) para humano.")
                    await sessions_collection.update_one(
                        {"telefone": telefone_paciente, "empresa_id": empresa_id},
                        {"$set": {
                            "owner": "human",
                            "human_takeover_at": datetime.utcnow(),
                            "last_human_activity_at": datetime.utcnow()
                        }}
                    )
                else:
                    print(f"🕐 [Transbordo] Fora do horário. {telefone_paciente} ficará com o bot.")
                    texto_resposta = (
                        "Nossos atendentes estão disponíveis de segunda a sexta, "
                        "das 08h às 18h. Posso anotar seu contato para que a equipe "
                        "retorne no próximo horário comercial. Enquanto isso, posso "
                        "continuar te ajudando por aqui! 😊"
                    )

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print(f"⚠️ Erro crítico ao decodificar JSON: {e}. Conteúdo: {conteudo_bruto}")
            texto_resposta = "Desculpe, tive um pequeno lapso de memória. Poderia repetir?"
            dados_extraidos = {}

        # 5. Salva no banco (histórico + dados estruturados)
        novo_historico = historico_bd + [
            {"role": "user", "content": texto_usuario},
            {"role": "assistant", "content": texto_resposta}
        ]

        update_payload = {"$set": {"historico": novo_historico}}

        if dados_extraidos:
            campos_para_atualizar = {
                key: value for key, value in dados_extraidos.items()
                if value is not None and value != "null"
            }
            if campos_para_atualizar:
                print(f"📊 Dados extraídos: {campos_para_atualizar}")
                update_payload["$set"].update(campos_para_atualizar)

        await sessions_collection.update_one(
            {"telefone": telefone_paciente, "empresa_id": empresa_id},
            update_payload
        )

        return texto_resposta

    except Exception as e:
        print(f"❌ Erro em processar_mensagem_com_memoria: {e}")
        return "Olá! Tivemos um pequeno problema técnico, mas já estamos de volta. Como posso te ajudar?"