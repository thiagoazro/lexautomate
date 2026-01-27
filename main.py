# main.py (estilo ORIGINAL com abas + atualizado: sem Azure + GraphRAG visualizations)
import os
import glob
import streamlit as st
from dotenv import load_dotenv

# Carrega variáveis de ambiente do .env (local)
# No Streamlit Cloud, use secrets.
load_dotenv()

# Define caminho do script principal no session_state (mantém como original)
if 'main_script_path' not in st.session_state:
    st.session_state.main_script_path = os.path.abspath(__file__)

# Paths locais dos assets
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE_DIR, "logo_lexautomate.png")
ICON_PATH = os.path.join(BASE_DIR, "lexautomate_icon.png")

# Pasta onde os grafos HTML são salvos (GraphRAG)
GRAPH_VIZ_DIR = (os.getenv("GRAPH_VIZ_DIR") or "graph_visualizations").strip()
os.makedirs(GRAPH_VIZ_DIR, exist_ok=True)

# Configuração da página (visual branco padrão)
st.set_page_config(
    page_title="LexAutomate | Legal Techonology - Plataforma Jurídica Inteligente",
    page_icon=ICON_PATH if os.path.exists(ICON_PATH) else "⚖️",
    layout="wide"
)

# Importação das interfaces dos apps (atualizados sem Azure)
from app import resumo_interface
from app2 import peticao_interface
from app3 import validacao_interface
from app4 import consultor_juridico_interface
from app5 import parametrizador_interface

# (Opcional) para exibir no topo
from rag_utils import OPENAI_LLM_MODEL


# ---------------------------
# GUIA DE USO (mantido como no original)
# ---------------------------
def guia_de_uso_interface():
    st.title("📘 Guia de Uso - LexAutomate")
    st.markdown("Bem-vindo ao LexAutomate! Esta plataforma utiliza Inteligência Artificial para auxiliar em diversas tarefas jurídicas.")
    st.markdown("---")

    st.header("Recursos Disponíveis")
    st.markdown("""
    - **📄 Resumo de Documento:** Gere resumos concisos de documentos jurídicos.
    - **📑 Validação de Cláusula:** Analise cláusulas contratuais quanto à validade, riscos e conformidade.
    - **🤖 Consultor Jurídico:** Obtenha respostas para perguntas jurídicas gerais em um formato de chat.
    - **✍️ Peça Jurídica Livre:** Crie rascunhos de peças processuais com base em fatos, documentos e instruções.
    - **🧩 Modelo Parametrizado:** Gere peças jurídicas personalizadas a partir de modelos e parâmetros específicos.
    - **🕸️ Graph Visualizations:** Visualize os grafos HTML gerados pelo GraphRAG.
    """)
    st.markdown("---")

    st.header("Como Usar Cada Funcionalidade")

    with st.expander("📄 Guia - Resumo de Documento", expanded=False):
        st.markdown("""
        - **Objetivo:** Gerar um resumo estruturado de documentos jurídicos.
        - **Passos:**
            1.  Navegue até a aba "Resumo de Documento".
            2.  **Carregue os Documentos:** Utilize o botão "Envie um ou mais documentos" para carregar arquivos PDF ou DOCX.
            3.  **(Opcional) Instruções Específicas:** No campo "Direcione o resumo", você pode fornecer instruções para a IA focar em aspectos particulares do documento.
            4.  **(Opcional) URLs de Contexto:** Na barra lateral à esquerda, cole até 3 URLs (jurisprudência/artigos) para contexto adicional.
            5.  **Gerar:** Clique no botão de geração.
            6.  **Revisão e Edição:** Ajuste o texto gerado se necessário.
            7.  **Exportar:** Baixe em DOCX quando disponível.
        """)

    with st.expander("✍️ Guia - Peça Jurídica Livre", expanded=False):
        st.markdown("""
        - **Objetivo:** Criar rascunhos de peças processuais com base em fatos, documentos e instruções fornecidas.
        - **Passos:**
            1.  Navegue até a aba "Peça Jurídica Livre".
            2.  Carregue documentos (PDF/DOCX) e descreva fatos/pedidos.
            3.  (Opcional) Cole URLs na sidebar para enriquecer com jurisprudência/doutrina.
            4.  Gere e revise a peça.
        """)

    with st.expander("📑 Guia - Validação de Cláusula", expanded=False):
        st.markdown("""
        - **Objetivo:** Analisar cláusulas contratuais quanto à validade, riscos, abusividade, conformidade e sugestões.
        - **Passos:**
            1.  Navegue até a aba "Validação de Cláusula".
            2.  Cole a cláusula ou envie documento.
            3.  (Opcional) URLs na sidebar.
            4.  Gere a análise e revise.
        """)

    with st.expander("🤖 Guia - Consultor Jurídico", expanded=False):
        st.markdown("""
        - **Objetivo:** Chat jurídico para dúvidas gerais e teses.
        - **Passos:**
            1.  Navegue até a aba "Consultor Jurídico".
            2.  Faça perguntas.
            3.  (Opcional) URLs na sidebar para contexto.
            4.  O sistema pode usar RAG + (quando necessário) GraphRAG.
        """)

    with st.expander("🧩 Guia - Modelo Parametrizado", expanded=False):
        st.markdown("""
        - **Objetivo:** Gerar peças a partir de modelos (MongoDB) preenchendo campos específicos.
        - **Passos:**
            1.  Navegue até a aba "Modelo Parametrizado".
            2.  Selecione área/tipo/modelo.
            3.  Preencha parâmetros.
            4.  (Opcional) documentos de exemplo + URLs na sidebar.
            5.  Gere, revise e exporte (DOCX).
        """)

    with st.expander("🕸️ Guia - Graph Visualizations", expanded=False):
        st.markdown("""
        - **Objetivo:** Inspecionar os grafos HTML gerados pelo GraphRAG para entender relações semânticas e depurar qualidade do RAG.
        - **Como funciona:**
            - Quando o GraphRAG é acionado (auto nos apps, conforme heurística), ele salva um arquivo HTML na pasta **graph_visualizations/**.
            - Nesta aba você pode abrir qualquer HTML salvo e ver nós/arestas.
        """)


