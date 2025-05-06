# ingest_data.py
import os
import uuid # Para gerar IDs únicos
# Importe suas funções de extração de texto, por exemplo:
from app import extract_text_from_pdf # Assumindo que as funções estão em app.py
from app import extract_text_from_docx # Assumindo que as funções estão em app.py
# Se as funções estiverem em outro lugar ou em utils, ajuste os imports
import rag_utils # Importa seu módulo de utilidades RAG
from tqdm.auto import tqdm # Para mostrar barra de progresso (instale: pip install tqdm)
import time
from openai import AzureOpenAI
from pinecone import Pinecone


# --- Configurações ---
DATA_DIR = "./documentos_juridicos" # Pasta onde seus documentos estão salvos
# Tamanho do chunk e sobreposição (ajuste conforme seu tipo de documento)
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
# Tamanho do lote (batch) para upsert no Pinecone (ajuste conforme sua conexão e limites)
UPSERT_BATCH_SIZE = 100

# --- Inicializa Clientes (sem cache, pois é um script de ingestão único) ---
# Use as configurações definidas em rag_utils
PINECONE_API_KEY = rag_utils.PINECONE_API_KEY
PINECONE_INDEX_NAME = rag_utils.PINECONE_INDEX_NAME
AZURE_OPENAI_ENDPOINT = rag_utils.AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY = rag_utils.AZURE_OPENAI_API_KEY
AZURE_API_VERSION = rag_utils.AZURE_API_VERSION
AZURE_OPENAI_DEPLOYMENT_EMBEDDING = rag_utils.AZURE_OPENAI_DEPLOYMENT_EMBEDDING


# Função para inicializar o cliente OpenAI (sem cache)
def get_openai_client_ingestion():
     print("INFO: Inicializando cliente Azure OpenAI para ingestão...")
     try:
        client = AzureOpenAI(
            api_version=AZURE_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY,
        )
        # Opcional: Testar conexão
        # client.models.list()
        print("INFO: Cliente Azure OpenAI inicializado com sucesso para ingestão.")
        return client
     except Exception as e:
         print(f"ERRO: Falha ao inicializar cliente Azure OpenAI para ingestão: {e}")
         return None

# Função para inicializar o índice Pinecone (sem cache)
def get_pinecone_index_ingestion():
    print("INFO: Inicializando conexão com Pinecone para ingestão...")
    try:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        # Verifica se o índice existe (usando a lógica corrigida)
        index_list_object = pc.list_indexes()
        index_names = []
        if hasattr(index_list_object, 'names') and callable(index_list_object.names):
             index_names = index_list_object.names()
        elif isinstance(index_list_object, list):
             index_names = [index_info.get('name') for index_info in index_list_object if isinstance(index_info, dict) and 'name' in index_info]

        if PINECONE_INDEX_NAME not in index_names:
             print(f"ERRO: Índice Pinecone '{PINECONE_INDEX_NAME}' não encontrado. Índices disponíveis: {', '.join(index_names) if index_names else 'Nenhum'}. Crie o índice primeiro.")
             return None

        index = pc.Index(PINECONE_INDEX_NAME)
        # Opcional: Testar conexão
        # index.describe_index_stats()
        print(f"INFO: Conexão com índice Pinecone '{PINECONE_INDEX_NAME}' estabelecida com sucesso para ingestão.")
        return index
    except Exception as e:
        print(f"ERRO: Falha ao conectar ao Pinecone para ingestão: {e}")
        return None


# Função simples para dividir texto em chunks (pode precisar de otimização)
def chunk_text(text, chunk_size, chunk_overlap):
    chunks = []
    if not text:
        return chunks
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:min(end, len(text))]
        chunks.append(chunk)
        if end >= len(text):
            break
        start += chunk_size - chunk_overlap
    return chunks

