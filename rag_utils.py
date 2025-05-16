# rag_utils.py
import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery, QueryType
from azure.search.documents.indexes import SearchIndexClient
from azure.core.credentials import AzureKeyCredential
import os
import traceback
import re
import json
import requests

from io import BytesIO
from docx import Document as DocxDocument
from docx.shared import Pt
from docx.enum.text import WD_LINE_SPACING

# --- ATENÇÃO: CREDENCIAIS HARDCODED - NÃO RECOMENDADO PARA PRODUÇÃO ---
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA'
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate_agent'
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'text-embedding-3-large'
AZURE_API_VERSION = '2024-02-15-preview'

AZURE_SEARCH_ENDPOINT = "https://lexautomate-rag2.search.windows.net"
AZURE_SEARCH_KEY = "igJqXTXsYEC6gpIzFvjOvjm0WtSgd0Xrw8TNMDkwK9AzSeC5ft3H"
DEFAULT_AZURE_SEARCH_INDEX_NAME = "docs-index"
AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT = "default"

GOOGLE_API_KEY = "AIzaSyCUT6HKCaOe51hTM7PY3sexnSJm1mlO5k0"
GOOGLE_CX_ID = "e3c7fef3c7d1c4a10"
# -----------------------------------------------------------------------

@st.cache_resource
def get_openai_client():
    print("INFO RAG_UTILS: Inicializando cliente Azure OpenAI...")
    if not all([AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_API_VERSION, AZURE_OPENAI_DEPLOYMENT_LLM, AZURE_OPENAI_DEPLOYMENT_EMBEDDING]):
         print("ERRO RAG_UTILS: Configurações Azure OpenAI incompletas.");
         st.error("ERRO: Configs OpenAI.")
         return None
    try:
        client = AzureOpenAI(
            api_version=AZURE_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY
        )
        try:
            client.models.list()
            print("INFO RAG_UTILS: Cliente Azure OpenAI inicializado e conectado com sucesso.")
        except Exception as me:
            print(f"AVISO RAG_UTILS: Cliente Azure OpenAI inicializado, mas teste de listagem de modelos falhou: {me}.")
        return client
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS: Falha ao inicializar cliente Azure OpenAI: {traceback.format_exc()}");
        st.error(f"Falha OpenAI: {e}");
        return None

@st.cache_resource
def get_azure_search_client(index_name: str = DEFAULT_AZURE_SEARCH_INDEX_NAME):
    print(f"INFO RAG_UTILS: Inicializando cliente Azure AI Search para o índice '{index_name}'...")
    if not all([AZURE_SEARCH_ENDPOINT, index_name, AZURE_SEARCH_KEY]):
        print("ERRO RAG_UTILS: Configurações do Azure AI Search incompletas.");
        st.error("ERRO: Configs AI Search.")
        return None
    try:
        search_credential = AzureKeyCredential(AZURE_SEARCH_KEY)
        search_client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=index_name, credential=search_credential)
        try:
            index_admin_client = SearchIndexClient(endpoint=AZURE_SEARCH_ENDPOINT, credential=search_credential) # type: ignore
            idx_properties = index_admin_client.get_index(index_name)
            semantic_config_name_to_log = "Nenhuma"
            if idx_properties and idx_properties.semantic_search and idx_properties.semantic_search.configurations: # type: ignore
                 semantic_config_name_to_log = f"'{idx_properties.semantic_search.configurations[0].name}'" # type: ignore
            print(f"INFO RAG_UTILS: Conexão ao índice '{index_name}' estabelecida. Configuração semântica principal: {semantic_config_name_to_log}.")
            print(f"INFO RAG_UTILS: Contagem atual de documentos no índice '{index_name}': {search_client.get_document_count()}")
        except Exception as se_test:
            print(f"AVISO RAG_UTILS: Falha ao obter detalhes do índice '{index_name}' ou contagem de documentos: {se_test}.");
        return search_client
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS: Falha ao inicializar Azure AI Search Client: {traceback.format_exc()}");
        st.error(f"Falha Azure AI Search: {e}");
        return None

