import json
import re
import logging
from typing import Dict, Any, Callable
from pydantic import ValidationError
from .state import AgentState
from .schemas import AnalyzerOutput, SubQuestion, Intent, LegalCitation, ChunkEvaluationResult
from .prompts import ANALYZE_PROMPT, LEGAL_QUERY_PROMPT, DOC_RELATION_PROMPT, EVALUATE_CHUNKS_PROMPT, GENERATE_RESPONSE_PROMPT
from .tools import _filter_redundant_chunks

logger = logging.getLogger(__name__)

def make_analyze_node(llm_client: Any) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Tạo node phân tích câu hỏi:
    - Phân rã, chia nhỏ câu hỏi.
    - Xác định intent của câu hỏi.
    """
    def analyze_node(state: AgentState) -> Dict[str, Any]:
        question = state.get("question", "")
        print(f"\n[Analyze Node] Đang phân tích câu hỏi: '{question}'...")
        
        # 1. Ghép câu hỏi của user vào prompt mẫu
        prompt = ANALYZE_PROMPT + f"\n\nCâu hỏi người dùng: {question}"
        
        try:
            # 2. Gọi remote client (hàm generate mà bạn tự viết)
            # Nó sẽ trả về chuỗi text
            raw_response = llm_client.generate(prompt=prompt)
            print(f"\n[DEBUG Analyze] Raw LLM Response:\n{raw_response}\n")
            
            # 3. Làm sạch chuỗi trả về (Rất quan trọng với local LLM!)
            # Local LLM hay bị tật thêm ```json ... ``` bao quanh kết quả. Ta cần cắt bỏ nó đi.
            clean_json_str = raw_response
            match = re.search(r"```(?:json)?(.*?)```", raw_response, re.DOTALL)
            if match:
                clean_json_str = match.group(1).strip()
                
            # 4. Ép chuỗi text thành Dictionary chuẩn của Python
            json_dict = json.loads(clean_json_str)
            print(f"[DEBUG Analyze] Parsed JSON:\n{json.dumps(json_dict, indent=2, ensure_ascii=False)}\n")
            
            # 5. Dùng Pydantic ép kiểu và kiểm tra lỗi (Đây là lý do cần AnalyzerOutput)
            # Nếu JSON thiếu trường (ví dụ thiếu 'intent' hoặc 'query'), Pydantic sẽ ném ra ValidationError ngay lập tức.
            output_obj = AnalyzerOutput.model_validate(json_dict)
            
            # 6. Log kết quả phân tích
            print(f"[Analyze Node] ✓ Phân tích thành công - {len(output_obj.sub_questions)} sub_questions:")
            for i, sq in enumerate(output_obj.sub_questions, 1):
                print(f"  {i}. [intent={sq.intent}] {sq.query}")
            print()
            
            # 7. Thành công! Trả mảng sub_questions về cho AgentState
            return {"sub_questions": output_obj.sub_questions}
            
        except (json.JSONDecodeError, ValidationError, Exception) as e:
            # Nếu con LLM sinh rác, hoặc lỗi mạng... ta phải có phương án dự phòng
            # để luồng Graph không bị sập. Ta ép nó chạy vào nhánh CHITCHAT (hoặc GENERAL).
            print(f"[Analyze Node Error]: {e}")
            fallback_sq = SubQuestion(
                query=question,
                intent=Intent.CHITCHAT
            )
            print(f"[Analyze Node] ⚠ Fallback: {fallback_sq.query} (intent={fallback_sq.intent})\n")
            return {"sub_questions": [fallback_sq]}
            
    return analyze_node

def make_fallback_node(llm: Any) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Tạo nhánh Fallback: Xử lý khi không xác định được intent rõ ràng.
    """
    def fallback_node(state: AgentState) -> Dict[str, Any]:
        sq = state.get("current_sub_question")
        query = sq.query if sq else state.get("question", "")
        
        message = (
            f"Mình chưa rõ ý của bạn ở câu: '{query}'. "
            "Bạn có thể cung cấp thêm thông tin chi tiết hơn, "
            "hoặc chỉ định rõ văn bản/điều luật liên quan được không?"
        )
        # Ghi thẳng vào biến answer để trả về cho người dùng
        return {"answer": message}
        
    return fallback_node

