# main.py — atualizado
# - Carrega .env
# - Integra modelos .joblib (roteamento + defaults)
# - Remove referências Azure
# - Mantém sidebar de URLs global
# - Navegação via st.sidebar.radio (permite setar default programaticamente)

import os
import re
import joblib
import streamlit as st
from dotenv import load_dotenv
from typing import Any, Dict, Optional, Tuple

load_dotenv()

# -----------------------------
# Config página
# -----------------------------
st.set_page_config(
    page_title="LexAutomate | Legal Technology - Plataforma Jurídica Inteligente",
    page_icon="https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/lexautomate_icon.png",
    layout="wide"
)

# Caminho do script principal
if "main_script_path" not in st.session_state:
    st.session_state.main_script_path = os.path.abspath(__file__)

# -----------------------------
# Import apps
# -----------------------------
from app import resumo_interface
from app2 import peticao_interface
from app3 import validacao_interface
from app4 import consultor_juridico_interface
from app5 import parametrizador_interface
from rag_utils import OPENAI_LLM_MODEL


# -----------------------------
# Guia de uso (mantido)
# -----------------------------
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
    """)
    st.markdown("---")

    st.header("Como Usar Cada Funcionalidade")

    with st.expander("📄 Guia - Resumo de Documento", expanded=False):
        st.markdown("""
        - **Objetivo:** Gerar um resumo estruturado de documentos jurídicos.
        - **Passos:**
            1. Navegue até "Resumo de Documento".
            2. Carregue PDFs/DOCX.
            3. (Opcional) Direcione o resumo com instruções.
            4. (Opcional) Cole até 3 URLs na barra lateral (jurisprudência/artigos).
            5. Clique em "Gerar Resumo com RAG".
            6. Revise e edite.
            7. Exporte para DOCX.
        """)

    with st.expander("✍️ Guia - Peça Jurídica Livre", expanded=False):
        st.markdown("""
        - **Objetivo:** Criar rascunhos de peças processuais.
        - **Passos:**
            1. Navegue até "Peça Jurídica Livre".
            2. Envie documentos do caso (PDF/DOCX).
            3. Escreva instruções (tipo de peça, teses, pedidos).
            4. (Opcional) Cole URLs na barra lateral.
            5. Gere, revise e exporte.
        """)

    with st.expander("📑 Guia - Validação de Cláusula", expanded=False):
        st.markdown("""
        - **Objetivo:** Analisar uma cláusula ou ponto contratual.
        - **Passos:**
            1. Navegue até "Validação de Cláusula".
            2. Envie o contrato/documento.
            3. Informe a cláusula/ponto a analisar.
            4. (Opcional) Cole URLs na barra lateral.
            5. Gere análise, revise e exporte.
        """)

    with st.expander("🤖 Guia - Consultor Jurídico", expanded=False):
        st.markdown("""
        - **Objetivo:** Tirar dúvidas jurídicas em formato de chat.
        - **Passos:**
            1. Navegue até "Consultor Jurídico".
            2. Pergunte.
            3. (Opcional) Cole URLs na barra lateral.
            4. Envie feedback.
        """)

    with st.expander("🧩 Guia - Modelo Parametrizado", expanded=False):
        st.markdown("""
        - **Objetivo:** Gerar peças a partir de modelos parametrizados (MongoDB).
        - **Passos:**
            1. Navegue até "Modelo Parametrizado".
            2. Selecione área/tipo/modelo.
            3. Preencha dados e pedidos.
            4. (Opcional) Envie documentos de exemplo e/ou URLs na barra lateral.
            5. Gere e exporte.
        """)


# -----------------------------
# Joblib: carregamento e classificação
# -----------------------------
def _safe_readable_label(x: Any) -> str:
    s = str(x) if x is not None else ""
    s = s.strip()
    return s


def _normalize(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    return t


@st.cache_resource(show_spinner=False)
def load_joblib_models() -> Dict[str, Any]:
    """
    Carrega modelos joblib. Espera que os arquivos estejam no mesmo diretório do main.py.
    Ajuste os caminhos aqui se você guardar em outra pasta.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))

    paths = {
        "tipo_tarefa": os.path.join(base_dir, "classificador_tipo_tarefa.joblib"),
        "area_direito": os.path.join(base_dir, "classificador_area_direito.joblib"),
        "tipo_documento": os.path.join(base_dir, "classificador_tipo_documento.joblib"),
        "tipo_peca": os.path.join(base_dir, "classificador_tipo_peca.joblib"),
    }

    models: Dict[str, Any] = {}
    for k, p in paths.items():
        if os.path.exists(p):
            try:
                models[k] = joblib.load(p)
            except Exception as e:
                models[k] = None
                st.sidebar.warning(f"Falha ao carregar {os.path.basename(p)}: {e}")
        else:
            models[k] = None
            # não assusta o usuário final; só debug leve:
            # st.sidebar.info(f"Modelo não encontrado: {os.path.basename(p)}")

    return models


