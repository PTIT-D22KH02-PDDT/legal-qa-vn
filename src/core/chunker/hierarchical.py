from __future__ import annotations

import json
from typing import Dict, Any, List
from src.schemas import DocumentNode, HierarchicalChunkInput
from src.core.chunker.extract_metadata import Extractor
from pathlib import Path
extractor=Extractor()
class HierarchicalChunker:
    def chunk(
            self,
            data:  HierarchicalChunkInput |Dict[str, Any] | List[Dict[str, Any]],
    ) -> List[DocumentNode]:
        document = self._validate_input(data)
        chunks: List[DocumentNode] = []

        for node in self._get_root_nodes(document):
            chunks.extend(self._walk_node(node=node))

        return chunks

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
    ) -> List[DocumentNode]:
        chunks: List[DocumentNode] = []

        chunk = self._build_chunk(node=node)
        if chunk is not None:
            chunks.append(chunk)

        for child in self._get_children(node):
            chunks.extend(self._walk_node(node=child))

        return chunks

    def _build_chunk(
            self,
            *,
            node: Dict[str, Any],
    ) -> DocumentNode | None:
        node_id = str(node.get("type_id") or "").strip()
        title = self._as_clean_str(node.get("tittle")) if node.get("tittle") else None
        content = self._as_clean_str(node.get("content")) if node.get("content") else None
        refs = self._get_refs(node)
        parent_id = node.get("parent_id")
        type_node=node.get("type")
        full_text=node.get("full_text") if (node.get('type')=='khoan' or node.get('type')=="dieu") else None
        if not any([title, content, refs]):
            return None
        if not node_id:
            raise ValueError("Each hierarchical node must contain a non-empty 'id'")

        # metadata = ChunkMetadata(section_id=node_id)
        # metadata=None
        return DocumentNode(
            id=node_id,
            type=type_node,
            parent_id=parent_id,
            tittle=title,
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

    def _as_clean_str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    def create_document_node(self, file_path : str):
        # result=extractor.process_batch(file_paths=[file_path])
        result=extractor.process_document(file_path=file_path)
        chunks=self.chunk(data=result.tree)
        parent_dir=Path(__file__).resolve().parents[3]
        json_path=parent_dir / "chunk"
        json_path.mkdir(parents=True, exist_ok=True)
        json_file_path=json_path/(result.metadata.so_hieu+".jsonl")
        root_node=DocumentNode(
            id=result.metadata.so_hieu,
            type=result.metadata.loai,
            tittle=result.metadata.ten_van_ban,
        )
        chunks.insert(0, root_node)
        data={
            'metadata': result.metadata.model_dump(),
            'chunks': [c.model_dump() if hasattr(c, 'model_dump') else c for c in chunks]
        }
        with open(json_file_path, "w", encoding="utf-8") as f:
            # Chuyển dict thành chuỗi JSON và thêm dấu xuống dòng \n cho đúng định dạng jsonl
            line = json.dumps(data, ensure_ascii=False)
            f.write(line + "\n")
        return [result.metadata, chunks]


# def main() -> int:
#     input_path = Path(r"C:\Users\ADMIN\Desktop\luu-ban-nhap-tu-dong-9.pdf")
#     if not input_path.exists():
#         raise FileNotFoundError(f"Input file not found: {input_path}")

#     raw_text = extract_file(str(input_path))
#     print(raw_text)
#     payload = build_json_tree(raw_text)
#     print(json.dumps(payload, ensure_ascii=False, indent=2))

#     chunks = HierarchicalChunker().chunk({"payload": payload})
#     output_path = input_path.with_name(f"{input_path.stem}_chunks.json")
#     output_path.write_text(
#         json.dumps([c.model_dump() for c in chunks], ensure_ascii=False, indent=2),
#         encoding="utf-8",
#     )
#     print(f"Saved {len(chunks)} chunks to: {output_path}")
#     return 0


if __name__ == "__main__":
#     raise SystemExit(main())
        parent_dir=Path(__file__).resolve().parent.parent.parent
        json_path=parent_dir / "chunk"
        print(json_path)