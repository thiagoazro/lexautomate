
# app_5.py
import streamlit as st
import json
import os
import uuid
import traceback
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_conditional_google_search,
    AZURE_OPENAI_DEPLOYMENT_LLM,
    gerar_docx
)

try:
    from rag_docintelligence import extrair_texto_documento
    DOC_INTELLIGENCE_AVAILABLE = True
except ImportError:
    DOC_INTELLIGENCE_AVAILABLE = False
    st.warning("Módulo rag_docintelligence.py não encontrado. A funcionalidade de anexar documento de exemplo estará desabilitada.")

# --- CONFIGURAÇÕES ---
MODELOS_PECAS_FILE = "modelos_pecas.json"
PROMPT_PARAMETRIZADOR_FILE = "prompts/system_prompt_app5_parametrizador.md"

def carregar_prompt_parametrizador(prompt_path: str = PROMPT_PARAMETRIZADOR_FILE) -> str:
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        st.warning(f"Erro ao carregar o prompt do parametrizador: {e}")
        return "Você é um assistente jurídico especializado em peças processuais."

@st.cache_data
def carregar_modelos_pecas(file_path: str) -> dict:
    try:
        if not os.path.exists(file_path):
            st.error(f"Arquivo de modelos '{file_path}' não encontrado.")
            return {}
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Erro ao carregar o JSON: {e}")
        return {}

def parametrizador_interface():
    st.subheader("📁 Geração de Peças Jurídicas Parametrizadas")

    modelos_data = carregar_modelos_pecas(MODELOS_PECAS_FILE)
    if not modelos_data:
        st.warning("Modelos de peças não carregados.")
        areas_disponiveis = ["Trabalhista", "Cível", "Outra"]
        tipos_peca_disponiveis_fallback = ["Petição Inicial", "Outro"]
        modelos_peca_disponiveis_fallback = ["Modelo Genérico"]
    else:
        areas_disponiveis = list(modelos_data.keys())

    col1, col2, col3 = st.columns(3)
    with col1:
        area = st.selectbox("Área do Direito:", areas_disponiveis, key="area")
    with col2:
        tipos = list(modelos_data.get(area, {}).keys()) if area in modelos_data else ["Outro"]
        tipo = st.selectbox("Tipo da Peça:", tipos, key="tipo")
    with col3:
        modelos = list(modelos_data.get(area, {}).get(tipo, {}).keys()) if area in modelos_data and tipo in modelos_data[area] else ["Modelo Genérico"]
        modelo = st.selectbox("Modelo Específico:", modelos, key="modelo")

    info_modelo = modelos_data.get(area, {}).get(tipo, {}).get(modelo, {})

    st.markdown("### Informações Básicas")
    autor = st.text_input("Parte autora:", "João da Silva")
    reu = st.text_input("Parte ré:", "Empresa XYZ Ltda.")
    foro = st.text_input("Foro competente:", "Comarca de Exemplo")
    valor = st.text_input("Valor da causa (R$):", "10.000,00")

    reivindicacoes_default = info_modelo.get("reivindicacoes_comuns", [])
    pedidos = st.multiselect("Pedidos principais:", reivindicacoes_default)
    outros_pedidos = st.text_area("Outros pedidos (um por linha):")
    instrucao_adicional = st.text_area("Instruções adicionais:")

    doc_texto = ""
    if DOC_INTELLIGENCE_AVAILABLE:
        st.markdown("### Documento de Exemplo (Opcional)")
        doc = st.file_uploader("Anexar documento (PDF ou DOCX):", type=["pdf", "docx"])
        if doc:
            ext = os.path.splitext(doc.name)[1].lower()
            temp_path = f"temp_{uuid.uuid4().hex}{ext}"
            with open(temp_path, "wb") as f:
                f.write(doc.getvalue())
            with st.spinner("Extraindo texto..."):
                doc_texto = extrair_texto_documento(temp_path, ext)
            os.remove(temp_path)

    if st.button("Gerar Petição"):
        client = get_openai_client()
        search = get_azure_search_client()
        if not client or not search:
            st.error("Erro ao inicializar clientes.")
            return

        todos_pedidos = pedidos + [p.strip() for p in outros_pedidos.split("\n") if p.strip()]
        pedidos_formatados = ", ".join(todos_pedidos) if todos_pedidos else "(não especificado)"

        prompt = info_modelo.get("prompt_template", "")
        if prompt:
            prompt_final = prompt.format(
                autor=autor, reu=reu, foro=foro, valor=valor,
                reivindicacoes_formatadas=pedidos_formatados,
                instrucao_adicional=instrucao_adicional or "[Nenhuma instrução adicional]",
                documento_exemplo_para_referencia=doc_texto or "[Nenhum documento de exemplo fornecido]"
            )
        else:
            prompt_final = (
                f"Gere uma peça jurídica do tipo {tipo}, na área {area}, entre {autor} e {reu}, "
                f"foro: {foro}, valor da causa: {valor}, pedidos: {pedidos_formatados}. {instrucao_adicional}"
            )

        with st.spinner("Gerando petição..."):
            try:
                system_prompt_param = carregar_prompt_parametrizador()
                resposta = generate_response_with_conditional_google_search(
                    system_message_base=system_prompt_param,
                    user_instruction=prompt_final,
                    context_document_text=doc_texto,
                    search_client=search,
                    client_openai=client,
                    azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
                    azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM,
                    top_k_initial_search_azure=7,
                    use_semantic_search_azure=True,
                    enable_google_search_trigger=True,
                    temperature=0.3,
                    max_tokens=4000
                )
                st.session_state["peticao_gerada"] = str(resposta).strip()
            except Exception as e:
                st.error(f"Erro ao gerar petição: {e}")
                st.session_state["peticao_gerada"] = ""

    if "peticao_gerada" in st.session_state and st.session_state["peticao_gerada"]:
        st.markdown("---")
        st.markdown("## 📝 Petição Gerada")

        with st.expander("📄 Pré-visualização da Petição (Somente Leitura)", expanded=True):
            st.markdown(st.session_state["peticao_gerada"], unsafe_allow_html=True)

        texto_editado = st.text_area("Edição opcional:", value=st.session_state["peticao_gerada"], height=300)
        st.session_state["peticao_gerada"] = texto_editado

        try:
            docx_file = gerar_docx(st.session_state["peticao_gerada"])
            st.download_button(
                label="📅 Baixar em DOCX",
                data=docx_file,
                file_name="peticao_gerada.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        except Exception as e:
            st.error(f"Erro ao gerar o DOCX: {e}")