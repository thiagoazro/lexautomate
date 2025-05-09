import streamlit as st
from app import resumo_interface
from app2 import peticao_interface
from app3 import validacao_interface
from app4 import consultor_juridico_interface # Importa a nova interface do app4

# Importa a constante do nome do modelo LLM diretamente do rag_utils
# para evitar o uso de st.secrets aqui, já que as chaves estão hardcoded em rag_utils.
from rag_utils import AZURE_OPENAI_DEPLOYMENT_LLM

st.set_page_config(
    page_title="LexAutomate - Plataforma Jurídica Inteligente",
    page_icon="https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/lexautomate_icon.png", # Use o seu ícone
    layout="wide"
)

# --- INÍCIO: Conteúdo da Barra Lateral (Sidebar) ---
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
        - **Dica:** Se a resposta não for ideal, ajuste sua instrução no campo de prompt e gere novamente.
        """)

    with st.expander("Guia - Geração de Peça Jurídica", expanded=False):
        st.markdown("""
        - **Objetivo:** Criar rascunhos de peças processuais com base em fatos e documentos.
        - **Como Usar:**
            1. Vá para a aba "Geração de Peça Jurídica".
            2. Envie documentos com a situação do cliente (fatos, provas).
            3. Escreva uma instrução detalhada para a IA (tipo de peça, partes, teses principais, etc.).
            4. Clique em "Gerar Peça Processual".
            5. Revise cuidadosamente, edite o rascunho gerado e exporte.
        - **Dica:** Se a resposta não for ideal, ajuste sua instrução no campo de prompt e gere novamente.
        """)

    with st.expander("Guia - Validação de Cláusula", expanded=False):
        st.markdown("""
        - **Objetivo:** Analisar cláusulas contratuais quanto à validade, riscos e conformidade.
        - **Como Usar:**
            1. Vá para a aba "Validação de Cláusula".
            2. Envie o contrato (PDF, DOCX).
            3. Especifique a cláusula ou ponto a ser analisado na instrução.
            4. Clique em "Analisar/Validar Cláusulas".
            5. Revise a análise, edite e exporte.
        - **Dica:** Se a resposta não for ideal, ajuste sua instrução no campo de prompt e gere novamente.
        """)

    with st.expander("Guia - Consultor Jurídico (Chat)", expanded=False): # NOVA SEÇÃO
        st.markdown("""
        - **Objetivo:** Obter respostas para perguntas jurídicas gerais, discutir teses, legislação e jurisprudência.
        - **Como Usar:**
            1. Vá para a aba "Consultor Jurídico".
            2. Digite sua pergunta no campo de chat na parte inferior.
            3. LexConsult usará a base de conhecimento para fornecer uma resposta fundamentada.
            4. Você pode continuar a conversa fazendo perguntas de acompanhamento.
        """)

    st.markdown("---")
    st.markdown("### 🧠 Dicas Avançadas (Prompts)")
    st.markdown("""
    - **Seja Específico:** Quanto mais detalhes você fornecer no prompt, melhor será o resultado.
    - **Peças:** Indique tipo, foro, partes, valor da causa, teses desejadas.
    - **Análise:** Aponte a cláusula exata e o tipo de análise (validade, riscos, sugestões).
    - Consulte o [guia completo de prompts](https://medium.com/@thiagoazro/engenharia-de-prompt-e-modelos-de-linguagem-um-aliado-para-os-profissionais-do-direito-af86658e470b) para mais ideias.
    """)
    st.markdown("---")
    # Usa a constante importada de rag_utils.py para o nome do modelo
    st.caption(f"LexAutomate v1.2.2 (Chat Integrado) - LLM: {AZURE_OPENAI_DEPLOYMENT_LLM}")

# --- FIM: Conteúdo da Barra Lateral (Sidebar) ---


col1_main, col2_main = st.columns([1, 4])
with col1_main:
    st.image("https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/logo_lexautomate.png", width=250)
with col2_main:
    st.markdown("""
    ## LexAutomate - Plataforma Jurídica Inteligente
    ### Resumos, Geração de Peças, Análise de Cláusulas e Consultoria Jurídica com IA
    <small>Criado por Thiago Azeredo Rodrigues</small>
    """, unsafe_allow_html=True)

# Abas principais
abas_titulos = [
    "📄 Resumo de Documento", # Adicionando emojis
    "✍️ Geração de Peça Jurídica",
    "🔎 Validação de Cláusula",
    "🤖 Consultor Jurídico" # NOVA ABA
]
abas = st.tabs(abas_titulos)

with abas[0]:
    resumo_interface()

with abas[1]:
    peticao_interface()

with abas[2]:
    validacao_interface()

with abas[3]: # NOVA ABA PARA O CONSULTOR
    consultor_juridico_interface()


st.markdown("""
<hr style='margin-top: 3rem;'>
<div style='text-align: center; font-size: 0.8rem; color: gray;'>
    © 2025 LexAutomate. Todos os direitos reservados.
</div>
""", unsafe_allow_html=True)