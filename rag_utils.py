# rag_utils.py
import streamlit as st
from openai import AzureOpenAI
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
import os
import time # Mantido, pode ser útil para debugging ou futuras expansões
import uuid # Mantido, pode ser útil para futuras expansões
import traceback
import re # Para processar Markdown

from io import BytesIO
from docx import Document as DocxDocument
from docx.shared import Pt
from docx.enum.text import WD_LINE_SPACING

# --- Configurações (Suas Chaves e Endpoints - COMO NO SEU ARQUIVO ORIGINAL) ---
AZURE_OPENAI_ENDPOINT = 'https://lexautomate.openai.azure.com/'
AZURE_OPENAI_API_KEY = '6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA' # SUA CHAVE REAL
AZURE_OPENAI_DEPLOYMENT_LLM = 'lexautomate_agent'
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = 'text-embedding-3-large'
AZURE_API_VERSION = '2024-02-15-preview'

AZURE_SEARCH_ENDPOINT = "https://lexautomate-rag2.search.windows.net"
AZURE_SEARCH_KEY = "igJqXTXsYEC6gpIzFvjOvjm0WtSgd0Xrw8TNMDkwK9AzSeC5ft3H" # SUA CHAVE REAL
AZURE_SEARCH_INDEX_NAME = "docs-index"

DOCINTEL_ENDPOINT = "https://lexautomate-orc.cognitiveservices.azure.com/"
DOCINTEL_KEY = "FtqfVcECaQkohYtXfqvJYP2ttF2lx9fR9eyn13Yjww2n5Az9iVGTJQQJ99BEACYeBjFXJ3w3AAALACOGcxBe" # SUA CHAVE REAL

# --- Inicialização dos Clientes (COMO NO SEU ARQUIVO ORIGINAL) ---
@st.cache_resource
def get_openai_client():
    print("INFO: Inicializando cliente Azure OpenAI...")
    if not all([AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_API_VERSION, AZURE_OPENAI_DEPLOYMENT_LLM, AZURE_OPENAI_DEPLOYMENT_EMBEDDING]):
         print("ERRO: Configurações OpenAI incompletas."); st.error("ERRO: Configs OpenAI.")
         return None
    try:
        client = AzureOpenAI(api_version=AZURE_API_VERSION, azure_endpoint=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_API_KEY)
        try: client.models.list(); print("INFO: Cliente OpenAI OK.")
        except Exception as me: print(f"AVISO: OpenAI OK, mas listar modelos falhou: {me}.")
        return client
    except Exception as e: print(f"ERRO CRÍTICO OpenAI: {traceback.format_exc()}"); st.error(f"Falha OpenAI: {e}"); return None

@st.cache_resource
def get_azure_search_client():
    print("INFO: Inicializando cliente Azure AI Search...")
    if not all([AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_INDEX_NAME, AZURE_SEARCH_KEY]):
        print("ERRO: Configs AI Search incompletas."); st.error("ERRO: Configs AI Search.")
        return None
    try:
        client = SearchClient(endpoint=AZURE_SEARCH_ENDPOINT, index_name=AZURE_SEARCH_INDEX_NAME, credential=AzureKeyCredential(AZURE_SEARCH_KEY))
        try: client.get_document_count(); print(f"INFO: Conexão índice '{AZURE_SEARCH_INDEX_NAME}' OK.")
        except Exception as se: print(f"ERRO: Falha índice: {traceback.format_exc()}"); st.error(f"Falha índice '{AZURE_SEARCH_INDEX_NAME}': {se}"); return None
        return client
    except Exception as e: print(f"ERRO CRÍTICO AI Search: {traceback.format_exc()}"); st.error(f"Falha AI Search: {e}"); return None

@st.cache_resource
def get_docintel_client():
    print("INFO: Inicializando cliente Document Intelligence...")
    if not all([DOCINTEL_ENDPOINT, DOCINTEL_KEY]):
         print("ERRO: Configs Document Intelligence incompletas."); st.error("ERRO: Configs Doc Intel.")
         return None
    try:
        client = DocumentAnalysisClient(endpoint=DOCINTEL_ENDPOINT, credential=AzureKeyCredential(DOCINTEL_KEY))
        print("INFO: Cliente Document Intelligence OK.")
        return client
    except NameError: print("ERRO CRÍTICO: 'azure-ai-formrecognizer' não instalada."); st.error("Erro: 'azure-ai-formrecognizer' não instalada."); return None
    except Exception as e: print(f"ERRO CRÍTICO Doc Intel: {traceback.format_exc()}"); st.error(f"Falha Doc Intel: {e}"); return None


