import sys
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import json
import logging
import time
from pathlib import Path
from tqdm import tqdm

from src.api.remote_client import RemoteAPIClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent

def evaluate():
    logger.info("Starting evaluation...")
    
    # Load dataset
    dataset_path = PROJECT_ROOT / "valuate" / "loc_3_1_100.jsonl"
    if not dataset_path.exists():
        logger.error(f"Dataset file not found: {dataset_path}")
        return

    data = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line.strip()))
                
    logger.info(f"Loaded {len(data)} questions from {dataset_path}")
    
    # Load ground truth
    gt_path = PROJECT_ROOT / "valuate" / "ground_truth1.json"
    ground_truths = {}
    if gt_path.exists():
        with open(gt_path, "r", encoding="utf-8") as f:
            gt_data = json.load(f)
            # dict of id -> answer
            ground_truths = {item["id"]: item["answer"] for item in gt_data}
            logger.info(f"Loaded {len(ground_truths)} ground truth answers from {gt_path}")
    else:
        logger.warning(f"Ground truth file not found: {gt_path}. Will use 'ground_truth' from jsonl if available.")

    results = []
    correct_count = 0
    failed_count = 0

    from valuate.prompt_3_1 import EXAMPLE_REASONING, EXAMPLE_FEWSHOT
    from main import build_search_service # Dùng hàm build có sẵn từ main.py
    import re

    # Khởi tạo SearchService - chỉ search, không rerank
    search_service = build_search_service(
        use_remote_embedding=True,
        use_rerank=False,
        use_remote_rerank=False
    )
    
    api_client = RemoteAPIClient()

    logger.info("Starting RAG Evaluation (Search + Reasoning + Few-shot)...")
    
    for idx, item in enumerate(tqdm(data, desc="Evaluating")):
        question_id = idx + 1
        query = item.get('question', '')
        
        # BƯỚC 1: SEARCH - Chỉ search, không rerank (giống evaluate.py)
        try:
            search_results = search_service.search(
                query=query,
                top_k_retrieve=5,
                use_rerank=False,
            )

            # Gom context lại và định dạng
            context_parts = []
            for i, res in enumerate(search_results, 1):
                meta = res.metadata or {}
                hierarchy = ["diem", "khoan", "dieu", "muc", "chuong", "phan", "van_ban"]
                ref_parts = [str(meta[k]) for k in hierarchy if meta.get(k)]
                ref_display = " ".join(ref_parts) or res.chunk_id
                context_parts.append(f"[Nguồn {i}]: {ref_display}\n{res.text}")
            context_text = "\n\n".join(context_parts)
            # Truncate context to avoid exceeding the LLM's 8000 token limit
            if len(context_text) > 15000:
                logger.warning(f"Truncating context for question {question_id} from {len(context_text)} chars to 15000 chars.")
                context_text = context_text[:15000] + "\n...[Ngữ cảnh đã bị cắt bớt do giới hạn độ dài]..."

        except Exception as e:
            logger.error(f"Search failed for question {question_id}: {e}")
            context_text = "Không tìm thấy ngữ cảnh liên quan."

        # BƯỚC 2: BUILD PROMPT - Kết hợp Context vào Prompt
        prompt = f"{EXAMPLE_REASONING}\n\n"
        prompt += "--- VÍ DỤ THAM KHẢO ---\n"
        prompt += f"{EXAMPLE_FEWSHOT}\n\n"
        prompt += "--- NGỮ CẢNH TÌM KIẾM ĐƯỢC (CONTEXT) ---\n"
        prompt += f"{context_text}\n\n"
        prompt += "--- CÂU HỎI THỰC TẾ CẦN GIẢI QUYẾT ---\n"
        prompt += f"Nhiệm vụ: {item.get('instruction', '')}\n"
        prompt += f"Câu hỏi: {query}\n"
        prompt += f"Danh sách đáp án:\n{item.get('answers', '')}\n"
        prompt += "\nHãy dựa vào NGỮ CẢNH trên (nếu có) và kiến thức pháp luật để suy luận và đưa ra đáp án đúng nhất vào trong thẻ <output>."

        try:
            # Generate answer with more tokens for reasoning
            predicted_answer = api_client.generate(prompt=prompt, max_length=2048, temperature=0.1)
            
            # Extract answer from <output>...</output>
            match = re.search(r'<output>\s*([A-D])\s*</output>', predicted_answer, re.IGNORECASE)
            if match:
                predicted_char = match.group(1).upper()
            else:
                # Fallback: look for the first A, B, C, or D in the entire response if tags are missing
                # but focus on the end of the response or look for "Đáp án là A" style
                fallback_match = re.search(r'(?:đáp án|chọn|là)\s*([A-D])', predicted_answer, re.IGNORECASE)
                if fallback_match:
                    predicted_char = fallback_match.group(1).upper()
                else:
                    # Last resort: just try to find any A/B/C/D if it's very short
                    clean_ans = predicted_answer.strip().upper()
                    if len(clean_ans) == 1 and clean_ans in 'ABCD':
                        predicted_char = clean_ans
                    else:
                        predicted_char = "N/A"

            # Get ground truth
            gt = ground_truths.get(question_id, item.get("ground_truth", ""))
            
            is_correct = (predicted_char == gt)
            if is_correct:
                correct_count += 1
                
            results.append({
                "id": question_id,
                "question": item.get("question", ""),
                "predicted": predicted_char,
                "ground_truth": gt,
                "is_correct": is_correct,
                "raw_response": predicted_answer
            })
            
        except Exception as e:
            logger.error(f"Error evaluating question {question_id}: {str(e)}")
            failed_count += 1
            results.append({
                "id": question_id,
                "question": item.get("question", ""),
                "predicted": "ERROR",
                "ground_truth": ground_truths.get(question_id, item.get("ground_truth", "")),
                "is_correct": False,
                "raw_response": str(e)
            })

        # To avoid rate limiting or overwhelming the server, sleep slightly if needed
        # time.sleep(0.5)
        
    api_client.close()

    total_valid = len(data) - failed_count
    accuracy = (correct_count / total_valid) * 100 if total_valid > 0 else 0

    logger.info("=" * 50)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 50)
    logger.info(f"Total Questions: {len(data)}")
    logger.info(f"Failed API Calls: {failed_count}")
    logger.info(f"Correct Answers: {correct_count}")
    logger.info(f"Accuracy: {accuracy:.2f}%")
    logger.info("=" * 50)

    # Save results to file
    output_file = PROJECT_ROOT / "valuate" / "evaluation_results1.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({
            "summary": {
                "total": len(data),
                "failed": failed_count,
                "correct": correct_count,
                "accuracy": accuracy
            },
            "details": results
        }, f, ensure_ascii=False, indent=4)
        
    logger.info(f"Results saved to {output_file}")

if __name__ == "__main__":
    evaluate()
