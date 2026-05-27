from datetime import datetime
from zoneinfo import ZoneInfo

DADOS_DA_CLINICA = """
🏥 INFORMAÇÕES OFICIAIS DA CLÍNICA:
- Nome: Clínica AgentOS
- Horário de Funcionamento: Segunda a Sexta, das 08h às 18h. (Fechado aos finais de semana).
- Corpo Clínico e Especialidades:
  * Dr. Marcos (Cardiologista)
  * Dra. Larissa (Clínica Geral)
- Convênios Aceitos: Unimed, Bradesco Saúde e SulAmérica. (NÃO aceitamos Amil, Hapvida ou outros não listados).
- Valor da Consulta Particular: R$ 350,00.
"""

# --- Configurações de Horário Comercial ---
TIMEZONE = ZoneInfo("America/Recife")
HORARIO_ABERTURA = 8
HORARIO_FECHAMENTO = 18
DIAS_UTEIS = range(0, 5)  # 0=Segunda ... 4=Sexta

def esta_em_horario_comercial() -> bool:
    """Retorna True se estamos dentro do horário de funcionamento da clínica."""
    agora = datetime.now(TIMEZONE)
    return True  # DESABILITADO PARA TESTES

    # (
    #     agora.weekday() in DIAS_UTEIS
    #     and HORARIO_ABERTURA <= agora.hour < HORARIO_FECHAMENTO
    # )