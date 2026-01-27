# converter_mongoDB.py
from pymongo import MongoClient
import os
import json
from pathlib import Path
from datetime import datetime, timezone
from docx import Document
from langchain_openai import ChatOpenAI
from langchain.schema.messages import HumanMessage
from string import Formatter
import traceback

# CONFIGURAÇÃO DO LLM (OpenAI direto)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_LLM_MODEL = os.getenv("OPENAI_LLM_MODEL", "gpt-4o-mini").strip()

llm = ChatOpenAI(
    model=OPENAI_LLM_MODEL,
    openai_api_key=OPENAI_API_KEY,
    temperature=0.3
)

# CONFIGURAÇÃO DO MONGO
mongo_uri = "mongodb+srv://thiagoazro:FqBdZcF7vtiZXOwl@cluster0.8fmcx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
db_name = "lexautomate"
collection_name = "modelos_pecas"
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

# FUNÇÃO PARA ANALISAR COM LLM E EXTRAIR CAMPOS PARAMETRIZÁVEIS
def gerar_campos_com_llm(texto):
    # Primeiro, tenta extrair o prompt_template e outras informações básicas
    # Aprimorando o prompt para instruir o LLM a formatar corretamente os placeholders
    prompt_primeira_passagem = (
        "Analise a peça jurídica abaixo e extraia os seguintes campos como um JSON:\n"
        "- area_direito (string): A área do direito (ex: 'Civil', 'Trabalhista').\n"
        "- tipo_peca (string): O tipo de peça (ex: 'Petição Inicial', 'Contestação').\n"
        "- descricao (string): Uma breve descrição do modelo da peça.\n"
        "- tags (lista de strings): Tags relevantes (ex: 'divórcio', 'alimentos').\n"
        "- reivindicacoes_comuns (lista de strings): Lista de pedidos ou reivindicações comuns que esta peça geralmente faz. **Se houver um template de pedidos, extraia-o para aqui.**\n"
        "- prompt_template (string): O modelo COMPLETO da peça. **CRÍTICO: Substitua TODAS as informações variáveis (ex: nomes de partes, valores, foros, endereços, datas, números de documentos como RG/CPF/CNPJ/OAB, ou qualquer texto como '[DADO NAO INFORMADO]' ou '[COMPLETAR COM DADO FALTANTE DO USUÁRIO]') por placeholders no formato '{nome_do_campo_relevante}'. Mantenha a formatação original da peça e TODO o seu conteúdo, incluindo seções como DOS FATOS, DO DIREITO, DOS PEDIDOS, etc.** Por exemplo, 'NOME DO AUTOR' deve se tornar '{autor_recorrente}', 'VALOR DA CAUSA' deve se tornar '{valor_causa}'.\n\n"
        "Peça jurídica:\n" + texto[:4000] # Aumentar o limite para mais contexto
    )
    resposta_primeira_passagem = llm.invoke([HumanMessage(content=prompt_primeira_passagem)])

    try:
        campos_primeira_passagem = json.loads(limpar_resposta_json(resposta_primeira_passagem.content))
    except json.JSONDecodeError:
        print("❌ Erro ao interpretar resposta do LLM (JSON inválido na primeira passagem):")
        print(resposta_primeira_passagem.content)
        return {}
    except Exception as e:
        print(f"❌ Erro inesperado ao processar resposta do LLM: {e}")
        print(resposta_primeira_passagem.content)
        return {}

    prompt_template_extraido = campos_primeira_passagem.get("prompt_template", "")
    campos_parametrizaveis = []

    if prompt_template_extraido:
        # Usa Formatter para encontrar os nomes dos campos no prompt_template
        # Isso garante que os campos parametrizáveis correspondam exatamente aos placeholders
        # que o LLM colocou no prompt_template.
        try:
            placeholders = [field_name for _, field_name, _, _ in Formatter().parse(prompt_template_extraido) if field_name is not None]
            
            # Remove duplicatas e mantém a ordem de aparição (aproximadamente)
            seen = set()
            unique_placeholders = []
            for p in placeholders:
                if p not in seen:
                    unique_placeholders.append(p)
                    seen.add(p)

            # Para cada placeholder, criar um dicionário com 'nome' e 'label'
            for p_name in unique_placeholders:
                # Tenta criar um label amigável (ex: "nome_completo" -> "Nome Completo")
                label = p_name.replace('_', ' ').title()
                campos_parametrizaveis.append({"nome": p_name, "label": label})
            
            print(f"INFO CONVERTER: Campos parametrizáveis identificados: {campos_parametrizaveis}")

        except Exception as e:
            print(f"AVISO CONVERTER: Falha ao extrair campos parametrizáveis do prompt_template: {e}")
            traceback.print_exc()
            campos_parametrizaveis = [] # Garante que seja uma lista vazia em caso de erro

    campos_primeira_passagem["campos_parametrizaveis"] = campos_parametrizaveis
    return campos_primeira_passagem

