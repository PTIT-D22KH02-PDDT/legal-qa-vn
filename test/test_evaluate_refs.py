"""
Test file for LegalAgentTools._evaluate_refs

Strategy: Mock chroma_store.get_by_ids and api_client.generate
so that no real DB or LLM connection is needed.
"""
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Minimal stubs (replicate only what the test needs, no project imports)
# ---------------------------------------------------------------------------

class ChromaQueryResult:
    def __init__(self, chunk_id: str, text: str = "", metadata: Dict[str, Any] = None):
        self.chunk_id = chunk_id
        self.text = text
        self.metadata = metadata or {}


def _get_base_chunk_id(chunk_id: str) -> str:
    segments = chunk_id.strip().split(".")
    clean = [seg.rsplit("__dup_", 1)[0] if "__dup_" in seg else seg for seg in segments]
    return ".".join(clean)


# ---------------------------------------------------------------------------
# Inline _evaluate_refs (copy logic from tools.py, using stubs above)
# ---------------------------------------------------------------------------

def _evaluate_refs(
    chroma_store,
    api_client,
    query: str,
    main_chunk: ChromaQueryResult,
    score_threshold: float = 6.0,
    max_refs: int = 3,
) -> List[ChromaQueryResult]:
    """Standalone copy of LegalAgentTools._evaluate_refs for isolated testing."""

    if api_client is None:
        return []

    raw_refs: List[str] = []
    ref_field = main_chunk.metadata.get("reference")
    if ref_field:
        try:
            parsed = json.loads(ref_field)
            if isinstance(parsed, list):
                raw_refs = [str(r).strip() for r in parsed if r]
        except (json.JSONDecodeError, TypeError):
            pass

    if not raw_refs:
        return []

    # Step 1: Pre-filter family relations
    main_base_id = _get_base_chunk_id(main_chunk.chunk_id)
    candidate_ref_ids: List[str] = []
    for ref_id in raw_refs:
        ref_base_id = _get_base_chunk_id(ref_id)
        is_ancestor   = main_base_id.startswith(ref_base_id + ".")
        is_descendant = ref_base_id.startswith(main_base_id + ".")
        if not (is_ancestor or is_descendant):
            candidate_ref_ids.append(ref_id)

    if not candidate_ref_ids:
        return []

    # Step 2: Batch fetch — drop IDs missing in DB
    fetched: List[ChromaQueryResult] = chroma_store.get_by_ids(candidate_ref_ids)
    ref_by_id = {c.chunk_id: c for c in fetched}
    valid_ref_chunks = [ref_by_id[rid] for rid in candidate_ref_ids if rid in ref_by_id]

    if not valid_ref_chunks:
        return []

    # Step 3: LLM grading
    refs_block = "\n".join(
        f'[{c.chunk_id}]\n{c.metadata.get("full_text") or c.text}'
        for c in valid_ref_chunks
    )
    prompt = (
        "Ban la chuyen gia phap ly.\n\n"
        f"Cau hoi: {query}\n\n"
        f"Noi dung chinh:\n{main_chunk.metadata.get('full_text') or main_chunk.text}\n\n"
        f"Tham chieu can danh gia:\n{refs_block}\n\n"
        "Cham diem 0-10. Chi tra ve JSON thuan tuy.\n"
        '{"<chunk_id>": <score>, ...}'
    )

    try:
        raw_response = api_client.generate(prompt=prompt, max_length=256, temperature=0.0)
        scores: Dict[str, Any] = json.loads(raw_response)
    except Exception:
        return []

    scored = []
    for chunk in valid_ref_chunks:
        try:
            score = float(scores.get(chunk.chunk_id, 0))
        except (TypeError, ValueError):
            continue
        if score >= score_threshold:
            scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max_refs]]


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def make_chunk(chunk_id: str, text: str = "noi dung", refs: List[str] = None) -> ChromaQueryResult:
    metadata = {}
    if refs is not None:
        metadata["reference"] = json.dumps(refs, ensure_ascii=False)
    return ChromaQueryResult(chunk_id=chunk_id, text=text, metadata=metadata)