def _predict_label_and_conf(model: Any, text: str) -> Tuple[Optional[str], Optional[float]]:
    """
    Tenta retornar (label, confidence). Se não houver predict_proba, retorna conf None.
    """
    if model is None:
        return None, None

    try:
        # pipeline sklearn normalmente aceita lista[str]
        pred = model.predict([text])[0]
        label = _safe_readable_label(pred)

        conf = None
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba([text])[0]
            try:
                conf = float(max(proba))
            except Exception:
                conf = None
        return label, conf
    except Exception:
        return None, None


def _route_from_tipo_tarefa_label(label: str) -> Optional[str]:
    """
    Mapeia o label do classificador para uma página do app.
    Faz match por palavras-chave (robusto mesmo se seus labels forem diferentes).
    """
    if not label:
        return None
    L = _normalize(label)

    # Resumo
    if any(k in L for k in ["resumo", "sumar", "sintese", "resumir"]):
        return "📄 Resumo de Documento"

    # Validação
    if any(k in L for k in ["valid", "claus", "contrat", "compliance", "risco"]):
        return "📑 Validação de Cláusula"

    # Consultor
    if any(k in L for k in ["consult", "duvida", "pergunta", "orienta", "explica"]):
        return "🤖 Consultor Jurídico"

    # Peça livre
    if any(k in L for k in ["peti", "peca", "contest", "recurso", "inicial", "manifest"]):
        return "✍️ Peça Jurídica Livre"

    # Parametrizado
    if any(k in L for k in ["param", "modelo", "template", "padrao"]):
        return "🧩 Modelo Parametrizado"

    return None


def run_classification_and_set_defaults(user_text: str) -> None:
    """
    Executa classificadores e grava resultados em session_state:
    - page_suggested
    - pred_area_direito
    - pred_tipo_documento
    - pred_tipo_peca
    """
    models = load_joblib_models()
    text = (user_text or "").strip()
    if not text:
        return

    # tipo_tarefa => roteamento
    tarefa_label, tarefa_conf = _predict_label_and_conf(models.get("tipo_tarefa"), text)
    suggested_page = _route_from_tipo_tarefa_label(tarefa_label or "")

    st.session_state["joblib_pred_tipo_tarefa"] = tarefa_label
    st.session_state["joblib_pred_tipo_tarefa_conf"] = tarefa_conf
    if suggested_page:
        st.session_state["page"] = suggested_page  # roteia de verdade
        st.session_state["page_suggested"] = suggested_page
    else:
        st.session_state["page_suggested"] = None

    # area_direito
    area_label, area_conf = _predict_label_and_conf(models.get("area_direito"), text)
    st.session_state["joblib_pred_area_direito"] = area_label
    st.session_state["joblib_pred_area_direito_conf"] = area_conf

    # tipo_documento
    doc_label, doc_conf = _predict_label_and_conf(models.get("tipo_documento"), text)
    st.session_state["joblib_pred_tipo_documento"] = doc_label
    st.session_state["joblib_pred_tipo_documento_conf"] = doc_conf

    # tipo_peca
    peca_label, peca_conf = _predict_label_and_conf(models.get("tipo_peca"), text)
    st.session_state["joblib_pred_tipo_peca"] = peca_label
    st.session_state["joblib_pred_tipo_peca_conf"] = peca_conf


