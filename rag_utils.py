# rag_utils.py
import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery, QueryType
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
import os
import time
import uuid
import traceback
import re

from io import BytesIO
from docx import Document as DocxDocument
from docx.shared import Pt
from docx.enum.text import WD_LINE_SPACING

# --- Configurações (Suas Chaves e Endpoints) ---
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate_agent'
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'text-embedding-3-large'
AZURE_API_VERSION = '2024-02-15-preview'

AZURE_SEARCH_ENDPOINT = "https://lexautomate-rag2.search.windows.net"
AZURE_SEARCH_KEY = "igJqXTXsYEC6gpIzFvjOvjm0WtSgd0Xrw8TNMDkwK9AzSeC5ft3H"
DEFAULT_AZURE_SEARCH_INDEX_NAME = "docs-index"


# --- Inicialização dos Clientes ---
@st.cache_resource
def get_openai_client():
    print("INFO: A inicializar o cliente Azure OpenAI...")
    if not all([AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_API_VERSION, AZURE_OPENAI_DEPLOYMENT_LLM, AZURE_OPENAI_DEPLOYMENT_EMBEDDING]):
         print("ERRO: Configurações OpenAI incompletas."); st.error("ERRO: Configs OpenAI.")
         return None
    try:
        client = AzureOpenAI(api_version=AZURE_API_VERSION, azure_endpoint=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_API_KEY)
        try: client.models.list(); print("INFO: Cliente Azure OpenAI OK.")
        except Exception as me: print(f"AVISO: Cliente Azure OpenAI OK, mas listar modelos falhou: {me}.")
        return client
    except Exception as e: print(f"ERRO CRÍTICO OpenAI: {traceback.format_exc()}"); st.error(f"Falha OpenAI: {e}"); return None

@st.cache_resource
def get_azure_search_client(index_name: str = DEFAULT_AZURE_SEARCH_INDEX_NAME):
    print(f"INFO: A inicializar o cliente Azure AI Search para o índice '{index_name}'...")
    if not all([AZURE_SEARCH_ENDPOINT, index_name, AZURE_SEARCH_KEY]):
        print("ERRO: Configurações do Azure AI Search incompletas."); st.error("ERRO: Configs AI Search.")
        return None
    try:
        search_credential = AzureKeyCredential(AZURE_SEARCH_KEY)
        client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=index_name, credential=search_credential)
        try:
            index_admin_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=search_credential)
            idx = index_admin_client.get_index(index_name)
            if idx.semantic_search and idx.semantic_search.configurations:
                 print(f"INFO: Ligação ao índice '{index_name}' OK e configuração semântica encontrada: '{idx.semantic_search.configurations[0].name}'.")
            else:
                 print(f"AVISO: Ligação ao índice '{index_name}' OK, MAS NENHUMA CONFIGURAÇÃO SEMÂNTICA ENCONTRADA NO ÍNDICE.")
                 print("A pesquisa semântica pode não funcionar como esperado.")
            print(f"INFO: Contagem atual de documentos no índice '{index_name}': {client.get_document_count()}")
        except Exception as se:
            print(f"ERRO: Falha ao verificar o índice '{index_name}' ou obter contagem: {traceback.format_exc()}");
            st.error(f"Falha no índice '{index_name}': {se}");
        return client
    except Exception as e:
        print(f"ERRO CRÍTICO Azure AI Search: {traceback.format_exc()}");
        st.error(f"Falha Azure AI Search: {e}");
        return None

# --- Funções Auxiliares RAG ---
def get_embedding(text_chunk, client_openai):
    if not text_chunk or client_openai is None: return None
    try:
        processed_chunk = ' '.join(text_chunk.replace('\n', ' ').split())
        if not processed_chunk: return None
        response = client_openai.embeddings.create(input=processed_chunk, model=AZURE_OPENAI_DEPLOYMENT_EMBEDDING)
        return response.data[0].embedding
    except Exception as e:
        print(f"ERRO: Falha em get_embedding: {traceback.format_exc()}")
        return None

