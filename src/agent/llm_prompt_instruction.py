"""
LLM Query Analyzer Prompt Instructions
Hướng dẫn chi tiết cho LLM để phân tích câu hỏi và trả về structured JSON output
"""

SYSTEM_PROMPT = """Bạn là một chuyên gia phân tích câu hỏi về pháp luật Việt Nam.
Nhiệm vụ của bạn là:
1. Phân loại loại câu hỏi (query_type)
2. Xác định ý định người dùng (intent)
3. Trích xuất các thực thể pháp lý (article items)
4. Trả về kết quả dưới dạng JSON có cấu trúc

Luôn trả về JSON, không thêm text khác."""


MAIN_INSTRUCTION = """
TASK: Phân tích câu hỏi sau và trích xuất tất cả thực thể pháp lý

Query: "{query}"

---

STEP 1: QUERY TYPE CLASSIFICATION
Phân loại vào một trong 6 loại:

1. SPECIFIC_LOOKUP
   - Hỏi về điều/khoản cụ thể
   - Ví dụ: "Điều 5 nói gì?", "Khoản 1 của Điều 3?"
   
2. SEMANTIC_SEARCH
   - Hỏi tổng quát không chỉ định cụ thể
   - Ví dụ: "Bảo hiểm là gì?", "Quy định về hôn nhân?"
   
3. COMPARATIVE
   - So sánh hai hay nhiều điều/luật
   - Ví dụ: "Khác biệt giữa luật A và luật B?"
   
4. PROCEDURAL
   - Hỏi về quy trình, cách làm
   - Ví dụ: "Quy trình cấp phép?", "Bước nào?"
   
5. CONTEXTUAL
   - Hỏi về bối cảnh pháp lý, mối quan hệ
   - Ví dụ: "Luật này còn hiện hành?", "Có luật nào thay thế?"
   
6. METADATA_SEARCH
   - Hỏi về metadata tài liệu
   - Ví dụ: "Có bao nhiêu luật?", "Cơ quan nào ban hành?"

---

STEP 2: INTENT IDENTIFICATION
Xác định ý định người dùng:

- LOOKUP: Tìm kiếm thông tin (mặc định)
- COMPARE: So sánh (từ khóa: "khác", "giống", "so sánh")
- EXPLAIN: Giải thích (từ khóa: "giải thích", "tại sao", "vì sao")
- VERIFY: Xác minh (từ khóa: "có phải", "đúng không")
- DEFINE: Định nghĩa (từ khóa: "là gì", "định nghĩa")
- CALCULATE: Tính toán/đếm (từ khóa: "bao nhiêu", "mấy")

---

STEP 3: ARTICLE BLOCK EXTRACTION (QUAN TRỌNG!)
Trích xuất các CỤM (block) thực thể pháp lý từ query.

Quy tắc nhóm:
- Mỗi ĐIỀU là 1 block riêng (hoặc CHƯƠNG nếu có)
- KHOẢN + ĐIỂM trong cùng ĐIỀU → 1 block
- Nếu có "và" giữa các ĐIỀU khác nhau → tách block
- Nếu document khác nhau → tách block

Ví dụ 1: "Khoản 2 điều 5 và điểm a"
→ 1 BLOCK: {dieu: 5, khoan: 2, diem: "a", chuong: null}

Ví dụ 2: "Khoản 2 điều 5 và khoản 1 điều 37"
→ 2 BLOCKS:
  Block 1: {dieu: 5, khoan: 2, diem: null, chuong: null}
  Block 2: {dieu: 37, khoan: 1, diem: null, chuong: null}

Ví dụ 3: "Chương 2 điều 5 khoản 1 điểm a"
→ 1 BLOCK: {dieu: 5, khoan: 1, diem: "a", chuong: 2}

IMPORTANT:
- Giữ DOCUMENT NAME trong mỗi block
- Nếu không có document → null
- Mỗi block tương ứng với 1 lần truy xuất sau này

---

STEP 4: ARTICLE BLOCKS (DANH SÁCH CÁC CỤM)
Tạo danh sách các block (cụm) thực thể:

extracted_blocks: [
  {
    "dieu": <số hoặc null>,
    "khoan": <số hoặc null>,
    "diem": <chữ hoặc null>,
    "chuong": <số hoặc null>,
    "document_name": "tên văn bản" (hoặc null)
  },
  ...
]

Mỗi block là 1 cụm độc lập để truy xuất về sau.

---

STEP 5: CONFIDENCE SCORING
Tính độ tin cậy (0.0 - 1.0):

- 0.95+: Rất rõ ràng, chỉ định cụ thể
- 0.80-0.95: Khá rõ ràng, có entities rõ
- 0.60-0.80: Có chút ambiguous, cần context
- 0.40-0.60: Ambiguous, khó hiểu
- <0.40: Rất ambiguous, vague

Nhân tố tính:
- +0.1 nếu có >= 1 block với dieu
- +0.1 nếu có >= 1 block có khoan
- +0.1 nếu có block có diem
- +0.1 nếu có document_name
- +0.1 nếu query rõ ràng, không ambiguous

---

STEP 6: ADDITIONAL FLAGS

requires_metadata_search: boolean
- True nếu query hỏi về metadata (loại, cơ quan, năm, v.v.)
- False nếu chỉ hỏi nội dung

requires_relationship_check: boolean
- True nếu query hỏi về mối quan hệ (thay thế, sửa đổi, hủy bỏ)
- False nếu không

---

JSON OUTPUT FORMAT (BẮTBUỘC):

{
  "query_type": "SPECIFIC_LOOKUP" | "SEMANTIC_SEARCH" | "COMPARATIVE" | "PROCEDURAL" | "CONTEXTUAL" | "METADATA_SEARCH",
  "intent": "LOOKUP" | "COMPARE" | "EXPLAIN" | "VERIFY" | "DEFINE" | "CALCULATE",
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
  ],
  "keywords": ["từ khóa 1", "từ khóa 2", ...],
  "confidence": 0.95,
  "requires_metadata_search": false,
  "requires_relationship_check": false,
  "reasoning": "Giải thích ngắn lý do phân loại"
}

---

EXAMPLES:

EXAMPLE 1:
Query: "Điều 5 của Luật 102/2017 nói gì?"
Output:
{
  "query_type": "SPECIFIC_LOOKUP",
  "intent": "LOOKUP",
  "extracted_blocks": [
    {
      "dieu": 5,
      "khoan": null,
      "diem": null,
      "chuong": null,
      "document_name": "Luật 102/2017"
    }
  ],
  "keywords": ["nói", "gì"],
  "confidence": 0.95,
  "requires_metadata_search": false,
  "requires_relationship_check": false,
  "reasoning": "Query chỉ định cụ thể Điều 5 của Luật 102/2017"
}

EXAMPLE 2:
Query: "Khoản 2 điều 5 và điểm a, khoản 1 điều 37 bộ luật dân sự"
Output:
{
  "query_type": "SPECIFIC_LOOKUP",
  "intent": "LOOKUP",
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
  ],
  "keywords": ["khoản", "điều", "điểm"],
  "confidence": 0.95,
  "requires_metadata_search": false,
  "requires_relationship_check": false,
  "reasoning": "Query chỉ định 2 cụm: (dieu 5 + khoan 2 + diem a) và (dieu 37 + khoan 1)"
}

EXAMPLE 3:
Query: "Chương 2 Điều 5 Khoản 1 Điểm a, b của Luật Lao Động?"
Output:
{
  "query_type": "SPECIFIC_LOOKUP",
  "intent": "LOOKUP",
  "extracted_blocks": [
    {
      "dieu": 5,
      "khoan": 1,
      "diem": "a",
      "chuong": 2,
      "document_name": "Luật Lao Động"
    },
    {
      "dieu": 5,
      "khoan": 1,
      "diem": "b",
      "chuong": 2,
      "document_name": "Luật Lao Động"
    }
  ],
  "keywords": ["chương", "điều", "khoản", "điểm"],
  "confidence": 0.98,
  "requires_metadata_search": false,
  "requires_relationship_check": false,
  "reasoning": "Query rất cụ thể, 2 block cho 2 điểm (a, b) cùng chuong-dieu-khoan"
}

EXAMPLE 4:
Query: "Bảo hiểm xã hội là gì?"
Output:
{
  "query_type": "SEMANTIC_SEARCH",
  "intent": "DEFINE",
  "extracted_blocks": [],
  "keywords": ["bảo", "hiểm", "xã", "hội"],
  "confidence": 0.65,
  "requires_metadata_search": false,
  "requires_relationship_check": false,
  "reasoning": "Query không chỉ định entities cụ thể, tìm kiếm tổng quát"
}

---

CONSTRAINTS:
1. Luôn trả JSON, không text khác
2. KHÔNG thêm dấu ngoặc kép extra hay escape ký tự
3. Nếu không chắc loại, đặt confidence thấp hơn
4. Keywords loại bỏ stop words tiếng Việt (các, cái, gì, nào, của, là, có)
5. extracted_blocks: mỗi block là 1 cụm độc lập để truy xuất
6. Nếu 1 điều có nhiều khoản/điểm → có thể tách thành nhiều block (hoặc gom 1 block tùy logic)
7. Luôn đặt document_name trong mỗi block (nếu có)
"""


