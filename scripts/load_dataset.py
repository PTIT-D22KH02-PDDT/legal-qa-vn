from huggingface_hub import snapshot_download

# Lệnh này sẽ tải toàn bộ các file (content, metadata, legacy, relationships...) 
# trực tiếp từ repo Hugging Face về thư mục "data" của bạn.
snapshot_download(
    repo_id="th1nhng0/vietnamese-legal-documents", 
    repo_type="dataset", 
    local_dir="data/"
)
print("Đã tải xong!")