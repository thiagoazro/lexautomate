"""
juit_rimor.py
Integração com a API JuIT Rimor para busca de jurisprudência pública brasileira.

Base: 70M+ precedentes de 92 tribunais + fontes administrativas/regulatórias.
Auth: Basic Auth (username:password)
Docs: https://api.juit.io/v1/data-products/search

Ativação: definir JUIT_USERNAME e JUIT_PASSWORD no .env.
Se não definidas, o módulo é desativado silenciosamente.

Campos de busca (search_on):
  - headnote: ementa
  - full_text: inteiro teor
  - title: título (número do processo)

Filtros disponíveis:
  - court_code: tribunal (STF, STJ, TST, TRT1-24, TRF1-6, TJSP, TJMG, etc.)
  - trier: magistrado/relator
  - judgment_body: órgão julgador (ex: "3ª Turma")
  - document_type: Acórdão, Decisão Monocrática, Sentença, etc.
  - degree: 1ª Instância, 2ª Instância, Tribunal Superior, Administrativo
  - order_date: data consolidada (formato YYYYMMDD com operadores $gt, $gte, $lt, $lte)
  - judgment_date: data de julgamento
  - publication_date: data de publicação
  - process_origin_state: estado de origem (UF)
  - district: comarca
  - document_matter_list: assuntos (TPU do CNJ)
  - process_class_name_list: classe da ação
  - justice_type: Juízo Comum, Juizado Especial

Operadores de busca na query:
  - E: todas as palavras (AND)
  - OU: qualquer palavra (OR)
  - MASNAO: excluir termo (NOT)
  - "aspas": busca exata
  - PARÊNTESES: agrupamento
  Exemplo: dano E (moral OU material) MASNAO estético
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ─── Configuração ────────────────────────────────────────────────────────────

JUIT_USERNAME = (os.getenv("JUIT_USERNAME") or "").strip()
JUIT_PASSWORD = (os.getenv("JUIT_PASSWORD") or "").strip()
JUIT_OWNER = (os.getenv("JUIT_OWNER") or "").strip()  # email do usuário
JUIT_BASE_URL = (
    os.getenv("JUIT_BASE_URL")
    or "https://api.juit.io/v1/data-products/search"
).strip()


# ─── Disponibilidade ─────────────────────────────────────────────────────────

def is_available() -> bool:
    """Retorna True se a API JuIT Rimor está configurada."""
    return bool(JUIT_USERNAME and JUIT_PASSWORD and JUIT_OWNER)


# ─── Busca principal ─────────────────────────────────────────────────────────

def buscar_jurisprudencias(
    query: str,
    search_on: Optional[List[str]] = None,
    top_k: int = 10,
    tribunal: Optional[str] = None,
    relator: Optional[str] = None,
    orgao_julgador: Optional[str] = None,
    tipo_documento: Optional[str] = None,
    grau: Optional[str] = None,
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    estado_origem: Optional[str] = None,
    comarca: Optional[str] = None,
    assunto: Optional[str] = None,
    classe_acao: Optional[str] = None,
    tipo_justica: Optional[str] = None,
    ordenar_por: str = "relevancia",
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """
    Busca jurisprudências na API JuIT Rimor.

    Args:
        query: termo de busca (suporta operadores E, OU, MASNAO, "aspas")
        search_on: campos para buscar (["headnote"], ["headnote", "full_text"], ["title"])
                   Default: ["headnote", "full_text"]
        top_k: número máximo de resultados (API retorna 10 por página)
        tribunal: filtro por tribunal (ex: "STF", "STJ", "TST", "TRT3", "TJMG")
        relator: filtro por magistrado (ex: "Alexandre de Moraes")
        orgao_julgador: filtro por órgão (ex: "3ª Turma")
        tipo_documento: "Acórdão", "Decisão Monocrática", "Sentença", etc.
        grau: "1ª Instância", "2ª Instância", "Tribunal Superior", "Administrativo"
        data_inicio: data mínima formato YYYYMMDD (ex: "20240101")
        data_fim: data máxima formato YYYYMMDD (ex: "20241231")
        estado_origem: UF de origem (ex: "SP", "MG", "RJ")
        comarca: comarca de origem (ex: "São Paulo", "Campinas")
        assunto: assunto TPU CNJ (ex: "Indenização Por Dano Moral")
        classe_acao: classe da ação (ex: "Agravo de instrumento")
        tipo_justica: "Juízo Comum" ou "Juizado Especial"
        ordenar_por: "relevancia" (score) ou "recentes" (order_date desc) ou "antigos" (order_date asc)
        timeout: timeout em segundos

    Returns:
        Lista de dicts normalizados para o pipeline RAG.
    """
    if not is_available():
        return []

    if search_on is None:
        search_on = ["headnote", "full_text"]

    # ── Montar query params ──────────────────────────────────────────────
    params: List[Tuple[str, str]] = [
        ("query", query),
        ("owner", JUIT_OWNER),
    ]

    # Campos de busca (podem ser múltiplos)
    for field in search_on:
        params.append(("search_on", field))

    # Ordenação
    if ordenar_por == "recentes":
        params.extend([
            ("sort_by_field", "order_date"),
            ("sort_by_direction", "desc"),
            ("sort_by_field", "juit_id"),
            ("sort_by_direction", "desc"),
        ])
    elif ordenar_por == "antigos":
        params.extend([
            ("sort_by_field", "order_date"),
            ("sort_by_direction", "asc"),
            ("sort_by_field", "juit_id"),
            ("sort_by_direction", "desc"),
        ])
    else:  # relevancia (default)
        params.extend([
            ("sort_by_field", "score"),
            ("sort_by_direction", "desc"),
            ("sort_by_field", "juit_id"),
            ("sort_by_direction", "desc"),
        ])

    # Filtros opcionais
    if tribunal:
        params.append(("court_code", tribunal))
    if relator:
        params.append(("trier", relator))
    if orgao_julgador:
        params.append(("judgment_body", orgao_julgador))
    if tipo_documento:
        params.append(("document_type", tipo_documento))
    if grau:
        params.append(("degree", grau))
    if estado_origem:
        params.append(("process_origin_state", estado_origem))
    if comarca:
        params.append(("district", comarca))
    if assunto:
        params.append(("document_matter_list", assunto))
    if classe_acao:
        params.append(("process_class_name_list", classe_acao))
    if tipo_justica:
        params.append(("justice_type", tipo_justica))

    # Filtro de datas (order_date com operadores)
    if data_inicio:
        params.append(("order_date", f"$gte{data_inicio}"))
    if data_fim:
        params.append(("order_date", f"$lte{data_fim}"))

    # ── Headers ──────────────────────────────────────────────────────────
    headers = {
        "Accept": "application/json",
        "Accept-Language": "pt-br",
        "Content-Type": "application/json",
    }

    # ── Requisição com paginação (se top_k > 10) ─────────────────────────
    all_items: List[Dict[str, Any]] = []
    search_id: Optional[str] = None
    next_page_token: Optional[str] = None
    pages_fetched = 0
    max_pages = max(1, (top_k + 9) // 10)  # cada página = 10 resultados

    try:
        while pages_fetched < max_pages:
            # Adicionar paginação se não é a primeira página
            current_params = list(params)
            if search_id:
                current_params.append(("search_id", search_id))
            if next_page_token:
                current_params.append(("next_page_token", next_page_token))

            response = requests.get(
                f"{JUIT_BASE_URL}/jurisprudence",
                params=current_params,
                headers=headers,
                auth=(JUIT_USERNAME, JUIT_PASSWORD),
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()

            # Extrair itens
            items = data.get("items", [])
            if not items:
                break

            all_items.extend(items)

            # Guardar search_id da primeira página
            search_info = data.get("search_info", {})
            if not search_id and search_info.get("search_id"):
                search_id = search_info["search_id"]

            # Próxima página
            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break

            pages_fetched += 1

            # Log de progresso
            total = data.get("total", 0)
            logger.debug(
                f"JuIT Rimor: página {pages_fetched}, "
                f"{len(all_items)}/{min(top_k, total)} itens"
            )

    except requests.exceptions.Timeout:
        logger.warning(f"JuIT Rimor: timeout após {timeout}s")
        # Retorna o que já coletou
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response else "?"
        logger.error(f"JuIT Rimor HTTP {status}: {exc}")
        return []
    except Exception as exc:
        logger.error(f"JuIT Rimor falhou: {exc}")
        return []

    # ── Normalizar resultados ────────────────────────────────────────────
    results = []
    for item in all_items[:top_k]:
        result = normalize_juit_result(item)
        if result:
            results.append(result)

    if results:
        logger.info(
            f"JuIT Rimor: {len(results)} jurisprudências para '{query[:60]}'"
        )

    return results


# ─── Normalização ────────────────────────────────────────────────────────────

def normalize_juit_result(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Converte um item da API JuIT Rimor para o formato padrão do pipeline RAG.

    Campos da API JuIT:
      - headnote: ementa
      - full_text: inteiro teor (pode ser None)
      - court_code: tribunal (STF, STJ, TJSP, etc.)
      - cnj_unique_number: número CNJ do processo
      - trier: magistrado relator
      - judgment_body: órgão julgador (ex: "3ª Turma")
      - judgment_date: data de julgamento
      - publication_date: data de publicação
      - order_date: data consolidada
      - document_type: tipo (Acórdão, Decisão Monocrática, etc.)
      - degree: grau (1ª Instância, 2ª Instância, Tribunal Superior)
      - title: título (ex: "STJ / Acórdão / 2023/0183915-0")
      - rimor_url: link para o documento no Rimor
      - artifacts: lista de arquivos (PDF, etc.)
      - document_matter_list: assuntos
      - process_class_name_list: classes da ação
      - juit_id: ID único JuIT
    """
    ementa = (item.get("headnote") or "").strip()
    if not ementa:
        return None

    # Extrair campos
    tribunal = (item.get("court_code") or "").strip()
    numero_cnj = (item.get("cnj_unique_number") or "").strip()
    titulo = (item.get("title") or "").strip()
    relator = (item.get("trier") or "").strip()
    orgao = (item.get("judgment_body") or "").strip()
    tipo_doc = (item.get("document_type") or "").strip()
    grau = (item.get("degree") or "").strip()
    juit_id = (item.get("juit_id") or item.get("id") or "").strip()
    rimor_url = (item.get("rimor_url") or "").strip()

    # Datas (formato ISO → YYYY-MM-DD)
    data_julgamento = _parse_date(item.get("judgment_date"))
    data_publicacao = _parse_date(item.get("publication_date"))
    data_consolidada = _parse_date(item.get("order_date"))
    data_display = data_julgamento or data_publicacao or data_consolidada

    # Número do processo: preferir CNJ, senão extrair do título
    numero_processo = numero_cnj
    if not numero_processo and titulo:
        # Título formato: "STJ / Acórdão / 2023/0183915-0"
        parts = titulo.split("/")
        if len(parts) >= 3:
            numero_processo = "/".join(parts[2:]).strip()

    # Assuntos e classes
    assuntos = item.get("document_matter_list") or []
    classes = item.get("process_class_name_list") or []

    # Estado de origem
    estado_origem = (item.get("process_origin_state") or "").strip()

    # Artifacts (PDFs)
    artifacts = item.get("artifacts") or []
    has_pdf = any(a.get("mime_type") == "application/pdf" for a in artifacts)

    # ── Montar content formatado para o pipeline RAG ─────────────────────
    header_parts = []
    if tribunal:
        header_parts.append(tribunal)
    if tipo_doc:
        header_parts.append(tipo_doc)
    if numero_processo:
        header_parts.append(numero_processo)

    meta_parts = []
    if relator:
        meta_parts.append(f"Relator: {relator}")
    if orgao:
        meta_parts.append(f"Órgão: {orgao}")
    if data_display:
        meta_parts.append(f"Data: {data_display}")
    if grau:
        meta_parts.append(f"Grau: {grau}")

    header = " | ".join(header_parts) if header_parts else ""
    meta = " | ".join(meta_parts) if meta_parts else ""

    content_lines = []
    if header:
        content_lines.append(header)
    if meta:
        content_lines.append(meta)
    content_lines.append("")
    content_lines.append(ementa)

    content = "\n".join(content_lines).strip()

    return {
        # Campos padrão do pipeline RAG
        "content": content,
        "chunk_id": f"juit_{juit_id}" if juit_id else f"juit_{id(item)}",
        "document_id": f"juit_{juit_id}" if juit_id else f"juit_{id(item)}",
        "arquivo_origem": f"JuIT Rimor — {tribunal} {numero_processo}".strip(),
        "tipo_documento": "jurisprudencia",
        "area_direito": "jurisprudencia",
        "language_code": "pt",
        "_source": "juit_rimor",

        # Campos específicos JuIT (para exibição no frontend)
        "_juit_raw": item,
        "_juit_tribunal": tribunal,
        "_juit_numero_processo": numero_processo,
        "_juit_numero_cnj": numero_cnj,
        "_juit_relator": relator,
        "_juit_orgao_julgador": orgao,
        "_juit_data_julgamento": data_julgamento,
        "_juit_data_publicacao": data_publicacao,
        "_juit_tipo_documento": tipo_doc,
        "_juit_grau": grau,
        "_juit_assuntos": assuntos,
        "_juit_classes": classes,
        "_juit_estado_origem": estado_origem,
        "_juit_rimor_url": rimor_url,
        "_juit_has_pdf": has_pdf,
        "_juit_juit_id": juit_id,
    }


