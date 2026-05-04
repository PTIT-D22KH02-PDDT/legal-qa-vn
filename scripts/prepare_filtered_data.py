import polars as pl
import os

# --- Cấu hình đường dẫn ---
AGENCIES_FILE = "/content/drive/MyDrive/legal-qa-vn_data/data/co_quan_filtered.csv"
CONTENT_IN = "/content/drive/MyDrive/legal-qa-vn_data/data/content.parquet"
METADATA_IN = "/content/drive/MyDrive/legal-qa-vn_data/data/metadata.parquet"
CONTENT_OUT = "/content/drive/MyDrive/legal-qa-vn_data/data/content_filtered.parquet" # Lưu tạm tên khác để an toàn

def prepare_data():
    print("1. Reading filtered agencies list...")
    # Lấy danh sách cơ quan từ cột đầu tiên bất kể tên là gì
    agencies_df = pl.read_csv(AGENCIES_FILE)
    allowed_agencies = agencies_df.select(df_col = pl.col(agencies_df.columns[0]).str.strip_chars().str.to_lowercase()).to_series().to_list()
    print(f"   - Found {len(allowed_agencies)} target agencies.")

    print("2. Reading metadata...")
    # Lấy id, co_quan_ban_hanh và so_ky_hieu, ép kiểu id sang String để join
    meta_df = pl.scan_parquet(METADATA_IN).select([
        pl.col("id").cast(pl.Utf8),
        pl.col("co_quan_ban_hanh"),
        pl.col("so_ky_hieu").alias("so_hieu")
    ])

    print("3. Filtering metadata...")
    meta_filtered = meta_df.filter(
        pl.col("co_quan_ban_hanh").str.to_lowercase().str.strip_chars().is_in(allowed_agencies)
    ).collect()
    print(f"   - {len(meta_filtered)} documents match the criteria.")

    print("4. Joining with content parquet...")
    # Đọc content, đổi tên content_html thành content
    content_df = pl.scan_parquet(CONTENT_IN).select([
        pl.col("id").cast(pl.Utf8),
        pl.col("content_html").alias("content")
    ])

    final_df = content_df.join(
        meta_filtered.lazy(),
        on="id",
        how="inner"
    ).select(["id", "content", "so_hieu", "co_quan_ban_hanh"]).collect(engine="streaming") # Đã cập nhật engine streaming

    print(f"5. Saving full result to {CONTENT_OUT}...")
    final_df.write_parquet(CONTENT_OUT)

    # Đảm bảo thư mục tồn tại
    JSON_SAMPLE = "data/data/content_sample.json"
    os.makedirs(os.path.dirname(JSON_SAMPLE), exist_ok=True)

    print(f"6. Exporting sample JSON (50 rows) to {JSON_SAMPLE}...")
    final_df.head(50).write_json(JSON_SAMPLE)

    print("\n=== SUCCESS ===")
    print(f"Total records after filtering: {len(final_df)}")
    print(f"- Parquet: {CONTENT_OUT} (Use this for indexing)")
    print(f"- Sample JSON: {JSON_SAMPLE} (Open this to inspect!)")

if __name__ == "__main__":
    prepare_data()