def call_google_custom_search(query: str, num_results: int = 3) -> list:
    if not GOOGLE_API_KEY:
        print("ALERTA RAG_UTILS: GOOGLE_API_KEY não configurada.")
        return []
    if not GOOGLE_CX_ID:
        print("ALERTA RAG_UTILS: GOOGLE_CX_ID não configurado.")
        return []
    print(f"INFO RAG_UTILS: Realizando Google Custom Search para: '{query}' (solicitando {num_results} resultados).")
    try:
        url = f"https://www.googleapis.com/customsearch/v1?key={GOOGLE_API_KEY}&cx={GOOGLE_CX_ID}&q={query}&num={num_results}&hl=pt-BR"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        search_results = response.json()
        formatted_results = []
        if "items" in search_results:
            for item in search_results.get("items", []):
                title = item.get("title")
                link = item.get("link")
                snippet = item.get("snippet", item.get("htmlSnippet"))
                if snippet:
                    snippet = re.sub('<[^<]+?>', '', snippet).strip()
                    snippet = re.sub('\s+', ' ', snippet)
                formatted_results.append({"title": title, "link": link, "snippet": snippet})
        print(f"INFO RAG_UTILS: Google Search para '{query}' retornou {len(formatted_results)} resultados.")
        return formatted_results
    except requests.exceptions.Timeout:
        print(f"ERRO RAG_UTILS: Timeout ao chamar Google Custom Search API para query: {query}")
    except requests.exceptions.HTTPError as e_http:
        print(f"ERRO RAG_UTILS: Erro HTTP ({e_http.response.status_code}) ao chamar Google Custom Search API: {e_http}. Resposta: {e_http.response.text if e_http.response else 'N/A'}")
    except requests.exceptions.RequestException as e_req:
        print(f"ERRO RAG_UTILS: Falha na requisição ao Google Custom Search API: {e_req}")
    except json.JSONDecodeError as e_json_decode:
        print(f"ERRO RAG_UTILS: Falha ao decodificar resposta JSON do Google Custom Search. Erro: {e_json_decode}. Resposta: {response.text if 'response' in locals() and hasattr(response, 'text') else 'N/A'}")
    except Exception as e_generic:
        print(f"ERRO RAG_UTILS: Erro inesperado no call_google_custom_search: {e_generic}\n{traceback.format_exc()}")
    return []

# --- CORREÇÃO DO NOME DA FUNÇÃO ---
def should_trigger_google_search(user_instruction: str, azure_search_results: list, min_azure_results_threshold: int = 1) -> bool:
    palavras_chave_busca_web = [
        "pesquise na web", "busque na internet", "notícias recentes sobre",
        "informações atuais sobre", "google por", "qual a cotação atual",
        "dados atualizados de", "legislação mais recente sobre", "jurisprudência recente sobre"
    ]
    if any(keyword.lower() in user_instruction.lower() for keyword in palavras_chave_busca_web):
        print("INFO RAG_UTILS: Busca no Google acionada por palavra-chave explícita na instrução do usuário.")
        return True
    if not azure_search_results or len(azure_search_results) < min_azure_results_threshold:
        print(f"INFO RAG_UTILS: Busca no Google acionada por resultados insuficientes do Azure AI Search (encontrados: {len(azure_search_results)}, mínimo desejado: {min_azure_results_threshold}).")
        return True
    return False

def formatar_google_results_para_llm(google_results: list) -> str:
    if not google_results:
        return "\n\n--- CONTEXTO DA BUSCA NA WEB (Google) ---\nNenhuma informação adicional encontrada na busca web para esta consulta.\n--- FIM DO CONTEXTO DA BUSCA NA WEB ---\n"
    context = "\n\n--- INÍCIO DO CONTEXTO DA BUSCA NA WEB (Google) ---\n"
    context += "As seguintes informações foram recuperadas da internet:\n"
    for i, res in enumerate(google_results):
        context += f"\n[WEB {i+1}: {res.get('title', 'N/A')}] (Link: {res.get('link', 'N/A')})\nSnippet: {res.get('snippet', 'N/A')}\n"
    context += "--- FIM DO CONTEXTO DA BUSCA NA WEB (Google) ---\n"
    return context

def get_embedding(text_chunk: str, client_openai: AzureOpenAI, deployment_name: str = AZURE_OPENAI_DEPLOYMENT_EMBEDDING):
    if not text_chunk or client_openai is None:
        print("AVISO RAG_UTILS: Texto ou cliente OpenAI não fornecido para get_embedding.")
        return None
    try:
        processed_chunk = ' '.join(text_chunk.replace('\n', ' ').split())
        if not processed_chunk:
            print("  AVISO RAG_UTILS: Chunk vazio após processamento, não será gerado embedding.")
            return None
        response = client_openai.embeddings.create(input=[processed_chunk], model=deployment_name)
        return response.data[0].embedding
    except Exception as e:
        print(f"  ERRO RAG_UTILS: Falha em get_embedding para chunk '{processed_chunk[:50]}...': {e}\n{traceback.format_exc()}")
        return None