# ---------------------------
# GRAPH VISUALIZATIONS (nova aba, mantendo estilo original)
# ---------------------------
def graph_visualizations_interface():
    st.title("🕸️ Graph Visualizations (GraphRAG)")
    st.caption(f"Pasta de saída: {GRAPH_VIZ_DIR}")
    st.markdown("---")

    files = sorted(glob.glob(os.path.join(GRAPH_VIZ_DIR, "graph_*.html")), reverse=True)
    if not files:
        st.info("Nenhum grafo encontrado ainda. Gere uma resposta que acione GraphRAG para criar HTMLs.")
        return

    selected = st.selectbox("Selecione um grafo", options=files, format_func=lambda p: os.path.basename(p))
    st.caption(f"Arquivo: `{selected}`")

    import streamlit.components.v1 as components
    with open(selected, "r", encoding="utf-8") as f:
        components.html(f.read(), height=780, scrolling=True)


# ---------------------------
# SIDEBAR (mantida como original, só trocando logo pra arquivo local)
# ---------------------------
with st.sidebar:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=150)
    else:
        st.markdown("## LexAutomate")

    st.markdown("## Contexto Adicional via URL (Opcional)")
    st.markdown("Cole até 3 URLs de jurisprudência ou artigos relevantes para a tarefa atual:")

    url_placeholder_sidebar = "URL de site jurídico relevante"

    # Inicializa as variáveis de estado para as URLs da sidebar
    if 'sidebar_url1' not in st.session_state:
        st.session_state.sidebar_url1 = ""
    if 'sidebar_url2' not in st.session_state:
        st.session_state.sidebar_url2 = ""
    if 'sidebar_url3' not in st.session_state:
        st.session_state.sidebar_url3 = ""

    st.session_state.sidebar_url1 = st.text_input(
        "URL 1:", value=st.session_state.sidebar_url1, placeholder=url_placeholder_sidebar, key="sidebar_url1_input"
    )
    st.session_state.sidebar_url2 = st.text_input(
        "URL 2:", value=st.session_state.sidebar_url2, placeholder=url_placeholder_sidebar, key="sidebar_url2_input"
    )
    st.session_state.sidebar_url3 = st.text_input(
        "URL 3:", value=st.session_state.sidebar_url3, placeholder=url_placeholder_sidebar, key="sidebar_url3_input"
    )

    st.markdown("---")
    st.caption(f"LLM atual: {OPENAI_LLM_MODEL}")


# ---------------------------
# HEADER (mantido como original)
# ---------------------------
col1, col2 = st.columns([1, 7])
with col1:
    if os.path.exists(ICON_PATH):
        st.image(ICON_PATH, width=70)
with col2:
    st.title("LexAutomate")
    st.subheader("Plataforma Jurídica Inteligente com Agentes de IA")

st.markdown("---")


# ---------------------------
# NAVEGAÇÃO ENTRE ABAS (ORIGINAL + nova aba Graph Visualizations)
# ---------------------------
abas_disponiveis = [
    "📄 Resumo de Documento",
    "📑 Validação de Cláusula",
    "🤖 Consultor Jurídico",
    "✍️ Peça Jurídica Livre",
    "🧩 Modelo Parametrizado",
    "🕸️ Graph Visualizations",
    "📘 Guia de Uso"
]

(
    tab_resumo,
    tab_validacao,
    tab_consultor,
    tab_peca,
    tab_param,
    tab_graph,
    tab_guia
) = st.tabs(abas_disponiveis)

with tab_resumo:
    resumo_interface()

with tab_validacao:
    validacao_interface()

with tab_consultor:
    consultor_juridico_interface()

with tab_peca:
    peticao_interface()

with tab_param:
    parametrizador_interface()

with tab_graph:
    graph_visualizations_interface()

with tab_guia:
    guia_de_uso_interface()
