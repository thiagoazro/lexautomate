"""
legal_ontology.py
Ontologia jurídica brasileira baseada em Knowledge Graph (NetworkX).

Carrega entidades e relações de ontology_data.json e fornece:
  - Reconhecimento de entidades em texto
  - Expansão via sinônimos, broader/narrower, normas relacionadas
  - Triplas estruturadas para enriquecer o contexto do LLM
  - Formatação de conhecimento KG para o prompt

Singleton: carregado uma vez, reutilizado em todas as requisições.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx

logger = logging.getLogger(__name__)

_ONTOLOGY_INSTANCE: Optional[LegalOntology] = None
_DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), "ontology_data.json")


class LegalOntology:
    """Knowledge Graph jurídico brasileiro."""

    def __init__(self, data_path: str = None):
        self.graph = nx.DiGraph()
        self.entities: Dict[str, Dict[str, Any]] = {}
        self._lookup: Dict[str, List[str]] = {}  # lowered label/synonym → [entity_ids]
        self._loaded = False

        path = data_path or _DEFAULT_DATA_PATH
        self._load(path)

    # ─── Carregamento ────────────────────────────────────────────────────────

    def _load(self, path: str) -> None:
        if not os.path.isfile(path):
            logger.warning(f"Ontologia não encontrada em {path}. KG desativado.")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Entidades
            for eid, edata in (data.get("entities") or {}).items():
                self.entities[eid] = edata
                self.graph.add_node(eid, **edata)

                # Lookup: label + synonyms → entity_id
                label = (edata.get("label") or "").strip().lower()
                if label:
                    self._lookup.setdefault(label, []).append(eid)

                for syn in edata.get("synonyms") or []:
                    syn_lower = syn.strip().lower()
                    if syn_lower:
                        self._lookup.setdefault(syn_lower, []).append(eid)

            # Relações
            for rel in data.get("relations") or []:
                src = rel.get("source", "")
                tgt = rel.get("target", "")
                rtype = rel.get("type", "related")
                if src in self.entities and tgt in self.entities:
                    self.graph.add_edge(src, tgt, type=rtype)

            self._loaded = True
            logger.info(
                f"Ontologia carregada: {len(self.entities)} entidades, "
                f"{self.graph.number_of_edges()} relações, "
                f"{len(self._lookup)} termos de lookup"
            )
        except Exception as exc:
            logger.error(f"Erro ao carregar ontologia: {exc}")

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ─── Reconhecimento de entidades ─────────────────────────────────────────

    def recognize_entities(self, text: str) -> List[Dict[str, Any]]:
        """
        Encontra entidades jurídicas mencionadas no texto.
        Usa substring matching contra labels e sinônimos.
        Retorna lista de dicts com id, label, type, domain.
        """
        if not self._loaded or not text:
            return []

        text_lower = text.lower()
        found: Dict[str, Dict[str, Any]] = {}

        # Ordenar por comprimento decrescente (match mais específico primeiro)
        sorted_terms = sorted(self._lookup.keys(), key=len, reverse=True)

        for term in sorted_terms:
            if term in text_lower and len(term) >= 3:
                for eid in self._lookup[term]:
                    if eid not in found:
                        edata = self.entities.get(eid, {})
                        found[eid] = {
                            "id": eid,
                            "label": edata.get("label", eid),
                            "type": edata.get("type", ""),
                            "domain": edata.get("domain", ""),
                            "matched_term": term,
                        }

        return list(found.values())

    # ─── Navegação no grafo ──────────────────────────────────────────────────

    def get_synonyms(self, entity_id: str) -> List[str]:
        """Retorna todos os sinônimos de uma entidade."""
        edata = self.entities.get(entity_id, {})
        return list(edata.get("synonyms") or [])

    def _get_neighbors_by_relation(
        self, entity_id: str, relation_types: List[str], direction: str = "out"
    ) -> List[Dict[str, Any]]:
        """Busca vizinhos por tipo de relação."""
        if entity_id not in self.graph:
            return []

        results = []
        if direction in ("out", "both"):
            for _, tgt, data in self.graph.out_edges(entity_id, data=True):
                if data.get("type") in relation_types:
                    edata = self.entities.get(tgt, {})
                    results.append({
                        "id": tgt,
                        "label": edata.get("label", tgt),
                        "type": edata.get("type", ""),
                        "domain": edata.get("domain", ""),
                        "relation": data.get("type"),
                    })

        if direction in ("in", "both"):
            for src, _, data in self.graph.in_edges(entity_id, data=True):
                if data.get("type") in relation_types:
                    edata = self.entities.get(src, {})
                    results.append({
                        "id": src,
                        "label": edata.get("label", src),
                        "type": edata.get("type", ""),
                        "domain": edata.get("domain", ""),
                        "relation": data.get("type"),
                    })

        return results

    def get_related_norms(self, entity_id: str) -> List[Dict[str, Any]]:
        """Normas que regulam/citam esta entidade."""
        return self._get_neighbors_by_relation(
            entity_id, ["regulates", "cites", "part_of"], direction="both"
        )

    def get_broader(self, entity_id: str) -> List[Dict[str, Any]]:
        """Conceitos mais gerais (hiperônimos)."""
        return self._get_neighbors_by_relation(entity_id, ["broader"], direction="out")

    def get_narrower(self, entity_id: str) -> List[Dict[str, Any]]:
        """Conceitos mais específicos (hipônimos)."""
        return self._get_neighbors_by_relation(entity_id, ["narrower"], direction="out")

    def get_related_themes(self, entity_id: str) -> List[Dict[str, Any]]:
        """Temas relacionados."""
        return self._get_neighbors_by_relation(
            entity_id, ["related_theme", "related"], direction="both"
        )

    # ─── Triplas ─────────────────────────────────────────────────────────────

    def get_triples(
        self, entity_ids: List[str], max_depth: int = 2
    ) -> List[Tuple[str, str, str]]:
        """
        Coleta triplas (sujeito, predicado, objeto) até max_depth saltos
        das entidades fornecidas. Retorna (label_source, relation, label_target).
        """
        if not self._loaded:
            return []

        visited: Set[str] = set()
        triples: List[Tuple[str, str, str]] = []
        queue: List[Tuple[str, int]] = [(eid, 0) for eid in entity_ids if eid in self.graph]

        while queue:
            current, depth = queue.pop(0)
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            src_label = self.entities.get(current, {}).get("label", current)

            for _, tgt, data in self.graph.out_edges(current, data=True):
                tgt_label = self.entities.get(tgt, {}).get("label", tgt)
                rel = data.get("type", "related")
                triple = (src_label, rel, tgt_label)
                if triple not in triples:
                    triples.append(triple)
                if depth + 1 <= max_depth and tgt not in visited:
                    queue.append((tgt, depth + 1))

            for src, _, data in self.graph.in_edges(current, data=True):
                src_label_in = self.entities.get(src, {}).get("label", src)
                rel = data.get("type", "related")
                triple = (src_label_in, rel, self.entities.get(current, {}).get("label", current))
                if triple not in triples:
                    triples.append(triple)
                if depth + 1 <= max_depth and src not in visited:
                    queue.append((src, depth + 1))

        return triples[:50]  # limitar para não explodir o contexto

    # ─── Expansão de termos ──────────────────────────────────────────────────

    def expand_query_terms(self, entity_ids: List[str]) -> List[str]:
        """
        Coleta termos para expansão de query: sinônimos + labels de normas
        relacionadas + labels de conceitos mais gerais.
        """
        terms: List[str] = []
        seen: Set[str] = set()

        for eid in entity_ids:
            # Sinônimos
            for syn in self.get_synonyms(eid):
                syn_lower = syn.lower()
                if syn_lower not in seen:
                    seen.add(syn_lower)
                    terms.append(syn)

            # Normas relacionadas
            for norm in self.get_related_norms(eid):
                label = norm.get("label", "")
                if label.lower() not in seen:
                    seen.add(label.lower())
                    terms.append(label)

            # Conceitos mais gerais
            for broader in self.get_broader(eid):
                label = broader.get("label", "")
                if label.lower() not in seen:
                    seen.add(label.lower())
                    terms.append(label)

        return terms

    # ─── Formatação para LLM ─────────────────────────────────────────────────

    def format_kg_context_for_llm(self, entity_ids: List[str]) -> str:
        """
        Formata conhecimento estruturado do KG para injetar no prompt do LLM.
        Inclui: entidades reconhecidas, triplas, hierarquia, normas.
        """
        if not self._loaded or not entity_ids:
            return ""

        sections = []

        # 1. Entidades reconhecidas
        entity_lines = []
        for eid in entity_ids:
            edata = self.entities.get(eid, {})
            label = edata.get("label", eid)
            etype = edata.get("type", "")
            domain = edata.get("domain", "")
            desc = edata.get("description", "")
            line = f"• {label}"
            if etype:
                line += f" ({etype})"
            if domain:
                line += f" [{domain}]"
            if desc:
                line += f" — {desc}"
            entity_lines.append(line)

        if entity_lines:
            sections.append("ENTIDADES IDENTIFICADAS:\n" + "\n".join(entity_lines))

        # 2. Relações (triplas)
        triples = self.get_triples(entity_ids, max_depth=1)
        if triples:
            # Traduzir tipos de relação
            rel_labels = {
                "regulates": "regulado por",
                "cites": "citado por",
                "part_of": "parte de",
                "broader": "é tipo de",
                "narrower": "inclui",
                "synonym_of": "sinônimo de",
                "supersedes": "revogado por",
                "related_theme": "tema relacionado",
                "related": "relacionado a",
            }
            triple_lines = []
            for src, rel, tgt in triples[:30]:
                rel_pt = rel_labels.get(rel, rel)
                triple_lines.append(f"  {src} → {rel_pt} → {tgt}")
            sections.append("RELAÇÕES JURÍDICAS:\n" + "\n".join(triple_lines))

        # 3. Hierarquia
        hierarchy_lines = []
        for eid in entity_ids:
            label = self.entities.get(eid, {}).get("label", eid)
            broader = self.get_broader(eid)
            narrower = self.get_narrower(eid)
            if broader:
                broader_labels = ", ".join(b["label"] for b in broader[:5])
                hierarchy_lines.append(f"  {label} ⊂ {broader_labels}")
            if narrower:
                narrower_labels = ", ".join(n["label"] for n in narrower[:5])
                hierarchy_lines.append(f"  {label} ⊃ {narrower_labels}")

        if hierarchy_lines:
            sections.append("HIERARQUIA DE CONCEITOS:\n" + "\n".join(hierarchy_lines))

        # 4. Normas relacionadas
        norm_lines = []
        for eid in entity_ids:
            norms = self.get_related_norms(eid)
            if norms:
                label = self.entities.get(eid, {}).get("label", eid)
                norm_labels = [f"{n['label']} ({n['relation']})" for n in norms[:8]]
                norm_lines.append(f"  {label}: {', '.join(norm_labels)}")

        if norm_lines:
            sections.append("NORMAS RELACIONADAS:\n" + "\n".join(norm_lines))

        if not sections:
            return ""

        return "===== CONHECIMENTO ESTRUTURADO (Knowledge Graph) =====\n\n" + "\n\n".join(sections)


# ─── Singleton ───────────────────────────────────────────────────────────────

def get_ontology() -> LegalOntology:
    """Retorna instância singleton da ontologia."""
    global _ONTOLOGY_INSTANCE
    if _ONTOLOGY_INSTANCE is None:
        _ONTOLOGY_INSTANCE = LegalOntology()
    return _ONTOLOGY_INSTANCE