def expand_query_with_llm(
    original_query: str,
    client_openai: AzureOpenAI,
    azure_openai_deployment: str = AZURE_OPENAI_DEPLOYMENT_LLM
) -> str:
    if not original_query.strip():
        print("AVISO RAG_UTILS (QueryExpansion): Query original vazia, retornando como está.")
        return original_query

    prompt_de_expansao = f"""Analise a seguinte pergunta de um usuário e gere uma consulta otimizada para uma base de dados jurídica.
Siga estas regras para gerar a "Consulta Otimizada":
1.  Se a pergunta do usuário for PRIMARIAMENTE sobre um precedente ou número de processo específico (ex: "do que trata o precedente X?", "qual a decisão no caso Y?", "detalhes sobre TST-Ag-E-ED-RR-1002446-80.2016.5.02.0433"), a "Consulta Otimizada" DEVE ser APENAS o número exato do precedente/processo entre aspas duplas.
    Exemplo:
    Pergunta do Usuário: "qual o resultado do TST-Ag-E-ED-RR-1002446-80.2016.5.02.0433?"
    Consulta Otimizada: "TST-Ag-E-ED-RR-1002446-80.2016.5.02.0433"
2.  Se a pergunta for mais geral, mas mencionar um precedente como parte de um contexto maior, extraia o precedente EXATAMENTE e identifique até 3 tópicos/palavras-chave principais da pergunta que descrevam o assunto jurídico. Nesse caso, a "Consulta Otimizada" deve ser: "[Número do Precedente Exato]" E ([Tópico 1] OU [Tópico 2])
    Exemplo:
    Pergunta do Usuário: "Gostaria de saber sobre a responsabilidade da empresa no fornecimento do perfil profissiográfico, citando o TST-Ag-E-ED-RR-1002446-80.2016.5.02.0433."
    Consulta Otimizada: "TST-Ag-E-ED-RR-1002446-80.2016.5.02.0433" E (responsabilidade empresa OU perfil profissiográfico)
3.  Se a pergunta NÃO mencionar um precedente específico, identifique 3-4 tópicos/palavras-chave principais e forme a "Consulta Otimizada" como: [Tópico 1] OU [Tópico 2] OU [Tópico 3]
    Exemplo:
    Pergunta do Usuário: "Quais os requisitos para aposentadoria especial por insalubridade?"
    Consulta Otimizada: requisitos aposentadoria especial OU insalubridade OU tempo de contribuição especial

Retorne APENAS a "Consulta Otimizada:", sem nenhuma outra explicação ou texto.

Pergunta do Usuário: "{original_query}"

Consulta Otimizada:"""

    try:
        print(f"INFO RAG_UTILS (QueryExpansion): Expandindo query original: '{original_query}'")
        response = client_openai.chat.completions.create(
            model=azure_openai_deployment,
            messages=[
                {"role": "system", "content": "Você é um assistente especialista em otimizar consultas de busca para sistemas jurídicos, focando em extrair termos precisos e precedentes e formatar a consulta de busca conforme as regras fornecidas."},
                {"role": "user", "content": prompt_de_expansao}
            ],
            temperature=0.0,
            max_tokens=250
        )
        expanded_query_text = response.choices[0].message.content.strip()

        if not expanded_query_text or expanded_query_text.lower() == "n/a" or len(expanded_query_text) < 3:
            print("AVISO RAG_UTILS (QueryExpansion): LLM não retornou uma consulta expandida útil ou muito curta, usando query original.")
            return original_query

        print(f"INFO RAG_UTILS (QueryExpansion): Query expandida/transformada para busca: '{expanded_query_text}'")
        return expanded_query_text

    except Exception as e:
        print(f"ERRO RAG_UTILS (QueryExpansion): Falha ao expandir query com LLM: {e}")
        traceback.print_exc()
        return original_query

def formatar_chunks_para_llm_azure(chunks_info_list: list, fonte_descricao: str = "Base de Conhecimento Interna (Azure AI Search)") -> str:
    context = f"\n\n--- INÍCIO DO CONTEXTO DE {fonte_descricao} ---\n"
    if not chunks_info_list:
        context += "Nenhum documento ou trecho relevante foi encontrado nesta fonte para a consulta atual.\n"
    else:
        for i, chunk_info in enumerate(chunks_info_list, 1):
            content = chunk_info.get('content', 'Conteúdo não disponível')
            source = chunk_info.get('arquivo_origem', 'Fonte desconhecida')
            tipo_doc = chunk_info.get('tipo_documento', 'N/A')
            score = chunk_info.get('score', None)
            reranker_score = chunk_info.get('reranker_score', None)
            score_info = []
            if score is not None: score_info.append(f"Score Busca: {score:.3f}")
            if reranker_score is not None: score_info.append(f"Score Semântico: {reranker_score:.3f}")
            score_str = f" ({', '.join(score_info)})" if score_info else ""
            context += f"\n[FONTE INTERNA {i}: {source} (Tipo: {tipo_doc}){score_str}]\n"
            if chunk_info.get("semantic_caption"):
                context += f"Destaque Semântico: {chunk_info['semantic_caption']}\n"
            context += f"Conteúdo do Trecho: {content}\n"
    context += f"--- FIM DO CONTEXTO DE {fonte_descricao} ---\n"
    return context