# FUNÇÃO PARA SALVAR NO MONGO
def inserir_modelo_peca(modelo):
    # Usar update_one com upsert=True para evitar duplicatas e atualizar se já existir
    filter_query = {
        "area_direito": modelo["area_direito"],
        "tipo_peca": modelo["tipo_peca"],
        "nome_modelo": modelo["nome_modelo"]
    }
    update_operation = {
        "$set": modelo,
        "$setOnInsert": {"data_criacao": datetime.now(timezone.utc)} # Define data_criacao apenas na primeira inserção
    }
    
    result = collection.update_one(filter_query, update_operation, upsert=True)
    
    if result.upserted_id:
        print(f"✅ Inserido (novo documento): {modelo['nome_modelo']} com ID: {result.upserted_id}")
    elif result.modified_count > 0:
        print(f"🔄 Atualizado (documento existente): {modelo['nome_modelo']}")
    else:
        print(f"⏩ Modelo já existe e não precisou de atualização: {modelo['nome_modelo']}")


# FUNÇÃO PRINCIPAL PARA CADA DOCX
def processar_docx_para_mongo(docx_path):
    texto = extrair_texto_docx(docx_path)
    campos = gerar_campos_com_llm(texto)

    if not campos:
        print(f"⚠️  Falha ao processar: {docx_path}")
        return

    # Use o nome do arquivo DOCX como nome_modelo (garante consistência com o original)
    nome_modelo_base = Path(docx_path).name 
    
    # Prepara o dicionário do modelo para inserção/atualização
    modelo_doc = {
        "area_direito": campos.get("area_direito", "Não identificado"),
        "tipo_peca": campos.get("tipo_peca", "Outro"),
        "nome_modelo": nome_modelo_base, # Usa o nome base do arquivo DOCX
        "autor_modelo": campos.get("autor_modelo", "LexAutomate - Conversor DOCX"), # Tenta manter autor se o LLM identificou
        "complexidade": campos.get("complexidade", "Não especificado"), 
        "data_atualizacao": datetime.now(timezone.utc), # Sempre atualiza esta data
        "descricao": campos.get("descricao", ""),
        "jurisprudencia_exemplar": campos.get("jurisprudencia_exemplar", []), 
        "legislacao_relevante": campos.get("legislacao_relevante", []),
        "prompt_template": campos.get("prompt_template", ""),
        "reivindicacoes_comuns": campos.get("reivindicacoes_comuns", []),
        "requisitos_especificos": campos.get("requisitos_especificos", ""),
        "tags": campos.get("tags", []),
        "campos_parametrizaveis": campos.get("campos_parametrizaveis", []) # Adicionado
    }

    inserir_modelo_peca(modelo_doc)

# VARRER TODAS AS SUBPASTAS E CONVERTER OS DOCX
def converter_todos_os_docx():
    # Ajuste o caminho da raiz conforme a sua estrutura de pastas
    # Ex: se 'pecas_processuais' está na mesma pasta que o script converter_mongoDB.py
    raiz = Path("pecas_processuais") 
    if not raiz.exists():
        print(f"AVISO: O diretório '{raiz}' não foi encontrado. Certifique-se de que suas peças DOCX estão lá.")
        print("Tentando procurar DOCX no diretório atual...")
        raiz = Path(".") # Procura no diretório atual como fallback

    # Antes de iniciar o processo de conversão, você pode querer limpar o cache do Streamlit
    # para garantir que o app5.py pegue os dados atualizados após a execução deste script.
    # Isso é feito na função inserir_modelo_peca, mas um "clear all" global aqui poderia ser considerado
    # se você tiver outros caches. Por enquanto, confiamos no clear() dentro de inserir_modelo_peca.

    for docx_file in raiz.rglob("*.docx"):
        print(f"\n📄 Processando: {docx_file}")
        processar_docx_para_mongo(str(docx_file))
    
    print("\nProcesso de conversão/atualização de DOCX para MongoDB concluído.")

# EXECUÇÃO
if __name__ == "__main__":
    converter_todos_os_docx()