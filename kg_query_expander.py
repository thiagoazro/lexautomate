"""
kg_query_expander.py
Expansão de consultas jurídicas via Knowledge Graph.

Substitui o expand_query() baseado em dicionário fixo por expansão
inteligente via ontologia jurídica:
  1. Reconhece entidades na query do usuário
  2. Navega o KG para encontrar sinônimos, normas, hierarquias
  3. Retorna query expandida + contexto estruturado para o LLM

Fallback: se a ontologia não estiver disponível, usa dicionário fixo.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


# ─── Dicionário fixo (fallback) ──────────────────────────────────────────────

_QUERY_EXPANSIONS: Dict[str, List[str]] = {
    "rescisão indireta": ["art. 483 clt", "falta grave do empregador"],
    "justa causa": ["art. 482 clt", "falta grave do empregado"],
    "horas extras": ["art. 59 clt", "jornada extraordinária", "sobrejornada"],
    "dano moral": ["art. 186 código civil", "indenização por dano extrapatrimonial"],
    "estabilidade gestante": ["art. 10 adct", "estabilidade provisória gestante"],
    "acidente de trabalho": ["art. 19 lei 8213", "nexo causal", "responsabilidade do empregador"],
    "adicional de insalubridade": ["art. 189 clt", "nr-15", "agente insalubre"],
    "adicional de periculosidade": ["art. 193 clt", "nr-16", "atividade perigosa"],
    "aviso prévio": ["art. 487 clt", "aviso prévio proporcional"],
    "fgts": ["fundo de garantia", "lei 8036", "multa 40%"],
    "prescrição trabalhista": ["art. 7 xxix constituição", "prescrição quinquenal", "prescrição bienal"],
    "assédio moral": ["dano moral no trabalho", "ambiente de trabalho hostil"],
    "equiparação salarial": ["art. 461 clt", "trabalho de igual valor"],
    "terceirização": ["lei 13429", "responsabilidade subsidiária", "atividade-fim"],
    "contrato de experiência": ["art. 443 clt", "contrato por prazo determinado"],
    "férias": ["art. 129 clt", "período aquisitivo", "período concessivo"],
    "mandado de segurança": ["art. 5 lxix constituição", "lei 12016", "direito líquido e certo"],
    "habeas corpus": ["art. 5 lxviii constituição", "liberdade de locomoção"],
    "usucapião": ["art. 1238 código civil", "posse ad usucapionem", "prescrição aquisitiva"],
    "pensão alimentícia": ["art. 1694 código civil", "alimentos", "necessidade e possibilidade"],
    "guarda compartilhada": ["art. 1583 código civil", "lei 13058", "melhor interesse da criança"],
    "divórcio": ["art. 226 constituição", "dissolução do casamento", "partilha de bens"],
    "despejo": ["lei 8245", "lei do inquilinato", "retomada do imóvel"],
    "execução fiscal": ["lei 6830", "certidão de dívida ativa", "cda"],
    "improbidade administrativa": ["lei 8429", "enriquecimento ilícito", "dano ao erário"],
    "licitação": ["lei 14133", "pregão", "concorrência pública"],
    "consumidor": ["cdc", "lei 8078", "relação de consumo", "vício do produto"],
    "sobreaviso": ["plantão", "disponibilidade", "tempo à disposição", "art. 244 clt", "súmula 428 tst"],
}


# ─── Expansão via KG ─────────────────────────────────────────────────────────

def kg_expand_query(query: str) -> Dict[str, Any]:
    """
    Expansão completa de query via Knowledge Graph jurídico.

    Fluxo:
      1. Reconhece entidades jurídicas na query
      2. Para cada entidade, coleta sinônimos, normas, conceitos broader
      3. Constrói query expandida para busca vetorial
      4. Formata contexto estruturado (triplas) para o LLM

    Returns:
        {
            "original_query": str,
            "expanded_query": str,
            "recognized_entities": List[Dict],
            "expansion_terms": List[str],
            "kg_context": str,         # texto formatado para o LLM
            "triples": List[Tuple],    # (subject, relation, object)
            "kg_available": bool,
        }
    """
    result = {
        "original_query": query,
        "expanded_query": query,
        "recognized_entities": [],
        "expansion_terms": [],
        "kg_context": "",
        "triples": [],
        "kg_available": False,
    }

    if not query or not query.strip():
        return result

    try:
        from legal_ontology import get_ontology

        ontology = get_ontology()
        if not ontology.is_loaded:
            logger.debug("Ontologia não carregada, usando fallback")
            result["expanded_query"] = fallback_expand_query(query)
            return result

        result["kg_available"] = True

        # 1. Reconhecer entidades
        entities = ontology.recognize_entities(query)
        result["recognized_entities"] = entities

        if not entities:
            # Sem entidades reconhecidas, fallback
            result["expanded_query"] = fallback_expand_query(query)
            return result

        entity_ids = [e["id"] for e in entities]
        logger.info(
            f"KG: {len(entities)} entidades reconhecidas: "
            f"{', '.join(e['label'] for e in entities[:5])}"
        )

        # 2. Coletar termos de expansão
        expansion_terms = ontology.expand_query_terms(entity_ids)
        result["expansion_terms"] = expansion_terms

        # 3. Construir query expandida (sem duplicatas)
        query_lower = query.lower()
        unique_terms = []
        for term in expansion_terms:
            if term.lower() not in query_lower and term.lower() not in " ".join(unique_terms).lower():
                unique_terms.append(term)

        if unique_terms:
            # Limitar a 15 termos para não poluir a busca
            limited = unique_terms[:15]
            result["expanded_query"] = f"{query} ({' '.join(limited)})"
            logger.info(f"KG: query expandida com {len(limited)} termos")

        # 4. Coletar triplas
        triples = ontology.get_triples(entity_ids, max_depth=1)
        result["triples"] = triples

        # 5. Formatar contexto KG para o LLM
        kg_context = ontology.format_kg_context_for_llm(entity_ids)
        result["kg_context"] = kg_context

        return result

    except ImportError:
        logger.warning("legal_ontology não disponível, usando fallback")
        result["expanded_query"] = fallback_expand_query(query)
        return result
    except Exception as exc:
        logger.error(f"KG expansion falhou: {exc}")
        result["expanded_query"] = fallback_expand_query(query)
        return result


def fallback_expand_query(query: str) -> str:
    """
    Fallback: expansão simples via dicionário fixo.
    Usado quando a ontologia não está disponível.
    """
    if not query:
        return query

    query_lower = query.lower()
    expansions = []

    for term, equivalents in _QUERY_EXPANSIONS.items():
        if term in query_lower:
            for eq in equivalents:
                if eq.lower() not in query_lower:
                    expansions.append(eq)

    if expansions:
        return f"{query} ({' '.join(expansions)})"

    return query