def find_relevant_chunks_azure_search(query_text, search_client, client_openai, top_k=5, use_semantic_search=True):
    if not query_text or search_client is None or client_openai is None:
        return []

    query_embedding = get_embedding(query_text, client_openai)
    if query_embedding is None:
        print("AVISO: Não foi possível gerar embedding para a consulta. A pesquisa vetorial será ignorada.")

    vector_query = None
    if query_embedding:
        vector_query = VectorizedQuery(
            vector=query_embedding,
            k_nearest_neighbors=top_k,
            fields="content_vector",
            exhaustive=True
        )

    print(f"INFO: A procurar top_{top_k} chunks para a consulta: '{query_text[:100]}...' com pesquisa semântica: {use_semantic_search}")

    try:
        # Certifique-se de que 'arquivo_origem', 'entities', 'key_phrases' estão no seu índice e são selecionáveis
        # Se não estiverem no índice, remova-os do select ou adicione-os ao seu índice e reindexe.
        fields_to_select = ["chunk_id", "document_id", "arquivo_origem", "content"]
        # Opcionalmente adicione "keywords_list", "entities", "key_phrases" se existirem no índice
        # e você quiser usá-los nos logs ou na interface.
        # fields_to_select.extend(["keywords_list", "entities", "key_phrases"])


        search_results = search_client.search(
            search_text=query_text if use_semantic_search else None,
            vector_queries=[vector_query] if vector_query else None,
            select=fields_to_select,
            query_type=QueryType.SEMANTIC if use_semantic_search else QueryType.SIMPLE,
            semantic_configuration_name='default' if use_semantic_search else None,
            query_caption="extractive" if use_semantic_search else None,
            query_answer="extractive" if use_semantic_search else None,
            top=top_k
        )

        retrieved_chunks_details = []

        if use_semantic_search:
            semantic_answers = search_results.get_answers()
            if semantic_answers:
                print(f"INFO: Respostas Semânticas encontradas:")
                for answer in semantic_answers:
                    if answer.highlights:
                        print(f"  - Resposta (destaques): {answer.highlights}")
                    else:
                        print(f"  - Resposta: {answer.text}")
                    print(f"  - (ID do Documento da Resposta: {answer.key})")

        print(f"\n--- DETALHES DOS CHUNKS RECUPERADOS (Consulta: '{query_text[:50]}...') ---")
        for i, doc in enumerate(search_results):
            chunk_detail = {
                "rank": i + 1,
                "chunk_id": doc.get("chunk_id", "N/A"),
                "document_id": doc.get("document_id", "N/A"),
                "arquivo_origem": doc.get("arquivo_origem", "N/A"),
                "score": doc.get("@search.score"),
                "reranker_score": doc.get("@search.reranker_score"),
                "content": doc.get("content", ""), # Conteúdo completo do chunk
                "content_preview": doc.get("content", "")[:200] + "..." # Preview para logs/UI
                # Opcional: Adicionar entities e key_phrases se selecionados e presentes
                # "entities_preview": doc.get("entities", [])[:5],
                # "key_phrases_preview": doc.get("key_phrases", [])[:5]
            }
            retrieved_chunks_details.append(chunk_detail)

            print(f"  Chunk #{chunk_detail['rank']}:")
            print(f"    ID: {chunk_detail['chunk_id']}")
            print(f"    Documento ID: {chunk_detail['document_id']}")
            print(f"    Arquivo Origem: {chunk_detail['arquivo_origem']}")
            print(f"    Score Busca: {chunk_detail['score']:.4f if chunk_detail['score'] else 'N/A'}")
            if chunk_detail['reranker_score'] is not None:
                print(f"    Score Reclassificação Semântica: {chunk_detail['reranker_score']:.4f}")

            if use_semantic_search and "@search.captions" in doc:
                captions = doc["@search.captions"]
                if captions:
                    caption_text = " ".join([c.text for c in captions])
                    chunk_detail["semantic_caption"] = caption_text # Adiciona ao dicionário
                    print(f"    Caption Semântico: '{caption_text}'")
            print(f"    Conteúdo (início): {chunk_detail['content_preview']}")
            print("-" * 20)

        print(f"--- FIM DETALHES DOS CHUNKS ---")
        print(f"INFO: Encontrados {len(retrieved_chunks_details)} chunks relevantes (após possível reclassificação semântica).")

        # Armazenar os detalhes recuperados no session_state para exibição na UI
        # Isso será feito na interface que chama esta função, para evitar dependência direta de st aqui
        # st.session_state.last_retrieved_chunks_details = retrieved_chunks_details

        return retrieved_chunks_details # Retorna a lista de dicionários com detalhes

    except Exception as e:
        print(f"ERRO: Falha na pesquisa (híbrida/semântica): {traceback.format_exc()}")
        st.session_state.last_retrieved_chunks_details = [] # Limpa em caso de erro
        return []


