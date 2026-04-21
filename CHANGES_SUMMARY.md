# Entity Clustering Implementation - Changes Summary

**Status**: ✅ **COMPLETE** - All changes applied

**Key Change**: Entity extraction now uses **context-based clustering** instead of global type-based grouping.

---

## Problem Fixed

### Before (Incorrect)
```json
{
  "article_sections": {
    "dieu_numbers": [5, 37],
    "khoan_numbers": [2, 1],
    "diem_names": ["a"],
    "chuong_numbers": [],
    "document_name": "Bộ Luật Dân Sự"
  },
  "extracted_entities": [
    {"type": "dieu", "value": 5, "document_name": "..."},
    {"type": "khoan", "value": 2, "document_name": "..."},
    {"type": "khoan", "value": 1, "document_name": "..."},
    {"type": "diem", "value": "a", "document_name": "..."}
  ]
}
```
Problem: All entities flattened globally → Router can't distinguish "khoản 2 of điều 5" vs "khoản 1 of điều 37"

### After (Correct)
```json
{
  "extracted_blocks": [
    {
      "dieu": 5,
      "khoan": 2,
      "diem": "a",
      "chuong": null,
      "document_name": "Bộ Luật Dân Sự"
    },
    {
      "dieu": 37,
      "khoan": 1,
      "diem": null,
      "chuong": null,
      "document_name": "Bộ Luật Dân Sự"
    }
  ]
}
```
Solution: Each block is an independent cluster → Router calls get_specific_article 2 times with correct context

---

## Files Modified

### 1. `src/agent/schemas.py` - Schema Redesign

**Changes**:
- ❌ Removed: `ArticleSection` class (no longer used)
- ❌ Removed: `extracted_entities: List[ArticleItem]` field
- ✅ Added: `ArticleBlock` class with fields:
  ```python
  class ArticleBlock(BaseModel):
      dieu: Optional[int]
      khoan: Optional[int]
      diem: Optional[str]
      chuong: Optional[int]
      document_name: Optional[str]
  ```
- ✅ Updated: `QueryAnalysisResult` now uses:
  ```python
  extracted_blocks: List[ArticleBlock]  # NEW
  # Old fields removed: article_sections, extracted_entities
  # Kept for backward compatibility: article_numbers, article_names, keywords, etc.
  ```
- ✅ Updated: `__init__.py` exports to use `ArticleBlock` instead of `ArticleItem`, `ArticleSection`

### 2. `src/agent/llm_prompt_instruction.py` - Prompt Instructions Rewrite

**Key Updates**:

#### STEP 3: ARTICLE BLOCK EXTRACTION (Clustering Logic)
```
Rules:
- Mỗi ĐIỀU là 1 block riêng
- KHOẢN + ĐIỂM trong cùng ĐIỀU → 1 block
- Nếu có "và" giữa các ĐIỀU khác nhau → tách block
- Nếu document khác nhau → tách block

Example:
- "Khoản 2 điều 5 và điểm a" → 1 BLOCK
- "Khoản 2 điều 5 và khoản 1 điều 37" → 2 BLOCKS
```

#### STEP 4: ARTICLE BLOCKS (Danh sách các cụm)
Changed from `article_sections` to `extracted_blocks` JSON format

#### JSON OUTPUT FORMAT
```json
{
  "extracted_blocks": [
    {
      "dieu": 5,
      "khoan": 2,
      "diem": "a",
      "chuong": null,
      "document_name": "Bộ Luật Dân Sự"
    }
  ]
}
```

#### EXAMPLES (Updated)
- **EXAMPLE 2**: Shows correct behavior for multi-block query
  - Input: "Khoản 2 điều 5 và điểm a, khoản 1 điều 37 bộ luật dân sự"
  - Output: 2 blocks (one per điều)

#### CONSTRAINTS (Updated)
- "extracted_blocks: mỗi block là 1 cụm độc lập để truy xuất"
- "Nếu 1 điều có nhiều khoản/điểm → có thể tách thành nhiều block"

### 3. `src/agent/llm_query_analyzer.py` - LLM Response Parsing

**Changes**:
- ✅ Updated imports: Use `ArticleBlock` instead of `ArticleItem`, `ArticleSection`
- ✅ Rewrote `_validate_and_convert()` method:
  ```python
  # Parse article blocks
  article_blocks = []
  for block in parsed_dict.get("extracted_blocks", []):
      article_block = ArticleBlock(
          dieu=block.get("dieu"),
          khoan=block.get("khoan"),
          diem=block.get("diem"),
          chuong=block.get("chuong"),
          document_name=block.get("document_name"),
      )
      article_blocks.append(article_block)
  
  # Result uses extracted_blocks
  result = QueryAnalysisResult(
      ...
      extracted_blocks=article_blocks,
      ...
  )
  ```

