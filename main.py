# main.py
import streamlit as st
import os

if 'main_script_path' not in st.session_state:
    st.session_state.main_script_path = os.path.abspath(__file__)

st.set_page_config(
    page_title="LexAutomate - Plataforma Jurídica Inteligente",
    page_icon="https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/lexautomate_icon.png",
    layout="wide"
)

from app import resumo_interface
from app2 import peticao_interface
from app3 import validacao_interface
from app4 import consultor_juridico_interface
from app5 import parametrizador_interface
from rag_utils import AZURE_OPENAI_DEPLOYMENT_LLM

# --- INÍCIO: Sidebar ---
with st.sidebar:
    st.markdown("# Instruções de Uso")
    st.markdown("---")

    with st.expander("Guia - Resumo de Documento", expanded=False):
        st.markdown("""
        - **Objetivo:** Gerar um resumo estruturado de documentos jurídicos.
        - **Como Usar:**
            1. Vá para a aba "Resumo de Documento".
            2. Envie um ou mais arquivos PDF ou DOCX.
            3. (Opcional) Forneça uma instrução específica para direcionar o resumo.
            4. Clique em "Gerar Resumo com RAG".
            5. Revise, edite se necessário, e salve/exporte o resultado.
        """)

    with st.expander("Guia - Geração de Peça Jurídica", expanded=False):
        st.markdown("""
        - **Objetivo:** Criar rascunhos de peças processuais com base em fatos e documentos.
        - **Como Usar:**
            1. Vá para a aba "Geração de Peça Jurídica".
            2. Envie documentos com a situação do cliente.
            3. Escreva uma instrução detalhada para a IA.
            4. Clique em "Gerar Peça Processual".
            5. Revise, edite e exporte.
        """)

    with st.expander("Guia - Validação de Cláusula", expanded=False):
        st.markdown("""
        - **Objetivo:** Analisar cláusulas contratuais quanto à validade, riscos e conformidade.
        - **Como Usar:**
            1. Vá para a aba "Validação de Cláusula".
            2. Envie o contrato (PDF ou DOCX).
            3. Especifique a cláusula a ser analisada.
            4. Clique em "Analisar/Validar Cláusulas".
        """)

    with st.expander("Guia - Consultor Jurídico (Chat)", expanded=False):
        st.markdown("""
        - **Objetivo:** Obter respostas para perguntas jurídicas gerais.
        - **Como Usar:**
            1. Vá para a aba "Consultor Jurídico".
            2. Digite sua pergunta no chat.
            3. O LexConsult fornecerá uma resposta fundamentada.
        """)

    with st.expander("Guia - Modelos Jurídicos Parametrizáveis", expanded=False):
        st.markdown("""
        - **Objetivo:** Criar peças jurídicas personalizadas com base em parâmetros fornecidos.
        - **Como Usar:**
            1. Vá para a aba "Modelo Parametrizado".
            2. Preencha os campos como tipo de peça, partes, foro e pedidos.
            3. Clique em "Gerar Petição Parametrizada".
        """)

    st.markdown("---")
    st.markdown("### 🧠 Dicas Avançadas (Prompts)")
    st.markdown("""
    - **Seja Específico:** Quanto mais detalhes, melhor o resultado.
    - **Peças:** Indique tipo, partes, foro, valor da causa.
    - **Cláusulas:** Especifique número, assunto e tipo de análise.
    Veja o [guia completo de prompts](https://medium.com/@thiagoazro/engenharia-de-prompt-e-modelos-de-linguagem-um-aliado-para-os-profissionais-do-direito-af86658e470b).
    """)
    st.markdown("---")
    st.caption(f"LexAutomate v1.3.0 - LLM: {AZURE_OPENAI_DEPLOYMENT_LLM}")
    st.markdown("---")
    st.markdown("© 2025 LexAutomate. Todos os direitos reservados.")
# --- FIM Sidebar ---

# --- TOPO COM LOGO E TÍTULO ---
col1_main, col2_main = st.columns([1, 5])
with col1_main:
    st.image("https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/logo_lexautomate.png", width=250)
with col2_main:
    st.markdown("# LexAutomate: Plataforma Jurídica Inteligente")
    st.markdown("##### IA Jurídica com Agentes Inteligentes. Escolha seu agente de acordo com a tarefa desejada.")

# --- NAVEGAÇÃO ENTRE ABAS ---
aba_selecionada = st.radio(
    "Escolha a funcionalidade:",
    [
        "📄 Resumo de Documento",
        "📑 Validação de Cláusula",
        "🤖 Consultor Jurídico",
        "✍️ Geração de Peça Jurídica Livre",
        "🧩 Modelo Parametrizado"
    ],
    horizontal=True,
    key="menu_aba_principal"
)

if aba_selecionada == "📄 Resumo de Documento":
    resumo_interface()
elif aba_selecionada == "📑 Validação de Cláusula":
    validacao_interface()
elif aba_selecionada == "🤖 Consultor Jurídico":
    consultor_juridico_interface()
elif aba_selecionada == "✍️ Geração de Peça Jurídica Livre":
    peticao_interface()
elif aba_selecionada == "🧩 Modelo Parametrizado":
    parametrizador_interface()
