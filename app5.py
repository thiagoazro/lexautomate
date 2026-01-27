# app5.py
# Parametrizador de Peças Jurídicas (Modelos no MongoDB) — COM GraphRAG + HTML salvo
# - SEM Azure
# - Usa rag_utils: OpenAI + OpenSearch + Serper + Rerank + GraphRAG (auto)
# - Mantém: MongoDB para modelos parametrizados
# - Mantém: URLs da sidebar como contexto (via processar_urls_contexto)

import os
import datetime
from collections import defaultdict
import json

import streamlit as st
import streamlit.components.v1 as components

from rag_utils import (
    get_openai_client,
    get_opensearch_client,
    generate_response_with_rag_and_web_fallback,
    gerar_docx,
    OPENAI_LLM_MODEL,
    processar_urls_contexto,
)

from doc_processing_utils import extrair_conteudo_documento
from db_utils import carregar_modelos_pecas_from_mongodb


PROMPTS_FOLDER = "prompts"
SYSTEM_PROMPT_FILENAME = "system_prompt_app5_parametrizador.md"
SESSION_STATE_SUFFIX = "_app5"


def carregar_system_prompt(folder=PROMPTS_FOLDER, filename=SYSTEM_PROMPT_FILENAME) -> str:
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # tenta: ./prompts/filename
        filepath1 = os.path.join(current_dir, folder, filename)
        if os.path.exists(filepath1):
            return open(filepath1, "r", encoding="utf-8").read()

        # tenta: ../prompts/filename
        filepath2 = os.path.join(current_dir, "..", folder, filename)
        if os.path.exists(filepath2):
            return open(filepath2, "r", encoding="utf-8").read()

        # tenta: ./filename
        if os.path.exists(filename):
            return open(filename, "r", encoding="utf-8").read()

        return "Você é um advogado sênior. Gere a peça conforme o modelo parametrizado."
    except Exception:
        return "Você é um advogado sênior. Gere a peça conforme o modelo parametrizado."


def _render_graph_html_if_exists(graph_html_path: str):
    if not graph_html_path:
        return
    if not os.path.exists(graph_html_path):
        st.warning(f"Grafo salvo, mas o arquivo não foi encontrado: {graph_html_path}")
        return

    st.caption(f"📌 Grafo salvo em: `{graph_html_path}`")
    try:
        with open(graph_html_path, "r", encoding="utf-8") as f:
            html = f.read()
        components.html(html, height=720, scrolling=True)
    except Exception as e:
        st.warning(f"Não foi possível renderizar o HTML do grafo: {e}")


def _build_param_payload_from_form(form_data: dict) -> dict:
    """
    Mantém compatibilidade: consolida dados do formulário.
    """
    return dict(form_data or {})


