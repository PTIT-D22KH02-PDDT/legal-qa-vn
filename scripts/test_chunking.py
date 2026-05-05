from __future__ import annotations
import re
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = PROJECT_ROOT / ".temp" / "Thong-tu-108-2020-TT-BTC.docx"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def shorten(text: str | None, max_length: int) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def run_chunking(file_path: Path, limit: int, output_path: Path | None) -> None:
    from src.indexing.chunker import create_chunker

    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

    chunker = create_chunker(strategy="hierarchical")
    metadata, chunks = chunker.create_document_node(str(file_path))

    print(f"File: {file_path}")
    print(f"Strategy: hierarchical")
    print(f"Số hiệu: {getattr(metadata, 'so_hieu', '')}")
    print(f"Tên văn bản: {getattr(metadata, 'ten_van_ban', '')}")
    print(f"Tổng số chunk: {len(chunks)}")

    print("\nThống kê theo type:")
    for chunk_type, count in Counter(chunk.type or "unknown" for chunk in chunks).most_common():
        print(f"  {chunk_type}: {count}")

    print(f"\nPreview {min(limit, len(chunks))} chunk đầu:")
    print("-" * 100)
    for index, chunk in enumerate(chunks[:limit], start=1):
        print(f"#{index:03d} id={chunk.id} | type={chunk.type} | parent={chunk.parent_id or ''}")

        title = shorten(chunk.title, 120)
        content = shorten(chunk.content, 220)
        parent_context = shorten(chunk.parent_context, 160)
        raw_references = chunk.reference or []
        if isinstance(raw_references, str):
            references = raw_references
        else:
            references = ", ".join(str(ref) for ref in raw_references)

        if title:
            print(f"  title: {title}")
        if parent_context:
            print(f"  parent_context: {parent_context}")
        if content:
            print(f"  content: {content}")
        if references:
            print(f"  ref: {references}")
    print("-" * 100)

    safe_so_hieu = re.sub(r"[\\/]+", "_", str(getattr(metadata, "so_hieu", "")).strip()) or "unknown"
    auto_json = PROJECT_ROOT / "chunk" / f"{safe_so_hieu}.json"    # Tạo payload để lưu/in
    payload = {
        "file": str(file_path),
        "strategy": "hierarchical",
        "metadata": dump_model(metadata),
        "total_chunks": len(chunks),
        "chunks": [dump_model(chunk) for chunk in chunks],
    }
    json_str = json.dumps(payload, ensure_ascii=False, indent=2)

    # Luôn ghi file JSON ra auto_json
    auto_json.parent.mkdir(parents=True, exist_ok=True)
    auto_json.write_text(json_str, encoding="utf-8")
    print(f"\n✅ File JSON tự sinh: {auto_json}")

    # In FULL JSON output
    print("\n" + "=" * 100)
    print("JSON OUTPUT (FULL CHUNKING RESULT)")
    print("=" * 100)
    print(json_str)

    # Nếu có output_path, ghi thêm file đó
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_str, encoding="utf-8")
        print(f"\n✅ File JSON đầy đủ: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test chunking cho một file văn bản pháp luật.")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_FILE,
        help=f"Đường dẫn file .docx/.doc/.pdf, mặc định: {DEFAULT_FILE}",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Số chunk đầu tiên cần in preview.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Nếu truyền vào, lưu toàn bộ chunks ra file JSON.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_chunking(
        file_path=args.file,
        limit=max(args.limit, 0),
        output_path=args.output,
    )
