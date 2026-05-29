# Diretrizes para Assistentes de IA (Developer Rules)

Este arquivo serve como instrução padrão para qualquer Assistente de IA que trabalhar neste repositório do **AgentOS**.

## 📂 Pasta de Documentação Padrão (Obsidian)
Todos os documentos de negócio, arquitetura, progresso técnico e checklists do projeto são mantidos de forma espelhada na pasta do Obsidian em:
👉 `/home/dennysdev/Documentos/Obsidian/Projetos/AgentOS/Docs/`

## 📋 Arquivos Oficiais do Projeto (LEIA SEMPRE ANTES DE COMEÇAR):
1. **01_Visao_e_Negocio.md:**
   - Contém a precificação, metas e modelo "SaaS Agência". Atualize quando mudarmos a estratégia de negócio ou métricas do piloto.
2. **02_Arquitetura_Tecnica.md:**
   - Contém o mapa da codebase, stack e decisões arquiteturais. Atualize quando instalar novas dependências, mudar arquitetura ou adicionar novos módulos importantes.
3. **03_Roadmap_e_Checklist.md:**
   - Contém as tarefas pendentes, backlog e roadmap futuro. **SEMPRE ATUALIZE este documento** ao iniciar ou finalizar uma funcionalidade, marcando o que foi feito com `[x]`.
4. **04_Historico_e_Refatoracoes.md:**
   - Registro de grandes implementações concluídas. Adicione seus "Walkthroughs" (resumos do que você fez em uma refatoração grande) neste arquivo para manter o histórico.

## 🔄 Fluxo de Trabalho Esperado
Sempre que concluir uma nova conversa, funcionalidade ou correção:
1. Leia o `03_Roadmap_e_Checklist.md` para remover as tarefas concluídas.
2. Se houveram mudanças arquiteturais, atualize o `02_Arquitetura_Tecnica.md`.
3. É **obrigatório** manter essa documentação sincronizada para que as próximas instâncias de IA não percam o contexto.
