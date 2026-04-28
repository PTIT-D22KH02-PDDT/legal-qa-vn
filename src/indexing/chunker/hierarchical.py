from __future__ import annotations

import json
from typing import Dict, Any, List
from pathlib import Path
from src.core.models import DocumentNode
from .schemas import HierarchicalChunkInput
from src.indexing.parsing import Extractor


class HierarchicalChunker:
    def __init__(self):
        """Initialize HierarchicalChunker."""
        self.extractor = Extractor()
    
    def chunk(
            self,
            data:  HierarchicalChunkInput | Dict[str, Any] | List[Dict[str, Any]],
    ) -> List[DocumentNode]:
        document = self._validate_input(data)
        
        # Pass 1: Count IDs to detect duplicates
        id_counts: Dict[str, int] = {}
        for node in self._get_root_nodes(document):
            self._count_node_ids(node, id_counts)
        
        # Pass 2: Build chunks with suffix only if duplicate
        chunks: List[DocumentNode] = []
        chunk_id_counters: Dict[str, int] = {}  # Track index for each duplicate ID

        for node in self._get_root_nodes(document):
            chunks.extend(self._walk_node(node=node, id_counts=id_counts, chunk_id_counters=chunk_id_counters))

        return chunks
    
    def _count_node_ids(self, node: Dict[str, Any], id_counts: Dict[str, int]) -> None:
        """Count occurrences of each node ID"""
        node_id = str(node.get("type_id") or "").strip()
        if node_id and any([node.get("title"), node.get("content"), node.get("ref")]):
            id_counts[node_id] = id_counts.get(node_id, 0) + 1
        
        # Count children
        for child in self._get_children(node):
            self._count_node_ids(child, id_counts)

    def _validate_input(
            self,
            data: HierarchicalChunkInput | Dict[str, Any] | List[Dict[str, Any]],
    ) -> HierarchicalChunkInput:
        if isinstance(data, HierarchicalChunkInput):
            return data

        if isinstance(data, list):
            return HierarchicalChunkInput(json=data)

        if isinstance(data, dict) and ("json" in data or "payload" in data):
            return HierarchicalChunkInput.model_validate(data)

        if isinstance(data, dict):
            return HierarchicalChunkInput(json=data)

        raise TypeError("HierarchicalChunker.chunk expects HierarchicalChunkInput, dict, or list[dict]")

    def _get_root_nodes(self, document: HierarchicalChunkInput) -> List[Dict[str, Any]]:
        if isinstance(document.payload, list):
            return document.payload
        return [document.payload]

    def _walk_node(
            self,
            *,
            node: Dict[str, Any],
            id_counts: Dict[str, int],
            chunk_id_counters: Dict[str, int],
    ) -> List[DocumentNode]:
        chunks: List[DocumentNode] = []

        chunk = self._build_chunk(node=node, id_counts=id_counts, chunk_id_counters=chunk_id_counters)
        if chunk is not None:
            chunks.append(chunk)

        for child in self._get_children(node):
            chunks.extend(self._walk_node(node=child, id_counts=id_counts, chunk_id_counters=chunk_id_counters))

        return chunks

    def _as_clean_str(self, value: Any) -> str | None:
        """Clean and validate string value."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    
    def _build_chunk(
            self,
            *,
            node: Dict[str, Any],
            id_counts: Dict[str, int],
            chunk_id_counters: Dict[str, int],
    ) -> DocumentNode | None:
        node_id = str(node.get("type_id") or "").strip()
        title = self._as_clean_str(node.get("title")) if node.get("title") else None
        content = self._as_clean_str(node.get("content")) if node.get("content") else None
        refs = self._get_refs(node)
        parent_id = node.get("parent_id")
        type_node=node.get("type")
        full_text=node.get("full_text") if (node.get('type')=='khoan' or node.get('type')=="dieu") else None
        parent_context = node.get("parent_context")
        if not any([title, content, refs]):
            return None
        if not node_id:
            raise ValueError("Each hierarchical node must contain a non-empty 'id'")

        # Add counter suffix ONLY if this ID has duplicates (count > 1)
        if id_counts.get(node_id, 0) > 1:
            # Track index for this duplicate ID
            if node_id in chunk_id_counters:
                chunk_id_counters[node_id] += 1
            else:
                chunk_id_counters[node_id] = 0
            unique_id = f"{node_id}__dup_{chunk_id_counters[node_id]}"
        else:
            # No duplicate - keep ID as is
            unique_id = node_id

        return DocumentNode(
            id=unique_id,
            type=type_node,
            parent_id=parent_id,
            title=title,
            parent_context=parent_context,
            content=content,
            full_text=full_text,
            reference=refs
        )
    def _get_children(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        children = node.get("con", [])
        if not isinstance(children, list):
            return []
        return [child for child in children if isinstance(child, dict)]

    def _get_refs(self, node: Dict[str, Any]) -> List[str]:
        refs = node.get("ref", [])
        if not isinstance(refs, list):
            return []
        return [str(ref).strip() for ref in refs if str(ref).strip()]
    
    def create_document_node(self, file_path: str) -> tuple[Any, List[DocumentNode]]:
        """Process document and create chunks.
        
        Args:
            file_path: Path to input document
            
        Returns:
            Tuple of (metadata, chunks)
        """
        result = self.extractor.process_document(file_path=file_path)
        chunks = self.chunk(data=result.tree)
        
        # Save to output directory
        output_dir = Path(__file__).resolve().parents[3] / "chunk"
        output_dir.mkdir(parents=True, exist_ok=True)
        json_file_path = output_dir / f"{result.metadata.so_hieu}.jsonl"
        
        # Create root node
        root_node = DocumentNode(
            id=result.metadata.so_hieu,
            type=result.metadata.loai,
            title=result.metadata.ten_van_ban,
        )
        chunks.insert(0, root_node)
        
        data = {
            'metadata': result.metadata.model_dump(),
            'chunks': [c.model_dump() if hasattr(c, 'model_dump') else c for c in chunks]
        }
        with open(json_file_path, "w", encoding="utf-8") as f:
            line = json.dumps(data, ensure_ascii=False)
            f.write(line + "\n")
        
        return result.metadata, chunks