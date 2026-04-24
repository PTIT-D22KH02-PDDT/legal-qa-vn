"""
Prompt cho LLMQueryAnalyzer.

Triết lý mới (gọn, tập trung):
- Chỉ hỏi LLM 2 câu quan trọng: `in_scope` + `is_specific`.
- Trích `extracted_blocks` khi `is_specific=True`.
- Không dồn nhiều category chồng chéo như phiên bản cũ (bỏ QueryType 6 loại).

Output BẮT BUỘC là JSON hợp lệ — ta dùng Groq JSON mode nên LLM bị bắt buộc
trả JSON, nhưng vẫn nhắc trong prompt cho chắc.
"""

SYSTEM_PROMPT = """Bạn là bộ phân tích câu hỏi cho hệ thống hỏi đáp pháp luật Việt Nam.
Nhiệm vụ: đọc câu hỏi và trả về JSON theo schema đã cho. KHÔNG kèm chữ nào khác ngoài JSON."""


MAIN_INSTRUCTION = """Phân tích câu hỏi sau và trả JSON theo đúng schema.

Câu hỏi: "{query}"

SCHEMA (keys bắt buộc):
{{
  "in_scope": bool,
  "is_specific": bool,
  "extracted_blocks": [
    {{
      "dieu": int | null,
      "khoan": int | null,
      "diem": string | null,
      "chuong": int | null,
      "document_name": string | null
    }}
  ],
  "intent": "lookup" | "compare" | "explain" | "verify" | "define" | "calculate",
  "needs_metadata_search": bool,
  "needs_relationship_check": bool,
  "keywords": [string],
  "reasoning": string
}}

Ý NGHĨA TỪNG KEY:

1) in_scope
   - true  : câu hỏi về pháp luật, văn bản quy phạm pháp luật Việt Nam, điều/khoản,
             quyền/nghĩa vụ, thủ tục pháp lý, hiệu lực, v.v.
   - false : chào hỏi, tán gẫu, hỏi lập trình, thời tiết, kiến thức chung không
             liên quan tới pháp luật VN.

2) is_specific
   - true  : câu hỏi ĐỀ CẬP rõ ràng tới (ít nhất 1): số Điều, số Khoản, chữ Điểm,
             số Chương, hoặc tên/số hiệu văn bản cụ thể (vd: "Luật 102/2017",
             "Bộ luật Lao động", "Nghị định 123/2017/NĐ-CP").
   - false : hỏi chung về chủ đề pháp lý mà không chỉ ra điểm neo cụ thể.

3) extracted_blocks (trích khi is_specific=true; nếu không thì [])
   Quy tắc tách block — ÁP DỤNG NHẤT QUÁN:
   - Mỗi ĐIỀU khác nhau → block khác nhau.
   - Cùng Điều/Khoản nhưng LIỆT KÊ nhiều Điểm (vd "điểm a, b") → mỗi điểm là 1 block.
   - Cùng Điều nhưng LIỆT KÊ nhiều Khoản (vd "khoản 1, 2") → mỗi khoản là 1 block
     (copy Điều, Chương, document_name xuống).
   - Nếu field không được đề cập → null. KHÔNG đoán.
   - document_name: copy xuống MỌI block nếu câu hỏi đề cập văn bản chung.

4) intent (task người dùng muốn làm)
   - lookup   : tra cứu / tìm thông tin (mặc định nếu không chắc)
   - compare  : so sánh ("khác", "giống", "so sánh")
   - explain  : giải thích ("tại sao", "vì sao", "như thế nào")
   - verify   : xác minh ("có phải", "đúng không", "liệu")
   - define   : định nghĩa ("là gì", "định nghĩa")
   - calculate: tính toán/đếm ("bao nhiêu", "mấy", "tổng")

5) needs_metadata_search
   - true nếu hỏi về: loại văn bản, cơ quan ban hành, ngày ban hành, danh sách
     văn bản, số lượng văn bản.

6) needs_relationship_check
   - true nếu hỏi về: sửa đổi, bổ sung, thay thế, bãi bỏ, hiệu lực, còn áp dụng.

7) keywords: 3-7 từ/cụm từ cốt lõi (đã bỏ stop word).
8) reasoning: 1-2 câu giải thích ngắn.

VÍ DỤ:

Câu hỏi: "Điều 5 Luật 102/2017 nói gì?"
→
{{
  "in_scope": true,
  "is_specific": true,
  "extracted_blocks": [
    {{"dieu": 5, "khoan": null, "diem": null, "chuong": null, "document_name": "Luật 102/2017"}}
  ],
  "intent": "lookup",
  "needs_metadata_search": false,
  "needs_relationship_check": false,
  "keywords": ["điều 5", "luật 102/2017"],
  "reasoning": "Chỉ định rõ Điều 5 của một văn bản cụ thể."
}}

Câu hỏi: "Khoản 2 điều 5 và khoản 1 điều 37 bộ luật dân sự"
→
{{
  "in_scope": true,
  "is_specific": true,
  "extracted_blocks": [
    {{"dieu": 5,  "khoan": 2, "diem": null, "chuong": null, "document_name": "Bộ luật Dân sự"}},
    {{"dieu": 37, "khoan": 1, "diem": null, "chuong": null, "document_name": "Bộ luật Dân sự"}}
  ],
  "intent": "lookup",
  "needs_metadata_search": false,
  "needs_relationship_check": false,
  "keywords": ["khoản 2 điều 5", "khoản 1 điều 37", "bộ luật dân sự"],
  "reasoning": "Hai block độc lập trong cùng một văn bản."
}}

Câu hỏi: "Chương 2 Điều 5 Khoản 1 Điểm a, b của Luật Lao động"
→
{{
  "in_scope": true,
  "is_specific": true,
  "extracted_blocks": [
    {{"dieu": 5, "khoan": 1, "diem": "a", "chuong": 2, "document_name": "Luật Lao động"}},
    {{"dieu": 5, "khoan": 1, "diem": "b", "chuong": 2, "document_name": "Luật Lao động"}}
  ],
  "intent": "lookup",
  "needs_metadata_search": false,
  "needs_relationship_check": false,
  "keywords": ["chương 2", "điều 5", "khoản 1", "điểm a", "điểm b", "luật lao động"],
  "reasoning": "Hai điểm (a, b) cùng khoản/điều → 2 block."
}}

Câu hỏi: "Bảo hiểm xã hội là gì?"
→
{{
  "in_scope": true,
  "is_specific": false,
  "extracted_blocks": [],
  "intent": "define",
  "needs_metadata_search": false,
  "needs_relationship_check": false,
  "keywords": ["bảo hiểm xã hội", "định nghĩa"],
  "reasoning": "Hỏi định nghĩa tổng quát, không trích điều cụ thể."
}}

Câu hỏi: "Luật 102/2017 còn hiệu lực không? Có luật nào thay thế?"
→
{{
  "in_scope": true,
  "is_specific": true,
  "extracted_blocks": [
    {{"dieu": null, "khoan": null, "diem": null, "chuong": null, "document_name": "Luật 102/2017"}}
  ],
  "intent": "verify",
  "needs_metadata_search": false,
  "needs_relationship_check": true,
  "keywords": ["luật 102/2017", "hiệu lực", "thay thế"],
  "reasoning": "Hỏi hiệu lực + văn bản thay thế → cần kiểm tra quan hệ."
}}

Câu hỏi: "Thời tiết Hà Nội hôm nay thế nào?"
→
{{
  "in_scope": false,
  "is_specific": false,
  "extracted_blocks": [],
  "intent": "lookup",
  "needs_metadata_search": false,
  "needs_relationship_check": false,
  "keywords": ["thời tiết", "hà nội"],
  "reasoning": "Không liên quan tới pháp luật Việt Nam."
}}

CHỈ TRẢ JSON.
"""


EXAMPLE_QUERIES = [
    {"query": "Điều 5 của Luật 102/2017 nói gì?", "expected_blocks_count": 1, "expected_in_scope": True, "expected_is_specific": True},
    {"query": "Khoản 2 điều 5 và điểm a, khoản 1 điều 37 bộ luật dân sự", "expected_blocks_count": 2, "expected_in_scope": True, "expected_is_specific": True},
    {"query": "Chương 2 Điều 5 Khoản 1 Điểm a, b?", "expected_blocks_count": 2, "expected_in_scope": True, "expected_is_specific": True},
    {"query": "Bảo hiểm xã hội là gì?", "expected_blocks_count": 0, "expected_in_scope": True, "expected_is_specific": False},
    {"query": "Thời tiết Hà Nội hôm nay?", "expected_blocks_count": 0, "expected_in_scope": False, "expected_is_specific": False},
]


def get_llm_prompt(query: str) -> tuple[str, str]:
    """Trả (system_prompt, user_prompt) đã điền query."""
    return SYSTEM_PROMPT, MAIN_INSTRUCTION.format(query=query)


def get_examples() -> list[dict]:
    return EXAMPLE_QUERIES
