"""
Prompt cho LLMQueryAnalyzer.

Triết lý mới (gọn, tập trung):
- Chỉ hỏi LLM 2 câu quan trọng: `in_scope` + `is_specific`.
- Trích `extracted_blocks` khi `is_specific=True`.
- Không dồn nhiều category chồng chéo như phiên bản cũ.
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
      "dieu": string | null,
      "khoan": string | null,
      "diem": string | null,
      "chuong": string | null,
      "so_hieu": string | null,
      "document_name": string | null
    }}
  ],
  "intent": "lookup" | "compare" | "explain" | "verify" | "define" | "calculate",
  "needs_metadata_search": bool,
  "keywords": [string],
  "reasoning": string
}}

Ý NGHĨA TỪNG KEY:

1) in_scope
   - true  : câu hỏi về pháp luật, văn bản quy phạm pháp luật Việt Nam.
   - false : chào hỏi, tán gẫu, hoặc kiến thức không liên quan tới pháp luật VN.

2) is_specific
   - true  : câu hỏi ĐỀ CẬP rõ ràng tới: số Điều, Khoản, Chương, hoặc tên/số hiệu văn bản cụ thể.
   - false : hỏi chung về chủ đề pháp lý mà không chỉ ra điểm neo cụ thể.

3) extracted_blocks (trích khi is_specific=true; nếu không thì [])
   - `dieu`, `khoan`, `chuong`: Trích xuất số hoặc ký hiệu (ví dụ: "5", "1a", "1.1"). 
   - `so_hieu`: MÃ số chính thức (ví dụ: "102/2017", "91/2015/QH13").
   - `document_name`: Tên gọi văn bản (ví dụ: "Bộ luật Dân sự", "Luật Lao động").

4) intent: task người dùng muốn làm (lookup, compare, explain, verify, define, calculate).

5) needs_metadata_search
   - true nếu hỏi về: thông tin hành chính, cơ quan ban hành, ngày ban hành, ngày hiệu lực, tình trạng văn bản.

6) keywords: 3-7 từ cốt lõi.
7) reasoning: giải thích ngắn gọn lý do phân tích.

VÍ DỤ:

Câu hỏi: "Điều 5 Luật 102/2017 do ai ban hành và còn hiệu lực không?"
→
{{
  "in_scope": true,
  "is_specific": true,
  "extracted_blocks": [
    {{"dieu": "5", "khoan": null, "diem": null, "chuong": null, "so_hieu": "102/2017", "document_name": null}}
  ],
  "intent": "lookup",
  "needs_metadata_search": true,
  "keywords": ["điều 5", "luật 102/2017", "ban hành", "hiệu lực"],
  "reasoning": "Câu hỏi hỏi nội dung Điều 5 và thông tin hành chính (cơ quan ban hành, hiệu lực) của văn bản."
}}

Câu hỏi: "Khoản 2 điều 5.1 bộ luật dân sự"
→
{{
  "in_scope": true,
  "is_specific": true,
  "extracted_blocks": [
    {{"dieu": "5.1", "khoan": "2", "diem": null, "chuong": null, "so_hieu": null, "document_name": "Bộ luật Dân sự"}}
  ],
  "intent": "lookup",
  "needs_metadata_search": false,
  "keywords": ["khoản 2 điều 5.1", "bộ luật dân sự"],
  "reasoning": "Trích xuất điều khoản có số hiệu mở rộng (5.1)."
}}

CHỈ TRẢ JSON.
"""


def get_llm_prompt(query: str) -> tuple[str, str]:
    return SYSTEM_PROMPT, MAIN_INSTRUCTION.format(query=query)

def get_examples() -> list[dict]:
    """Trả về danh sách ví dụ mẫu để kiểm thử."""
    return [
        {"query": "Điều 5 của Luật 102/2017 nói gì?", "expected_is_specific": True},
        {"query": "Bảo hiểm xã hội là gì?", "expected_is_specific": False},
    ]