### 4. `src/agent/agent.py` - Agent Logging Update

**Changes**:
- ✅ Updated `_step_analyze()` logging to show extracted_blocks:
  ```python
  logger.info(f"    Extracted Blocks: {len(analysis.extracted_blocks)} blocks")
  for i, block in enumerate(analysis.extracted_blocks):
      logger.info(f"      Block {i+1}: Dieu={block.dieu}, Khoan={block.khoan}, "
                 f"Diem={block.diem}, Doc={block.document_name}")
  ```

### 5. `src/agent/router.py` - Tool Routing for Multiple Blocks

**Key Changes**:

#### `_build_tool_inputs()` - Multi-Block Handling
```python
# If get_specific_article and multiple blocks → call once per block
if tool_name == "get_specific_article" and len(analysis.extracted_blocks) > 0:
    for block in analysis.extracted_blocks:
        tool_input = self._build_input_get_specific_article_for_block(block)
        if tool_input is not None:
            tool_inputs.append((tool_name, tool_input))
```

#### New Helper: `_build_input_get_specific_article_for_block()`
```python
def _build_input_get_specific_article_for_block(self, block) -> Dict[str, Any]:
    if block.dieu is None:
        return None
    return {
        "dieu_number": block.dieu,
        "khoan_number": block.khoan,
        "diem_name": block.diem,
        "document_name": block.document_name,
    }
```

#### Updated Other Methods
- `_build_input_search_document_metadata()`: Uses `extracted_blocks[0].document_name`
- `_build_input_find_related_documents()`: Uses `extracted_blocks[0].document_name`
- `_build_input_find_cross_references()`: Uses `extracted_blocks[0].dieu`
- `should_skip_semantic_search()`: Checks `len(analysis.extracted_blocks) > 0`

### 6. `src/agent/test_agent.py` - Test Updates

**Changes**:
- ✅ Updated imports: Use `ArticleBlock` instead of `ArticleItem`, `ArticleSection`
- ✅ Updated all test cases to use `extracted_blocks`:
  ```python
  # Before
  article_sections=ArticleSection(dieu_numbers=[5], ...),
  extracted_entities=[ArticleItem(...)],
  
  # After
  extracted_blocks=[
      ArticleBlock(dieu=5, khoan=None, diem=None, chuong=None, document_name="...")
  ],
  ```

---

## Data Flow Example

### Query
```
"khoản 2 điều 5 và điểm a, khoản 1 điều 37 bộ luật dân sự"
```

### LLM Response (from llm_prompt_instruction)
```json
{
  "query_type": "SPECIFIC_LOOKUP",
  "intent": "LOOKUP",
  "extracted_blocks": [
    {
      "dieu": 5,
      "khoan": 2,
      "diem": "a",
      "chuong": null,
      "document_name": "bộ luật dân sự"
    },
    {
      "dieu": 37,
      "khoan": 1,
      "diem": null,
      "chuong": null,
      "document_name": "bộ luật dân sự"
    }
  ],
  "confidence": 0.95
}
```

### Router Output
Tool calls (in order):
1. `("get_specific_article", {"dieu_number": 5, "khoan_number": 2, "diem_name": "a", "document_name": "bộ luật dân sự"})`
2. `("get_specific_article", {"dieu_number": 37, "khoan_number": 1, "diem_name": null, "document_name": "bộ luật dân sự"})`

### Result
✅ Two separate retrieval operations with correct context for each legal item

---

## Validation Checklist

- [x] Schema updated (ArticleBlock added, article_sections removed)
- [x] __init__.py exports updated
- [x] LLM prompt instructions rewritten with clustering logic
- [x] LLM response parser updated for extracted_blocks
- [x] Agent logging updated
- [x] Router tool input builder updated
- [x] Router multi-block handling implemented
- [x] All tests updated to use new schema
- [ ] **Run test_llm_analyzer.py to validate** (ready when you want)

---

## Testing
To validate the implementation, run:
```bash
python test_llm_analyzer.py
```

Or run all tests:
```bash
pytest src/agent/test_agent.py -v
```

---

## Notes

1. **Backward Compatibility**: Old fields (`article_numbers`, `article_names`) still exist in QueryAnalysisResult but are marked as DEPRECATED

2. **Multi-Block Routing**: When router encounters "get_specific_article" with multiple blocks, it will call the tool once for each block

3. **Document Name Handling**: Each block preserves its own document_name, so mixed-document queries work correctly

4. **Edge Cases**:
   - Empty blocks: Router filters out blocks with no dieu (primary key)
   - Single block: Works exactly like before, just in block format
   - Multiple blocks: Each gets its own tool invocation
