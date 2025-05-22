# graph_rag.py
import streamlit as st
import networkx as nx
from pyvis.network import Network
import re
import os
import uuid
from collections import Counter

# (Optional) For more advanced semantic similarity if not using existing embeddings
# from sentence_transformers import SentenceTransformer, util

# --- CONFIGURATION ---
# Basic regex patterns for Brazilian legal entities (can be expanded and refined)
# Consider moving to a separate config file or class if they become numerous
PATTERNS = {
    "article": re.compile(
        r"(art\.|artigo|arts\.|artigos)\s*"  # Art. Artigo, Arts. Artigos
        r"(\d+[º°ª]?[-\w\/]*)"  # Number, e.g., 1, 1-A, 1.234, 5º, L9099/95 (within article context)
        r"(\s*(?:par[áa]grafo[\súuÚnico]*|§)[\s\dº°ª\w\-]*)*"  # Optional Paragraphs, e.g., § 1º, Parágrafo único
        r"(\s*(?:inciso|inc\.)[\s\wIVXLCDM\-º°ª]*)*"  # Optional Incisos, e.g., inc I, Inciso XV
        r"(\s*(?:al[íi]nea)?\s*[\w]\))*" # Optional Alíneas e.g., a)
        r"(\s*d[aoes]?\s*(?:Constituiç[ãa]o Federal|CF|C[oó]digo\s*[\w\s]+|Lei\s*(?:Complementar\s*)?n?[º°ª]?\s*[\d\.\/\-]+|CLT|CPC|CC|CP|CTN|CDC|Estatuto[\w\s]*|Decreto-Lei|Dec\.\s*nº))?",
        re.IGNORECASE
    ),
    "sumula": re.compile(
        r"(s[úu]mula)\s*(?:vinculante\s*)?(?:n?[º°ª]?\s*)?" # Súmula, Súmula Vinculante, nº
        r"(\d+)" # Number of the súmula
        r"(\s*d[aoes]?\s*(STF|STJ|TST|TNU|TRF\d*|TJ\w*))?", # Issuing court
        re.IGNORECASE
    ),
    "precedent": re.compile( # Basic pattern for case numbers like REsp, HC, AgRg etc.
        r"\b((?:REsp|HC|AgRg|AREsp|RR|AP|RMS|MS|AI|EAREsp|ERE|CC|PET|SL|SS|RHC|RMS|Ag|AR|ACO|ADC|ADI|ADO|ADPF|IF|MI|MC| ইনquérito|QO|RC|Rcl|RE|RI|RP|RvC|STA|TP)\s*[\d\.\-\/]+)\b",
        re.IGNORECASE
    )
    # Add more patterns for "tese", "repercussão geral", "tema repetitivo" etc. as needed.
}

# (Optional) Initialize a sentence transformer model for semantic similarity
# SIMILARITY_MODEL = None
# try:
#     SIMILARITY_MODEL = SentenceTransformer('all-MiniLM-L6-v2') # or a legal-specific one
# except Exception as e:
#     print(f"GraphRAG: Could not load SentenceTransformer model: {e}")

