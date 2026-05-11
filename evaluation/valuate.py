import sys
try:
    __import__('pysqlite3')
    sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')
except ImportError:
    pass

import json
import logging
import time
import re
from pathlib import Path
from tqdm import tqdm
from main import setup_workflow_dependencies
from src.api.nvidia_api_client import OpenAICompatibleClient
from src.agent.graph import build_graph
from src.agent.state import initial_state
from evaluate.prompt_1_4 import EXAMPLE_FEWSHOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent

def evaluate():
    logger.info("Starting evaluation (Standard mode)...")
    
    # Load dataset
    dataset_path = PROJECT_ROOT / "evaluate" / "loc_1_4_100.jsonl"
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
    gt_path = PROJECT_ROOT / "evaluate" / "ground_truth.json"
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

    # Khởi tạo workflow dependencies
    deps = setup_workflow_dependencies()
    
    # Build graph
    graph = build_graph(
        llm=deps["llm"],
        db_client=deps["db_client"],
        retriever=deps["retriever"],
        doc_retriever=deps["doc_retriever"],
    )
    
    api_client = OpenAICompatibleClient()
    logger.info("Starting RAG Evaluation (Graph Search + Manual Prompt)...")
    
    for idx, item in enumerate(tqdm(data, desc="Evaluating")):
        question_id = idx + 1
        query = item.get('question', '')
        
        try:
            # 1. Invoke graph để lấy context từ search
            initial = initial_state(query)
            result = graph.invoke(initial)
            
            # 2. Lấy context từ kết quả graph
            context_text = ""
            if result.get("context_text"):
                context_text = "\n\n".join(result["context_text"])
            
            if len(context_text) > 15000:
                logger.warning(f"Truncating context for question {question_id}")
                context_text = context_text[:15000] + "\n...[Ngữ cảnh đã bị cắt bớt]..."

        except Exception as e:
            logger.error(f"Graph search failed for question {question_id}: {e}")
            context_text = "Không tìm thấy ngữ cảnh."

        # 3. BUILD PROMPT manually
        prompt = f"{EXAMPLE_FEWSHOT}\n\n"
        prompt += "--- NGỮ CẢNH TÌM KIẾM ĐƯỢC (CONTEXT) ---\n"
        prompt += f"{context_text}\n\n"
        prompt += "--- CÂU HỎI THỰC TẾ ---\n"
        prompt += f"Instruction: {item.get('instruction', '')}\n"
        prompt += f"Câu hỏi: {query}\n"
        prompt += f"Đáp án:\n{item.get('answers', '')}\n"
        prompt += "Dựa vào ngữ cảnh trên, đáp án đúng (Chỉ ghi chữ cái A, B, C hoặc D):"
        prompt += "\n\n**LƯU Ý**: Chỉ trả lời A, B, C, hoặc D. Dựa vào CONTEXT để trả lời."

        try:
            # 4. Call LLM
            predicted_answer = api_client.generate(prompt=prompt)
            
            # 5. Extract A/B/C/D
            match = re.search(r'\b([A-D])\b', predicted_answer.upper())
            if match:
                predicted_char = match.group(1)
            else:
                clean_ans = predicted_answer.strip().upper()
                if len(clean_ans) > 0 and clean_ans[0] in ['A', 'B', 'C', 'D']:
                    predicted_char = clean_ans[0]
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
    output_file = PROJECT_ROOT / "evaluation" / "evaluation_result_1.4_rerank5_top20_1.json"
    import os
    os.makedirs(output_file.parent, exist_ok=True)
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