import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv

# Importa nossa coleção de sessões do MongoDB
from core.database import sessions_collection 

load_dotenv()

# Instancia o modelo atualizado que você testou
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    google_api_key=os.getenv("GEMINI_API_KEY"),
    temperature=0.2
)

# Prompt de Sistema: A "personalidade" do agente
PROMPT_SISTEMA = SystemMessage(
    content="Você é a AgentOS, uma assistente virtual inteligente e educada para clínicas médicas. "
            "Seu objetivo é ajudar pacientes a tirar dúvidas simples e iniciar atendimentos. "
            "Responda sempre de forma curta e objetiva, ideal para o WhatsApp."
)

async def processar_mensagem_com_memoria(telefone_paciente: str, texto_usuario: str) -> str:
    # 1. Busca ou cria a sessão no banco
    sessao = await sessions_collection.find_one({"telefone": telefone_paciente})
    
    historico_bd = []
    if sessao:
        historico_bd = sessao.get("historico", [])
    else:
        print(f"🆕 Nova sessão criada para o paciente {telefone_paciente}")
        await sessions_collection.insert_one({"telefone": telefone_paciente, "historico": []})

    # 2. Criamos o Prompt de Sistema DINÂMICO
    # Agora a IA sabe exatamente com quem está falando desde o primeiro segundo
    prompt_personalizado = SystemMessage(
        content=f"Você é a AgentOS, uma assistente virtual de uma clínica médica. "
                f"Você está conversando com o paciente do telefone: {telefone_paciente}. " # Injeção de contexto
                "Responda de forma curta, prestativa e objetiva."
    )

    # 3. Monta a lista de mensagens para o Gemini
    mensagens_langchain = [prompt_personalizado]
    
    for msg in historico_bd:
        if msg["role"] == "user":
            mensagens_langchain.append(HumanMessage(content=msg["content"]))
        else:
            mensagens_langchain.append(AIMessage(content=msg["content"]))

    # Adiciona a pergunta atual
    mensagens_langchain.append(HumanMessage(content=texto_usuario))

    try:
        # 4. Gera a resposta
        print(f"🧠 [AgentOS] Gerando resposta com contexto do telefone...")
        resposta = await llm.ainvoke(mensagens_langchain)
        texto_resposta = resposta.content

        # 5. Salva no banco (mantendo o histórico atualizado)
        novo_historico = historico_bd + [
            {"role": "user", "content": texto_usuario},
            {"role": "assistant", "content": texto_resposta}
        ]
        
        await sessions_collection.update_one(
            {"telefone": telefone_paciente},
            {"$set": {"historico": novo_historico}}
        )

        return texto_resposta

    except Exception as e:
        print(f"❌ Erro: {e}")
        return "Tivemos um problema técnico, mas já estamos resolvendo."