def gerar_peticao_parametrizada(
    area_direito: str,
    tipo_peca: str,
    nome_modelo: str,
    user_inputs: dict,
    urls_contexto: list[str],
    enable_web: bool = True,
) -> dict:
    """
    Retorna dict:
      {
        "texto": str,
        "graph_summary": str,
        "graph_html_path": str
      }
    """
    openai_client = get_openai_client()
    os_client = get_opensearch_client()
    if not openai_client or not os_client:
        return {"texto": "Erro: Serviços de IA não disponíveis.", "graph_summary": "", "graph_html_path": ""}

    SYSTEM_PROMPT_GERACAO = carregar_system_prompt()

    modelos = carregar_modelos_pecas_from_mongodb()
    info_modelo = None
    for item in modelos:
        if (
            (item.get("area_direito") or "") == area_direito
            and (item.get("tipo_peca") or "") == tipo_peca
            and (item.get("nome_modelo") or "") == nome_modelo
        ):
            info_modelo = item
            break

    if not info_modelo:
        return {"texto": "Erro: Modelo não encontrado no MongoDB.", "graph_summary": "", "graph_html_path": ""}

    modelo_texto = (info_modelo.get("modelo") or info_modelo.get("template") or "").strip()
    if not modelo_texto:
        return {"texto": "Erro: Modelo selecionado está vazio.", "graph_summary": "", "graph_html_path": ""}

    # Conteúdo de docs de exemplo (se houver)
    docs_exemplo_textos: list[str] = []
    arquivos_exemplo = user_inputs.get("arquivos_exemplo") or []
    for f in arquivos_exemplo:
        try:
            docs_exemplo_textos.append(extrair_conteudo_documento(f))
        except Exception:
            pass

    docs_exemplo_block = ""
    if docs_exemplo_textos:
        docs_exemplo_block = "\n\n".join([f"[Doc exemplo {i+1}]\n{t}" for i, t in enumerate(docs_exemplo_textos[:2])])

    # Contexto URLs da sidebar
    urls_block = processar_urls_contexto(urls_contexto or [], pergunta=user_inputs.get("instrucao_adicional_usuario", ""), top_k_chunks=2)

    # Monta instrução final
    params_block = json.dumps({k: v for k, v in (user_inputs or {}).items() if k != "arquivos_exemplo"}, ensure_ascii=False, indent=2)

    final_user_instruction = (
        f"MODELO PARAMETRIZADO (seguir estrutura e estilo):\n{modelo_texto}\n\n"
        f"PARÂMETROS DO USUÁRIO (preencher e adaptar):\n{params_block}\n\n"
    )

    if docs_exemplo_block:
        final_user_instruction += f"DOCUMENTOS DE EXEMPLO (apenas como referência de estilo e apoio):\n{docs_exemplo_block}\n\n"

    if urls_block:
        final_user_instruction += f"{urls_block}\n\n"

    final_user_instruction += "Gere a peça final completa conforme o modelo, pronta para revisão e protocolo."

    # Chama RAG com rerank + GraphRAG auto, salvando HTML
    resposta, _ctx, _details, _web, graph_summary, graph_html_path = generate_response_with_rag_and_web_fallback(
        user_query=final_user_instruction,
        system_message_base=SYSTEM_PROMPT_GERACAO,
        chat_history=None,
        search_client=os_client,
        client_openai=openai_client,
        top_k=10,
        use_web_fallback=enable_web,
        min_contexts_for_web_fallback=2,
        num_web_results=3,
        temperature=0.3,
        max_tokens=4000,
        use_llm_rerank=True,
        top_k_rerank=7,
        use_graph_rag="auto",
        app_hint="app5",
        save_graph_html=True,
    )

    return {
        "texto": (resposta or "").strip(),
        "graph_summary": (graph_summary or "").strip(),
        "graph_html_path": (graph_html_path or "").strip(),
    }