class GraphRAG:
    def __init__(self, retrieved_documents: list, user_query: str):
        """
        Initializes the GraphRAG processor.

        Args:
            retrieved_documents (list): A list of document dictionaries.
                                        Expected keys per dict: 'chunk_id' (or 'id'),
                                        'content', 'arquivo_origem', 'tipo_documento' (optional).
            user_query (str): The original user query for context.
        """
        self.retrieved_documents = retrieved_documents
        self.user_query = user_query
        self.graph = nx.DiGraph() # Directed graph is usually better for citations/mentions
        self.doc_nodes = {} # To quickly map doc_id to its node_id in graph if different
        self.entity_nodes = {} # To quickly map entity label to its node_id

        # Generate unique run ID for temporary files if needed
        self.run_id = uuid.uuid4().hex

        self._build_graph()

    def _normalize_entity_label(self, label: str, entity_type: str) -> str:
        """Normalizes entity labels for consistency."""
        label = label.strip().upper()
        if entity_type == "article":
            label = re.sub(r'\s+', ' ', label) # Consolidate multiple spaces
            label = label.replace("ARTIGO", "ART.").replace("ARTS.", "ART.")
        elif entity_type == "sumula":
            label = re.sub(r'\s+', ' ', label)
            label = label.replace("SÚMULA Nº", "SÚMULA").replace("SÚMULA N.", "SÚMULA")
        return label

    def _extract_entities_from_content(self, doc_id: str, content: str):
        """
        Extracts entities from a given text content using regex patterns
        and adds them to the graph, connecting them to the document.
        """
        if not content:
            return

        # Add document node first if not already present (should be by _build_graph)
        if doc_id not in self.graph:
             # This case should ideally not happen if _build_graph calls this
            doc_data = next((doc for doc in self.retrieved_documents if doc.get('chunk_id', doc.get('id')) == doc_id), None)
            doc_label = doc_data.get('arquivo_origem', doc_id) if doc_data else doc_id
            self.graph.add_node(doc_id, label=doc_label, type='document', title=f"Document: {doc_label}")
            self.doc_nodes[doc_id] = doc_id


        # Extract entities based on patterns
        for entity_type, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                raw_text = match.group(0).strip()
                entity_label = raw_text # Default label

                if entity_type == "article":
                    num = match.group(2)
                    source = (match.group(6) or "").strip()
                    entity_label = f"ART. {num}"
                    if source:
                        entity_label += f" {source.upper()}"
                    entity_label = self._normalize_entity_label(entity_label, "article")
                elif entity_type == "sumula":
                    num = match.group(2)
                    court = (match.group(4) or "").strip()
                    entity_label = f"SÚMULA {num}"
                    if court:
                        entity_label += f" {court.upper()}"
                    entity_label = self._normalize_entity_label(entity_label, "sumula")
                elif entity_type == "precedent":
                    entity_label = self._normalize_entity_label(raw_text, "precedent")


                if entity_label not in self.entity_nodes:
                    self.graph.add_node(entity_label, label=entity_label, type=entity_type, title=f"{entity_type.capitalize()}: {entity_label}")
                    self.entity_nodes[entity_label] = entity_label
                
                # Add edge from document to entity
                self.graph.add_edge(doc_id, entity_label, type=f"mentions_{entity_type}", title=f"Mentions: {raw_text[:50]}...")

        # Extract keywords (simple method: from user query, present in content)
        # More advanced: TF-IDF on retrieved set, NER, LLM-based keyword extraction
        query_keywords = [kw.strip().lower() for kw in self.user_query.split() if len(kw.strip()) > 3]
        content_lower = content.lower()
        for keyword in query_keywords:
            if keyword in content_lower:
                norm_keyword = keyword.upper()
                if norm_keyword not in self.entity_nodes:
                    self.graph.add_node(norm_keyword, label=norm_keyword, type='keyword', title=f"Keyword: {norm_keyword}")
                    self.entity_nodes[norm_keyword] = norm_keyword
                self.graph.add_edge(doc_id, norm_keyword, type='mentions_keyword', title=f"Mentions keyword: {keyword}")


    def _build_graph(self):
        """
        Builds the graph from the retrieved documents.
        - Adds document nodes.
        - Extracts entities (articles, súmulas, keywords) and adds them as nodes.
        - Adds edges representing relationships (e.g., document cites article).
        """
        # 1. Add document nodes
        for doc_data in self.retrieved_documents:
            doc_id = doc_data.get('chunk_id', doc_data.get('id', str(doc_data))) # Ensure unique ID
            doc_label = doc_data.get('arquivo_origem', doc_id)
            doc_type = doc_data.get('tipo_documento', 'document') # Get type from metadata if available
            
            self.graph.add_node(doc_id, label=doc_label, type=doc_type, title=f"{doc_type.capitalize()}: {doc_label}\nQuery: {self.user_query}")
            self.doc_nodes[doc_id] = doc_id # Map original doc_id to graph node_id

            # 2. Extract entities from this document's content
            self._extract_entities_from_content(doc_id, doc_data.get('content', ''))

        # 3. (Optional) Add semantic similarity edges between documents
        # if SIMILARITY_MODEL and len(self.retrieved_documents) > 1:
        #     contents = [doc.get('content', '') for doc in self.retrieved_documents]
        #     doc_ids = [doc.get('chunk_id', doc.get('id', str(doc))) for doc in self.retrieved_documents]
        #     embeddings = SIMILARITY_MODEL.encode(contents, convert_to_tensor=True)
        #     cosine_scores = util.pytorch_cos_sim(embeddings, embeddings)
        #     for i in range(len(doc_ids)):
        #         for j in range(i + 1, len(doc_ids)):
        #             if cosine_scores[i][j] > 0.7: # Similarity threshold
        #                 self.graph.add_edge(doc_ids[i], doc_ids[j], type='semantically_similar', weight=float(cosine_scores[i][j]), title=f"Similarity: {cosine_scores[i][j]:.2f}")


    def get_key_nodes_and_insights(self, top_n_central: int = 5) -> dict:
        """
        Identifies important nodes and extracts insights from the graph.

        Returns:
            dict: Contains 'central_nodes' (list of most connected/central items)
                  and 'document_connections' (dict mapping doc_id to its connections).
        """
        insights = {"central_nodes": [], "document_connections": {}}
        if not self.graph.nodes:
            return insights

        # Identify central entity nodes (not documents themselves initially)
        entity_node_ids = [node_id for node_id, data in self.graph.nodes(data=True) if data.get('type') not in ['document', 'jurisprudência', 'artigo_publicado']] # Exclude document type nodes for this centrality
        
        if not entity_node_ids: # if only document nodes exist
            return insights

        subgraph_entities = self.graph.subgraph(entity_node_ids)
        
        try:
            # Use degree centrality as a simple measure for "importance"
            centrality = nx.degree_centrality(subgraph_entities) # Consider in_degree_centrality for DiGraph if entities are mostly cited
            sorted_nodes = sorted(centrality.items(), key=lambda item: item[1], reverse=True)
        except Exception as e:
            print(f"GraphRAG: Error calculating centrality: {e}. Using simple degree.")
            # Fallback to simple degree if centrality fails (e.g. on very small/disconnected graphs)
            degrees = {node: self.graph.degree(node) for node in subgraph_entities.nodes()}
            sorted_nodes = sorted(degrees.items(), key=lambda item: item[1], reverse=True)


        for node_id, score in sorted_nodes[:top_n_central]:
            node_data = self.graph.nodes[node_id]
            # Find which documents are connected to this central entity
            connected_docs = []
            for pred in self.graph.predecessors(node_id): # Assuming edges go Doc -> Entity
                if self.graph.nodes[pred].get('type') in ['document', 'jurisprudência', 'artigo_publicado']: # Check if predecessor is a document
                    connected_docs.append(self.graph.nodes[pred].get('label', pred))
            
            insights["central_nodes"].append({
                "label": node_data.get("label", node_id),
                "type": node_data.get("type", "unknown"),
                "centrality_score": score,
                "connected_documents": list(set(connected_docs)) # Unique doc labels
            })

        # Get connections for each document
        for doc_node_id, original_doc_id in self.doc_nodes.items():
            doc_label = self.graph.nodes[doc_node_id].get('label', doc_node_id)
            connections = []
            for successor in self.graph.successors(doc_node_id): # Entities mentioned by the doc
                entity_data = self.graph.nodes[successor]
                edge_data = self.graph.get_edge_data(doc_node_id, successor)
                rel_type = edge_data.get('type', 'related_to') if edge_data else 'related_to'
                connections.append({
                    "target_label": entity_data.get("label", successor),
                    "target_type": entity_data.get("type", "unknown"),
                    "relation_type": rel_type
                })
            insights["document_connections"][doc_label] = connections
            
        return insights

    def generate_textual_summary_for_llm(self) -> str:
        """
        Generates a textual summary of the graph's key insights for LLM context.
        """
        insights = self.get_key_nodes_and_insights()
        if not insights["central_nodes"] and not insights["document_connections"]:
            return "No significant structural relationships or key entities were extracted from the provided documents to form a detailed knowledge graph."

        summary_parts = ["Análise estrutural dos documentos recuperados (Grafo de Conhecimento):"]

        if insights["central_nodes"]:
            summary_parts.append("\nPrincipais Entidades/Conceitos Interconectados:")
            for node_info in insights["central_nodes"]:
                doc_list = ", ".join(node_info['connected_documents'][:3]) # Show first 3 connected docs
                doc_count = len(node_info['connected_documents'])
                doc_info = f" (mencionado em {doc_count} documento(s) como: {doc_list}{'...' if doc_count > 3 else ''})" if doc_count else ""
                summary_parts.append(f"- {node_info['type'].capitalize()} '{node_info['label']}'{doc_info}.")
        
        if insights["document_connections"]:
            summary_parts.append("\nConexões por Documento:")
            for doc_label, connections in insights["document_connections"].items():
                if connections:
                    conn_descs = [f"{conn['relation_type'].replace('mentions_', '')} '{conn['target_label']}' ({conn['target_type']})" for conn in connections[:3]] # Show first 3
                    conn_str = "; ".join(conn_descs)
                    summary_parts.append(f"- Documento '{doc_label}' menciona: {conn_str}{'...' if len(connections) > 3 else ''}.")
                else:
                     summary_parts.append(f"- Documento '{doc_label}' não possui conexões explícitas com outras entidades extraídas no grafo.")


        # Add overall graph stats if useful
        num_nodes = self.graph.number_of_nodes()
        num_edges = self.graph.number_of_edges()
        if num_nodes > 0 and num_edges > 0:
            summary_parts.append(f"\nResumo do Grafo: {num_nodes} nós e {num_edges} relações identificadas.")
        elif num_nodes > 0:
            summary_parts.append(f"\nResumo do Grafo: {num_nodes} nós identificados, mas sem relações explícitas entre eles no grafo gerado.")


        return "\n".join(summary_parts)

    def visualize_graph(self, filename_prefix: str = "lexautomate_graph", output_dir: str = "graph_visualizations", show_buttons: bool = True) -> str | None:
        """
        Generates an interactive HTML visualization of the graph using PyVis.

        Args:
            filename_prefix (str): Prefix for the output HTML file.
            output_dir (str): Directory to save the HTML file.
            show_buttons (bool): Whether to show PyVis interaction buttons.

        Returns:
            str | None: The path to the saved HTML file, or None if error.
        """
        if not self.graph.nodes:
            print("GraphRAG: Graph is empty, nothing to visualize.")
            return None

        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        output_filename = f"{filename_prefix}_{self.run_id[:8]}.html"
        output_path = os.path.join(output_dir, output_filename)

        nt = Network(notebook=True, cdn_resources='remote', height="800px", width="100%", directed=isinstance(self.graph, nx.DiGraph), select_menu=True, filter_menu=True)
        
        # Add nodes with specific styling based on 'type'
        for node_id, data in self.graph.nodes(data=True):
            label = data.get('label', node_id)
            node_type = data.get('type', 'unknown')
            title = data.get('title', f"{node_type}: {label}") # Hover text
            size = 15
            color = "#97C2FC" # Default color

            if node_type in ['document', 'jurisprudência', 'artigo_publicado']: # Main documents
                size = 25
                color = "#4A8FF7" # Blue
            elif node_type == 'article':
                size = 18
                color = "#F0A84F" # Orange
            elif node_type == 'sumula':
                size = 18
                color = "#50C878" # Green
            elif node_type == 'precedent':
                size = 18
                color = "#C8A2C8" # Lilac
            elif node_type == 'keyword':
                size = 12
                color = "#F5DD7E" # Yellow
            
            nt.add_node(node_id, label=label, title=title, type=node_type, size=size, color=color)

        # Add edges with specific styling based on 'type'
        for u, v, data in self.graph.edges(data=True):
            edge_type = data.get('type', 'related_to')
            title = data.get('title', edge_type)
            width = 1
            color = "#D3D3D3" # Light gray for default

            if edge_type == 'semantically_similar':
                width = data.get('weight', 0.5) * 3 # Make similarity more visible
                color = "#ADD8E6" # Light blue
            elif 'mentions' in edge_type:
                color = "#A9A9A9" # Darker gray

            # Ensure from_node and to_node are added if not already (pyvis requirement)
            # This should be handled by the node loop above, but as a safeguard:
            # if u not in nt.get_nodes(): nt.add_node(u, label=u) # Simplified, ideally get full data
            # if v not in nt.get_nodes(): nt.add_node(v, label=v)

            nt.add_edge(u, v, title=title, value=width, color=color)


        if show_buttons:
            nt.show_buttons(filter_=['physics', 'selection', 'renderer'])

        try:
            # Configure physics for better layout (optional, can be slow for large graphs)
            # nt.force_atlas_2based(gravity=-50, central_gravity=0.01, spring_length=100, spring_strength=0.08, damping=0.4, overlap=0)
            # nt.barnes_hut(gravity=-8000, central_gravity=0.1, spring_length=250, spring_strength=0.001, damping=0.09, overlap=0.01)
            
            nt.save_graph(output_path)
            print(f"GraphRAG: Graph visualization saved to {output_path}")
            return output_path
        except Exception as e:
            print(f"GraphRAG: Error saving graph visualization: {e}")
            # traceback.print_exc() # For debugging
            return None