def find_relevant_chunks_azure_search(
    original_user_query: str,
    search_client: SearchClient,
    client_openai: AzureOpenAI,
    azure_openai_deployment_for_expansion: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k: int = 7,
    use_semantic_search: bool = True,
    semantic_config_name: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    query_language: str = "pt-BR",
    query_speller: str = "lexicon"
):
    if not original_user_query or search_client is None or client_openai is None:
        print("ALERTA RAG_UTILS: Parâmetros inválidos para find_relevant_chunks_azure_search.")
        if 'streamlit' in __import__('sys').modules:
             st.session_state.last_retrieved_chunks_details = []
        return []

    query_for_search = expand_query_with_llm(
        original_user_query,
        client_openai,
        azure_openai_deployment_for_expansion
    )

    query_embedding_vector = get_embedding(query_for_search, client_openai)

    vector_query = None
    if query_embedding_vector:
        vector_query = VectorizedQuery(
            vector=query_embedding_vector,
            k_nearest_neighbors=top_k,
            fields="content_vector",
            exhaustive=True
        )

    print(f"INFO RAG_UTILS: Buscando top_{top_k} chunks no Azure AI Search para QUERY PROCESSADA: '{query_for_search[:200]}...' | Semântica: {use_semantic_search}")
    try:
        fields_to_select = ["chunk_id", "document_id", "arquivo_origem", "content", "tipo_documento", "language_code"]
        search_args: dict[str, any] = {
            "vector_queries": [vector_query] if vector_query else None,
            "select": fields_to_select,
            "top": top_k,
            "include_total_count": True
        }
        search_text_for_azure = query_for_search

        if use_semantic_search:
            search_args.update({
                "search_text": search_text_for_azure,
                "query_type": QueryType.SEMANTIC,
                "semantic_configuration_name": semantic_config_name,
                "query_caption": "extractive",
                "query_answer": "extractive",
                "query_language": query_language,
                "query_speller": query_speller
            })
        elif vector_query and not search_text_for_azure.strip():
             search_args["search_text"] = None
        else:
            search_args["search_text"] = search_text_for_azure

        search_results_iterable = search_client.search(**search_args)
        retrieved_chunks_details = []

        print(f"\n--- DETALHES DOS CHUNKS RECUPERADOS DO AZURE AI SEARCH (Consulta Processada: '{query_for_search[:50]}...') ---")
        for i, doc_result in enumerate(search_results_iterable):
            chunk_detail = {
                "rank": i + 1,
                "chunk_id": doc_result.get("chunk_id", "N/A"),
                "document_id": doc_result.get("document_id", "N/A"),
                "arquivo_origem": doc_result.get("arquivo_origem", "N/A"),
                "tipo_documento": doc_result.get("tipo_documento", "N/A"),
                "score": doc_result.get("@search.score"),
                "reranker_score": doc_result.get("@search.reranker_score"),
                "content": doc_result.get("content", ""),
                "content_preview": doc_result.get("content", "")[:200] + "...",
                "semantic_caption": None,
            }
            if use_semantic_search and "@search.captions" in doc_result and doc_result["@search.captions"]:
                chunk_detail["semantic_caption"] = " ".join([c.text for c in doc_result["@search.captions"] if c.text]) # type: ignore
            retrieved_chunks_details.append(chunk_detail)
            print(f"  Chunk #{chunk_detail['rank']}: ID: {chunk_detail['chunk_id']}, Origem: {chunk_detail['arquivo_origem']}")
            print(f"    Score Busca: {chunk_detail['score']:.4f if chunk_detail['score'] else 'N/A'}")
            if chunk_detail['reranker_score'] is not None:
                print(f"    Score Reclassificação Semântica: {chunk_detail['reranker_score']:.4f}")
            if chunk_detail["semantic_caption"]:
                print(f"    Caption Semântico: '{chunk_detail['semantic_caption']}'")
            print("-" * 20)
        print(f"--- FIM DETALHES DOS CHUNKS (Azure AI Search) ---")

        total_count_val = 0
        if hasattr(search_results_iterable, 'get_count'):
            try:
                total_count_val = search_results_iterable.get_count()
            except Exception as e_count:
                print(f"AVISO RAG_UTILS: Não foi possível obter a contagem total exata dos resultados da busca. Erro: {e_count}")
                total_count_val = len(retrieved_chunks_details)
        else:
            total_count_val = len(retrieved_chunks_details)

        print(f"INFO RAG_UTILS: Encontrados {total_count_val} resultados no total (conforme reportado pela busca ou pelo top_k), retornando {len(retrieved_chunks_details)} chunks (limitado pelo top_k).")

        if 'streamlit' in __import__('sys').modules:
            st.session_state.last_retrieved_chunks_details = retrieved_chunks_details
        return retrieved_chunks_details
    except Exception as e:
        print(f"ERRO RAG_UTILS: Falha na pesquisa no Azure AI Search com query expandida: {e}\n{traceback.format_exc()}")
        if 'streamlit' in __import__('sys').modules:
            st.session_state.last_retrieved_chunks_details = []
        return []

