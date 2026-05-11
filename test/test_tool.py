"""
Test cases cho LegalAgentTools.

Chạy:
    uv run src/agent/test_tool.py
"""
import sys
import logging
from pathlib import Path

# Đảm bảo project root trong sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.WARNING)  # Tắt bớt log của thư viện

# ---------------------------------------------------------------------------
# Khởi tạo dependencies — tham khảo main.py
# ---------------------------------------------------------------------------
import yaml
from main import build_chroma_store, build_search_service, resolve_project_path

CONFIG_PATH = PROJECT_ROOT / "configs" / "search_config.yaml"
APP_CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

from system.database.db_respository import (
    DatabaseConfig,
    DatabaseManager,
    DocumentMetadataRepository,
)
from src.agent.tools import LegalAgentTools


def build_tools() -> LegalAgentTools:
    """Khởi tạo LegalAgentTools với remote embedding và rerank (giống main.py)."""
    # Lấy cấu hình remote search từ config
    search_config = APP_CONFIG["search"]["remote"]
    use_remote_embedding = search_config.get("use_remote_embedding", True)
    use_rerank = search_config.get("use_rerank", True)
    use_remote_rerank = search_config.get("use_remote_rerank", True)

    # Khởi tạo SearchService với remote options
    search_service = build_search_service(
        use_remote_embedding=use_remote_embedding,
        use_rerank=use_rerank,
        use_remote_rerank=use_remote_rerank,
        app_config=APP_CONFIG,
    )

    # Lấy chroma_store từ search_service hoặc khởi tạo mới nếu cần
    chroma_store = search_service.chroma_store

    # Khởi tạo Database
    db_config = DatabaseConfig()
    db_manager = DatabaseManager(db_config)
    session = db_manager.get_session()
    meta_repo = DocumentMetadataRepository(session)

    return LegalAgentTools(
        search_service=search_service,
        chroma_store=chroma_store,
        meta_repo=meta_repo,
    )


SEP = "-" * 60

def print_result(label: str, output):
    print(f"\n{SEP}")
    print(f"[TEST] {label}")
    print(f"  success     : {output.success}")
    print(f"  tool_name   : {output.tool_name}")
    if output.error:
        print(f"  error       : {output.error}")
    if output.chunks:
        print(f"  chunks      : {len(output.chunks)} ket qua")
        for i, c in enumerate(output.chunks[:2], 1):
            meta = c.metadata or {}
            print(f"    [{i}] {c.chunk_id} | dieu={meta.get('dieu')} | khoan={meta.get('khoan')}")
            print(f"         {c.text[:120].strip()}...")
    if output.documents:
        print(f"  documents   : {len(output.documents)} van ban")
        for i, d in enumerate(output.documents[:3], 1):
            print(f"    [{i}] {d.so_hieu} | {d.ten_van_ban} | {d.loai} | {d.linh_vuc}")
    print(f"{SEP}")


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_vector_search(tools: LegalAgentTools):
    """TC1: Tìm kiếm ngữ nghĩa câu hỏi pháp lý."""
    out = tools.vector_search(
        query="quyền và nghĩa vụ của người lao động",
        top_k_retrieve=20,
        top_k_rerank=5,
        use_rerank=True,
    )
    print_result("vector_search — quyen va nghia vu nguoi lao dong", out)
    assert out.tool_name == "vector_search"


def test_chunk_metadata_search_by_so_hieu_and_dieu(tools: LegalAgentTools):
    """TC2: Tìm chính xác Khoản 4 Điều 10 Nghị định 88/2023/NĐ-CP."""
    out = tools.chunk_metadata_search(
        so_hieu="12/2022/NĐ-CP",
        dieu=4,
        khoan=1
    )
    print_result("chunk_metadata_search — so_hieu=12/2022/NĐ-CP, dieu=4, khoan=1", out)
    assert out.tool_name == "chunk_metadata_search"


def test_chunk_metadata_search_by_dieu_khoan(tools: LegalAgentTools):
    """TC3: Tìm Điều 5, Khoản 1 (không rõ văn bản)."""
    out = tools.chunk_metadata_search(
        dieu=5,
        khoan=1,
        top_k=3,
    )
    print_result("chunk_metadata_search — dieu=5, khoan=1", out)
    assert out.tool_name == "chunk_metadata_search"


def test_chunk_metadata_search_no_criteria(tools: LegalAgentTools):
    """TC4: Không truyền tiêu chí nào — expect success=False."""
    out = tools.chunk_metadata_search()
    print_result("chunk_metadata_search — no criteria (expect fail)", out)
    assert out.success is False


def test_doc_metadata_by_so_hieu(tools: LegalAgentTools):
    """TC5: Tra cứu văn bản theo số hiệu chính xác."""
    # "Khoản 4 Điều 10 Nghị định 12/2022/NĐ-CP"
    out = tools.doc_metadata_search(so_hieu="12/2022/NĐ-CP")
    print_result("doc_metadata_search — so_hieu=12/2022/NĐ-CP", out)
    assert out.tool_name == "doc_metadata_search"


def test_doc_metadata_by_ten_van_ban(tools: LegalAgentTools):
    """TC6: Tìm văn bản theo tên (fuzzy)."""
    # out = tools.doc_metadata_search(ten_van_ban="Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ", limit=5)
    # print_result("doc_metadata_search — ten_van_ban='Luật Phòng cháy, chữa cháy và cứu nạn, cứu hộ'", out)
    out = tools.doc_metadata_search(ten_van_ban="Bộ luật hình sự", limit=5)
    print_result("doc_metadata_search — ten_van_ban='Bộ luật hình sự'", out)
    assert out.tool_name == "doc_metadata_search"


def test_doc_metadata_by_loai(tools: LegalAgentTools):
    """TC7: Tìm tất cả văn bản loại 'Nghị định'."""
    out = tools.doc_metadata_search(loai="Nghị định")
    print_result("doc_metadata_search — loai='Nghị định'", out)
    assert out.tool_name == "doc_metadata_search"


def test_doc_metadata_by_linh_vuc(tools: LegalAgentTools):
    """TC8: Tìm văn bản theo lĩnh vực."""
    out = tools.doc_metadata_search(linh_vuc="lao động", limit=5)
    print_result("doc_metadata_search — linh_vuc='lao dong'", out)
    assert out.tool_name == "doc_metadata_search"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Khoi tao LegalAgentTools ===")
    tools = build_tools()
    print("OK\n")

    tests = [
        # test_vector_search,
        test_chunk_metadata_search_by_so_hieu_and_dieu,
        # test_chunk_metadata_search_by_dieu_khoan,
        # test_chunk_metadata_search_no_criteria,
        test_doc_metadata_by_so_hieu,
        test_doc_metadata_by_ten_van_ban,
        test_doc_metadata_by_loai,
        # test_doc_metadata_by_linh_vuc,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn(tools)
            passed += 1
        except Exception as e:
            print(f"\n[FAIL] {test_fn.__name__}: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Ket qua: {passed} passed / {failed} failed / {len(tests)} total")
    print(f"{'='*60}")
