# db_utils.py
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
import streamlit as st # Usado para cache_resource. Avisos em scripts CLI são normais.
import datetime 
import json

@st.cache_resource
def get_mongodb_client():
    """
    Inicializa e retorna uma instância do cliente MongoDB, utilizando cache do Streamlit.
    """
    mongo_uri = "mongodb+srv://thiagoazro:FqBdZcF7vtiZXOwl@cluster0.8fmcx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    if not mongo_uri:
        print("ERRO DB_UTILS: Variável de ambiente MONGODB_URI não configurada. Verifique os segredos do Streamlit ou seu arquivo .env.")
        # Comentado para evitar erros em scripts CLI sem contexto Streamlit
        # st.error("Erro: A URI de conexão com o MongoDB não foi configurada. Verifique suas variáveis de ambiente/secrets.")
        return None
    try:
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) # Timeout de 5 segundos
        client.admin.command('ping') # Testa a conexão
        print("INFO DB_UTILS: Conexão com MongoDB estabelecida com sucesso.")
        return client
    except ConnectionFailure as e:
        print(f"ERRO DB_UTILS: Falha na conexão com MongoDB: {e}. Verifique a URI e o status do servidor.")
        return None
    except Exception as e:
        print(f"ERRO DB_UTILS: Erro inesperado ao conectar ao MongoDB: {e}")
        return None

def get_modelos_collection():
    """
    Retorna a coleção de modelos de peças, conforme configurado em MONGODB_COLLECTION_MODELOS.
    """
    client = get_mongodb_client()
    if client is None:
        return None
    
    db_name = "lexautomate"
    collection_name = "modelos_pecas"
    
    return client[db_name][collection_name]

# Decorador st.cache_data é para o app Streamlit principal.
# Em scripts CLI, ele pode apenas adicionar avisos, mas não impede a execução.
@st.cache_data(ttl=3600) # Cachear dados por 1 hora
def carregar_modelos_pecas_from_mongodb() -> dict:
    """
    Carrega os modelos de peças do MongoDB e os formata no dicionário aninhado esperado
    pela interface do app5.py.
    """
    modelos_collection = get_modelos_collection()
    if modelos_collection is None:
        print("AVISO DB_UTILS: Coleção de modelos não disponível para carregamento.")
        return {}
    
    modelos_data = {}
    try:
        for doc in modelos_collection.find({}):
            area = doc.get("area_direito")
            tipo_peca = doc.get("tipo_peca")
            nome_modelo = doc.get("nome_modelo")

            if area and tipo_peca and nome_modelo:
                if area not in modelos_data:
                    modelos_data[area] = {}
                if tipo_peca not in modelos_data[area]:
                    modelos_data[area][tipo_peca] = {}
                
                modelos_data[area][tipo_peca][nome_modelo] = {
                    "descricao": doc.get("descricao", "Sem descrição."),
                    "reivindicacoes_comuns": doc.get("reivindicacoes_comuns", []),
                    "prompt_template": doc.get("prompt_template", ""),
                    "tags": doc.get("tags", []),
                    "legislacao_relevante": doc.get("legislacao_relevante", []),
                    "jurisprudencia_exemplar": doc.get("jurisprudencia_exemplar", []),
                    "requisitos_especificos": doc.get("requisitos_especificos", ""),
                    "complexidade": doc.get("complexidade", "Não especificado"),
                    "autor_modelo": doc.get("autor_modelo", "Não especificado")
                }
        print(f"INFO DB_UTILS: {sum(len(v2) for v in modelos_data.values() for v2 in v.values())} modelos carregados do MongoDB.")
        return modelos_data
    except OperationFailure as e:
        print(f"ERRO DB_UTILS: Erro de operação ao consultar MongoDB: {e.details}")
        return {}
    except Exception as e:
        print(f"ERRO DB_UTILS: Erro inesperado ao carregar modelos do MongoDB: {e}")
        return {}

def inserir_modelo_peca(
    area: str,
    tipo_peca: str,
    nome_modelo: str,
    prompt_template: str,
    reivindicacoes_comuns: list,
    descricao: str = "",
    tags: list = None,
    legislacao_relevante: list = None,
    jurisprudencia_exemplar: list = None,
    requisitos_especificos: str = "",
    complexidade: str = "",
    autor_modelo: str = ""
):
    """
    Insere ou atualiza um modelo de peça no MongoDB com metadados estendidos.
    Usa update_one com upsert=True para ser idempotente (evita duplicatas).
    """
    modelos_collection = get_modelos_collection()
    if modelos_collection is None:
        print("ERRO DB_UTILS: Coleção de modelos não disponível para inserção.")
        return False
    
    # Garante que listas vazias não causem problemas com None
    if tags is None: tags = []
    if legislacao_relevante is None: legislacao_relevante = []
    if jurisprudencia_exemplar is None: jurisprudencia_exemplar = []

    try:
        modelo_doc = {
            "area_direito": area,
            "tipo_peca": tipo_peca,
            "nome_modelo": nome_modelo,
            "prompt_template": prompt_template,
            "reivindicacoes_comuns": reivindicacoes_comuns,
            "descricao": descricao,
            "tags": tags,
            "legislacao_relevante": legislacao_relevante,
            "jurisprudencia_exemplar": jurisprudencia_exemplar,
            "requisitos_especificos": requisitos_especificos,
            "complexidade": complexidade,
            "autor_modelo": autor_modelo,
            "data_atualizacao": datetime.datetime.now()
        }
        
        filter_query = {
            "area_direito": area,
            "tipo_peca": tipo_peca,
            "nome_modelo": nome_modelo
        }

        update_operation = {
            "$set": modelo_doc,
            "$setOnInsert": {"data_criacao": datetime.datetime.now()}
        }

        result = modelos_collection.update_one(filter_query, update_operation, upsert=True)
        
        if result.upserted_id:
            print(f"INFO DB_UTILS: Modelo '{nome_modelo}' inserido (novo documento) com ID: {result.upserted_id}")
        elif result.modified_count > 0:
            print(f"INFO DB_UTILS: Modelo '{nome_modelo}' atualizado (documento existente).")
        else:
            # Não é um erro, apenas não precisou de alteração, mas foi "processado"
            pass 
            # print(f"INFO DB_UTILS: Modelo '{nome_modelo}' já existe e não precisou de atualização.")

        # Limpa o cache para que a próxima leitura no app Streamlit pegue os dados atualizados
        # A verificação 'if in globals()' é para evitar erro se o script não for do Streamlit
        if 'carregar_modelos_pecas_from_mongodb' in globals(): 
            carregar_modelos_pecas_from_mongodb.clear() 
        return True
    except ConnectionFailure as e:
        print(f"ERRO DB_UTILS: Falha de conexão ao inserir/atualizar modelo '{nome_modelo}': {e}")
        return False
    except OperationFailure as e:
        print(f"ERRO DB_UTILS: Erro de operação ao inserir/atualizar modelo '{nome_modelo}': {e.details}")
        return False
    except Exception as e:
        print(f"ERRO DB_UTILS: Erro inesperado ao inserir/atualizar modelo '{nome_modelo}': {e}")
        import traceback
        traceback.print_exc()
        return False