def run_tests():
    print("=== RUNNING _evaluate_refs TESTS ===\n")
    passed = 0
    total = 0

    def check(name: str, result_ids: List[str], expected_ids: List[str]):
        nonlocal passed, total
        total += 1
        ok = result_ids == expected_ids
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"[{status}] {name}")
        if not ok:
            print(f"    Expected: {expected_ids}")
            print(f"    Actual:   {result_ids}")

    # -----------------------------------------------------------------------
    # Case 1: No api_client -> always return []
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5", refs=["law.dieu_3"])
    result = _evaluate_refs(MagicMock(), None, "query", main)
    check("Case 1: No api_client returns []", [c.chunk_id for c in result], [])

    # -----------------------------------------------------------------------
    # Case 2: Chunk has no reference field -> return []
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5")       # no refs key in metadata
    api = MagicMock()
    chroma = MagicMock()
    result = _evaluate_refs(chroma, api, "query", main)
    check("Case 2: No reference field returns []", [c.chunk_id for c in result], [])

    # -----------------------------------------------------------------------
    # Case 3: Ref is ancestor (parent) of main -> pre-filtered out
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5.khoan_1", refs=["law.dieu_5"])  # dieu_5 is parent
    chroma = MagicMock()
    api = MagicMock()
    result = _evaluate_refs(chroma, api, "query", main)
    check("Case 3: Ancestor ref pre-filtered, returns []", [c.chunk_id for c in result], [])

    # -----------------------------------------------------------------------
    # Case 4: Ref is descendant (child) of main -> pre-filtered out
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5", refs=["law.dieu_5.khoan_1"])  # khoan_1 is child
    chroma = MagicMock()
    api = MagicMock()
    result = _evaluate_refs(chroma, api, "query", main)
    check("Case 4: Descendant ref pre-filtered, returns []", [c.chunk_id for c in result], [])

    # -----------------------------------------------------------------------
    # Case 5: Ref not found in DB (parse error) -> dropped silently
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5", refs=["law.dieu_99"])
    chroma = MagicMock()
    chroma.get_by_ids.return_value = []   # DB returns nothing
    api = MagicMock()
    result = _evaluate_refs(chroma, api, "query", main)
    check("Case 5: Non-existent ref_id dropped, returns []", [c.chunk_id for c in result], [])

    # -----------------------------------------------------------------------
    # Case 6: Valid ref, LLM gives score >= threshold -> kept
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5", refs=["law.dieu_3"])
    ref_chunk = make_chunk("law.dieu_3", text="Noi dung dieu 3")
    chroma = MagicMock()
    chroma.get_by_ids.return_value = [ref_chunk]
    api = MagicMock()
    api.generate.return_value = json.dumps({"law.dieu_3": 8.5})
    result = _evaluate_refs(chroma, api, "Dieu 5 quy dinh gi?", main)
    check("Case 6: Score 8.5 >= 6.0, ref kept", [c.chunk_id for c in result], ["law.dieu_3"])

    # -----------------------------------------------------------------------
    # Case 7: Valid ref, LLM gives score < threshold -> dropped
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5", refs=["law.dieu_3"])
    ref_chunk = make_chunk("law.dieu_3", text="Noi dung dieu 3")
    chroma = MagicMock()
    chroma.get_by_ids.return_value = [ref_chunk]
    api = MagicMock()
    api.generate.return_value = json.dumps({"law.dieu_3": 3.0})   # low score
    result = _evaluate_refs(chroma, api, "query", main)
    check("Case 7: Score 3.0 < 6.0, ref dropped", [c.chunk_id for c in result], [])

    # -----------------------------------------------------------------------
    # Case 8: Multiple refs, only top max_refs=2 kept by score
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5", refs=["law.dieu_1", "law.dieu_2", "law.dieu_3"])
    r1 = make_chunk("law.dieu_1", text="ref 1")
    r2 = make_chunk("law.dieu_2", text="ref 2")
    r3 = make_chunk("law.dieu_3", text="ref 3")
    chroma = MagicMock()
    chroma.get_by_ids.return_value = [r1, r2, r3]
    api = MagicMock()
    api.generate.return_value = json.dumps({
        "law.dieu_1": 9.0,   # highest
        "law.dieu_2": 4.0,   # below threshold -> dropped
        "law.dieu_3": 7.5,   # second highest
    })
    result = _evaluate_refs(chroma, api, "query", main, score_threshold=6.0, max_refs=2)
    check(
        "Case 8: 3 refs, score 9/4/7.5, max_refs=2 keeps top 2",
        [c.chunk_id for c in result],
        ["law.dieu_1", "law.dieu_3"],   # sorted by score desc
    )

    # -----------------------------------------------------------------------
    # Case 9: LLM returns invalid JSON -> return []
    # -----------------------------------------------------------------------
    main = make_chunk("law.dieu_5", refs=["law.dieu_3"])
    ref_chunk = make_chunk("law.dieu_3", text="ref text")
    chroma = MagicMock()
    chroma.get_by_ids.return_value = [ref_chunk]
    api = MagicMock()
    api.generate.return_value = "INVALID JSON {{{"
    result = _evaluate_refs(chroma, api, "query", main)
    check("Case 9: LLM returns invalid JSON, returns []", [c.chunk_id for c in result], [])

    print(f"\nSummary: {passed}/{total} cases passed.")


if __name__ == "__main__":
    run_tests()
