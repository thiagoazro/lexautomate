# app5.py (Geração de Peças Jurídicas Parametrizadas lendo do MongoDB e URLs da Sidebar Global)
import streamlit as st
import json # Mantido caso precise para outras operações futuras, mas não para carregar modelos
import os
import uuid
import traceback
from rag_utils import (
    get_openai_client,
    get_azure_search_client,
    generate_response_with_conditional_google_search,
    AZURE_OPENAI_DEPLOYMENT_LLM,
    gerar_docx,
    salvar_feedback_rag
)
# Importar utilitários Chroma
from chroma_utils import obter_contexto_relevante_de_url
# Importar utilitários de banco de dados
from db_utils import carregar_modelos_pecas_from_mongodb # Importa a função para carregar modelos do MongoDB

try:
    from rag_docintelligence import extrair_texto_documento
    DOC_INTELLIGENCE_AVAILABLE = True
except ImportError:
    DOC_INTELLIGENCE_AVAILABLE = False
    st.warning("Módulo rag_docintelligence.py não encontrado. A funcionalidade de anexar documento de exemplo estará desabilitada.")

# --- CONFIGURAÇÕES ---
# MODELOS_PECAS_FILE = "modelos_pecas.json" # REMOVIDO: Modelos vêm do MongoDB
PROMPT_PARAMETRIZADOR_FILE = "prompts/system_prompt_app5_parametrizador.md"

