import os
import json
import re
from datetime import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq # Importe o Groq
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv

# Importa nossa coleção de sessões do MongoDB
from core.database import sessions_collection 
# Importa os dados da clínica e o prompt
from core.config_clinica import esta_em_horario_comercial
from core.prompts import PROMPT_SISTEMA
load_dotenv()

def get_model():
    provider = os.getenv("MODEL_PROVIDER", "gemini").lower()
    
    if provider == "groq":
        print("🚀 [AgentOS] Usando motor Groq (Llama 3.1)")
        return ChatGroq(
            # Se não achar a variável GROQ_MODEL, usa o llama por padrão
            model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), 
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.1
        )
    else:
        print("🧠 [AgentOS] Usando motor Google (Gemini)")
        return ChatGoogleGenerativeAI(
            # Se não achar a variável GEMINI_MODEL, usa o 2.5-flash por padrão
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.1
        )
# Agora o seu llm é dinâmico!
llm = get_model()


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
    prompt_conteudo = PROMPT_SISTEMA
    if "{telefone_paciente}" in prompt_conteudo:
        prompt_conteudo = prompt_conteudo.replace("{telefone_paciente}", telefone_paciente)

    prompt_personalizado = SystemMessage(
        content=prompt_conteudo
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
                if esta_em_horario_comercial():
                    print(f"🚨 [Transbordo] Transferindo {telefone_paciente} para humano.")
                    await sessions_collection.update_one(
                        {"telefone": telefone_paciente},
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