import os
import json
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv

# Importa nossa coleção de sessões do MongoDB
from core.database import sessions_collection 

load_dotenv()

# Instancia o modelo atualizado
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash", # Notei que você usou 2.5, mas a versão estável atual é 2.0 ou 1.5
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.2
)

# Prompt de Sistema: A "personalidade" do agente
PROMPT_SISTEMA = """Você é a AgentOS, a assistente virtual inteligente da Clínica Médica.
Seu objetivo é realizar o pré-atendimento de forma profissional, empática e eficiente, enquanto extrai informações importantes.

DIRETRIZES DE ESTILO:
- Use um tom profissional, mas acolhedor.
- Seja direta: não envie textos muito longos.
- Use emojis de forma moderada (ex: 🩺, ✅, 🗓️).
- Nunca invente horários.

FLUXO OBRIGATÓRIO DE ATENDIMENTO:
1. SAUDAÇÃO E NOME
2. MOTIVO DA CONSULTA
3. CONVÊNIO OU PARTICULAR
4. FINALIZAÇÃO DA TRIAGEM

REGRAS DE EXTRAÇÃO E SAÍDA JSON:
Sua resposta DEVE SER SEMPRE um objeto JSON válido.
{{
  "resposta_para_paciente": "Texto amigável com separador | para balões.",
  "dados_extraidos": {{
    "nome": "string ou null",
    "motivo": "string ou null",
    "convenio": "string ou null"
  }}
}}
IMPORTANTE: Use o caractere "|" para separar frases em balões diferentes.
"""
 
async def processar_mensagem_com_memoria(telefone_paciente: str, texto_usuario: str) -> str:
    # 1. Busca ou cria a sessão no banco
    sessao = await sessions_collection.find_one({"telefone": telefone_paciente})
    
    historico_bd = []
    if sessao:
        historico_bd = sessao.get("historico", [])
    else:
        print(f"🆕 Nova sessão criada para o paciente {telefone_paciente}")
        await sessions_collection.insert_one({
            "telefone": telefone_paciente, 
            "historico": [],
            "nome": None,
            "motivo": None,
            "convenio": None,
            "status": "triagem_iniciada"
        })
 
    # 2. Criamos o Prompt de Sistema DINÂMICO
    prompt_personalizado = SystemMessage(
        content=PROMPT_SISTEMA.format(telefone_paciente=telefone_paciente)
    )

    # 3. Monta a lista de mensagens para o Gemini
    mensagens_langchain = [prompt_personalizado]
    for msg in historico_bd:
        if msg["role"] == "user":
            mensagens_langchain.append(HumanMessage(content=msg["content"]))
        else:
            mensagens_langchain.append(AIMessage(content=msg["content"]))

    mensagens_langchain.append(HumanMessage(content=texto_usuario))

    try:
        print(f"🧠 [AgentOS] Gerando resposta para {telefone_paciente}...")
        resposta = await llm.ainvoke(mensagens_langchain)
        conteudo_bruto = resposta.content

        # --- LÓGICA DE LIMPEZA E EXTRAÇÃO ROBUSTA ---
        try:
            # Remove blocos de código markdown (```json ... ```) caso a IA os envie
            conteudo_limpo = re.sub(r'```json\s*|```\s*', '', conteudo_bruto).strip()
            
            parsed_response = json.loads(conteudo_limpo)
            texto_resposta = parsed_response.get("resposta_para_paciente", "")
            dados_extraidos = parsed_response.get("dados_extraidos", {})
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print(f"⚠️ Erro ao decodificar JSON: {e}. Usando texto bruto.")
            texto_resposta = conteudo_bruto
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
            {"telefone": telefone_paciente},
            update_payload
        )
 
        return texto_resposta

    except Exception as e:
        print(f"❌ Erro em processar_mensagem_com_memoria: {e}")
        return "Olá! Tivemos um pequeno problema técnico, mas já estamos de volta. Como posso te ajudar?"