# ─── Download de artefatos ───────────────────────────────────────────────────

def download_artifact(
    juit_id: str,
    filename: str,
    output_path: Optional[str] = None,
    timeout: int = 60,
) -> Optional[str]:
    """
    Baixa um artefato (PDF, RTF, DocX) de uma jurisprudência.

    Args:
        juit_id: ID JuIT da jurisprudência
        filename: nome do arquivo (obtido de artifacts[].filename)
        output_path: caminho para salvar (default: /tmp/{filename})
        timeout: timeout em segundos

    Returns:
        Caminho do arquivo salvo, ou None se falhou.
    """
    if not is_available():
        return None

    if not output_path:
        output_path = f"/tmp/{filename}"

    try:
        response = requests.get(
            f"{JUIT_BASE_URL}/jurisprudence/{juit_id}/artifact",
            params={"owner": JUIT_OWNER, "filename": filename},
            headers={
                "Accept": "application/json",
                "Accept-Language": "pt-br",
            },
            auth=(JUIT_USERNAME, JUIT_PASSWORD),
            timeout=timeout,
            stream=True,
        )
        response.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"JuIT artifact baixado: {output_path}")
        return output_path

    except Exception as exc:
        logger.error(f"JuIT artifact download falhou: {exc}")
        return None


# ─── Utilitários ─────────────────────────────────────────────────────────────

