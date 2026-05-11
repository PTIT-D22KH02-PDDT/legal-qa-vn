import json

def calculate_accuracy(json_file_path):
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy file tại {json_file_path}")
        return
    if not data:
        print("File rỗng.")
        return

    correct_count = 0
    total_count = len(data)
    for item in data:
        predict = str(item.get("predict", "")).strip().upper()
        ground_truth = str(item.get("groundtruth", "")).strip().upper()

        if predict == ground_truth and predict != "":
            correct_count += 1

    accuracy = (correct_count / total_count) * 100

    print(f"Tổng số câu hỏi: {total_count}")
    print(f"Số câu trả lời đúng: {correct_count}")
    print(f"Số câu trả lời sai: {total_count - correct_count}")
    print(f"Accuracy: {accuracy:.2f}%")

if __name__ == "__main__":
    calculate_accuracy("data/evaluate/rag_predict_result_1_4.json")