# main.py (corrigido)
import streamlit as st
import os

# Define o caminho do script principal no session_state se não existir
if 'main_script_path' not in st.session_state:
    st.session_state.main_script_path = os.path.abspath(__file__)

# Configuração da página
st.set_page_config(
    page_title="LexAutomate | Legal Techonology - Plataforma Jurídica Inteligente",
    page_icon="https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/lexautomate_icon.png",
    layout="wide"
)

# Importação das interfaces dos apps
from app import resumo_interface
from app2 import peticao_interface
from app3 import validacao_interface
from app4 import consultor_juridico_interface
from app5 import parametrizador_interface
from rag_utils import AZURE_OPENAI_DEPLOYMENT_LLM # Para exibir a versão do LLM

# --- CONTEÚDO DO GUIA DE USO ---
def guia_de_uso_interface():
    st.title("📘 Guia de Uso - LexAutomate")
    st.markdown("Bem-vindo ao LexAutomate! Esta plataforma utiliza Inteligência Artificial para auxiliar em diversas tarefas jurídicas.")
    st.markdown("---")

    st.header("Recursos Disponíveis")
    st.markdown("""
    - **📄 Resumo de Documento:** Gere resumos concisos de documentos jurídicos.
    - **📑 Validação de Cláusula:** Analise cláusulas contratuais quanto à validade, riscos e conformidade.
    - **🤖 Consultor Jurídico:** Obtenha respostas para perguntas jurídicas gerais em um formato de chat.
    - **✍️ Peça Jurídica Livre:** Crie rascunhos de peças processuais com base em fatos, documentos e instruções. (Anteriormente "Geração de Peça Jurídica Livre")
    - **🧩 Modelo Parametrizado:** Gere peças jurídicas personalizadas a partir de modelos e parâmetros específicos.
    """)
    st.markdown("---")

    st.header("Como Usar Cada Funcionalidade")

    with st.expander("📄 Guia - Resumo de Documento", expanded=False):
        st.markdown("""
        - **Objetivo:** Gerar um resumo estruturado de documentos jurídicos.
        - **Passos:**
            1.  Navegue até a aba "Resumo de Documento".
            2.  **Carregue os Documentos:** Utilize o botão "Envie um ou mais documentos" para carregar arquivos PDF ou DOCX.
            3.  **(Opcional) Instruções Específicas:** No campo "Direcione o resumo", você pode fornecer instruções para a IA focar em aspectos particulares do documento (ex: "Resuma apenas as cláusulas de penalidade", "Destaque os prazos e valores envolvidos").
            4.  **(Opcional) URLs de Contexto:** Na barra lateral à esquerda, você pode colar até 3 URLs de páginas web (ex: artigos, jurisprudência específica) que podem fornecer contexto adicional relevante para o resumo. A IA tentará extrair informações dessas URLs para enriquecer o resultado.
            5.  **Gerar Resumo:** Clique no botão "Gerar Resumo com RAG".
            6.  **Revisão e Edição:** Após a geração, o rascunho do resumo aparecerá. Você pode editá-lo diretamente na área de texto.
            7.  **Exportar:** Se satisfeito, salve a versão editada e utilize o botão "Baixar Resumo em DOCX".
        """)

    with st.expander("✍️ Guia - Peça Jurídica Livre", expanded=False): # Nome atualizado
        st.markdown("""
        - **Objetivo:** Criar rascunhos de peças processuais com base em fatos, documentos e instruções fornecidas.
        - **Passos:**
            1.  Navegue até a aba "Peça Jurídica Livre".
            2.  **Carregue os Documentos:** Envie arquivos PDF ou DOCX que descrevam a situação do cliente, contenham provas, etc.
            3.  **Instruções para a IA:** No campo "Instruções para a IA", detalhe o tipo de peça desejada (ex: petição inicial, contestação, recurso), a área do Direito, os principais argumentos, pedidos, e qualquer outra informação relevante.
            4.  **(Opcional) URLs de Contexto:** Na barra lateral, cole até 3 URLs de jurisprudência, doutrina ou leis específicas que devem ser consideradas pela IA.
            5.  **Gerar Peça:** Clique em "Gerar Peça Processual".
            6.  **Revisão e Edição:** Analise o rascunho gerado, edite-o conforme necessário na área de texto.
            7.  **Exportar:** Salve e baixe a peça em formato DOCX.
        """)

    with st.expander("📑 Guia - Validação de Cláusula Contratual", expanded=False):
        st.markdown("""
        - **Objetivo:** Analisar cláusulas contratuais específicas, verificando conformidade, riscos e sugerindo melhorias.
        - **Passos:**
            1.  Navegue até a aba "Validação de Cláusula".
            2.  **Carregue o Contrato:** Envie o documento (PDF ou DOCX) contendo as cláusulas a serem analisadas.
            3.  **Especifique a Cláusula:** No campo "Especifique a cláusula ou ponto para análise/validação", indique claramente qual(is) cláusula(s) ou aspecto(s) do contrato você deseja que a IA analise (ex: "Analise a Cláusula 5ª sobre multa por rescisão", "Verifique a validade da cláusula de eleição de foro").
            4.  **(Opcional) URLs de Contexto:** Na barra lateral, forneça até 3 URLs com informações (leis, jurisprudência) que possam ser úteis para a análise da cláusula.
            5.  **Analisar:** Clique em "Analisar/Validar Cláusulas".
            6.  **Revisão e Edição:** Avalie a análise gerada, faça as edições necessárias.
            7.  **Exportar:** Salve e baixe o resultado em DOCX.
        """)

    with st.expander("🤖 Guia - Consultor Jurídico (Chat)", expanded=False):
        st.markdown("""
        - **Objetivo:** Obter respostas e orientações para perguntas jurídicas gerais, teses, e discussões sobre legislação ou jurisprudência.
        - **Passos:**
            1.  Navegue até a aba "Consultor Jurídico".
            2.  **(Opcional) URLs de Contexto:** Antes de fazer sua pergunta, você pode colar até 3 URLs na barra lateral. O consultor tentará usar o conteúdo dessas páginas para embasar a resposta.
            3.  **Faça sua Pergunta:** Digite sua dúvida ou o tema que deseja discutir no campo de chat na parte inferior da tela e pressione Enter.
            4.  **Interaja:** O LexConsult fornecerá uma resposta. Você pode continuar a conversa, fazendo novas perguntas ou pedindo esclarecimentos.
            5.  **Limpar Histórico:** Se desejar, use o botão "Limpar Histórico da Conversa".
        """)

    with st.expander("🧩 Guia - Modelo Parametrizado de Peças", expanded=False):
        st.markdown("""
        - **Objetivo:** Gerar peças jurídicas a partir de modelos pré-definidos, preenchendo campos específicos.
        - **Passos:**
            1.  Navegue até a aba "Modelo Parametrizado".
            2.  **Selecione o Modelo:** Escolha a Área do Direito, Tipo da Peça e Modelo Específico desejado.
            3.  **Preencha os Campos:** Informe os dados solicitados (Partes, Foro, Valor da Causa, Pedidos, etc.).
            4.  **(Opcional) Documentos de Exemplo:** Anexe documentos que possam servir de referência ou complementar informações.
            5.  **(Opcional) URLs de Contexto:** Na barra lateral, insira até 3 URLs para enriquecer a geração da peça com jurisprudência ou doutrina.
            6.  **Instruções Adicionais:** Forneça quaisquer detalhes ou instruções extras para a IA.
            7.  **Gerar Petição:** Clique em "Gerar Petição Parametrizada".
            8.  **Revisão e Edição:** Modifique o rascunho gerado conforme sua necessidade.
            9.  **Exportar:** Salve e baixe o documento final em DOCX.
        """)
    st.markdown("---")
    st.header("🧠 Dicas Avançadas para Melhores Resultados (Engenharia de Prompt)")
    st.markdown("""
    - **Seja Específico:** Quanto mais detalhes você fornecer nas suas instruções, mais precisa e relevante será a resposta da IA.
        - *Exemplo ruim:* "Faça uma petição."
        - *Exemplo bom:* "Elabore uma petição inicial de ação de divórcio consensual, para João Silva e Maria Silva, com partilha de bens (um imóvel e um veículo) e sem filhos menores. Foro da Comarca de Exemplo."
    - **Contextualize:** Sempre que possível, forneça o máximo de contexto sobre o caso, os fatos, e os documentos relevantes.
    - **Indique o Formato Desejado:** Se você espera uma lista, uma tabela, ou um texto com seções específicas, mencione isso.
    - **Use as URLs de Contexto:** Para tarefas que envolvem pesquisa ou fundamentação, colar URLs de jurisprudência ou artigos relevantes na barra lateral pode melhorar significativamente a qualidade da resposta.
    - **Itere:** Se a primeira resposta não for perfeita, refine sua pergunta ou instrução e tente novamente. Você pode editar o texto gerado e pedir para a IA continuar ou modificar a partir dali.
    - **Consulte o [guia completo de prompts](https://medium.com/@thiagoazro/engenharia-de-prompt-e-modelos-de-linguagem-um-aliado-para-os-profissionais-do-direito-af86658e470b) para mais técnicas.**
    """)
    st.markdown("---")
    st.info("Lembre-se: O LexAutomate é uma ferramenta de auxílio e não substitui o julgamento profissional de um advogado. Sempre revise cuidadosamente os materiais gerados.")