def generate_response_with_conditional_google_search(
    system_message: str,
    user_instruction: str,
    context_document_text: str | None,
    search_client: SearchClient,
    client_openai: AzureOpenAI,
    azure_openai_deployment_llm: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    azure_openai_deployment_expansion: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k_azure: int = 7,
    use_semantic_search_azure: bool = True,
    semantic_config_name_azure: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    enable_google_search_fallback: bool = True,
    min_azure_results_for_fallback: int = 2,
    num_google_results: int = 3,
    temperature: float = 0.1,
    max_tokens: int = 4000
):
    print(f"INFO RAG_UTILS (CondSearch): Gerando resposta para instrução original: '{user_instruction[:100]}...'")
    retrieved_azure_chunks = find_relevant_chunks_azure_search(
        original_user_query=user_instruction,
        search_client=search_client,
        client_openai=client_openai,
        azure_openai_deployment_for_expansion=azure_openai_deployment_expansion,
        top_k=top_k_azure,
        use_semantic_search=use_semantic_search_azure,
        semantic_config_name=semantic_config_name_azure
    )
    context_from_azure_search = formatar_chunks_para_llm_azure(retrieved_azure_chunks)
    context_from_google_search = ""
    if GOOGLE_API_KEY and GOOGLE_CX_ID and \
       enable_google_search_fallback and \
       should_trigger_google_search(user_instruction, retrieved_azure_chunks, min_azure_results_for_fallback): # Nome da função corrigido
        print(f"INFO RAG_UTILS (CondSearch): Acionando Google Search com query original: '{user_instruction}'")
        google_search_results = call_google_custom_search(user_instruction, num_results=num_google_results)
        context_from_google_search = formatar_google_results_para_llm(google_search_results)
    combined_context = context_from_azure_search
    if context_from_google_search:
        combined_context += "\n" + context_from_google_search
    final_user_message = (
        f"{combined_context}\n\n"
        f"Considerando o CONTEXTO ADICIONAL RECUPERADO acima (que pode incluir Fontes Documentais Internas e/ou informações da web) e, PRINCIPALMENTE, o TEXTO COMPLETO DO DOCUMENTO FORNECIDO abaixo (se houver), "
        f"siga EXATAMENTE a seguinte instrução:\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"---\n**TEXTO COMPLETO DO DOCUMENTO FORNECIDO (do arquivo carregado):**\n---\n"
        f"{context_document_text if context_document_text else 'Nenhum documento principal foi fornecido para esta tarefa.'}\n"
        f"---\nFim do Documento Fornecido\n---"
    )
    messages = [{"role": "system", "content": system_message}, {"role": "user", "content": final_user_message}]
    print(f"INFO RAG_UTILS (CondSearch): Enviando requisição para Azure OpenAI (Modelo: {azure_openai_deployment_llm})...")
    try:
        response = client_openai.chat.completions.create(
            model=azure_openai_deployment_llm, messages=messages, temperature=temperature, max_tokens=max_tokens
        )
        generated_text = response.choices[0].message.content
        print("INFO RAG_UTILS (CondSearch): Resposta recebida do Azure OpenAI.")
        return generated_text
    except Exception as e:
        print(f"ERRO RAG_UTILS (CondSearch): Erro ao chamar Azure OpenAI: {e}\n{traceback.format_exc()}")
        return f"Erro ao gerar resposta: {e}"

google_search_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "google_custom_search_tool",
        "description": (
            "Realiza uma busca na internet usando o Google Custom Search para obter informações atuais, "
            "notícias, ou dados que não estão presentes no conhecimento interno ou nos documentos fornecidos. "
            "Use esta ferramenta quando a pergunta do usuário explicitamente pedir informações da web, "
            "ou quando você julgar que o conhecimento disponível é insuficiente ou desatualizado. "
            "Não use para consultas sobre o conteúdo específico de documentos já fornecidos."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "A consulta de busca precisa e concisa para o Google. Exemplo: 'últimas decisões STF sobre PIS/COFINS 2024'."
                },
                "num_results": {
                    "type": "integer",
                    "description": "Número de resultados de busca a serem retornados (entre 1 e 5). Padrão é 3.",
                    "default": 3
                }
            },
            "required": ["query"]
        }
    }
}
AVAILABLE_FUNCTIONS_MAP = {"google_custom_search_tool": call_google_custom_search}

