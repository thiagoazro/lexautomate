from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient
import fitz  # PyMuPDF para PDFs não escaneados (mais rápido)
import docx
from io import BytesIO
import os

# Configuração do Azure Document Intelligence (Form Recognizer)
# Use as chaves e endpoint corretos do seu serviço lexautomate-orc
docintel_endpoint = "https://lexautomate-orc.cognitiveservices.azure.com/" # Use o endpoint correto do seu serviço
docintel_key = "FtqfVcECaQkohYtXfqvJYP2ttF2lx9fR9eyn13Yjww2n5Az9iVGTJQQJ99BEACYeBjFXJ3w3AAALACOGcxBe" # Use a chave correta do seu serviço

docintel_client = DocumentAnalysisClient(docintel_endpoint, AzureKeyCredential(docintel_key))

# Função para extrair texto usando PyMuPDF (mais rápido para PDFs nativos)
def extract_text_from_pdf_pymupdf(caminho_pdf):
    try:
        doc = fitz.open(caminho_pdf)
        text = ""
        for page in doc:
            text += page.get_text() # Use get_text() que é mais geral
        return text.strip()
    except Exception as e:
        print(f"Erro ao ler PDF com PyMuPDF: {e}")
        return None # Retorna None se falhar, indicando que pode ser escaneado

# Função para extrair texto de DOCX
def extract_text_from_docx(caminho_docx):
    try:
        doc = docx.Document(caminho_docx)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip() != ""]).strip()
    except Exception as e:
        print(f"Erro ao ler DOCX: {e}")
        return ""

# Função para extrair texto de PDF usando Azure Document Intelligence (com OCR)
def extract_text_from_pdf_docintel(caminho_pdf):
    try:
        with open(caminho_pdf, "rb") as f:
            poller = docintel_client.begin_analyze_document("prebuilt-document", f)
            result = poller.result()

        texto = ""
        for page in result.pages:
            for line in page.lines:
                texto += line.content + "\n"
        return texto.strip()
    except Exception as e:
        print(f"Erro ao ler PDF com Document Intelligence: {e}")
        return ""

# Função unificada para extrair texto de diferentes tipos de documento
def extrair_texto_documento(caminho_arquivo, extensao):
    if extensao == ".pdf":
        # Tenta ler com PyMuPDF primeiro (mais rápido para PDFs nativos)
        texto = extract_text_from_pdf_pymupdf(caminho_arquivo)
        if texto is None or not texto.strip():
            # Se falhar ou não extrair texto, tenta com Document Intelligence (para OCR)
            print("Tentando extrair texto com Document Intelligence (OCR)...")
            texto = extract_text_from_pdf_docintel(caminho_arquivo)
        return texto
    elif extensao == ".docx":
        return extract_text_from_docx(caminho_arquivo)
    else:
        return "Formato de arquivo não suportado."