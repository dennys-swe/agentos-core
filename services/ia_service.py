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

REGRAS DE EXTRAÇÃO E SAÍDA JSON (MUITO IMPORTANTE):
Você está se comunicando com um sistema de backend.
Sua resposta DEVE SER EXCLUSIVAMENTE um objeto JSON válido.
Comece diretamente com {{ e termine com }}.

{{
  "resposta_para_paciente": "Texto amigável com separador | para balões.",
  "dados_extraidos": {{
    "nome": "string ou null",
    "motivo": "string ou null",
    "convenio": "string ou null"
  }},
  "necessita_humano": false 
}}

ATENÇÃO: Mude "necessita_humano" para true SOMENTE SE o paciente pedir explicitamente para falar com um atendente, humano, recepcionista, ou se relatar uma emergência médica grave.
"""
 
async def processar_mensagem_com_memoria(telefone_paciente: str, texto_usuario: str) -> str:
    # 1. Busca a sessão no banco
    sessao = await sessions_collection.find_one({"telefone": telefone_paciente})
    
    # 👇 A TRAVA DEVE FICAR AQUI, LOGO APÓS A BUSCA 👇
    if sessao and sessao.get("owner") == "human":
        print(f"⏸️ [Transbordo] Conversa com {telefone_paciente} pausada. IA silenciada.")
        
        # Apenas guarda a mensagem nova do paciente para a recepcionista ler depois
        novo_historico = sessao.get("historico", []) + [{"role": "user", "content": texto_usuario}]
        await sessions_collection.update_one(
            {"telefone": telefone_paciente},
            {"$set": {"historico": novo_historico}}
        )
        return "_SILENCE_" 
    # --------------------------------------------------
    
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
            "status": "triagem_iniciada",
            "owner": "bot"
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
            # Procura tudo que começa com { e termina com } (incluindo quebras de linha)
            match = re.search(r'\{.*\}', conteudo_bruto, re.DOTALL)
            
            if match:
                conteudo_limpo = match.group(0) # Pega apenas o JSON
            else:
                conteudo_limpo = conteudo_bruto # Fallback de segurança
                
            parsed_response = json.loads(conteudo_limpo)
            texto_resposta = parsed_response.get("resposta_para_paciente", "Desculpe, pode repetir?")
            dados_extraidos = parsed_response.get("dados_extraidos", {})

            # 👇 NOVO: Verifica se a IA pediu ajuda humana 👇
            necessita_humano = parsed_response.get("necessita_humano", False)
            
            if necessita_humano:
                print(f"🚨 [Transbordo Automático] IA solicitou humano para o paciente {telefone_paciente}.")
                # Muda o dono da sessão para humano automaticamente!
                await sessions_collection.update_one(
                    {"telefone": telefone_paciente},
                    {"$set": {"owner": "human"}}
                )
            
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print(f"⚠️ Erro crítico ao decodificar JSON: {e}. Conteúdo: {conteudo_bruto}")
            # Se der erro grave, mandamos uma mensagem padrão em vez de cuspir código na tela
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
            {"telefone": telefone_paciente},
            update_payload
        )
 
        return texto_resposta

    except Exception as e:
        print(f"❌ Erro em processar_mensagem_com_memoria: {e}")
        return "Olá! Tivemos um pequeno problema técnico, mas já estamos de volta. Como posso te ajudar?"