# -----------------------------
# Sidebar global
# -----------------------------
with st.sidebar:
    st.image("https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/logo_lexautomate.png", width=150)

    st.markdown("## 🎛️ Navegação")
    pages = [
        "📄 Resumo de Documento",
        "📑 Validação de Cláusula",
        "🤖 Consultor Jurídico",
        "✍️ Peça Jurídica Livre",
        "🧩 Modelo Parametrizado",
        "📘 Guia de Uso",
    ]

    if "page" not in st.session_state:
        st.session_state["page"] = pages[0]

    # Bloco de sugestão automática por joblib
    st.markdown("## 🧭 Sugestão Automática (ML)")
    user_goal = st.text_area(
        "Descreva em 1-2 frases o que você quer fazer:",
        placeholder="Ex.: Quero validar uma cláusula de multa e verificar riscos.\nEx.: Preciso redigir uma petição inicial trabalhista.",
        height=90,
        key="ml_user_goal_text",
    )

    colA, colB = st.columns(2)
    with colA:
        if st.button("Sugerir aba", use_container_width=True):
            run_classification_and_set_defaults(user_goal)
            st.toast("Sugestão aplicada.", icon="✅")

    with colB:
        if st.button("Limpar sugestão", use_container_width=True):
            for k in list(st.session_state.keys()):
                if k.startswith("joblib_pred_") or k in ["page_suggested"]:
                    del st.session_state[k]
            st.toast("Sugestão removida.", icon="🧹")

    # Mostrar previsões (se existirem)
    if st.session_state.get("joblib_pred_tipo_tarefa") or st.session_state.get("joblib_pred_area_direito"):
        with st.expander("Ver previsões", expanded=False):
            st.write("**Tipo de tarefa:**", st.session_state.get("joblib_pred_tipo_tarefa") or "—",
                     f"(conf: {st.session_state.get('joblib_pred_tipo_tarefa_conf'):.2f})"
                     if isinstance(st.session_state.get("joblib_pred_tipo_tarefa_conf"), float) else "")
            st.write("**Área do direito:**", st.session_state.get("joblib_pred_area_direito") or "—",
                     f"(conf: {st.session_state.get('joblib_pred_area_direito_conf'):.2f})"
                     if isinstance(st.session_state.get("joblib_pred_area_direito_conf"), float) else "")
            st.write("**Tipo de documento:**", st.session_state.get("joblib_pred_tipo_documento") or "—",
                     f"(conf: {st.session_state.get('joblib_pred_tipo_documento_conf'):.2f})"
                     if isinstance(st.session_state.get("joblib_pred_tipo_documento_conf"), float) else "")
            st.write("**Tipo de peça:**", st.session_state.get("joblib_pred_tipo_peca") or "—",
                     f"(conf: {st.session_state.get('joblib_pred_tipo_peca_conf'):.2f})"
                     if isinstance(st.session_state.get("joblib_pred_tipo_peca_conf"), float) else "")

    st.markdown("---")

    # Navegação efetiva
    st.session_state["page"] = st.radio(
        "Ir para:",
        options=pages,
        index=pages.index(st.session_state["page"]) if st.session_state["page"] in pages else 0,
        key="page_radio",
    )

    st.markdown("---")
    st.markdown("## 🔗 Contexto Adicional via URL (Opcional)")
    st.markdown("Cole até 3 URLs de jurisprudência ou artigos relevantes para a tarefa atual:")

    if "sidebar_url1" not in st.session_state:
        st.session_state.sidebar_url1 = ""
    if "sidebar_url2" not in st.session_state:
        st.session_state.sidebar_url2 = ""
    if "sidebar_url3" not in st.session_state:
        st.session_state.sidebar_url3 = ""

    placeholder = "URL de site jurídico relevante"
    st.session_state.sidebar_url1 = st.text_input("URL 1:", value=st.session_state.sidebar_url1, placeholder=placeholder)
    st.session_state.sidebar_url2 = st.text_input("URL 2:", value=st.session_state.sidebar_url2, placeholder=placeholder)
    st.session_state.sidebar_url3 = st.text_input("URL 3:", value=st.session_state.sidebar_url3, placeholder=placeholder)

    st.markdown("---")
    st.caption(f"LexAutomate • LLM: {OPENAI_LLM_MODEL}")
    st.markdown("© 2024–2026 LexAutomate. Todos os direitos reservados.")


# -----------------------------
# Topo
# -----------------------------
st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns([1, 4])
with col1:
    st.image("https://raw.githubusercontent.com/thiagoazro/-cone_lexautomate/main/logo_lexautomate.png", width=280)
with col2:
    st.title("LexAutomate | Legal Technology")
    st.subheader("Plataforma Jurídica Inteligente com Agentes de IA")

st.markdown("---")


# -----------------------------
# Render página selecionada
# -----------------------------
page = st.session_state.get("page", "📄 Resumo de Documento")

if page == "📄 Resumo de Documento":
    resumo_interface()

elif page == "📑 Validação de Cláusula":
    validacao_interface()

elif page == "🤖 Consultor Jurídico":
    consultor_juridico_interface()

elif page == "✍️ Peça Jurídica Livre":
    peticao_interface()

elif page == "🧩 Modelo Parametrizado":
    parametrizador_interface()

elif page == "📘 Guia de Uso":
    guia_de_uso_interface()

else:
    resumo_interface()