def generate_response_with_function_calling(
    system_message: str, user_instruction: str, context_document_text: str | None,
    search_client: SearchClient, client_openai: AzureOpenAI,
    azure_openai_deployment_llm: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    azure_openai_deployment_expansion: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k_azure: int = 3, use_semantic_search_azure: bool = True,
    semantic_config_name_azure: str = AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    temperature: float = 0.1, max_tokens: int = 4000, max_function_calls: int = 2
):
    print(f"INFO RAG_UTILS (FuncCall): Gerando resposta para instrução original: '{user_instruction[:100]}...'")
    context_from_azure_search = ""
    if search_client:
        retrieved_azure_chunks = find_relevant_chunks_azure_search(
            original_user_query=user_instruction, search_client=search_client,
            client_openai=client_openai, azure_openai_deployment_for_expansion=azure_openai_deployment_expansion,
            top_k=top_k_azure, use_semantic_search=use_semantic_search_azure,
            semantic_config_name=semantic_config_name_azure
        )
        context_from_azure_search = formatar_chunks_para_llm_azure(retrieved_azure_chunks)
    initial_user_content = (
        f"{context_from_azure_search}\n\n"
        f"Considerando o CONTEXTO ADICIONAL RECUPERADO acima (se houver) e, PRINCIPALMENTE, o TEXTO COMPLETO DO DOCUMENTO FORNECIDO abaixo (se houver), "
        f"siga EXATAMENTE a seguinte instrução. Você pode usar ferramentas disponíveis se julgar necessário para obter informações mais atuais ou que não estão no contexto fornecido.\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"---\n**TEXTO COMPLETO DO DOCUMENTO FORNECIDO (do arquivo carregado):**\n---\n"
        f"{context_document_text if context_document_text else 'Nenhum documento principal foi fornecido para esta tarefa.'}\n"
        f"---\nFim do Documento Fornecido\n---"
    )
    messages = [{"role": "system", "content": system_message}, {"role": "user", "content": initial_user_content}]
    tools_param = [google_search_TOOL_DEFINITION] if (GOOGLE_API_KEY and GOOGLE_CX_ID) else None
    tool_choice_param: str | None = "auto" if tools_param else None

    for i in range(max_function_calls + 1):
        print(f"INFO RAG_UTILS (FuncCall): Iteração {i+1}. Enviando para Azure OpenAI (Modelo: {azure_openai_deployment_llm}). Tool choice: {tool_choice_param}")
        try:
            response = client_openai.chat.completions.create(
                model=azure_openai_deployment_llm, messages=messages,
                tools=tools_param if tool_choice_param == "auto" and tools_param else None, # type: ignore
                tool_choice=tool_choice_param if tool_choice_param == "auto" and tools_param else None, # type: ignore
                temperature=temperature, max_tokens=max_tokens
            )
        except Exception as e:
            print(f"ERRO RAG_UTILS (FuncCall): Erro ao chamar Azure OpenAI: {e}\n{traceback.format_exc()}")
            return f"Erro ao gerar resposta: {e}"
        response_message = response.choices[0].message
        messages.append(response_message) # type: ignore

        if response_message.tool_calls and tools_param:
            print(f"INFO RAG_UTILS (FuncCall): LLM solicitou chamada de ferramenta: {response_message.tool_calls[0].function.name}")
            for tool_call in response_message.tool_calls:
                function_name = tool_call.function.name
                function_to_call = AVAILABLE_FUNCTIONS_MAP.get(function_name)
                tool_response_content = f"Erro: Ferramenta '{function_name}' não encontrada ou não configurada corretamente."
                if function_to_call and GOOGLE_API_KEY and GOOGLE_CX_ID:
                    try:
                        function_args = json.loads(tool_call.function.arguments)
                        query_for_google_tool = function_args.get("query")
                        num_res = function_args.get("num_results", 3)
                        if query_for_google_tool:
                            function_response_data = function_to_call(query=query_for_google_tool, num_results=num_res)
                            if function_response_data:
                                tool_response_content = "Resultados da busca na web:\n"
                                for item_idx, item_data in enumerate(function_response_data):
                                    tool_response_content += f"- Título {item_idx+1}: {item_data.get('title', 'N/A')}\n  Snippet: {item_data.get('snippet', 'N/A')}\n  Link: {item_data.get('link', 'N/A')}\n"
                            else:
                                tool_response_content = "Nenhum resultado encontrado na busca web para esta consulta."
                        else:
                            tool_response_content = f"Erro: Query não fornecida para a ferramenta {function_name}."
                    except json.JSONDecodeError as e_json_args:
                        print(f"ERRO RAG_UTILS (FuncCall): Falha ao decodificar argumentos JSON para {function_name}: {e_json_args}")
                        tool_response_content = f"Erro nos argumentos da função {function_name}: {str(e_json_args)}"
                    except Exception as e_func:
                        print(f"ERRO RAG_UTILS (FuncCall): Erro ao executar {function_name}: {e_func}\n{traceback.format_exc()}")
                        tool_response_content = f"Erro ao executar a função {function_name}: {str(e_func)}"
                messages.append({ # type: ignore
                    "tool_call_id": tool_call.id, "role": "tool",
                    "name": function_name, "content": tool_response_content,
                })
        else:
            final_answer = response_message.content
            print("INFO RAG_UTILS (FuncCall): LLM gerou resposta final.")
            return str(final_answer) if final_answer is not None else "Erro: Resposta final nula."
    print("ALERTA RAG_UTILS (FuncCall): Máximo de chamadas de função atingido.")
    last_assistant_message_content = None
    for m in reversed(messages):
        if m.get("role") == "assistant" and m.get("content"): # type: ignore
            last_assistant_message_content = m.get("content") # type: ignore
            break
    return str(last_assistant_message_content) if last_assistant_message_content else "Não foi possível obter uma resposta final."