# def make_doc_retrieve_node(retriever: Any) -> Callable[[AgentState], Dict[str, Any]]:
#     """
#     Tạo nhánh doc_retrieve:
#     - Vector search (metadata chunk, doc meta)
#     - Trả về context.
#     """
#     def doc_retrieve_node(state: AgentState) -> Dict[str, Any]:
#         sq = state.get("current_sub_question")
#         # Vector search dựa trên sq.query và sq.keywords
#         pass
#         
#     return doc_retrieve_node

def make_legal_query_node(retriever: Any, llm_client: Any) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Tạo nhánh legal_query:
    - Trích xuất metadata từ câu hỏi bằng LLM
    - Gọi chunk_metadata_search để lấy chính xác điều khoản
    """
    def legal_query_node(state: AgentState) -> Dict[str, Any]:
        sq = state.get("current_sub_question")
        query = sq.query if sq else state.get("question", "")
        print(f"\n[Legal Query Node] Đang trích xuất metadata cho: '{query}'...")
        
        # 1. Dùng LLM để trích xuất cấu trúc văn bản
        prompt = LEGAL_QUERY_PROMPT + f"\n\nCâu hỏi: {query}"
        try:
            raw_response = llm_client.generate(prompt=prompt)
            clean_json = raw_response
            match = re.search(r"```(?:json)?(.*?)```", raw_response, re.DOTALL)
            if match:
                clean_json = match.group(1).strip()
                
            json_dict = json.loads(clean_json)
            citation = LegalCitation.model_validate(json_dict)
            
            so_hieu_to_search = citation.so_hieu
            
            # 1.5. Nếu chỉ có tên văn bản (không có số hiệu), gọi DB để tìm số hiệu chuẩn
            if not so_hieu_to_search and citation.ten_van_ban:
                print(f"[Legal Query Node] Tìm số hiệu chuẩn cho tên văn bản: '{citation.ten_van_ban}'...")
                doc_output = retriever.doc_metadata_search(
                    ten_van_ban=citation.ten_van_ban, 
                    limit=1
                )
                if doc_output.success and doc_output.documents:
                    so_hieu_to_search = doc_output.documents[0].so_hieu
                    print(f"[Legal Query Node] Đã tìm thấy số hiệu chuẩn: {so_hieu_to_search}")
                else:
                    print(f"[Legal Query Node] Không tìm thấy văn bản nào có tên '{citation.ten_van_ban}'")
            
            # 2. Gọi tool tìm kiếm chính xác
            print(f"[Legal Query Node] Tìm metadata: so_hieu={so_hieu_to_search}, dieu={citation.dieu}, khoan={citation.khoan}")
            tool_output = retriever.chunk_metadata_search(
                so_hieu=so_hieu_to_search,
                phan=citation.phan,
                chuong=citation.chuong,
                muc=citation.muc,
                dieu=citation.dieu,
                khoan=citation.khoan,
                diem=citation.diem,
                top_k=5 # Lấy 5 chunk nếu có trùng lặp hoặc lấy các chunk con
            )
            
            # 3. Trả về context và tool_output
            if tool_output.success and tool_output.display_text:
                context_str = f"--- TRÍCH XUẤT CHÍNH XÁC CHO: '{query}' ---\n{tool_output.display_text}"
            else:
                context_str = f"--- KHÔNG TÌM THẤY ĐIỀU LUẬT CHÍNH XÁC CHO: '{query}' ---\n{tool_output.display_text or ''}"
                
            return {
                "context_text": [context_str],
                "tool_outputs": [tool_output]
            }
            
        except Exception as e:
            print(f"[Legal Query Error] {e}")
            # Fallback về text trống nếu lỗi
            return {"context_text": [f"--- LỖI TRÍCH XUẤT CHO: '{query}' ---"]}
        
    return legal_query_node

def make_general_node(retriever: Any, llm: Any) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Tạo nhánh general:
    - Vector search -> Trả về context_text
    """
    def general_node(state: AgentState) -> Dict[str, Any]:
        sq = state.get("current_sub_question")
        query = sq.query if sq else state.get("question", "")
        
        print(f"\n[General Node] Đang tìm kiếm ngữ nghĩa cho: '{query}'...")
        
        # Gọi tool vector_search từ LegalAgentTools (truyền qua tham số retriever)
        tool_output = retriever.vector_search(
            query=query,
            top_k_retrieve=50, # Lấy 20 kết quả thô
            top_k_rerank=5,    # Giữ lại 5 kết quả tốt nhất
            use_rerank=True
        )
        
        # Đóng gói kết quả thành text để nối vào context_text chung
        if tool_output.success and tool_output.display_text:
            context_str = f"--- KẾT QUẢ TÌM KIẾM CHO: '{query}' ---\n{tool_output.display_text}"
        else:
            context_str = f"--- TÌM KIẾM CHO '{query}' KHÔNG CÓ KẾT QUẢ ---\n{tool_output.display_text or ''}"
            
        # Trả về cả context_text (dạng chuỗi) và tool_outputs (dạng object thô)
        # Để node evaluate_chunks phía sau có thể lôi object thô ra rerank/deduplicate nếu cần.
        return {
            "context_text": [context_str],
            "tool_outputs": [tool_output]
        }
    return general_node