# --- Funções Auxiliares RAG (COMO NO SEU ARQUIVO ORIGINAL) ---
def chunk_text(text, max_chunk_size=1000, chunk_overlap=100):
    if not text: return []
    chunks = []; start = 0
    while start < len(text):
        end = start + max_chunk_size; chunks.append(text[start:end].strip())
        next_start = start + max_chunk_size - chunk_overlap
        if next_start <= start: start += 1
        else: start = next_start
    return [c for c in chunks if c]

def get_embedding(text_chunk, client_openai):
    if not text_chunk or client_openai is None: return None
    try:
        processed_chunk = ' '.join(text_chunk.replace('\n', ' ').split())
        if not processed_chunk: return None # Retorna None se o chunk ficar vazio após o processamento
        response = client_openai.embeddings.create(input=processed_chunk, model=AZURE_OPENAI_DEPLOYMENT_EMBEDDING)
        return response.data[0].embedding
    except Exception as e: print(f"ERRO: Falha get_embedding: {traceback.format_exc()}"); st.error(f"Erro API Embedding: {e}"); return None

def find_relevant_chunks_azure_search(query_text, search_client, client_openai, top_k=5):
    if not query_text or search_client is None or client_openai is None: return []
    query_embedding = get_embedding(query_text, client_openai)
    if query_embedding is None: return [] # Não prossegue se não houver embedding
    print(f"INFO: Buscando top_{top_k} chunks para a query: '{query_text[:100]}...'")
    try:
        vectorized_query = VectorizedQuery(vector=query_embedding, k_nearest_neighbors=top_k, fields="content_vector")
        results = search_client.search(search_text=None, vector_queries=[vectorized_query], select=["id", "content", "arquivo"], top=top_k)
        relevant_texts = [doc["content"] for doc in results if doc.get("content")]
        print(f"INFO: Encontrados {len(relevant_texts)} chunks.")
        return relevant_texts
    except Exception as e: print(f"ERRO: Falha busca vetorial: {traceback.format_exc()}"); st.error(f"Erro busca vetorial: {e}"); return []

# --- Função Principal RAG (COMO NO SEU ARQUIVO ORIGINAL) ---
def generate_response_with_rag(system_message, user_instruction, context_document_text, search_client, client_openai, top_k_chunks=5):
    if client_openai is None or search_client is None:
         st.error("Erro interno: Clientes IA não disponíveis."); return "Erro interno nos serviços de IA."
    retrieved_chunks = []
    with st.spinner(f"Consultando base ({AZURE_SEARCH_INDEX_NAME})..."): # Spinner na UI é melhor, mas mantendo consistência
        retrieved_chunks = find_relevant_chunks_azure_search(user_instruction, search_client, client_openai, top_k=top_k_chunks)
    context_string = "" # Nome da variável alterado para evitar conflito com 'context_string_from_search' nas novas funções
    if retrieved_chunks:
        context_string = "---\n**Contexto Recuperado da Base de Conhecimento Jurídico:**\n---\n"
        for i, chunk in enumerate(retrieved_chunks, 1): context_string += f"**Contexto {i}:**\n{chunk}\n\n"
        context_string += "---\nFim do Contexto Recuperado\n---"
    else:
        context_string = "\n(Nenhum contexto específico foi recuperado da base de conhecimento para esta consulta.)\n"
    final_user_message = (
        f"{context_string}\n\n"
        f"Considerando o CONTEXTO RECUPERADO acima e, PRINCIPALMENTE, o TEXTO COMPLETO DO DOCUMENTO FORNECIDO abaixo, "
        f"siga EXATAMENTE a seguinte instrução:\n\n"
        f"Instrução do Usuário: '{user_instruction}'\n\n"
        f"---\n**TEXTO COMPLETO DO DOCUMENTO FORNECIDO (do arquivo carregado):**\n---\n"
        f"{context_document_text if context_document_text else 'Nenhum documento foi carregado ou o texto não pôde ser extraído.'}\n"
        f"---\nFim do Documento Fornecido\n---"
    )
    final_response = "Erro: Falha ao gerar resposta."
    with st.spinner(f"Gerando resposta com IA ({AZURE_OPENAI_DEPLOYMENT_LLM})..."): # Spinner na UI é melhor
        try:
            response = client_openai.chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT_LLM,
                messages=[ {"role": "system", "content": system_message}, {"role": "user", "content": final_user_message} ],
                temperature=0.1, max_tokens=4000, top_p=0.9,
            )
            if response.choices and response.choices[0].message and response.choices[0].message.content:
                final_response = response.choices[0].message.content.strip()
            else: st.error("Erro: Resposta API LLM inválida."); final_response = "Erro: Resposta IA vazia."
        except Exception as e: print(f"ERRO CRÍTICO: Falha chat.completions: {traceback.format_exc()}"); st.error(f"Erro LLM: {e}"); final_response = f"Erro ao gerar resposta."
    return final_response