def gerar_docx(texto_markdown):
    print("INFO RAG_UTILS: Gerando arquivo DOCX com interpretação de Markdown...")
    try:
        document = DocxDocument()
        style = document.styles['Normal']
        if style and style.font: # type: ignore
            font = style.font # type: ignore
            font.name = 'Arial'
            font.size = Pt(11)
        if style and style.paragraph_format: # type: ignore
            paragraph_format = style.paragraph_format # type: ignore
            paragraph_format.space_before = Pt(0)
            paragraph_format.space_after = Pt(6)

        linhas = texto_markdown.split('\n')
        for linha_idx, linha_original in enumerate(linhas):
            paragrafo_docx = document.add_paragraph()
            linha_strip = linha_original.strip()
            match_heading = re.match(r'^(#{1,6})\s+(.*)', linha_strip)
            if match_heading:
                nivel = len(match_heading.group(1))
                texto_titulo = match_heading.group(2).strip()
                if texto_titulo.startswith('**') and texto_titulo.endswith('**') and len(texto_titulo) > 4:
                    texto_titulo = texto_titulo[2:-2]
                run = paragrafo_docx.add_run(texto_titulo)
                run.bold = True
                if nivel == 1: run.font.size = Pt(16)
                elif nivel == 2: run.font.size = Pt(14)
                elif nivel == 3: run.font.size = Pt(13)
                else: run.font.size = Pt(12)
                if paragrafo_docx.paragraph_format:
                    paragrafo_docx.paragraph_format.space_before = Pt(12) if nivel <= 2 else Pt(6)
                    paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue
            eh_titulo_linha_inteira_bold = linha_strip.startswith('**') and \
                                           linha_strip.endswith('**') and \
                                           len(linha_strip) > 4 and \
                                           linha_strip.count('**') == 2
            if eh_titulo_linha_inteira_bold:
                texto_do_titulo = linha_strip[2:-2]
                run = paragrafo_docx.add_run(texto_do_titulo)
                run.bold = True
                run.font.size = Pt(12)
                if paragrafo_docx.paragraph_format:
                    paragrafo_docx.paragraph_format.space_before = Pt(6)
                    paragrafo_docx.paragraph_format.space_after = Pt(6)
                continue
            if linha_strip:
                partes = re.split(r'(\*\*.+?\*\*)', linha_original)
                for parte_idx, parte in enumerate(partes):
                    if parte.startswith('**') and parte.endswith('**') and len(parte) > 4:
                        texto_do_negrito = parte[2:-2]
                        run_bold = paragrafo_docx.add_run(texto_do_negrito)
                        run_bold.bold = True
                    elif parte:
                        paragrafo_docx.add_run(parte)
            # else:
            #     pass # Linhas vazias no markdown resultam em parágrafos vazios no DOCX
        buffer = BytesIO()
        document.save(buffer)
        buffer.seek(0)
        print("INFO RAG_UTILS: Arquivo DOCX gerado com sucesso.")
        return buffer.getvalue()
    except Exception as e:
        print(f"ERRO RAG_UTILS: Falha ao gerar DOCX: {e}\n{traceback.format_exc()}")
        if 'streamlit' in __import__('sys').modules:
            st.error(f"Erro ao gerar arquivo DOCX: {e}")
        raise
import sys

def generate_response_with_rag(
    system_message, user_instruction, context_document_text,
    search_client, client_openai, top_k_chunks=7,
    use_semantic_search_in_rag=True
    ):
    print("AVISO RAG_UTILS: Chamando função de compatibilidade 'generate_response_with_rag'.")
    if client_openai is None or search_client is None:
        print("ERRO RAG_UTILS: Cliente OpenAI ou SearchClient não inicializado para generate_response_with_rag (compatibilidade).")
        return "Erro: Serviços de IA não configurados corretamente."

    return generate_response_with_conditional_google_search(
        system_message=system_message, user_instruction=user_instruction,
        context_document_text=context_document_text, search_client=search_client,
        client_openai=client_openai, azure_openai_deployment_llm=AZURE_OPENAI_DEPLOYMENT_LLM,
        azure_openai_deployment_expansion=AZURE_OPENAI_DEPLOYMENT_LLM,
        top_k_azure=top_k_chunks, use_semantic_search_azure=use_semantic_search_in_rag,
        semantic_config_name_azure=AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT,
    )