def make_doc_relation_node(retriever: Any, llm_client: Any) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Tạo nhánh doc_relation:
    - Trích xuất tên/số hiệu văn bản từ câu hỏi bằng LLM
    - Gọi doc_relation_search để lấy thông tin hiệu lực và quan hệ thay thế
    """
    def doc_relation_node(state: AgentState) -> Dict[str, Any]:
        sq = state.get("current_sub_question")
        query = sq.query if sq else state.get("question", "")
        
        print(f"\n[Doc Relation Node] Đang trích xuất văn bản mục tiêu cho: '{query}'...")
        
        # 1. Dùng LLM để trích xuất danh tính văn bản
        prompt = DOC_RELATION_PROMPT + f"\n\nCâu hỏi: {query}"
        try:
            raw_response = llm_client.generate(prompt=prompt)
            print(f"\n[DEBUG Doc Relation] Raw LLM Response:\n{raw_response}\n")
            
            clean_json = raw_response
            match = re.search(r"```(?:json)?(.*?)```", raw_response, re.DOTALL)
            if match:
                clean_json = match.group(1).strip()
            
            print(f"[DEBUG Doc Relation] Cleaned JSON:\n{clean_json}\n")
                
            json_dict = json.loads(clean_json)
            citation = LegalCitation.model_validate(json_dict)
            
            print(f"[DEBUG Doc Relation] Parsed Citation: so_hieu='{citation.so_hieu}', ten_van_ban='{citation.ten_van_ban}'\n")
            
            so_hieu_list = []
            if citation.so_hieu:
                so_hieu_list.append(citation.so_hieu)
            
            # 2. Tìm số hiệu chuẩn nếu chỉ có tên văn bản
            if not so_hieu_list and citation.ten_van_ban:
                print(f"[Doc Relation Node] Tìm số hiệu chuẩn cho tên văn bản: '{citation.ten_van_ban}'...")
                doc_output = retriever.doc_metadata_search(
                    ten_van_ban=citation.ten_van_ban, 
                    limit=5,
                    fuzzy_threshold=0.6
                )
                if doc_output.success and doc_output.documents:
                    so_hieu_list = [doc.so_hieu for doc in doc_output.documents if doc.so_hieu]
                    print(f"[Doc Relation Node] Đã tìm thấy các số hiệu chuẩn: {so_hieu_list}")
                else:
                    print(f"[Doc Relation Node] Không tìm thấy văn bản nào có tên '{citation.ten_van_ban}'")
            
            from src.agent.schemas import ToolOutput
            all_tool_outputs = []
            
            # 3. Tra cứu quan hệ bằng danh sách so_hieu
            if so_hieu_list:
                combined_texts = []
                for sh in so_hieu_list:
                    print(f"[Doc Relation Node] Tra cứu quan hệ cho số hiệu: {sh}")
                    t_out = retriever.doc_relation_search(so_hieu=sh)
                    all_tool_outputs.append(t_out)
                    
                    # DEBUG: In ra toàn bộ display_text
                    print(f"[DEBUG Doc Relation] Doc relation search result for {sh}:")
                    print(f"  success: {t_out.success}")
                    print(f"  display_text length: {len(t_out.display_text) if t_out.display_text else 0}")
                    if t_out.display_text:
                        print(f"[DEBUG Doc Relation] Display text:\n{t_out.display_text}\n")
                    
                    if t_out.success and t_out.display_text:
                        combined_texts.append(t_out.display_text)
                
                if combined_texts:
                    context_str = f"--- QUAN HỆ VĂN BẢN CHO: '{query}' ---\n" + "\n\n".join(combined_texts)
                    print(f"[Doc Relation Node] Combined context length: {len(context_str)} ký tự")
                else:
                    context_str = f"--- KHÔNG TÌM THẤY THÔNG TIN VỀ QUAN HỆ VĂN BẢN CHO '{query}' ---\n"
            else:
                # Không fallback sang vector search ở nhánh này!
                t_out = ToolOutput(
                    tool_name="doc_relation_search",
                    success=False,
                    display_text=f"Không tìm thấy văn bản '{citation.ten_van_ban or query}' trong CSDL hiện tại để tra cứu thông tin/quan hệ."
                )
                all_tool_outputs.append(t_out)
                context_str = f"--- LỖI TÌM KIẾM CHO '{query}' ---\n{t_out.display_text}"
                
            return {
                "context_text": [context_str],
                "tool_outputs": all_tool_outputs
            }
            
        except Exception as e:
            print(f"[Doc Relation Error] {e}")
            return {"context_text": [f"--- LỖI TRÍCH XUẤT CHO: '{query}' ---"]}

    return doc_relation_node

def make_evaluate_chunks_node(llm_client: Any) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Tạo node đánh giá và lọc chunks:
    - Gom tất cả chunks từ tool_outputs của các nhánh trước.
    - Dùng LLM phán Yes/No: chunk có trực tiếp liên quan đến câu hỏi không?
    - Chỉ giữ lại chunk relevant=true. Nếu không có chunk nào relevant → trả về rỗng (không fallback).
    """
    def evaluate_chunks_node(state: AgentState) -> Dict[str, Any]:
        question = state.get("question", "")
        tool_outputs = state.get("tool_outputs", [])

        # 1. Gom tất cả chunks từ mọi tool_outputs
        all_chunks = []
        seen_ids: set = set()
        for tool_out in tool_outputs:
            for chunk in (tool_out.chunks or []):
                if chunk.chunk_id not in seen_ids:
                    seen_ids.add(chunk.chunk_id)
                    all_chunks.append(chunk)

        if not all_chunks:
            print("[Evaluate Chunks] Không có chunk nào để đánh giá.")
            return {"context_text": ["--- KHÔNG CÓ THÔNG TIN ---\nHệ thống không tìm thấy điều khoản pháp luật nào liên quan."]}

        # 1b. Lọc redundant (cha/con) cross-node
        before_count = len(all_chunks)
        all_chunks = _filter_redundant_chunks(all_chunks)
        print(f"[Evaluate Chunks] De-dup + Filter cha/con: {before_count} → {len(all_chunks)} chunks.")

        # 2. Build chunks block để đưa vào prompt
        chunks_block = "\n".join(
            f"[{c.chunk_id}]\n{c.metadata.get('full_text') or c.text}"
            for c in all_chunks
        )
        valid_chunk_ids = [c.chunk_id for c in all_chunks]

        prompt = (
            EVALUATE_CHUNKS_PROMPT
            + f"\n\nCâu hỏi: {question}\n\n"
            + f"Các chunks cần đánh giá:\n{chunks_block}"
        )

        # 3. Gọi LLM để đánh giá
        try:
            raw_response = llm_client.generate(prompt=prompt)
            print(f"[DEBUG Evaluate Chunks] Raw LLM Response:\n{raw_response}\n")

            eval_result = ChunkEvaluationResult.from_llm_response(raw_response, valid_chunk_ids)

            # 4. Lấy các chunk_id được đánh giá relevant=true
            relevant_ids = {
                e.chunk_id for e in eval_result.evaluations if e.relevant
            }

            # Log để debug
            for e in eval_result.evaluations:
                status = "GIỮ" if e.relevant else "BỎ"
                print(f"[Evaluate Chunks] {status} [{e.chunk_id}] — {e.reason}")

        except (json.JSONDecodeError, Exception) as e:
            print(f"[Evaluate Chunks Error] {e} — Giữ toàn bộ chunks (failsafe).")
            relevant_ids = set(valid_chunk_ids)  # Failsafe khi LLM lỗi: giữ hết

        # 5. Lọc và build context_text mới
        kept_chunks = [c for c in all_chunks if c.chunk_id in relevant_ids]

        if not kept_chunks:
            print("[Evaluate Chunks] Không có chunk nào đạt tiêu chí liên quan.")
            return {
                "context_text": ["--- KHÔNG CÓ THÔNG TIN PHÙ HỢP ---\nHệ thống không tìm thấy điều khoản pháp luật nào liên quan trực tiếp đến câu hỏi của bạn."],
                "context_chunks": []
            }

        context_parts = [
            f"{i+1}. [{c.chunk_id}]\n{c.metadata.get('full_text') or c.text}"
            for i, c in enumerate(kept_chunks)
        ]
        context_str = f"--- NGỮ CẢNH PHÁP LÝ ---\n" + "\n\n".join(context_parts)
        print(f"[Evaluate Chunks] Giữ lại {len(kept_chunks)}/{len(all_chunks)} chunks.")

        return {
            "context_text": [context_str],
            "context_chunks": kept_chunks
        }

    return evaluate_chunks_node

