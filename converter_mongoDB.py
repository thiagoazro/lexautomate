import os
import json
from pathlib import Path
from datetime import datetime, timezone
from pymongo import MongoClient
from docx import Document
from langchain_openai import AzureChatOpenAI
from langchain.schema.messages import HumanMessage

# CONFIGURAÇÃO DO LLM VIA AZURE
llm = AzureChatOpenAI(
    deployment_name="lexautomate",
    model="gpt-4",
    azure_endpoint="https://lexautomate.openai.azure.com/",
    api_key="6ZJIKi1REnxeAALGOQQ2mFi7KL78gCyVYMq3yzv0xKae620iLHzdJQQJ99BDACYeBjFXJ3w3AAABACOGHcjA",
    api_version="2024-05-01-preview",
    temperature=0.3
)

# CONFIGURAÇÃO DO MONGO
mongo_uri = os.getenv("MONGODB_URI")
client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
db_name = os.getenv("MONGODB_DB_NAME", "lexautomate")
collection_name = os.getenv("MONGODB_COLLECTION_MODELOS", "modelos_pecas")
collection = client[db_name][collection_name]

# FUNÇÃO PARA EXTRAIR TEXTO DE UM .DOCX
def extrair_texto_docx(path):
    doc = Document(path)
    return "\n".join([para.text.strip() for para in doc.paragraphs if para.text.strip()])

# FUNÇÃO PARA LIMPAR JSON ENTRE MARCADORES
def limpar_resposta_json(texto):
    if texto.strip().startswith("```json"):
        texto = texto.strip().lstrip("```json").rstrip("```").strip()
    elif texto.strip().startswith("```"):
        texto = texto.strip().lstrip("```").rstrip("```").strip()
    return texto

# FUNÇÃO PARA ANALISAR COM LLM
def gerar_campos_com_llm(texto):
    prompt = (
        "Analise a peça jurídica abaixo e extraia os seguintes campos como um JSON:\n"
        "- area_direito\n"
        "- tipo_peca\n"
        "- descricao\n"
        "- tags (como lista)\n"
        "- reivindicacoes_comuns (como lista)\n"
        "- prompt_template (modelo da peça com placeholders)\n\n"
        "Peça jurídica:\n" + texto[:3000]
    )
    resposta = llm.invoke([HumanMessage(content=prompt)])

    try:
        texto_limpo = limpar_resposta_json(resposta.content)
        return json.loads(texto_limpo)
    except json.JSONDecodeError:
        print("❌ Erro ao interpretar resposta do LLM (JSON inválido):")
        print(resposta.content)
        return {}

# FUNÇÃO PARA SALVAR NO MONGO
def inserir_modelo_peca(modelo):
    collection.insert_one(modelo)
    print(f"✅ Inserido: {modelo['nome_modelo']}")

# FUNÇÃO PRINCIPAL PARA CADA DOCX
def processar_docx_para_mongo(docx_path):
    texto = extrair_texto_docx(docx_path)
    campos = gerar_campos_com_llm(texto)

    if not campos:
        print(f"⚠️  Falha ao processar: {docx_path}")
        return

    nome_modelo = Path(docx_path).name
    ja_existe = collection.find_one({"nome_modelo": nome_modelo})
    if ja_existe:
        print(f"⏩ Modelo já existe no Mongo: {nome_modelo}")
        return

    modelo = {
        "area_direito": campos.get("area_direito", "Não identificado"),
        "tipo_peca": campos.get("tipo_peca", "Outro"),
        "nome_modelo": nome_modelo,
        "autor_modelo": "LexAutomate - Conversor DOCX",
        "complexidade": "Não especificado",
        "data_criacao": datetime.now(timezone.utc),
        "data_atualizacao": datetime.now(timezone.utc),
        "descricao": campos.get("descricao", ""),
        "jurisprudencia_exemplar": [],
        "legislacao_relevante": [],
        "prompt_template": campos.get("prompt_template", ""),
        "reivindicacoes_comuns": campos.get("reivindicacoes_comuns", []),
        "requisitos_especificos": "",
        "tags": campos.get("tags", [])
    }

    inserir_modelo_peca(modelo)

# VARRER TODAS AS SUBPASTAS E CONVERTER OS DOCX
def converter_todos_os_docx():
    raiz = Path("pecas_processuais")
    for docx_file in raiz.rglob("*.docx"):
        print(f"\n📄 Processando: {docx_file}")
        processar_docx_para_mongo(str(docx_file))

# EXECUÇÃO
if __name__ == "__main__":
    converter_todos_os_docx()