# Examples for testing
EXAMPLE_QUERIES = [
    {
        "query": "Điều 5 của Luật 102/2017 nói gì?",
        "expected_query_type": "SPECIFIC_LOOKUP",
        "expected_blocks_count": 1,
    },
    {
        "query": "Khoản 2 điều 5 và điểm a, khoản 1 điều 37 bộ luật dân sự",
        "expected_query_type": "SPECIFIC_LOOKUP",
        "expected_blocks_count": 2,  # 2 blocks: (dieu 5 + khoan 2 + diem a) + (dieu 37 + khoan 1)
    },
    {
        "query": "Chương 2 Điều 5 Khoản 1 Điểm a, b?",
        "expected_query_type": "SPECIFIC_LOOKUP",
        "expected_blocks_count": 2,  # 2 blocks: một cho diem a, một cho diem b
    },
    {
        "query": "Bảo hiểm xã hội là gì?",
        "expected_query_type": "SEMANTIC_SEARCH",
        "expected_blocks_count": 0,
    },
    {
        "query": "Khác biệt giữa Luật A và Luật B?",
        "expected_query_type": "COMPARATIVE",
        "expected_blocks_count": 0,
    },
]


def get_llm_prompt(query: str) -> tuple[str, str]:
    """
    Lấy system prompt và user prompt
    
    Returns:
        (system_prompt, user_prompt)
    """
    user_prompt = MAIN_INSTRUCTION.format(query=query)
    return SYSTEM_PROMPT, user_prompt


def get_examples() -> list[dict]:
    """Lấy danh sách ví dụ"""
    return EXAMPLE_QUERIES
