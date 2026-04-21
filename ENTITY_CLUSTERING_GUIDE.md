# Entity Clustering - Visual Flow Guide

## Old Flow (Global Grouping) ❌

```
Query: "khoản 2 điều 5 và điểm a, khoản 1 điều 37"
                    ↓
         ┌─────────────────────┐
         │  LLM Analyzer       │
         └─────────────────────┘
                    ↓
    ┌────────────────────────────────┐
    │ article_sections: {            │
    │   dieu_numbers: [5, 37],       │  ← All items FLATTENED
    │   khoan_numbers: [2, 1],       │    globally by type
    │   diem_names: ["a"],           │
    │   ...                          │
    │ }                              │
    │ extracted_entities: [          │
    │   {type: dieu, value: 5},      │
    │   {type: khoan, value: 2},     │
    │   {type: khoan, value: 1},     │
    │   {type: diem, value: "a"}     │
    │ ]                              │
    └────────────────────────────────┘
                    ↓
         ┌─────────────────────┐
         │  Router             │
         └─────────────────────┘
                    ↓
         ❌ Router confused:
            "Which khoan belongs to which dieu?"
            Calls: get_specific_article(dieu=5, khoan=2)
            But also mixed with dieu=37 info
```

---

## New Flow (Context-Based Clustering) ✅

```
Query: "khoản 2 điều 5 và điểm a, khoản 1 điều 37"
                    ↓
         ┌─────────────────────┐
         │  LLM Analyzer       │
         │  (with prompts)     │
         └─────────────────────┘
                    ↓
    ┌────────────────────────────────┐
    │ extracted_blocks: [            │
    │   {                            │  ← BLOCK 1
    │     dieu: 5,                   │    (điều 5 cluster)
    │     khoan: 2,                  │
    │     diem: "a",                 │
    │     document_name: "..."       │
    │   },                           │
    │   {                            │  ← BLOCK 2
    │     dieu: 37,                  │    (điều 37 cluster)
    │     khoan: 1,                  │
    │     diem: null,                │
    │     document_name: "..."       │
    │   }                            │
    │ ]                              │
    └────────────────────────────────┘
                    ↓
         ┌─────────────────────┐
         │  Router             │
         │  (multi-block)      │
         └─────────────────────┘
                    ↓
         ✅ Router knows context!
            Call 1: get_specific_article(
                dieu=5, khoan=2, diem="a"
            )
            Call 2: get_specific_article(
                dieu=37, khoan=1, diem=null
            )
            ↓
         Retrieve 2 separate legal items
         with correct context
```

---

## Block Definition

```
ArticleBlock = {
  dieu: int|null           ← Số điều (primary)
  khoan: int|null          ← Số khoản (optional, belongs to dieu)
  diem: str|null           ← Tên điểm (optional, belongs to khoan)
  chuong: int|null         ← Số chương (optional, parent of dieu)
  document_name: str|null  ← Tài liệu liên quan
}
```

### Hierarchy
```
Chương N
  └─ Điều M (dieu)
      └─ Khoản K (khoan)
          └─ Điểm X (diem)
```

---

## Clustering Rules (LLM Instruction)

### Rule 1: New Điều = New Block
```
"điều 5 và điều 37" 
→ 2 blocks (each dieu gets its own block)
```

### Rule 2: Khoản + Điểm Same Block
```
"khoản 2 điều 5 và điểm a"
→ 1 block (both refer to same điều 5)
{dieu: 5, khoan: 2, diem: "a"}
```

### Rule 3: Multiple Điểm = Multiple Blocks
```
"điểm a, b của khoản 1 điều 5"
→ 2 blocks (one per điểm):
  Block 1: {dieu: 5, khoan: 1, diem: "a"}
  Block 2: {dieu: 5, khoan: 1, diem: "b"}
```

### Rule 4: Different Document = New Block
```
"điều 5 luật A và điều 5 luật B"
→ 2 blocks (different documents)
  Block 1: {dieu: 5, document: "luật A"}
  Block 2: {dieu: 5, document: "luật B"}
```

---

## Impact on Tools

### Before: Single Tool Call ❌
```python
get_specific_article(
    dieu_number=5,
    khoan_number=[2, 1],      ← Ambiguous!
    diem_names=["a"],
    document_name="..."
)
# Tool doesn't know how to match khoản to dieu
```

### After: Multiple Tool Calls ✅
```python
# Call 1
get_specific_article(
    dieu_number=5,
    khoan_number=2,
    diem_name="a",
    document_name="bộ luật dân sự"
)

# Call 2  
get_specific_article(
    dieu_number=37,
    khoan_number=1,
    diem_name=None,
    document_name="bộ luật dân sự"
)
# Each call is precise and unambiguous
```

---

## Code Integration Points

| Component | Change | Impact |
|-----------|--------|--------|
| **schemas.py** | ArticleBlock replaces ArticleSection + ArticleItem | Data structure simplified |
| **llm_prompt_instruction.py** | Prompt teaches block extraction | LLM outputs blocks instead of flat lists |
| **llm_query_analyzer.py** | Parse extracted_blocks from JSON | Converts LLM response to ArticleBlock list |
| **agent.py** | Logging shows blocks | Better debugging visibility |
| **router.py** | Iterate blocks → multiple tool calls | Each block = separate retrieval |
| **test_agent.py** | Test cases use ArticleBlock | Tests match new schema |

---

## Testing Strategy

1. **Unit Tests**: `pytest src/agent/test_agent.py`
   - Verify block parsing
   - Verify router multi-block handling

2. **Integration Test**: `python test_llm_analyzer.py`
   - End-to-end: Query → LLM → Blocks → Router

3. **Example Queries**:
   ```
   1. Simple: "Điều 5" → 1 block
   2. Multi-article: "Điều 5 và 37" → 2 blocks
   3. Multi-level: "Khoản 2 điều 5 điểm a" → 1 block
   4. Mixed: "Khoản 2 điều 5 và khoản 1 điều 37" → 2 blocks
   ```

---

## Summary

✅ **Problem Solved**: Entity extraction now understands context
✅ **Data Structure**: ArticleBlock represents independent legal item clusters
✅ **Prompt**: LLM trained to extract by context (STEP 3 instructions)
✅ **Parsing**: LLM response converted to ArticleBlock list
✅ **Routing**: Each block gets independent tool invocation
✅ **Tests**: All test cases updated to validate new structure

🎯 **Result**: Precise legal item retrieval with correct hierarchical context
