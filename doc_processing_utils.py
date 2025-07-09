# doc_processing_utils.py
import streamlit as st
from io import BytesIO
from docx import Document as DocxDocument
try:
    import pypdf
except ImportError:
    st.warning("A biblioteca 'pypdf' não está instalada. A extração de texto de PDF não funcionará. Instale com 'pip install pypdf'.")
    pypdf = None

def extrair_conteudo_documento(uploaded_file):
    """
    Extrai o conteúdo de um arquivo .docx ou .pdf.
    Recebe um objeto UploadedFile do Streamlit.
    """
    if uploaded_file.name.endswith('.docx'):
        try:
            doc = DocxDocument(uploaded_file)
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            return '\n'.join(full_text)
        except Exception as e:
            st.error(f"Erro ao extrair texto do DOCX '{uploaded_file.name}': {e}")
            return ""
    elif uploaded_file.name.endswith('.pdf'):
        if pypdf is None:
            st.error(f"Erro: A extração de PDF para '{uploaded_file.name}' requer a biblioteca 'pypdf'. Por favor, instale-a.")
            return ""
        try:
            reader = pypdf.PdfReader(uploaded_file)
            full_text = []
            for page in reader.pages:
                full_text.append(page.extract_text() or '')
            return '\n'.join(full_text)
        except Exception as e:
            st.error(f"Erro ao extrair texto do PDF '{uploaded_file.name}': {e}")
            return ""
    else:
        st.warning(f"Tipo de arquivo não suportado para extração: {uploaded_file.name}. Suportados: .docx, .pdf.")
        return ""