def make_merge_results_node() -> Callable[[AgentState], Dict[str, Any]]:
    """
    Node gom hợp kết quả từ các nhánh song song (Send API).
    
    Khi có nhiều sub_questions được xử lý song song:
    - legal_query, doc_relation, general chạy đồng thời → tích lũy context vào state
    - merge_results_node tổ chức lại context theo từng sub_question
    - QUAN TRỌNG: Giữ chunks trong sub_question_contexts để generate_response_node có thể gọi _evaluate_refs
    
    sub_question_contexts structure:
    {
        "câu hỏi con 1": {
            "query": "...",
            "intent": "legal_query",
            "context_chunks": [...],      ← Chunks thật, không chỉ text!
            "context_text": [...]
        },
        ...
    }
    """
    def merge_results_node(state: AgentState) -> Dict[str, Any]:
        sub_questions = state.get("sub_questions", [])
        context_chunks = state.get("context_chunks", [])
        context_text_list = state.get("context_text", [])
        
        if not sub_questions:
            print("[Merge Results] Không có sub_questions để gom hợp.")
            return {"sub_question_contexts": None}
        
        print(f"[Merge Results] Gom hợp kết quả từ {len(sub_questions)} câu hỏi con...")
        
        # --- Bước 1: Tổ chức context theo từng sub_question ---
        sub_question_contexts = {}
        
        for i, sq in enumerate(sub_questions):
            sq_key = sq.query
            
            # Khởi tạo context cho sub_question này
            context_for_sq = {
                "query": sq.query,
                "intent": str(sq.intent),
                "context_chunks": context_chunks,  # ← GIỮ CHUNKS CỐN GỌIPYTHON!
                "context_text": context_text_list
            }
            
            sub_question_contexts[sq_key] = context_for_sq
            print(f"[Merge Results] Sub-question {i+1}: '{sq.query[:50]}...'")
            if context_chunks:
                print(f"                 chunks: {len(context_chunks)}")
            if context_text_list:
                print(f"                 text: {sum(len(t) for t in context_text_list)} ký tự")
        
        print(f"[Merge Results] Hoàn thành gom hợp {len(sub_question_contexts)} sub_questions.")
        
        return {
            "sub_question_contexts": sub_question_contexts
        }
    
    return merge_results_node