# --- Processo Principal de Ingestão ---
def ingest_documents():
    client_openai = get_openai_client_ingestion()
    pinecone_index = get_pinecone_index_ingestion()

    if client_openai is None or pinecone_index is None:
        print("Erro: Clientes não inicializados. Abortando ingestão.")
        return

    if not os.path.exists(DATA_DIR):
        print(f"Erro: Diretório de dados '{DATA_DIR}' não encontrado.")
        return

    document_files = [f for f in os.listdir(DATA_DIR) if f.endswith(('.pdf', '.docx'))]

    if not document_files:
        print(f"Nenhum arquivo PDF ou DOCX encontrado no diretório '{DATA_DIR}'.")
        return

    print(f"\n--- Iniciando processo de ingestão de {len(document_files)} documentos ---")

    total_chunks_processed = 0
    vectors_to_upsert = []

    for filename in tqdm(document_files, desc="Processando documentos"):
        filepath = os.path.join(DATA_DIR, filename)
        text = ""

        print(f"\nProcessando arquivo: {filename}")
        try:
            if filename.endswith(".pdf"):
                with open(filepath, "rb") as f:
                    text = extract_text_from_pdf(f.read())
            elif filename.endswith(".docx"):
                 with open(filepath, "rb") as f:
                    text = extract_text_from_docx(f.read())

            if not text:
                print(f"Aviso: Não foi possível extrair texto ou arquivo vazio: {filename}")
                continue # Pula para o próximo arquivo

            # Dividir texto em chunks
            chunks = chunk_text(text, CHUNK_SIZE, CHUNK_OVERLAP)
            print(f"Arquivo dividido em {len(chunks)} chunks.")

            for i, chunk in enumerate(chunks):
                # Gerar embedding para o chunk
                embedding = rag_utils.get_embedding(chunk, client_openai) # Reutiliza sua função de embedding

                if embedding is not None:
                    # Preparar dados para o upsert
                    vector_id = str(uuid.uuid4()) # ID único para cada chunk
                    metadata = {
                        "source_file": filename,
                        "chunk_index": i,
                        "text": chunk # Armazena o texto original do chunk nos metadados
                        # Você pode adicionar outros metadados aqui (ex: numero da página, título, etc.)
                    }
                    vectors_to_upsert.append((vector_id, embedding, metadata))
                    total_chunks_processed += 1

                    # Upsert em lotes
                    if len(vectors_to_upsert) >= UPSERT_BATCH_SIZE:
                        print(f"Upserting batch de {len(vectors_to_upsert)} vetores...")
                        try:
                            pinecone_index.upsert(vectors=vectors_to_upsert)
                            print("Batch upserted com sucesso.")
                            vectors_to_upsert = [] # Limpa o lote
                        except Exception as upsert_error:
                            print(f"ERRO ao upsert batch: {upsert_error}")
                            # Implementar retry aqui se necessário

                else:
                     print(f"Aviso: Falha ao gerar embedding para o chunk {i} do arquivo {filename}. Pulando chunk.")


        except Exception as e:
            print(f"ERRO geral ao processar arquivo {filename}: {e}")
            continue # Continua processando outros arquivos mesmo com erro em um


    # Upsert de quaisquer vetores restantes no último lote
    if vectors_to_upsert:
        print(f"\nUpserting lote final de {len(vectors_to_upsert)} vetores...")
        try:
            pinecone_index.upsert(vectors=vectors_to_upsert)
            print("Lote final upserted com sucesso.")
        except Exception as upsert_error:
             print(f"ERRO ao upsert lote final: {upsert_error}")

    print(f"\n--- Processo de ingestão finalizado ---")
    print(f"Total de chunks processados e tentados upsert: {total_chunks_processed}")
    # Nota: O número de registros no Pinecone pode ser ligeiramente diferente devido a falhas de upsert ou processamento interno do Pinecone.

if __name__ == "__main__":
    # Crie a pasta para seus documentos se ela não existir
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        print(f"Diretório '{DATA_DIR}' criado. Coloque seus arquivos PDF e DOCX aqui.")
    else:
        ingest_documents()