# --- INÍCIO: Novas Funções para o App4 (Consultor Jurídico / Chat RAG) ---

MAX_CHAT_HISTORY_MESSAGES = 10 # Exemplo: manter as últimas 5 trocas (usuário + assistente)

def build_messages_for_llm_chat(system_message, chat_history, user_instruction_with_context):
    """
    Constrói a lista de mensagens para o LLM para o modo chat,
    incluindo o system prompt, um histórico limitado e a pergunta atual com contexto RAG.
    """
    messages = [{"role": "system", "content": system_message}]
    if chat_history:
        start_index = max(0, len(chat_history) - MAX_CHAT_HISTORY_MESSAGES)
        for msg in chat_history[start_index:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_instruction_with_context})
    return messages

def generate_consultor_response_with_rag(system_message, user_instruction, chat_history, search_client, client_openai, top_k_chunks=3):
    """
    Gera uma resposta para o chat do Consultor Jurídico usando RAG sobre a base de conhecimento.
    """
    if client_openai is None or search_client is None:
        print("ERRO (Consultor): Clientes OpenAI ou Search não disponíveis.")
        # Não use st.error() aqui, pois esta função pode ser chamada de um contexto não-Streamlit.
        return "Desculpe, estou com problemas para acessar meus serviços de IA no momento."

    retrieved_chunks = []
    query_for_search = user_instruction
    
    print(f"INFO (Consultor): Buscando na base com query: '{query_for_search[:100]}...'")
    # O spinner é melhor tratado na UI (app4.py)
    retrieved_chunks = find_relevant_chunks_azure_search(query_for_search, search_client, client_openai, top_k=top_k_chunks)

    context_string_from_search = ""
    if retrieved_chunks:
        context_string_from_search = "---\n**Contexto Relevante da Base de Conhecimento Encontrado:**\n---\n"
        for i, chunk in enumerate(retrieved_chunks, 1):
            context_string_from_search += f"**Referência {i}:**\n{chunk}\n\n"
        context_string_from_search += "---\nFim do Contexto Relevante\n---"
    else:
        context_string_from_search = "\n(Para esta pergunta específica, não encontrei informações diretamente relevantes na minha base de conhecimento atual.)\n"

    user_instruction_with_context_for_llm = (
        f"Pergunta do Usuário: '{user_instruction}'\n\n"
        f"{context_string_from_search}\n\n"
        f"Com base no contexto acima e em seu conhecimento geral, por favor, responda à pergunta do usuário de forma completa e didática."
    )

    messages_for_llm = build_messages_for_llm_chat(
        system_message,
        chat_history, # Passa o histórico como está
        user_instruction_with_context_for_llm
    )
    
    final_response = "Desculpe, não consegui processar sua solicitação para o consultor no momento."
    print(f"INFO (Consultor): Enviando para LLM ({AZURE_OPENAI_DEPLOYMENT_LLM}) com {len(messages_for_llm)} mensagens.")
    # O spinner é melhor tratado na UI (app4.py)
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
            # st.error() não deve ser usado aqui
    except Exception as e:
        print(f"ERRO CRÍTICO (Consultor): Falha chat.completions: {traceback.format_exc()}")
        final_response = f"Erro ao gerar resposta do consultor. Tente novamente mais tarde." # Mensagem genérica
    return final_response

# --- FIM: Novas Funções para o App4 ---


# --- Função de Exportação DOCX (COMO NO SEU ARQUIVO ORIGINAL) ---
def gerar_docx(texto_markdown):
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
                partes = re.split(r'(\*\*.+?\*\*)', linha_original) # Corrigido regex para negrito
                for parte in partes:
                    if parte.startswith('**') and parte.endswith('**') and len(parte) > 4:
                        texto_do_negrito = parte[2:-2]
                        run = paragrafo_docx.add_run(texto_do_negrito)
                        run.bold = True
                    elif parte:
                        paragrafo_docx.add_run(parte)
            else: 
                # Linha vazia, pode adicionar um pouco mais de espaço se não for precedida por um título
                # Isso ajuda a simular parágrafos separados por linhas em branco no Markdown
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
        st.error(f"Erro ao gerar arquivo DOCX: {e}") # st.error pode ficar aqui, pois gerar_docx é chamado da UI.
        raise

# --- FIM do rag_utils.py ---