# rag_docintelligence_open_source.py
# Extração de texto SEM Azure (Open Source)
#
# - PDF nativo: PyMuPDF (fitz)
# - PDF escaneado (opcional): OCR via pytesseract + imagens geradas pelo PyMuPDF
# - DOCX: python-docx
#
# Config via .env (opcional):
#   ENABLE_OCR=true|false   (default: false)
#   OCR_LANG=por           (default: por)
#
# Dependências:
#   pip install pymupdf python-docx python-dotenv
#   (opcional OCR) pip install pytesseract pillow
#   (opcional OCR) instalar binário do tesseract no SO (ex: sudo apt install tesseract-ocr tesseract-ocr-por)

from __future__ import annotations

import os
from io import BytesIO
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

ENABLE_OCR = os.getenv("ENABLE_OCR", "false").strip().lower() in ("1", "true", "yes", "y", "on")
OCR_LANG = os.getenv("OCR_LANG", "por").strip() or "por"

# --- PDF (PyMuPDF) ---
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

# --- DOCX ---
try:
    import docx
except Exception:
    docx = None

# --- OCR (opcional) ---
try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None


def extract_text_from_pdf_pymupdf(caminho_pdf: str) -> Optional[str]:
    """Extrai texto de PDF nativo (rápido). Retorna None em falha."""
    if fitz is None:
        raise RuntimeError("PyMuPDF (pymupdf) não instalado. Instale com: pip install pymupdf")

    try:
        doc = fitz.open(caminho_pdf)
        parts = []
        for page in doc:
            parts.append(page.get_text() or "")
        return "\n".join(parts).strip()
    except Exception as e:
        print(f"Erro ao ler PDF com PyMuPDF: {e}")
        return None


def extract_text_from_docx(caminho_docx: str) -> str:
    """Extrai texto de DOCX."""
    if docx is None:
        raise RuntimeError("python-docx não instalado. Instale com: pip install python-docx")

    try:
        d = docx.Document(caminho_docx)
        return "\n".join([p.text for p in d.paragraphs if (p.text or "").strip()]).strip()
    except Exception as e:
        print(f"Erro ao ler DOCX: {e}")
        return ""


def _ocr_pdf_with_pymupdf(caminho_pdf: str, lang: str = "por") -> str:
    """OCR simples página a página usando renderização do PyMuPDF."""
    if not ENABLE_OCR:
        return ""

    if fitz is None:
        raise RuntimeError("PyMuPDF (pymupdf) não instalado. Instale com: pip install pymupdf")

    if pytesseract is None or Image is None:
        raise RuntimeError(
            "OCR habilitado, mas dependências faltando. Instale com: pip install pytesseract pillow "
            "e instale o binário tesseract no SO."
        )

    try:
        doc = fitz.open(caminho_pdf)
        parts = []
        mat = fitz.Matrix(2.0, 2.0)  # escala 2.0
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img = Image.open(BytesIO(pix.tobytes("png")))
            txt = pytesseract.image_to_string(img, lang=lang) or ""
            txt = txt.strip()
            if txt:
                parts.append(txt)
        return "\n".join(parts).strip()
    except Exception as e:
        print(f"Erro no OCR do PDF: {e}")
        return ""


def extrair_texto_documento(caminho_arquivo: str, extensao: str) -> str:
    """Função unificada usada pelo restante do projeto."""
    ext = (extensao or "").lower().strip()
    if ext and not ext.startswith("."):
        ext = "." + ext

    if ext == ".pdf":
        texto = extract_text_from_pdf_pymupdf(caminho_arquivo)
        if not texto or not texto.strip():
            if ENABLE_OCR:
                print("PDF parece escaneado/vazio. Tentando OCR (open source)...")
                return _ocr_pdf_with_pymupdf(caminho_arquivo, lang=OCR_LANG)
            return ""
        return texto

    if ext == ".docx":
        return extract_text_from_docx(caminho_arquivo)

    if ext in (".txt", ".md"):
        try:
            with open(caminho_arquivo, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception as e:
            print(f"Erro ao ler arquivo texto: {e}")
            return ""

    return ""
