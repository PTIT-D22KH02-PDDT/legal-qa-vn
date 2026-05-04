"""
Prompt Templates cho Legal QA Agent

Chứa các prompt templates cho LLM để sinh câu trả lời
"""

from langchain_core.prompts import PromptTemplate, ChatPromptTemplate


# System prompt cho agent
SYSTEM_PROMPT = """Bạn là một trợ lý pháp lý thông minh, chuyên trả lời các câu hỏi về pháp luật Việt Nam.
Bạn có quyền truy cập vào các công cụ tìm kiếm tài liệu pháp luật.

Khi trả lời:
1. Sử dụng thông tin từ các công cụ tìm kiếm
2. Luôn trích dẫn nguồn tài liệu cụ thể (số hiệu, điều khoản)
3. Giải thích một cách rõ ràng và dễ hiểu
4. Nếu có nhiều góc độ, hãy trình bày cân bằng
5. Nếu không chắc chắn, hãy nói rõ điều đó

Hãy tập trung vào câu hỏi của người dùng và sử dụng các công cụ một cách hiệu quả."""


# Template để tạo final answer
FINAL_ANSWER_TEMPLATE = """Dựa trên thông tin tìm kiếm dưới đây, hãy trả lời câu hỏi của người dùng một cách rõ ràng và chính xác.

Câu hỏi: {query}

Thông tin tìm kiếm:
{context}

Câu trả lời:"""


# Template để tạo prompt cho comparison queries
COMPARISON_PROMPT = """Hãy so sánh các tài liệu/điều luật sau dựa trên thông tin được cung cấp:

Tài liệu/Điều luật 1: {doc1}
Tài liệu/Điều luật 2: {doc2}

Thông tin tài liệu 1:
{info1}

Thông tin tài liệu 2:
{info2}

Hãy chỉ ra những điểm giống nhau và khác nhau chính giữa hai tài liệu này."""


# Template để tạo prompt cho procedural queries
PROCEDURAL_PROMPT = """Hãy mô tả quy trình hoặc cách thực hiện sau dựa trên các điều luật liên quan:

Câu hỏi: {query}

Thông tin từ tài liệu:
{context}

Hãy trình bày từng bước một cách rõ ràng, dễ hiểu."""


# Template để tạo prompt cho contextual queries
CONTEXTUAL_PROMPT = """Hãy cung cấp bối cảnh pháp lý cho tài liệu sau:

Tài liệu: {document}

Thông tin về tài liệu:
{info}

Các tài liệu liên quan:
{related_docs}

Hãy giải thích:
1. Tài liệu này còn hiện hành hay đã hết hiệu lực?
2. Có tài liệu nào thay thế, sửa đổi, hoặc bổ sung nó không?
3. Mối quan hệ giữa các tài liệu này."""


# Template để tạo prompt cho definition/explanation queries
DEFINITION_PROMPT = """Hãy giải thích các khái niệm hoặc quy định sau dựa trên tài liệu pháp luật:

Câu hỏi: {query}

Định nghĩa/Quy định từ tài liệu:
{definitions}

Hãy cung cấp:
1. Định nghĩa rõ ràng
2. Ví dụ nếu có
3. Quy định chi tiết"""


# Prompt templates cho tool inputs
SEARCH_TOOLS_INSTRUCTION = """Bạn hãy tìm kiếm thông tin bằng các công cụ sau:
1. search_legal_documents - Tìm kiếm vector (semantic search)
2. search_document_metadata - Tìm kiếm metadata
3. get_specific_article - Lấy điều khoản cụ thể
4. find_related_documents - Tìm tài liệu liên quan
5. find_cross_references - Tìm tham chiếu chéo

Chọn công cụ phù hợp dựa trên loại câu hỏi."""


# Summary template
SUMMARY_TEMPLATE = """Hãy tóm tắt thông tin sau về một tài liệu pháp luật:

Tài liệu: {document_title}

Nội dung:
{content}

Tóm tắt (2-3 câu):"""


# Verification template
VERIFICATION_TEMPLATE = """Hãy xác minh xem khẳng định sau đúng hay sai dựa trên tài liệu pháp luật:

Khẳng định: {statement}

Thông tin từ tài liệu:
{reference_info}

Xác minh (Đúng/Sai/Không chắc chắn):"""


# Create LangChain PromptTemplates
def create_final_answer_prompt():
    """Tạo final answer prompt"""
    return PromptTemplate(
        input_variables=["query", "context"],
        template=FINAL_ANSWER_TEMPLATE,
    )


def create_comparison_prompt():
    """Tạo comparison prompt"""
    return PromptTemplate(
        input_variables=["doc1", "doc2", "info1", "info2"],
        template=COMPARISON_PROMPT,
    )


def create_procedural_prompt():
    """Tạo procedural prompt"""
    return PromptTemplate(
        input_variables=["query", "context"],
        template=PROCEDURAL_PROMPT,
    )


def create_contextual_prompt():
    """Tạo contextual prompt"""
    return PromptTemplate(
        input_variables=["document", "info", "related_docs"],
        template=CONTEXTUAL_PROMPT,
    )


def create_definition_prompt():
    """Tạo definition prompt"""
    return PromptTemplate(
        input_variables=["query", "definitions"],
        template=DEFINITION_PROMPT,
    )


def create_summary_prompt():
    """Tạo summary prompt"""
    return PromptTemplate(
        input_variables=["document_title", "content"],
        template=SUMMARY_TEMPLATE,
    )


def create_verification_prompt():
    """Tạo verification prompt"""
    return PromptTemplate(
        input_variables=["statement", "reference_info"],
        template=VERIFICATION_TEMPLATE,
    )


# Prompt factory
class PromptFactory:
    """Factory để tạo prompts"""
    
    PROMPTS = {
        "final_answer": create_final_answer_prompt(),
        "comparison": create_comparison_prompt(),
        "procedural": create_procedural_prompt(),
        "contextual": create_contextual_prompt(),
        "definition": create_definition_prompt(),
        "summary": create_summary_prompt(),
        "verification": create_verification_prompt(),
    }
    
    @classmethod
    def get_prompt(cls, prompt_type: str):
        """Lấy prompt theo type"""
        if prompt_type not in cls.PROMPTS:
            raise ValueError(f"Unknown prompt type: {prompt_type}")
        return cls.PROMPTS[prompt_type]
    
    @classmethod
    def get_all_prompts(cls):
        """Lấy tất cả prompts"""
        return cls.PROMPTS
    
    @classmethod
    def format_prompt(cls, prompt_type: str, **kwargs):
        """Format prompt với variables"""
        prompt = cls.get_prompt(prompt_type)
        return prompt.format(**kwargs)