def _parse_date(date_str: Optional[str]) -> Optional[str]:
    """Converte data ISO (2025-02-26T00:00:00Z) para YYYY-MM-DD."""
    if not date_str:
        return None
    try:
        return date_str[:10]  # "2025-02-26T00:00:00Z" → "2025-02-26"
    except Exception:
        return None


# ─── Tribunais disponíveis ───────────────────────────────────────────────────

TRIBUNAIS = {
    # Superiores
    "STF": "Supremo Tribunal Federal",
    "STJ": "Superior Tribunal de Justiça",
    "TST": "Tribunal Superior do Trabalho",
    "TSE": "Tribunal Superior Eleitoral",
    "STM": "Superior Tribunal Militar",

    # TRFs
    "TRF1": "TRF 1ª Região (DF, GO, MT, BA, PI, MA, PA, AM, AC, RO, RR, AP, TO)",
    "TRF2": "TRF 2ª Região (RJ, ES)",
    "TRF3": "TRF 3ª Região (SP, MS)",
    "TRF4": "TRF 4ª Região (RS, PR, SC)",
    "TRF5": "TRF 5ª Região (PE, CE, PB, RN, AL, SE)",
    "TRF6": "TRF 6ª Região (MG)",

    # TRTs
    "TRT1": "TRT 1ª Região (RJ)", "TRT2": "TRT 2ª Região (SP Capital)",
    "TRT3": "TRT 3ª Região (MG)", "TRT4": "TRT 4ª Região (RS)",
    "TRT5": "TRT 5ª Região (BA)", "TRT6": "TRT 6ª Região (PE)",
    "TRT7": "TRT 7ª Região (CE)", "TRT8": "TRT 8ª Região (PA/AP)",
    "TRT9": "TRT 9ª Região (PR)", "TRT10": "TRT 10ª Região (DF/TO)",
    "TRT12": "TRT 12ª Região (SC)", "TRT13": "TRT 13ª Região (PB)",
    "TRT14": "TRT 14ª Região (RO/AC)", "TRT15": "TRT 15ª Região (Campinas)",
    "TRT16": "TRT 16ª Região (MA)", "TRT17": "TRT 17ª Região (ES)",
    "TRT18": "TRT 18ª Região (GO)", "TRT19": "TRT 19ª Região (AL)",
    "TRT20": "TRT 20ª Região (SE)", "TRT21": "TRT 21ª Região (RN)",
    "TRT22": "TRT 22ª Região (PI)", "TRT23": "TRT 23ª Região (MT)",
    "TRT24": "TRT 24ª Região (MS)",

    # TJs
    "TJAC": "TJ Acre", "TJAL": "TJ Alagoas", "TJAM": "TJ Amazonas",
    "TJAP": "TJ Amapá", "TJBA": "TJ Bahia", "TJCE": "TJ Ceará",
    "TJDFT": "TJ Distrito Federal", "TJES": "TJ Espírito Santo",
    "TJGO": "TJ Goiás", "TJMA": "TJ Maranhão", "TJMG": "TJ Minas Gerais",
    "TJMS": "TJ Mato Grosso do Sul", "TJMT": "TJ Mato Grosso",
    "TJPA": "TJ Pará", "TJPB": "TJ Paraíba", "TJPE": "TJ Pernambuco",
    "TJPI": "TJ Piauí", "TJPR": "TJ Paraná", "TJRJ": "TJ Rio de Janeiro",
    "TJRN": "TJ Rio Grande do Norte", "TJRO": "TJ Rondônia",
    "TJRR": "TJ Roraima", "TJRS": "TJ Rio Grande do Sul",
    "TJSC": "TJ Santa Catarina", "TJSE": "TJ Sergipe",
    "TJSP": "TJ São Paulo", "TJTO": "TJ Tocantins",

    # TREs
    "TRE-AC": "TRE Acre", "TRE-AL": "TRE Alagoas", "TRE-AM": "TRE Amazonas",
    "TRE-AP": "TRE Amapá", "TRE-BA": "TRE Bahia", "TRE-CE": "TRE Ceará",
    "TRE-DF": "TRE Distrito Federal", "TRE-ES": "TRE Espírito Santo",
    "TRE-GO": "TRE Goiás", "TRE-MA": "TRE Maranhão", "TRE-MG": "TRE Minas Gerais",
    "TRE-MS": "TRE Mato Grosso do Sul", "TRE-MT": "TRE Mato Grosso",
    "TRE-PA": "TRE Pará", "TRE-PB": "TRE Paraíba", "TRE-PE": "TRE Pernambuco",
    "TRE-PI": "TRE Piauí", "TRE-PR": "TRE Paraná", "TRE-RJ": "TRE Rio de Janeiro",
    "TRE-RN": "TRE Rio Grande do Norte", "TRE-RO": "TRE Rondônia",
    "TRE-RR": "TRE Roraima", "TRE-RS": "TRE Rio Grande do Sul",
    "TRE-SC": "TRE Santa Catarina", "TRE-SE": "TRE Sergipe",
    "TRE-SP": "TRE São Paulo", "TRE-TO": "TRE Tocantins",

    # Justiça Militar Estadual
    "TJMMG": "TJM Minas Gerais", "TJMRS": "TJM Rio Grande do Sul",
    "TJMSP": "TJM São Paulo",

    # Fontes Administrativas e Regulatórias
    "CARF": "Conselho Administrativo de Recursos Fiscais",
    "RFB": "Receita Federal do Brasil",
    "TIT-SP": "Tribunal de Impostos e Taxas de São Paulo",
    "TCE-SP": "Tribunal de Contas do Estado de São Paulo",
    "TCU": "Tribunal de Contas da União",
    "ANEEL": "Agência Nacional de Energia Elétrica",
}