# --- INÍCIO: Sidebar ---
with st.sidebar:
    st.image("https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/logo_lexautomate.png", width=150)
    st.markdown("## Contexto Adicional via URL (Opcional)")
    st.markdown("Cole até 3 URLs de jurisprudência ou artigos relevantes para a tarefa atual:")

    url_placeholder_sidebar = "URL de site jurídico relevante"

    if 'sidebar_url1' not in st.session_state:
        st.session_state.sidebar_url1 = ""
    if 'sidebar_url2' not in st.session_state:
        st.session_state.sidebar_url2 = ""
    if 'sidebar_url3' not in st.session_state:
        st.session_state.sidebar_url3 = ""

    st.session_state.sidebar_url1 = st.text_input("URL 1:", value=st.session_state.sidebar_url1, placeholder=url_placeholder_sidebar, key="sidebar_url1_input")
    st.session_state.sidebar_url2 = st.text_input("URL 2:", value=st.session_state.sidebar_url2, placeholder=url_placeholder_sidebar, key="sidebar_url2_input")
    st.session_state.sidebar_url3 = st.text_input("URL 3:", value=st.session_state.sidebar_url3, placeholder=url_placeholder_sidebar, key="sidebar_url3_input")

    st.markdown("---")
    st.caption(f"LexAutomate v1.4.1\nLLM: {AZURE_OPENAI_DEPLOYMENT_LLM}") # Versão atualizada
    st.markdown("---")
    st.markdown("© 2024-2025 LexAutomate.\nTodos os direitos reservados.")