MAX_CHAT_HISTORY_MESSAGES = 10
def build_messages_for_llm_chat(system_message, chat_history, user_instruction_with_context):
    messages: list[dict[str,str]] = [{"role": "system", "content": system_message}]
    if chat_history:
        start_index = max(0, len(chat_history) - MAX_CHAT_HISTORY_MESSAGES)
        for msg_item in chat_history[start_index:]:
            if isinstance(msg_item, dict) and "role" in msg_item and "content" in msg_item:
                messages.append({"role": msg_item["role"], "content": msg_item["content"]})
            else:
                print(f"AVISO RAG_UTILS: Item de histórico de chat mal formatado ignorado: {msg_item}")
    messages.append({"role": "user", "content": user_instruction_with_context})
    return messages

def generate_consultor_response_with_rag(
    system_message: str, user_instruction: str, chat_history: list,
    search_client: SearchClient, client_openai: AzureOpenAI,
    azure_openai_deployment_llm: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    azure_openai_deployment_expansion: str = AZURE_OPENAI_DEPLOYMENT_LLM,
    top_k_chunks: int = 7, use_semantic_search_in_consultor: bool = True,
    enable_google_search: bool = True, min_azure_results_for_google: int = 1,
    num_google_results_consultor: int = 2
    ):
    print(f"INFO RAG_UTILS (Consultor): Gerando resposta para instrução original: '{user_instruction[:100]}...'")

    if client_openai is None or search_client is None:
        print("ERRO RAG_UTILS (Consultor): Cliente OpenAI ou SearchClient não inicializado.")
        return "Erro: Serviços de IA não configurados para o consultor."

    retrieved_azure_chunks = find_relevant_chunks_azure_search(
        original_user_query=user_instruction, search_client=search_client,
        client_openai=client_openai, azure_openai_deployment_for_expansion=azure_openai_deployment_expansion,
        top_k=top_k_chunks, use_semantic_search=use_semantic_search_in_consultor,
        semantic_config_name=AZURE_SEARCH_SEMANTIC_CONFIG_NAME_DEFAULT
    )
    if 'streamlit' in __import__('sys').modules:
        st.session_state.last_retrieved_chunks_details_consultor = retrieved_azure_chunks
    context_from_azure_search = formatar_chunks_para_llm_azure(
        retrieved_azure_chunks,
        fonte_descricao="Base de Conhecimento Jurídico Interna"
    )
    context_from_google_search = ""
    if GOOGLE_API_KEY and GOOGLE_CX_ID and \
       enable_google_search and \
       should_trigger_google_search(user_instruction, retrieved_azure_chunks, min_azure_results_for_google): # Nome da função corrigido
        google_search_results = call_google_custom_search(user_instruction, num_results=num_google_results_consultor)
        context_from_google_search = formatar_google_results_para_llm(google_search_results)
    combined_context_for_llm = context_from_azure_search
    if context_from_google_search:
        combined_context_for_llm += "\n" + context_from_google_search
    user_instruction_with_context_for_llm = (
        f"Pergunta do Utilizador: '{user_instruction}'\n\n"
        f"{combined_context_for_llm}\n\n"
        f"Com base no contexto acima (que pode incluir informações da base interna e/ou da web) e no seu conhecimento geral, por favor, responda à pergunta do utilizador de forma completa e didática, citando as fontes do contexto quando apropriado."
    )
    messages_for_llm = build_messages_for_llm_chat(
        system_message, chat_history, user_instruction_with_context_for_llm
    )
    final_response = "Desculpe, não consegui processar o seu pedido para o consultor neste momento."
    print(f"INFO RAG_UTILS (Consultor): Enviando para LLM (Modelo: {azure_openai_deployment_llm}) com {len(messages_for_llm)} mensagens.")
    try:
        response = client_openai.chat.completions.create(
            model=azure_openai_deployment_llm, messages=messages_for_llm,
            temperature=0.5, max_tokens=2000, top_p=0.95,
        )
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            final_response = response.choices[0].message.content.strip()
        else:
            print("ERRO RAG_UTILS (Consultor): Resposta da API LLM inválida.")
    except Exception as e:
        print(f"ERRO CRÍTICO RAG_UTILS (Consultor): Falha chat.completions: {e}\n{traceback.format_exc()}")
        final_response = f"Erro ao gerar resposta do consultor. Tente novamente mais tarde."
    return final_response

print("INFO RAG_UTILS: Módulo `rag_utils.py` carregado (versão com correções de sintaxe, SEM CrewAI).")
