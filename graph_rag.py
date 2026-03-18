"""
graph_rag.py
GraphRAG com teoria dos grafos relacionais para conhecimento jurídico.

Constrói um grafo de conhecimento a partir dos documentos recuperados e aplica:
  - PageRank:             identifica as entidades jurídicas mais importantes
  - Betweenness:          identifica artigos/leis que ponteiam domínios distintos
  - Comunidades:          agrupa conceitos jurídicos relacionados (greedy modularity)
  - Arestas ponderadas:   frequência de co-ocorrência como peso das relações

Sem dependências Streamlit.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
from pyvis.network import Network

logger = logging.getLogger(__name__)

# ─── Padrões regex para entidades jurídicas brasileiras ──────────────────────

PATTERNS: Dict[str, re.Pattern] = {
    "article": re.compile(
        r"(art\.|artigo|arts\.|artigos)\s*"
        r"(\d+[º°ª]?[-\w\/]*)"
        r"(\s*(?:par[áa]grafo[\súuÚnico]*|§)[\s\dº°ª\w\-]*)*"
        r"(\s*(?:inciso|inc\.)[\s\wIVXLCDM\-º°ª]*)*"
        r"(\s*(?:al[íi]nea)?\s*[\w]\))*"
        r"(\s*d[aoes]?\s*(?:Constituiç[ãa]o Federal|CF|C[oó]digo\s*[\w\s]+|"
        r"Lei\s*(?:Complementar\s*)?n?[º°ª]?\s*[\d\.\/\-]+|CLT|CPC|CC|CP|CTN|CDC|"
        r"Estatuto[\w\s]*|Decreto-Lei|Dec\.\s*nº))?",
        re.IGNORECASE,
    ),
    "sumula": re.compile(
        r"(s[úu]mula)\s*(?:vinculante\s*)?(?:n?[º°ª]?\s*)?"
        r"(\d+)"
        r"(\s*d[aoes]?\s*(STF|STJ|TST|TNU|TRF\d*|TJ\w*))?",
        re.IGNORECASE,
    ),
    "precedent": re.compile(
        r"\b((?:REsp|HC|AgRg|AREsp|RR|AP|RMS|MS|AI|EAREsp|ERE|PET|SL|SS|"
        r"RHC|Ag|AR|ACO|ADC|ADI|ADO|ADPF|IF|MI|Rcl|RE|RI)\s*[\d\.\-\/]+)\b",
        re.IGNORECASE,
    ),
    "lei": re.compile(
        r"\b(Lei\s*(?:Complementar\s*)?(?:Federal\s*)?n[ºo°ª]?\s*[\d\.]+(?:\/\d+)?)\b",
        re.IGNORECASE,
    ),
}

# Paleta de cores por comunidade
_COMMUNITY_COLORS = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
    "#FFEAA7", "#DDA0DD", "#98D8C8", "#F7DC6F",
    "#BB8FCE", "#85C1E9", "#F0B27A", "#82E0AA",
]

# Stop words básicas para filtrar keywords da query
_STOP_WORDS = {
    "para", "como", "que", "com", "uma", "um", "por", "mais",
    "mas", "não", "nos", "das", "dos", "nas", "aos", "pelo",
    "pela", "quando", "onde", "qual", "quais", "este", "esta",
    "esse", "essa", "isso", "aqui", "ali", "sobre", "entre",
}


class GraphRAG:
    """
    GraphRAG jurídico com teoria dos grafos relacionais.

    Uso:
        gr = GraphRAG(retrieved_documents, user_query)
        gr.process()                                  # computa métricas
        summary = gr.generate_textual_summary_for_llm()
        path = gr.visualize_graph(output_filename="graph.html")
    """

    def __init__(
        self,
        retrieved_documents: List[Dict[str, Any]],
        user_query: str,
    ) -> None:
        self.retrieved_documents = retrieved_documents
        self.user_query = user_query
        self.graph: nx.DiGraph = nx.DiGraph()
        self.doc_nodes: Dict[str, str] = {}      # doc_id → node_id
        self.entity_nodes: Dict[str, str] = {}    # label → node_id

        # Métricas de grafo (populadas por process())
        self._pagerank: Dict[str, float] = {}
        self._betweenness: Dict[str, float] = {}
        self._communities: Dict[str, int] = {}    # node_id → community_id

        self._build_graph()

    # ── Normalização ─────────────────────────────────────────────────────────

    def _normalize(self, label: str, entity_type: str) -> str:
        label = re.sub(r"\s+", " ", label.strip().upper())
        if entity_type == "article":
            label = label.replace("ARTIGO", "ART.").replace("ARTS.", "ART.")
        elif entity_type == "sumula":
            for rep in ("SÚMULA Nº", "SÚMULA N.", "SUMULA Nº", "SUMULA N."):
                label = label.replace(rep, "SÚMULA")
        return label

    # ── Extração de entidades ─────────────────────────────────────────────────

    def _extract_entities(self, doc_id: str, content: str) -> None:
        """
        Extrai entidades jurídicas do conteúdo e adiciona ao grafo.
        Arestas ponderadas pela frequência de menção.
        """
        if not content:
            return

        mention_count: Dict[str, int] = defaultdict(int)

        for entity_type, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                raw = match.group(0).strip()
                label = raw

                if entity_type == "article":
                    num = match.group(2)
                    source = (match.group(6) or "").strip()
                    label = f"ART. {num}" + (f" {source.upper()}" if source else "")
                elif entity_type == "sumula":
                    num = match.group(2)
                    court = (match.group(4) or "").strip()
                    label = f"SÚMULA {num}" + (f" {court.upper()}" if court else "")
                elif entity_type == "lei":
                    label = raw.upper()

                label = self._normalize(label, entity_type)

                if label not in self.entity_nodes:
                    self.graph.add_node(
                        label,
                        label=label,
                        type=entity_type,
                        title=f"{entity_type.upper()}: {label}",
                        mention_count=0,
                    )
                    self.entity_nodes[label] = label

                # Incrementa contador global de menções
                self.graph.nodes[label]["mention_count"] = (
                    self.graph.nodes[label].get("mention_count", 0) + 1
                )
                mention_count[label] += 1

        # Arestas doc→entidade ponderadas pela frequência
        for entity_label, count in mention_count.items():
            if self.graph.has_edge(doc_id, entity_label):
                self.graph[doc_id][entity_label]["weight"] += count
            else:
                self.graph.add_edge(
                    doc_id,
                    entity_label,
                    type="mentions",
                    weight=count,
                    title=f"Mencionado {count}×",
                )

        # Keywords da query que aparecem no conteúdo
        query_words = [
            w.strip().lower()
            for w in re.split(r"\W+", self.user_query)
            if len(w.strip()) > 4 and w.strip().lower() not in _STOP_WORDS
        ]
        content_lower = content.lower()
        for kw in set(query_words):
            if kw in content_lower:
                norm_kw = kw.upper()
                if norm_kw not in self.entity_nodes:
                    self.graph.add_node(
                        norm_kw,
                        label=norm_kw,
                        type="keyword",
                        title=f"Keyword: {norm_kw}",
                        mention_count=0,
                    )
                    self.entity_nodes[norm_kw] = norm_kw
                if not self.graph.has_edge(doc_id, norm_kw):
                    self.graph.add_edge(doc_id, norm_kw, type="keyword", weight=1, title="Keyword")
                else:
                    self.graph[doc_id][norm_kw]["weight"] += 1

    # ── Arestas de co-ocorrência entre entidades ──────────────────────────────

    def _add_co_mention_edges(self) -> None:
        """
        Liga entidades co-mencionadas nos mesmos documentos.
        Peso = número de documentos onde ambas aparecem juntas.
        Essas arestas habilitam a detecção de comunidades entre conceitos.
        """
        entity_doc_map: Dict[str, Set[str]] = defaultdict(set)
        for doc_id in self.doc_nodes:
            for entity in self.graph.successors(doc_id):
                entity_doc_map[entity].add(doc_id)

        entities = list(entity_doc_map.keys())
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                shared = entity_doc_map[entities[i]] & entity_doc_map[entities[j]]
                if shared:
                    u, v = entities[i], entities[j]
                    if not self.graph.has_edge(u, v):
                        self.graph.add_edge(
                            u, v,
                            type="co_mentioned",
                            weight=len(shared),
                            title=f"Co-mencionados em {len(shared)} doc(s)",
                        )

    # ── Construção do grafo ───────────────────────────────────────────────────

    def _build_graph(self) -> None:
        for doc_data in self.retrieved_documents:
            doc_id = str(
                doc_data.get("chunk_id") or doc_data.get("id") or id(doc_data)
            )
            doc_label = str(doc_data.get("arquivo_origem") or doc_id)
            doc_type = str(doc_data.get("tipo_documento") or "document")

            self.graph.add_node(
                doc_id,
                label=doc_label,
                type=doc_type,
                title=f"Documento: {doc_label}",
                mention_count=0,
            )
            self.doc_nodes[doc_id] = doc_id
            self._extract_entities(doc_id, doc_data.get("content", ""))

        self._add_co_mention_edges()

    # ── Métricas de teoria dos grafos ─────────────────────────────────────────

    def process(self) -> None:
        """
        Computa PageRank, betweenness centrality e comunidades.
        Deve ser chamado após __init__ antes de gerar resumo ou visualização.
        """
        if not self.graph.nodes:
            return

        # 1. PageRank (grafo dirigido, ponderado)
        try:
            self._pagerank = nx.pagerank(self.graph, weight="weight", alpha=0.85)
            logger.debug(f"PageRank computado para {len(self._pagerank)} nós.")
        except Exception as exc:
            logger.warning(f"PageRank falhou: {exc}")
            self._pagerank = {}

        # 2. Betweenness centrality (grafo não-dirigido, ponderado)
        #    Mede nós que servem de ponte entre diferentes partes do grafo.
        try:
            undirected = self.graph.to_undirected()
            self._betweenness = nx.betweenness_centrality(
                undirected, weight="weight", normalized=True
            )
            logger.debug(f"Betweenness computado para {len(self._betweenness)} nós.")
        except Exception as exc:
            logger.warning(f"Betweenness centrality falhou: {exc}")
            self._betweenness = {}

        # 3. Detecção de comunidades (greedy modularity — NX built-in)
        #    Agrupa entidades jurídicas em clusters temáticos.
        try:
            undirected = self.graph.to_undirected()
            communities = list(
                nx.community.greedy_modularity_communities(undirected, weight="weight")
            )
            for comm_id, members in enumerate(communities):
                for node in members:
                    self._communities[node] = comm_id
            logger.debug(f"Comunidades detectadas: {len(communities)}")
        except Exception as exc:
            logger.warning(f"Detecção de comunidades falhou: {exc}")
            self._communities = {}

    # ── Resumo textual para LLM ───────────────────────────────────────────────

    def generate_textual_summary_for_llm(self, top_n: int = 5) -> str:
        """
        Gera um resumo estruturado do grafo para enriquecer o contexto do LLM.

        Inclui:
          - Estatísticas gerais do grafo
          - Top entidades por PageRank (importância)
          - Top entidades por Betweenness (pontes entre domínios)
          - Comunidades de conceitos relacionados
          - Conexões por documento (top menções)
        """
        if not self.graph.nodes:
            return ""

        entity_ids = [
            n for n, d in self.graph.nodes(data=True)
            if d.get("type") not in ("document",)
        ]
        if not entity_ids:
            return ""

        num_communities = len(set(self._communities.values()))
        lines = [
            "=== GRAFO DE CONHECIMENTO JURÍDICO (GraphRAG) ===",
            (
                f"Grafo: {self.graph.number_of_nodes()} nós | "
                f"{self.graph.number_of_edges()} relações | "
                f"{num_communities} comunidades temáticas"
            ),
        ]

        # Top por PageRank
        if self._pagerank:
            top_pr = sorted(
                [(n, self._pagerank[n]) for n in entity_ids if n in self._pagerank],
                key=lambda x: x[1],
                reverse=True,
            )[:top_n]
            if top_pr:
                lines.append("\n📌 Entidades mais importantes (PageRank):")
                for node_id, score in top_pr:
                    data = self.graph.nodes[node_id]
                    label = data.get("label", node_id)
                    ntype = data.get("type", "")
                    doc_count = sum(
                        1 for pred in self.graph.predecessors(node_id)
                        if pred in self.doc_nodes
                    )
                    lines.append(
                        f"  [{ntype}] {label}  "
                        f"(importância={score:.4f}, mencionado em {doc_count} doc(s))"
                    )

        # Top por Betweenness (pontes)
        if self._betweenness:
            top_bc = sorted(
                [
                    (n, self._betweenness[n])
                    for n in entity_ids
                    if n in self._betweenness and self._betweenness[n] > 0.01
                ],
                key=lambda x: x[1],
                reverse=True,
            )[:3]
            if top_bc:
                lines.append("\n🌉 Conceitos ponte entre domínios (Betweenness):")
                for node_id, score in top_bc:
                    label = self.graph.nodes[node_id].get("label", node_id)
                    lines.append(f"  {label}  (centralidade={score:.4f})")

        # Comunidades
        if self._communities:
            comm_members: Dict[int, List[str]] = defaultdict(list)
            for node_id, comm_id in self._communities.items():
                if node_id not in self.doc_nodes and self.graph.nodes[node_id].get("type") != "keyword":
                    comm_members[comm_id].append(node_id)

            if comm_members:
                lines.append("\n👥 Comunidades de conceitos relacionados:")
                for comm_id, members in sorted(comm_members.items()):
                    if not members:
                        continue
                    # Ordenar membros da comunidade por PageRank
                    top_members = sorted(
                        members,
                        key=lambda m: self._pagerank.get(m, 0),
                        reverse=True,
                    )[:5]
                    labels = [self.graph.nodes[m].get("label", m) for m in top_members]
                    lines.append(f"  Comunidade {comm_id + 1}: {', '.join(labels)}")

        # Conexões por documento
        lines.append("\n📄 Referências por documento recuperado:")
        for doc_id in self.doc_nodes:
            doc_label = self.graph.nodes[doc_id].get("label", doc_id)
            successors = list(self.graph.successors(doc_id))
            if not successors:
                continue
            top_conns = sorted(
                successors,
                key=lambda s: self.graph[doc_id][s].get("weight", 1),
                reverse=True,
            )[:5]
            conn_str = "; ".join(
                f"{self.graph.nodes[s].get('label', s)} "
                f"({self.graph[doc_id][s].get('weight', 1)}×)"
                for s in top_conns
            )
            lines.append(f"  {doc_label}: {conn_str}")

        return "\n".join(lines)

    # ── Visualização interativa ───────────────────────────────────────────────

    def visualize_graph(
        self,
        output_filename: Optional[str] = None,
        output_dir: str = "graph_visualizations",
        show_buttons: bool = True,
    ) -> Optional[str]:
        """
        Gera visualização HTML interativa com PyVis.

        Nós:
          - Documentos: azul escuro, tamanho fixo grande
          - Entidades: coloridas por comunidade, tamanho proporcional ao PageRank
          - Keywords: amarelo, pequenas

        Arestas:
          - Espessura proporcional ao peso (frequência de menção)

        Args:
            output_filename: caminho completo do HTML (tem precedência sobre output_dir)
            output_dir: diretório onde salvar se output_filename não for fornecido
            show_buttons: exibe controles de física/seleção do PyVis

        Returns:
            Caminho do HTML salvo, ou None em caso de erro.
        """
        if not self.graph.nodes:
            logger.warning("Grafo vazio — nada para visualizar.")
            return None

        if output_filename:
            output_path = output_filename
            parent = os.path.dirname(output_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        else:
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"graph_{uuid.uuid4().hex[:8]}.html")

        nt = Network(
            notebook=False,
            cdn_resources="remote",
            height="800px",
            width="100%",
            directed=True,
            select_menu=True,
            filter_menu=True,
        )

        max_pr = max(self._pagerank.values()) if self._pagerank else 1.0

        for node_id, data in self.graph.nodes(data=True):
            label = data.get("label", str(node_id))
            ntype = data.get("type", "unknown")
            mention_count = data.get("mention_count", 0)

            # Hover tooltip com métricas
            tooltip_lines = [f"<b>{label}</b>", f"Tipo: {ntype}"]
            if mention_count:
                tooltip_lines.append(f"Menções: {mention_count}")
            if node_id in self._pagerank:
                tooltip_lines.append(f"PageRank: {self._pagerank[node_id]:.4f}")
            if self._betweenness.get(node_id, 0) > 0.01:
                tooltip_lines.append(f"Betweenness: {self._betweenness[node_id]:.4f}")
            comm_id = self._communities.get(node_id)
            if comm_id is not None:
                tooltip_lines.append(f"Comunidade: {comm_id + 1}")
            title = "<br>".join(tooltip_lines)

            if node_id in self.doc_nodes:
                size = 30
                color = "#1E3D7A"
            elif ntype == "keyword":
                size = 10
                color = "#F5DD7E"
            else:
                pr = self._pagerank.get(node_id, 0.0)
                size = max(12, int(12 + (pr / max_pr) * 22)) if max_pr > 0 else 14
                if comm_id is not None:
                    color = _COMMUNITY_COLORS[comm_id % len(_COMMUNITY_COLORS)]
                else:
                    color = {
                        "article": "#F0A84F",
                        "sumula": "#50C878",
                        "precedent": "#C8A2C8",
                        "lei": "#87CEEB",
                    }.get(ntype, "#97C2FC")

            nt.add_node(str(node_id), label=label, title=title, size=size, color=color)

        for u, v, data in self.graph.edges(data=True):
            etype = data.get("type", "related")
            weight = data.get("weight", 1)
            title = data.get("title", etype)
            width = min(1.0 + weight * 0.4, 6.0)
            color = "#AAAAAA" if etype == "co_mentioned" else "#888888"
            nt.add_edge(str(u), str(v), title=title, value=width, color=color)

        if show_buttons:
            nt.show_buttons(filter_=["physics", "selection"])

        try:
            nt.save_graph(output_path)
            logger.info(f"Grafo salvo em: {output_path}")
            return output_path
        except Exception as exc:
            logger.error(f"Falha ao salvar grafo: {exc}")
            return None