def carregar_prompt_parametrizador(prompt_path: str = PROMPT_PARAMETRIZADOR_FILE) -> str:
    """
    Carrega o system prompt específico para a funcionalidade de parametrizador.
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        full_prompt_path = os.path.join(current_dir, "..", prompt_path)
        if not os.path.exists(full_prompt_path):
             full_prompt_path = os.path.join(current_dir, prompt_path)
        
        with open(full_prompt_path, "r", encoding="utf-8") as f:
            print(f"INFO APP5 (Parametrizador): Prompt carregado de: {full_prompt_path}")
            return f.read()
    except Exception as e:
        st.warning(f"Erro ao carregar o prompt do parametrizador de '{prompt_path}': {e}. Usando prompt padrão.")
        return "Você é um assistente jurídico especializado em criar peças processuais detalhadas e bem fundamentadas."


def parametrizador_interface():
    st.markdown("Preencha os campos, anexe documentos de exemplo e, opcionalmente, utilize as URLs da barra lateral para enriquecer a geração da peça.")
    st.markdown("---")

    # Sufixo para chaves de session_state desta aba
    sfx = "_app5_sidebar"
    if f'peticao_gerada{sfx}' not in st.session_state:
        st.session_state[f'peticao_gerada{sfx}'] = ""
    if f'last_user_urls_context{sfx}' not in st.session_state:
        st.session_state[f'last_user_urls_context{sfx}'] = ""
    if f'last_prompt{sfx}' not in st.session_state:
        st.session_state[f'last_prompt{sfx}'] = ""
    if f'last_response_text{sfx}' not in st.session_state:
        st.session_state[f'last_response_text{sfx}'] = ""
    if f'geracao_em_andamento{sfx}' not in st.session_state:
        st.session_state[f'geracao_em_andamento{sfx}'] = False

    # >>> ALTERAÇÃO AQUI: Carrega os modelos do MongoDB
    # Esta função está decorada com @st.cache_data e @st.cache_resource, então ela será eficiente.
    modelos_data = carregar_modelos_pecas_from_mongodb()
    
    # Define fallbacks se nenhum modelo for carregado (ex: problema de conexão com o DB)
    if not modelos_data:
        st.warning("Modelos de peças não carregados do MongoDB. Algumas opções podem estar limitadas ou ausentes. Verifique a conexão e se o DB está populado.")
        areas_disponiveis = ["Nenhum Modelo Disponível"]
        tipos_peca_disponiveis_fallback = {"Nenhum Modelo Disponível": ["Nenhum"]}
        modelos_peca_disponiveis_fallback = {"Nenhum": ["Nenhum"]}
    else:
        areas_disponiveis = list(modelos_data.keys())

    col1, col2, col3 = st.columns(3)
    with col1:
        # Garante que a área selecionada é válida ou a primeira disponível
        area_selecionada = st.selectbox("Área do Direito:", areas_disponiveis, key=f"area{sfx}")
    
    # Garante que os tipos de peça e modelos específicos são válidos para a seleção atual
    tipos_na_area = list(modelos_data.get(area_selecionada, {}).keys()) if area_selecionada in modelos_data else tipos_peca_disponiveis_fallback.get(area_selecionada, ["Outro"])
    with col2:
        tipo_peca_selecionado = st.selectbox("Tipo da Peça:", tipos_na_area, key=f"tipo{sfx}")
    
    modelos_no_tipo = list(modelos_data.get(area_selecionada, {}).get(tipo_peca_selecionado, {}).keys()) if area_selecionada in modelos_data and tipo_peca_selecionado in modelos_data[area_selecionada] else modelos_peca_disponiveis_fallback.get(tipo_peca_selecionado, ["Modelo Genérico"])
    with col3:
        modelo_especifico_selecionado = st.selectbox("Modelo Específico:", modelos_no_tipo, key=f"modelo{sfx}")

    # Garante que info_modelo_selecionado seja um dicionário vazio se não houver seleção válida
    info_modelo_selecionado = modelos_data.get(area_selecionada, {}).get(tipo_peca_selecionado, {}).get(modelo_especifico_selecionado, {})

    # Define um fallback para o prompt_template e reivindicacoes_comuns se o modelo não for encontrado/válido
    prompt_template_modelo_fallback = "Gere uma peça jurídica padrão com as informações fornecidas, pois o modelo selecionado não está disponível ou está incompleto. Use as seguintes informações: Autor: {autor}, Réu: {reu}, Foro: {foro}, Valor da causa: {valor}, Pedidos: {pedidos_formatados_str}, Instruções: {instrucao_adicional_usuario}. Se houver, utilize o documento de exemplo: {documento_exemplo_para_referencia}"
    reivindicacoes_comuns_modelo = info_modelo_selecionado.get("reivindicacoes_comuns", [])

    # Se a seleção inicial resultou em um modelo vazio (ex: "Nenhum Modelo Disponível"),
    # ou o modelo selecionado não tem os dados esperados.
    if not info_modelo_selecionado and area_selecionada != "Nenhum Modelo Disponível":
        st.warning("Detalhes do modelo selecionado não encontrados no banco de dados. Um prompt genérico será usado.")


    st.markdown("### Informações Básicas da Peça")
    autor_recorrente = st.text_input("Parte Autora/Reclamante/Recorrente:", placeholder="Ex: João da Silva", key=f"autor{sfx}")
    reu_recorrente = st.text_input("Parte Ré/Reclamada/Recorrida:", placeholder="Ex: Empresa XYZ Ltda.", key=f"reu{sfx}")
    foro_competente = st.text_input("Foro Competente:", placeholder="Ex: Comarca de Exemplo / Vara do Trabalho de Exemplo", key=f"foro{sfx}")
    valor_causa = st.text_input("Valor da Causa (R$):", placeholder="Ex: 10.000,00", key=f"valor{sfx}")

    pedidos_selecionados = st.multiselect("Pedidos Principais (selecione do modelo ou adicione abaixo):", reivindicacoes_comuns_modelo, key=f"pedidos_multiselect{sfx}")
    outros_pedidos_texto = st.text_area("Outros Pedidos (um por linha):", placeholder="Ex: Indenização por danos morais\nEx: Reintegração ao emprego", key=f"outros_pedidos{sfx}")
    
    instrucao_adicional_usuario = st.text_area("Instruções Adicionais para a IA (detalhes específicos, teses, etc.):", key=f"instrucao_adicional{sfx}")

    texto_documento_exemplo = ""
    if DOC_INTELLIGENCE_AVAILABLE:
        st.markdown("### Documento(s) de Exemplo (Opcional)")
        docs_exemplo = st.file_uploader("Anexar documento(s) de referência (PDF ou DOCX):", type=["pdf", "docx"], accept_multiple_files=True, key=f"docs_exemplo{sfx}")
        if docs_exemplo:
            textos_docs_exemplo = []
            for doc in docs_exemplo:
                ext = os.path.splitext(doc.name)[1].lower()
                temp_path = f"temp{sfx}_{uuid.uuid4().hex}{ext}"
                try:
                    with open(temp_path, "wb") as f:
                        f.write(doc.getvalue())
                    with st.spinner(f"Extraindo texto de {doc.name}..."):
                        texto_extraido_doc = extrair_texto_documento(temp_path, ext)
                    if texto_extraido_doc:
                        textos_docs_exemplo.append(f"---\n**Documento de Exemplo: {doc.name}**\n\n{texto_extraido_doc}")
                    else:
                        st.warning(f"Não foi possível extrair texto de {doc.name}.")
                except Exception as e:
                    st.error(f"Erro ao processar {doc.name}: {e}")
                    traceback.print_exc()
                finally:
                    if os.path.exists(temp_path):
                        try: os.remove(temp_path)
                        except Exception as e_rm: print(f"Aviso: Falha ao remover arquivo temporário {temp_path}: {e_rm}")
            
            if textos_docs_exemplo:
                texto_documento_exemplo = "\n\n".join(textos_docs_exemplo)
                with st.expander("Ver Texto dos Documentos de Exemplo Anexados", expanded=False):
                    st.text_area("Texto Extraído dos Documentos de Exemplo:", texto_documento_exemplo, height=150, disabled=True, key=f"texto_docs_exemplo_display{sfx}")

    # Lê as URLs da sidebar (definidas em main.py)
    url1_sidebar = st.session_state.get('sidebar_url1', "")
    url2_sidebar = st.session_state.get('sidebar_url2', "")
    url3_sidebar = st.session_state.get('sidebar_url3', "")
    user_urls_from_sidebar = [url for url in [url1_sidebar, url2_sidebar, url3_sidebar] if url.strip()]

    if user_urls_from_sidebar:
        st.info(f"Utilizando {len(user_urls_from_sidebar)} URL(s) de contexto da barra lateral para esta peça.")
    
    enable_google_search_app5 = st.checkbox("Habilitar busca complementar na Web (Google) para esta peça?", value=True, key=f"param_enable_google_search{sfx}_checkbox")

    if st.button("Gerar Petição Parametrizada", key=f"gerar_peticao_param{sfx}_button"):
        if area_selecionada == "Nenhum Modelo Disponível" or not info_modelo_selecionado:
            st.warning("Selecione um modelo de peça válido para gerar. Não há modelos disponíveis ou o selecionado está incompleto.")
            return

        client = get_openai_client()
        search_client = get_azure_search_client()
        if not client or not search_client:
            st.error("Erro ao inicializar clientes de IA. Verifique as configurações e logs.")
            return

        st.session_state[f'geracao_em_andamento{sfx}'] = True
        st.session_state[f'last_user_urls_context{sfx}'] = ""

        todos_pedidos_finais = pedidos_selecionados + [p.strip() for p in outros_pedidos_texto.split("\n") if p.strip()]
        pedidos_formatados_str = ", ".join(todos_pedidos_finais) if todos_pedidos_finais else "(não especificado)"

        prompt_base_para_contexto_urls = (
            f"Pesquisar jurisprudência e informações relevantes para uma peça do tipo '{tipo_peca_selecionado}' na área '{area_selecionada}', "
            f"envolvendo as partes '{autor_recorrente}' e '{reu_recorrente}', com os pedidos: '{pedidos_formatados_str}'. "
            f"Considerar também as seguintes instruções adicionais: '{instrucao_adicional_usuario}'."
        )

        contexto_urls_agregado_para_prompt = ""
        contexto_urls_agregado_para_exibir = ""

        if user_urls_from_sidebar:
            num_urls_para_consultar = len(user_urls_from_sidebar)
            spinner_message_urls = f"Consultando {num_urls_para_consultar} URL(s) da barra lateral..."
            with st.spinner(spinner_message_urls):
                for i, url_item in enumerate(user_urls_from_sidebar, 1):
                    print(f"INFO APP5 (Parametrizador): Obtendo contexto Chroma da URL {i} (sidebar): {url_item} para a consulta: '{prompt_base_para_contexto_urls}'")
                    contexto_url_individual = obter_contexto_relevante_de_url(
                        url_item,
                        prompt_base_para_contexto_urls,
                        top_k_chunks=2 
                    )
                    if contexto_url_individual and "Nenhum conteúdo relevante" not in contexto_url_individual and "Falha ao carregar" not in contexto_url_individual:
                        contexto_urls_agregado_para_prompt += f"\n--- Contexto da URL {i} ({url_item}) ---\n{contexto_url_individual}\n--- Fim do Contexto da URL {i} ---\n\n"
                        contexto_urls_agregado_para_exibir += f"<b>Contexto da URL {i} ({url_item}):</b><br>{contexto_url_individual}<hr>"
                        print(f"INFO APP5 (Parametrizador): Contexto da URL {i} (sidebar) adicionado.")
                    else:
                        aviso_url = f"<i>Nenhum contexto útil obtido da URL {i} ({url_item}) da barra lateral.</i><br>"
                        contexto_urls_agregado_para_exibir += aviso_url
                        print(f"AVISO APP5 (Parametrizador): {aviso_url}")
        
        st.session_state[f'last_user_urls_context{sfx}'] = contexto_urls_agregado_para_exibir if contexto_urls_agregado_para_exibir else "Nenhuma URL fornecida na barra lateral ou nenhum contexto relevante extraído."

        # Usa o prompt_template do modelo selecionado ou o fallback
        prompt_template_utilizado = info_modelo_selecionado.get("prompt_template", prompt_template_modelo_fallback)
        
        format_args_peca = {
            "area_selecionada": area_selecionada,
            "tipo_peca_selecionado": tipo_peca_selecionado,
            "modelo_especifico_selecionado": modelo_especifico_selecionado,
            "autor_recorrente": autor_recorrente or "[NOME AUTOR/RECORRENTE]",
            "reu_recorrente": reu_recorrente or "[NOME RÉU/RECORRIDO]",
            "foro": foro_competente or "[FORO COMPETENTE]",
            "valor": valor_causa or "[VALOR DA CAUSA]",
            "pedidos_formatados_str": pedidos_formatados_str,
            "instrucao_adicional_usuario": instrucao_adicional_usuario or "[Nenhuma instrução adicional específica]",
            "texto_documento_exemplo": texto_documento_exemplo or "[Nenhum documento de exemplo fornecido]",
            "autor": autor_recorrente or "[NOME AUTOR]", "reu": reu_recorrente or "[NOME RÉU]",
            "reclamante": autor_recorrente or "[NOME RECLAMANTE]", "reclamada": reu_recorrente or "[NOME RECLAMADA]",
            "reivindicacoes_formatadas": pedidos_formatados_str,
            "instrucao_adicional": instrucao_adicional_usuario or "[Nenhuma instrução adicional]",
            "documento_exemplo_para_referencia": texto_documento_exemplo or "[Nenhum documento de exemplo fornecido]"
            }
        
        prompt_final_para_llm = prompt_template_utilizado.format(**{k: v if v is not None else f"[{k.upper()}]" for k, v in format_args_peca.items()})

        if contexto_urls_agregado_para_prompt:
            prompt_final_para_llm = (
                f"{contexto_urls_agregado_para_prompt}"
                f"Considerando os contextos acima extraídos das URLs fornecidas pelo usuário na barra lateral, "
                f"e o(s) documento(s) de exemplo também fornecido(s) (se houver), gere a peça conforme as seguintes especificações:\n\n"
                f"Especificações da Peça: \"{prompt_final_para_llm}\""
            )

        with st.spinner("Gerando petição parametrizada com todas as fontes..."):
            try:
                system_prompt_base_app5 = carregar_prompt_parametrizador()
                resposta = generate_response_with_conditional_google_search(
                    system_message_base=system_prompt_base_app5,
                    user_instruction=prompt_final_para_llm,
                    context_document_text=texto_documento_exemplo,
                    search_client=search_client,
                    client_openai=client,
                    azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
                    azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM,
                    top_k_initial_search_azure=5,
                    top_k_rerank_azure=2,
                    use_semantic_search_azure=True,
                    enable_google_search_trigger=enable_google_search_app5,
                    temperature=0.3,
                    max_tokens=4000
                )
                st.session_state[f'peticao_gerada{sfx}'] = str(resposta).strip()
                
                st.session_state[f'last_prompt{sfx}'] = prompt_final_para_llm
                st.session_state[f'last_response_text{sfx}'] = st.session_state[f'peticao_gerada{sfx}']

            except Exception as e:
                st.error(f"Erro ao gerar petição parametrizada: {e}")
                st.session_state[f'peticao_gerada{sfx}'] = ""
                traceback.print_exc()
            finally:
                st.session_state[f'geracao_em_andamento{sfx}'] = False
                st.rerun()

    if st.session_state.get(f'peticao_gerada{sfx}', ""):
        st.markdown("---")
        st.markdown("## 📝 Petição Gerada")

        if st.session_state.get(f'last_user_urls_context{sfx}') and ("Contexto da URL" in st.session_state.get(f'last_user_urls_context{sfx}')):
            with st.expander("Contexto das URLs da Barra Lateral Utilizado", expanded=False):
                st.markdown(st.session_state[f'last_user_urls_context{sfx}'], unsafe_allow_html=True)

        with st.expander("📄 Pré-visualização da Petição (Somente Leitura)", expanded=True):
            st.markdown(st.session_state[f'peticao_gerada{sfx}'], unsafe_allow_html=True)

        texto_editado_app5 = st.text_area("Edição opcional:", value=st.session_state[f'peticao_gerada{sfx}'], height=400, key=f"editor_peticao{sfx}")
        
        if texto_editado_app5 != st.session_state[f'peticao_gerada{sfx}']:
            st.session_state[f'peticao_gerada{sfx}'] = texto_editado_app5

        try:
            docx_file = gerar_docx(st.session_state[f'peticao_gerada{sfx}'])
            st.download_button(
                label="📅 Baixar Petição em DOCX",
                data=docx_file,
                file_name=f"LexAutomate_Peticao_{tipo_peca_selecionado.replace(' ', '_')}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"download_docx{sfx}_button"
            )
        except Exception as e:
            st.error(f"Erro ao gerar o DOCX para a petição: {e}")
            traceback.print_exc()

    if f'last_response_text{sfx}' in st.session_state and st.session_state[f'last_response_text{sfx}']:
        with st.expander("💬 Sua opinião nos ajuda a melhorar esta funcionalidade"):
            feedback_opcao_app5 = st.radio(
                "Esta petição gerada foi útil?",
                ["👍 Sim", "👎 Não"],
                key=f"feedback_radio_param{sfx}_{st.session_state.get(f'last_prompt{sfx}', uuid.uuid4().hex)}"
            )
            comentario_app5 = st.text_area(
                "Comentário sobre a petição (opcional):",
                placeholder="Diga o que achou da petição ou o que faltou.",
                key=f"feedback_comment_param{sfx}_{st.session_state.get(f'last_prompt{sfx}', uuid.uuid4().hex)}"
            )
            if st.button("Enviar Feedback da Petição Parametrizada", key=f"feedback_submit_param{sfx}_{st.session_state.get(f'last_prompt{sfx}', uuid.uuid4().hex)}"):
                salvar_feedback_rag(
                    pergunta=st.session_state.get(f'last_prompt{sfx}', "Instrução não registrada"),
                    resposta=st.session_state.get(f'last_response_text{sfx}', ""),
                    feedback=feedback_opcao_app5,
                    comentario=comentario_app5,
                )
                st.success("Feedback sobre a petição enviado com sucesso. Obrigado!")
                if f'last_response_text{sfx}' in st.session_state: del st.session_state[f'last_response_text{sfx}']
                if f'last_prompt{sfx}' in st.session_state: del st.session_state[f'last_prompt{sfx}']
                st.rerun()