# --- Função Principal RAG ---
def generate_response_with_rag(system_message, user_instruction, context_document_text, search_client, client_openai, top_k_chunks=5, use_semantic_search_in_rag=True):
    if client_openai is None or search_client is None:
         print("ERRO RAG: Clientes IA não disponíveis.")
         return "Erro interno nos serviços de IA."

    print(f"INFO RAG: A recuperar chunks para a instrução: '{user_instruction[:100]}...'")

    # find_relevant_chunks_azure_search agora retorna uma lista de dicionários
    retrieved_chunks_info_list = find_relevant_chunks_azure_search(
        user_instruction,
        search_client,
        client_openai,
        top_k=top_k_chunks,
        use_semantic_search=use_semantic_search_in_rag
    )
    # Armazena os detalhes recuperados no session_state para uso na UI
    st.session_state.last_retrieved_chunks_details = retrieved_chunks_info_list


    context_from_search = ""
    if retrieved_chunks_info_list:
        context_from_search = "---\n**Contexto Adicional Recuperado da Base de Conhecimento Jurídico:**\n---\n"
        for i, chunk_info in enumerate(retrieved_chunks_info_list, 1):
            source_name = chunk_info.get('arquivo_origem', 'Fonte Desconhecida')
            chunk_content = chunk_info.get('content', '') # Usar o conteúdo completo do chunk
            context_from_search += f"**Referência {i} (Fonte Documental: {source_name}):**\n{chunk_content}\n\n"
        context_from_search += "---\nFim do Contexto Adicional Recuperado\n---"
        print(f"DEBUG RAG: Contexto recuperado para o LLM (COM FONTES):\n{context_from_search[:500]}...")
    else:
        context_from_search = "\n(Nenhum contexto adicional específico foi recuperado da base de conhecimento para esta consulta.)\n"
        print("DEBUG RAG: Nenhum contexto adicional recuperado para o LLM.")

    final_user_message = (
        f"{context_from_search}\n\n"
        f"Considerando o CONTEXTO ADICIONAL RECUPERADO acima (incluindo suas Fontes Documentais) e, PRINCIPALMENTE, o TEXTO COMPLETO DO DOCUMENTO FORNECIDO abaixo (se houver), "
        f"siga EXATAMENTE a seguinte instrução:\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"---\n**TEXTO COMPLETO DO DOCUMENTO FORNECIDO (do arquivo carregado):**\n---\n"
        f"{context_document_text if context_document_text else 'Nenhum documento principal foi fornecido para esta tarefa.'}\n"
        f"---\nFim do Documento Fornecido\n---"
    )

    final_response = "Erro: Falha ao gerar resposta."
    print(f"INFO RAG: A enviar para LLM ({AZURE_OPENAI_DEPLOYMENT_LLM}).")
    try:
        response = client_openai.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_LLM,
            messages=[ {"role": "system", "content": system_message}, {"role": "user", "content": final_user_message} ],
            temperature=0.1, max_tokens=4000, top_p=0.9, # Ajuste a temperatura e max_tokens conforme necessário
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            final_response = response.choices[0].message.content.strip()
        else:
            print("ERRO RAG: Resposta API LLM inválida.")
            final_response = "Erro: Resposta IA vazia."
    except Exception as e:
        print(f"ERRO CRÍTICO RAG: Falha chat.completions: {traceback.format_exc()}");
        final_response = f"Erro ao gerar resposta."
    return final_response

# --- Função para o Consultor Jurídico (App4) com Pesquisa Semântica ---
MAX_CHAT_HISTORY_MESSAGES = 10

def build_messages_for_llm_chat(system_message, chat_history, user_instruction_with_context):
    messages = [{"role": "system", "content": system_message}]
    if chat_history:
        start_index = max(0, len(chat_history) - MAX_CHAT_HISTORY_MESSAGES)
        for msg in chat_history[start_index:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_instruction_with_context})
    return messages

