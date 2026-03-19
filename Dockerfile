# ── Dockerfile — LexAutomate API (Render) ─────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Dependências de sistema para PyMuPDF (PDF) e sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmupdf-dev \
    libfreetype6-dev \
    libharfbuzz-dev \
    libjpeg62-turbo-dev \
    libopenjp2-7-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instala dependências Python antes de copiar o código (melhor cache de layers)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pré-baixa o modelo BM25 (fastembed) para não baixar na primeira requisição
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding(model_name='Qdrant/bm25')" || true

# Pré-baixa o cross-encoder de reranking
RUN python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-multilingual-MiniLM-L12-en')" || true

# Copia o código da aplicação
COPY . .

# Diretório para grafos GraphRAG (ephemeral no Render — /tmp é sempre gravável)
RUN mkdir -p /tmp/graph_visualizations

EXPOSE 8000

# Render injeta PORT como variável de ambiente — o uvicorn usa 8000 por padrão
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