def parametrizador_interface():
    st.header("🧩 Modelo Parametrizado de Peças Jurídicas")
    st.caption(f"LLM: {OPENAI_LLM_MODEL}")
    st.markdown("Gere petições e documentos jurídicos a partir de modelos pré-definidos (MongoDB), com apoio de RAG (OpenSearch) e GraphRAG.")
    st.markdown("---")

    # URLs da sidebar global
    url1_sidebar = st.session_state.get('sidebar_url1', "")
    url2_sidebar = st.session_state.get('sidebar_url2', "")
    url3_sidebar = st.session_state.get('sidebar_url3', "")
    urls_contexto = [u for u in [url1_sidebar, url2_sidebar, url3_sidebar] if (u or "").strip()]

    modelos = carregar_modelos_pecas_from_mongodb()
    if not modelos:
        st.error("Não encontrei modelos no MongoDB. Verifique a conexão/coleção.")
        return

    # Agrupa para selects
    areas = sorted({m.get("area_direito", "").strip() for m in modelos if m.get("area_direito")})
    if not areas:
        st.error("Modelos sem 'area_direito'. Verifique os registros no MongoDB.")
        return

    # Defaults do joblib (se existir no session_state)
    default_area = st.session_state.get("joblib_pred_area_direito") or None

    area_sel = st.selectbox(
        "Área do Direito",
        options=areas,
        index=areas.index(default_area) if (default_area in areas) else 0,
        key=f"area_sel{SESSION_STATE_SUFFIX}",
    )

    tipos = sorted({m.get("tipo_peca", "").strip() for m in modelos if m.get("area_direito") == area_sel and m.get("tipo_peca")})
    if not tipos:
        st.warning("Nenhum tipo de peça para a área selecionada.")
        return

    default_tipo = st.session_state.get("joblib_pred_tipo_peca") or None
    tipo_sel = st.selectbox(
        "Tipo de Peça",
        options=tipos,
        index=tipos.index(default_tipo) if (default_tipo in tipos) else 0,
        key=f"tipo_sel{SESSION_STATE_SUFFIX}",
    )

    nomes_modelo = sorted({m.get("nome_modelo", "").strip() for m in modelos if m.get("area_direito") == area_sel and m.get("tipo_peca") == tipo_sel and m.get("nome_modelo")})
    if not nomes_modelo:
        st.warning("Nenhum modelo disponível para os filtros selecionados.")
        return

    nome_modelo_sel = st.selectbox(
        "Modelo",
        options=nomes_modelo,
        index=0,
        key=f"modelo_sel{SESSION_STATE_SUFFIX}",
    )

    st.markdown("### Parâmetros do Usuário")
    col1, col2 = st.columns(2)

    with col1:
        parte_autora = st.text_input("Parte Autora", key=f"autora{SESSION_STATE_SUFFIX}")
        parte_re = st.text_input("Parte Ré", key=f"re{SESSION_STATE_SUFFIX}")
        foro = st.text_input("Foro/Comarca", key=f"foro{SESSION_STATE_SUFFIX}")
        valor_causa = st.text_input("Valor da Causa (se aplicável)", key=f"valor{SESSION_STATE_SUFFIX}")

    with col2:
        fatos = st.text_area("Fatos (resumo)", height=140, key=f"fatos{SESSION_STATE_SUFFIX}")
        pedidos = st.text_area("Pedidos (resumo)", height=140, key=f"pedidos{SESSION_STATE_SUFFIX}")
        instrucao_extra = st.text_area("Instruções adicionais", height=100, key=f"instrucao{SESSION_STATE_SUFFIX}")

    arquivos_exemplo = st.file_uploader(
        "Documentos de exemplo (opcional — PDF/DOCX)",
        type=["pdf", "docx"],
        accept_multiple_files=True,
        key=f"upload_exemplo{SESSION_STATE_SUFFIX}",
    )

    enable_web = st.checkbox("Permitir complemento via Web (Serper)", value=True, key=f"web{SESSION_STATE_SUFFIX}")

    user_inputs = {
        "parte_autora": parte_autora,
        "parte_re": parte_re,
        "foro": foro,
        "valor_causa": valor_causa,
        "fatos": fatos,
        "pedidos": pedidos,
        "instrucao_adicional_usuario": instrucao_extra,
        "arquivos_exemplo": arquivos_exemplo,
        "data_hoje": datetime.date.today().isoformat(),
    }

    st.markdown("---")

    if st.button("⚙️ Gerar peça parametrizada", type="primary", use_container_width=True, key=f"gerar{SESSION_STATE_SUFFIX}"):
        with st.spinner("Gerando peça com RAG + GraphRAG..."):
            result = gerar_peticao_parametrizada(
                area_direito=area_sel,
                tipo_peca=tipo_sel,
                nome_modelo=nome_modelo_sel,
                user_inputs=user_inputs,
                urls_contexto=urls_contexto,
                enable_web=enable_web,
            )

        texto = (result.get("texto") or "").strip()
        graph_summary = (result.get("graph_summary") or "").strip()
        graph_html_path = (result.get("graph_html_path") or "").strip()

        if not texto:
            st.error("Não consegui gerar a peça.")
            return

        st.session_state[f"last_piece_text{SESSION_STATE_SUFFIX}"] = texto
        st.session_state[f"last_graph_summary{SESSION_STATE_SUFFIX}"] = graph_summary
        st.session_state[f"last_graph_html{SESSION_STATE_SUFFIX}"] = graph_html_path

        st.success("Peça gerada com sucesso!")

    # Exibe resultado se existir
    texto = st.session_state.get(f"last_piece_text{SESSION_STATE_SUFFIX}", "")
    if texto:
        st.markdown("## ✅ Resultado")
        st.text_area("Texto gerado (edite se necessário):", value=texto, height=520, key=f"resultado{SESSION_STATE_SUFFIX}")

        colA, colB = st.columns([1, 1])
        with colA:
            if st.button("📄 Exportar DOCX", use_container_width=True, key=f"export{SESSION_STATE_SUFFIX}"):
                filename = f"peca_parametrizada_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
                path = gerar_docx(texto, filename)
                st.success(f"DOCX gerado: {path}")
        with colB:
            st.caption("Dica: revise nomes/foros/valores e adequação ao caso concreto.")

        # GraphRAG outputs
        graph_html = st.session_state.get(f"last_graph_html{SESSION_STATE_SUFFIX}", "")
        graph_summary = st.session_state.get(f"last_graph_summary{SESSION_STATE_SUFFIX}", "")

        if graph_html or graph_summary:
            with st.expander("🕸️ GraphRAG — Visualização e Sumário", expanded=False):
                if graph_summary:
                    st.markdown("### 🧩 Sumário estrutural")
                    st.markdown(graph_summary)
                if graph_html:
                    st.markdown("### 🕸️ Visualização (HTML)")
                    _render_graph_html_if_exists(graph_html)