def generate_consultor_response_with_rag(system_message, user_instruction, chat_history, search_client, client_openai, top_k_chunks=3, use_semantic_search_in_consultor=True):
    if client_openai is None or search_client is None:
        print("ERRO (Consultor): Clientes OpenAI ou Search não disponíveis.")
        return "Desculpe, estou com problemas para aceder aos meus serviços de IA no momento."

    # find_relevant_chunks_azure_search retorna lista de dicionários
    retrieved_chunks_info_list = find_relevant_chunks_azure_search(
        user_instruction,
        search_client,
        client_openai,
        top_k=top_k_chunks,
        use_semantic_search=use_semantic_search_in_consultor
    )
    # Armazena os detalhes recuperados no session_state para uso na UI (se o app4 tiver essa funcionalidade)
    st.session_state.last_retrieved_chunks_details_consultor = retrieved_chunks_info_list


    context_string_from_search = ""
    if retrieved_chunks_info_list:
        context_string_from_search = "---\n**Contexto Relevante da Base de Conhecimento Encontrado:**\n---\n"
        for i, chunk_info in enumerate(retrieved_chunks_info_list, 1):
            source_name = chunk_info.get('arquivo_origem', 'Fonte Desconhecida')
            chunk_content = chunk_info.get('content', '')
            context_string_from_search += f"**Referência {i} (Fonte: {source_name}):**\n{chunk_content}\n\n"
        context_string_from_search += "---\nFim do Contexto Relevante\n---"
        print(f"DEBUG Consultor: Contexto recuperado para o LLM:\n{context_string_from_search[:500]}...")
    else:
        context_string_from_search = "\n(Para esta pergunta específica, não encontrei informações diretamente relevantes na minha base de conhecimento atual.)\n"
        print("DEBUG Consultor: Nenhum contexto recuperado para o LLM.")

    user_instruction_with_context_for_llm = (
        f"Pergunta do Utilizador: '{user_instruction}'\n\n"
        f"{context_string_from_search}\n\n"
        f"Com base no contexto acima e no seu conhecimento geral, por favor, responda à pergunta do utilizador de forma completa e didática, citando as fontes do contexto quando apropriado."
    )

    messages_for_llm = build_messages_for_llm_chat(
        system_message,
        chat_history,
        user_instruction_with_context_for_llm
    )

    final_response = "Desculpe, não consegui processar o seu pedido para o consultor neste momento."
    print(f"INFO (Consultor): A enviar para LLM ({AZURE_OPENAI_DEPLOYMENT_LLM}) com {len(messages_for_llm)} mensagens.")
    try:
        response = client_openai.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_LLM,
            messages=messages_for_llm,
            temperature=0.5,
            max_tokens=2000,
            top_p=0.95,
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            final_response = response.choices[0].message.content.strip()
        else:
            print("ERRO (Consultor): Resposta da API LLM inválida.")
    except Exception as e:
        print(f"ERRO CRÍTICO (Consultor): Falha chat.completions: {traceback.format_exc()}")
        final_response = f"Erro ao gerar resposta do consultor. Tente novamente mais tarde."
    return final_response


# --- Função de Exportação DOCX (sem alterações) ---
def gerar_docx(texto_markdown):
    # (código da função gerar_docx original - sem alterações necessárias aqui)
    print("INFO: Gerando arquivo DOCX com interpretação de Markdown...")
    try:
        document = DocxDocument()
        style = document.styles['Normal']
        font = style.font
        font.name = 'Arial'
        font.size = Pt(11)
        linhas = texto_markdown.split('\n')
        for linha_idx, linha_original in enumerate(linhas):
            paragrafo_docx = document.add_paragraph()
            linha_strip = linha_original.strip()
            paragrafo_docx.paragraph_format.space_before = Pt(0)
            paragrafo_docx.paragraph_format.space_after = Pt(0)
            match_heading = re.match(r'^(#+)\s+(.*)', linha_strip)
            if match_heading:
                nivel = len(match_heading.group(1))
                texto_titulo = match_heading.group(2).strip()
                if texto_titulo.startswith('**') and texto_titulo.endswith('**'):
                    texto_titulo = texto_titulo[2:-2]
                run = paragrafo_docx.add_run(texto_titulo)
                run.bold = True
                if nivel == 1: run.font.size = Pt(16)
                elif nivel == 2: run.font.size = Pt(14)
                else: run.font.size = Pt(12)
                if linha_idx > 0: paragrafo_docx.paragraph_format.space_before = Pt(12)
                paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue
            eh_titulo_linha_inteira_bold = linha_strip.startswith('**') and \
                                           linha_strip.endswith('**') and \
                                           2 < len(linha_strip) and \
                                           linha_strip.count('**') == 2
            if eh_titulo_linha_inteira_bold:
                if linha_idx > 0 and linhas[linha_idx-1].strip():
                    paragrafo_docx.paragraph_format.space_before = Pt(6)
                texto_do_titulo = linha_strip[2:-2]
                run = paragrafo_docx.add_run(texto_do_titulo)
                run.bold = True
                paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue
            if linha_strip:
                partes = re.split(r'(\*\*.+?\*\*)', linha_original)
                for parte in partes:
                    if parte.startswith('**') and parte.endswith('**') and len(parte) > 4:
                        texto_do_negrito = parte[2:-2]
                        run = paragrafo_docx.add_run(texto_do_negrito)
                        run.bold = True
                    elif parte:
                        paragrafo_docx.add_run(parte)
            else:
                if not (linha_idx > 0 and re.match(r'^(#+)\s+(.*)', linhas[linha_idx-1].strip())) and \
                   not (linha_idx > 0 and (linhas[linha_idx-1].strip().startswith('**') and linhas[linha_idx-1].strip().endswith('**') and linhas[linha_idx-1].strip().count('**') == 2)):
                     paragrafo_docx.paragraph_format.space_after = Pt(6)
        buffer = BytesIO()
        document.save(buffer)
        buffer.seek(0)
        print("INFO: Arquivo DOCX gerado com sucesso.")
        return buffer.getvalue()
    except Exception as e:
        print(f"ERRO: Falha ao gerar DOCX: {e}\n{traceback.format_exc()}")
        st.error(f"Erro ao gerar arquivo DOCX: {e}")
        raise