def make_generate_response_node(retriever: Any, llm_client: Any) -> Callable[[AgentState], Dict[str, Any]]:
    """
    Tạo node sinh câu trả lời:
    
    Xử lý 2 trường hợp:
    1. Có sub_question_contexts từ merge_results_node → Xử lý từng SQ riêng biệt
       - Mỗi SQ: gọi _evaluate_refs cho mỗi chunk → build nested context blocks
       - Sinh answer riêng cho mỗi SQ
       - Merge tất cả answers thành 1 response cuối
    
    2. Không có sub_question_contexts → Fallback sang context_chunks (legacy)
       - Gọi _evaluate_refs đơn giản
       - Sinh 1 answer duy nhất
    """
    def generate_response_node(state: AgentState) -> Dict[str, Any]:
        question = state.get("question", "")
        sub_question_contexts = state.get("sub_question_contexts")
        context_chunks = state.get("context_chunks", [])
        tool_outputs = state.get("tool_outputs", [])
        context_text_parts = state.get("context_text", [])
        
        # === CASE 1: Có sub_question_contexts từ merge_results ===
        if sub_question_contexts:
            print(f"[Generate Response] Xử lý {len(sub_question_contexts)} sub_questions riêng biệt...")
            
            all_answers = []
            
            for sq_idx, (sq_query, sq_ctx_data) in enumerate(sub_question_contexts.items(), 1):
                print(f"\n[Generate Response] ===== SUB-QUESTION {sq_idx}: {sq_query} =====")
                
                sq_chunks = sq_ctx_data.get("context_chunks", [])
                sq_intent = sq_ctx_data.get("intent", "unknown")
                
                # --- Xây dựng context cho SQ này ---
                if not sq_chunks:
                    # Không có chunks, dùng text
                    sq_context_text = sq_ctx_data.get("context_text", [])
                    final_context = "\n\n".join(sq_context_text) if sq_context_text else ""
                    print(f"[Generate Response] SQ{sq_idx}: Không có chunks, dùng text ({len(final_context)} ký tự)")
                    
                    # DEBUG: In ra chính xác context_text
                    if final_context:
                        print(f"[DEBUG Generate Response] SQ{sq_idx} Context text content:\n{final_context}\n")
                    else:
                        print(f"[DEBUG Generate Response] SQ{sq_idx} Context text rỗng!\n")
                else:
                    # Có chunks → gọi _evaluate_refs cho mỗi chunk
                    print(f"[Generate Response] SQ{sq_idx}: Đánh giá refs cho {len(sq_chunks)} chunks...")
                    
                    context_blocks = []
                    for main_chunk in sq_chunks:
                        block = {
                            "main": main_chunk,
                            "refs": []
                        }
                        
                        # Gọi _evaluate_refs
                        try:
                            ref_chunks = retriever._evaluate_refs(
                                query=sq_query,
                                nvidia_client=llm_client,
                                main_chunk=main_chunk,
                                score_threshold=6.0,
                                max_refs=3
                            )
                            
                            if ref_chunks:
                                print(f"[Generate Response] SQ{sq_idx} Chunk '{main_chunk.chunk_id}': {len(ref_chunks)} refs")
                                block["refs"] = ref_chunks
                            else:
                                print(f"[Generate Response] SQ{sq_idx} Chunk '{main_chunk.chunk_id}': không có refs")
                        except Exception as e:
                            logger.warning("[Generate Response] SQ%d Lỗi eval refs '%s': %s", sq_idx, main_chunk.chunk_id, e)
                        
                        context_blocks.append(block)
                    
                    # Build final context từ context_blocks
                    context_parts = []
                    for i, block in enumerate(context_blocks):
                        main_chunk = block["main"]
                        ref_chunks = block["refs"]
                        
                        # Main chunk
                        main_text = f"[{main_chunk.chunk_id}]\n{main_chunk.metadata.get('full_text') or main_chunk.text}"
                        context_parts.append(main_text)
                        
                        # Refs
                        if ref_chunks:
                            for ref_chunk in ref_chunks:
                                ref_text = f"  └─ [REF: {ref_chunk.chunk_id}]\n  {ref_chunk.metadata.get('full_text') or ref_chunk.text}"
                                context_parts.append(ref_text)
                        
                        # Separator
                        if i < len(context_blocks) - 1:
                            context_parts.append("─" * 80)
                    
                    final_context = "\n\n".join(context_parts)
                
                # --- Sinh answer cho SQ này ---
                answer_prompt = (
                    GENERATE_RESPONSE_PROMPT
                    + f"\n\nTHÔNG TIN PHÁP LUẬT:\n{final_context}\n\n"
                    + f"CÂU HỎI CỦA NGƯỜI DÙNG:\n{sq_query}\n\n"
                    + "TRẢ LỜI:"
                )
                
                try:
                    print(f"[Generate Response] SQ{sq_idx}: Gọi LLM sinh answer...")
                    # sq_answer = llm.generate(
                    #     prompt=answer_prompt,
                    #     max_length=512,
                    #     temperature=0.1
                    # )
                    sq_answer = llm_client.generate(
                        prompt=answer_prompt)
                    if not sq_answer or sq_answer.strip() == "":
                        sq_answer = f"[SQ{sq_idx}] Không thể sinh câu trả lời."
                    
                    sq_answer = sq_answer.strip()
                    print(f"[Generate Response] SQ{sq_idx}: Sinh answer thành công ({len(sq_answer)} ký tự)")
                    
                    # Format answer với header SQ
                    formatted_answer = f"\n{'='*80}\n[Câu hỏi con {sq_idx}] {sq_query}\n{'='*80}\n{sq_answer}"
                    all_answers.append(formatted_answer)
                    
                except Exception as e:
                    logger.exception("[Generate Response] SQ%d Lỗi sinh answer: %s", sq_idx, e)
                    all_answers.append(f"\n[Câu hỏi con {sq_idx}] {sq_query}\n[LỖI] {str(e)}")
            
            # --- Merge tất cả answers ---
            final_answer = "\n\n".join(all_answers)
            print(f"\n[Generate Response] Merge {len(all_answers)} answers thành công")
            return {"answer": final_answer}
        
        # === CASE 2: Fallback - Không có sub_question_contexts (legacy) ===
        print("[Generate Response] [FALLBACK] Không có sub_question_contexts, dùng context_chunks...")
        
        # Nếu không có context_chunks, lấy từ tool_outputs
        if not context_chunks:
            print("[Generate Response] Không có context_chunks, lấy từ tool_outputs...")
            all_chunks = []
            seen_ids = set()
            for tool_out in tool_outputs:
                for chunk in (tool_out.chunks or []):
                    if chunk.chunk_id not in seen_ids:
                        seen_ids.add(chunk.chunk_id)
                        all_chunks.append(chunk)
            
            if all_chunks:
                context_chunks = _filter_redundant_chunks(all_chunks)
                print(f"[Generate Response] Lấy được {len(context_chunks)} chunks từ tool_outputs.")
            else:
                print("[Generate Response] Không có chunks từ tool_outputs.")
        
        # Build final context
        if not context_chunks:
            # Không có chunks, dùng context_text hiện tại
            final_context = "\n\n".join(context_text_parts) if context_text_parts else ""
        else:
            # Có chunks → gọi _evaluate_refs
            print(f"[Generate Response] Đánh giá refs cho {len(context_chunks)} chunks...")
            
            context_blocks = []
            for main_chunk in context_chunks:
                block = {
                    "main": main_chunk,
                    "refs": []
                }
                
                try:
                    ref_chunks = retriever._evaluate_refs(
                        query=question,
                        main_chunk=main_chunk,
                        score_threshold=6.0,
                        max_refs=3
                    )
                    
                    if ref_chunks:
                        print(f"[Generate Response] Chunk '{main_chunk.chunk_id}': {len(ref_chunks)} refs")
                        block["refs"] = ref_chunks
                except Exception as e:
                    logger.warning("[Generate Response] Lỗi eval refs '%s': %s", main_chunk.chunk_id, e)
                
                context_blocks.append(block)
            
            # Build final context từ context_blocks
            context_parts = []
            for i, block in enumerate(context_blocks):
                main_chunk = block["main"]
                ref_chunks = block["refs"]
                
                main_text = f"[{main_chunk.chunk_id}]\n{main_chunk.metadata.get('full_text') or main_chunk.text}"
                context_parts.append(main_text)
                
                if ref_chunks:
                    for ref_chunk in ref_chunks:
                        ref_text = f"  └─ [REF: {ref_chunk.chunk_id}]\n  {ref_chunk.metadata.get('full_text') or ref_chunk.text}"
                        context_parts.append(ref_text)
                
                if i < len(context_blocks) - 1:
                    context_parts.append("─" * 80)
            
            final_context = "\n\n".join(context_parts)
        
        # --- Sinh answer duy nhất ---
        answer_prompt = (
            GENERATE_RESPONSE_PROMPT
            + f"\n\nTHÔNG TIN PHÁP LUẬT:\n{final_context}\n\n"
            + f"CÂU HỎI CỦA NGƯỜI DÙNG:\n{question}\n\n"
            + "TRẢ LỜI:"
        )
        
        try:
            print("[Generate Response] Gọi LLM để sinh câu trả lời...")
            answer = llm_client.generate(
                prompt=answer_prompt)
            
            if not answer or answer.strip() == "":
                answer = "Xin lỗi, tôi không thể sinh câu trả lời từ thông tin được cung cấp."
            
            print(f"[Generate Response] Sinh answer thành công ({len(answer)} ký tự).")
            return {"answer": answer.strip()}
            
        except Exception as e:
            logger.exception("[Generate Response] Lỗi khi sinh answer: %s", e)
            return {
                "answer": f"Lỗi khi xử lý câu hỏi: {str(e)}"
            }
    
    return generate_response_node
