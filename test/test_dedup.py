
import logging
from typing import List, Dict, Any, Set, Optional
from pydantic import BaseModel, Field

# Mocking the logging and ChromaQueryResult to make the script standalone
class ChromaQueryResult(BaseModel):
    chunk_id: str
    text: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

# --- The Logic to Test ---

def _get_base_chunk_id(chunk_id: str) -> str:
    """Normalize chunk_id by removing __dup_N suffix from each segment."""
    segments = chunk_id.strip().split(".")
    clean_segments = [
        seg.rsplit("__dup_", 1)[0] if "__dup_" in seg else seg
        for seg in segments
    ]
    return ".".join(clean_segments)

def _filter_redundant_chunks(chunks: List[ChromaQueryResult]) -> List[ChromaQueryResult]:
    """Remove child chunks if an ancestor is present in the results."""
    if not chunks:
        return []

    # Map of base_id to all chunks in results for O(1) lookup
    retrieved_base_ids: Set[str] = {
        _get_base_chunk_id(c.chunk_id) for c in chunks
    }

    filtered: List[ChromaQueryResult] = []
    for chunk in chunks:
        base_id = _get_base_chunk_id(chunk.chunk_id)
        segments = base_id.split(".")

        # Generate all possible ancestors (e.g., A.B.C -> {A, A.B})
        ancestors = {
            ".".join(segments[:depth])
            for depth in range(1, len(segments))
        }

        # If any ancestor exists in the set, this chunk is redundant
        if ancestors & retrieved_base_ids:
            continue
        else:
            filtered.append(chunk)

    return filtered

# --- Test Execution ---

def test():
    cases = [
        {
            "name": "Case 1: Parent and Child (Keep Parent)",
            "input": ["law.art_1", "law.art_1.clause_1"],
            "expected": ["law.art_1"]
        },
        {
            "name": "Case 2: Grandparent and Grandchild (Keep Grandparent)",
            "input": ["law.art_2", "law.art_2.clause_1.point_a"],
            "expected": ["law.art_2"]
        },
        {
            "name": "Case 3: Duplicates handling (__dup_N)",
            "input": ["law.art_3__dup_0", "law.art_3.clause_1"],
            "expected": ["law.art_3__dup_0"]
        },
        {
            "name": "Case 4: Multiple branches (Keep both)",
            "input": ["law.art_4.clause_1", "law.art_5.clause_1"],
            "expected": ["law.art_4.clause_1", "law.art_5.clause_1"]
        },
        {
            "name": "Case 5: Complex mix",
            "input": [
                "doc_1.sec_1",           # Keep (Top level)
                "doc_1.sec_1.sub_1",     # Remove (Child of sec_1)
                "doc_1.sec_2.sub_2",     # Keep (No sec_2 present)
                "doc_1.sec_2.sub_2.p_a"  # Remove (Child of sub_2)
            ],
            "expected": ["doc_1.sec_1", "doc_1.sec_2.sub_2"]
        }
    ]

    print("=== RUNNING DEDUPLICATION TESTS ===\n")
    passed_count = 0
    for c in cases:
        input_chunks = [ChromaQueryResult(chunk_id=cid) for cid in c["input"]]
        results = _filter_redundant_chunks(input_chunks)
        result_ids = [r.chunk_id for r in results]
        
        is_passed = result_ids == c["expected"]
        status = "PASS" if is_passed else "FAIL"
        if is_passed: passed_count += 1
        
        print(f"[{status}] {c['name']}")
        if not is_passed:
            print(f"    Expected: {c['expected']}")
            print(f"    Actual:   {result_ids}")
            
    print(f"\nSummary: {passed_count}/{len(cases)} cases passed.")

if __name__ == "__main__":
    test()