# --- FIM Sidebar ---


# --- TOPO COM LOGO E TÍTULO ---
st.markdown("<br>", unsafe_allow_html=True) # Adiciona um espaço antes

col1, col2 = st.columns([1, 4])

with col1:
    st.image("https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/logo_lexautomate.png", width=300)

with col2:
    st.title("LexAutomate | Legal Techonology")
    st.subheader("Plataforma Jurídica Inteligente com Agentes de IA")

st.markdown("---")


# --- NAVEGAÇÃO ENTRE ABAS ---
abas_disponiveis = [
    "📄 Resumo de Documento",
    "📑 Validação de Cláusula",
    "🤖 Consultor Jurídico",
    "✍️ Peça Jurídica Livre",
    "🧩 Modelo Parametrizado",
    "📘 Guia de Uso"
]

# A variável st.session_state.aba_selecionada não é mais necessária para controlar o st.tabs.
# O st.tabs gerencia seu próprio estado de qual aba está ativa.
# Se você precisar saber programaticamente qual aba foi clicada,
# o widget st.tabs não retorna diretamente o nome da aba selecionada.
# Uma forma de contornar isso, se necessário, seria usar st.radio na sidebar
# para navegação, que permite um controle mais explícito do estado.
# Por agora, removeremos a lógica de st.session_state.aba_selecionada.

tab_resumo, tab_validacao, tab_consultor, tab_peca, tab_param, tab_guia = st.tabs(abas_disponiveis)


with tab_resumo:
    resumo_interface()

with tab_validacao:
    validacao_interface()

with tab_consultor:
    consultor_juridico_interface()

with tab_peca: # Corresponde a "Peça Jurídica Livre"
    peticao_interface() # app2.py

with tab_param: # Corresponde a "Modelo Parametrizado" (app5)
    parametrizador_interface() # app5.py

with tab_guia:
    guia_de_uso_interface()