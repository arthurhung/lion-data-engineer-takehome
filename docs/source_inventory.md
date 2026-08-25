# Phase 0 Source Inventory

## 範圍與方法

本文件只做 Phase 0 輕量盤點，不判定資料品質問題，也不決定清洗、SCD2、fact、incremental
或金額處理策略。實際唯讀來源根目錄為 `LionDEExam/`；題目資料包為
`LionDEExam/candidate_package/`。

盤點於 2026-08-25（Asia/Taipei）執行。CSV 使用 Python `csv` 模組及 `utf-8-sig`
逐列讀取；row count 不含 header。每個 CSV 的實際資料列欄位數均與 header 欄位數一致。
所有 CSV 的前三個 bytes 均為 `EF BB BF`（UTF-8 BOM）。檔案大小取自 `stat`，單位為 byte。

## 原始題目邊界與附檔清單

- `LionDEExam/01_考題卷_資料工程師TakeHome.docx`
- `LionDEExam/candidate_package/README.md`
- `LionDEExam/candidate_package/buggy_pipeline.py`
- `LionDEExam/candidate_package/dataset/`：7 個 CSV
- `LionDEExam/candidate_package/module_D/`：`baseline_etl.py`、`generate_perf_data.py`
- `LionDEExam/candidate_package/module_E/`：2 個 JSON、4 個 warehouse CSV
- `LionDEExam/candidate_package/module_F/churn_training_pipeline.py`

原始題目 manifest 共 19 檔：`LionDEExam/candidate_package/` 18 檔，加上正式考題 Word 1 檔。
`LionDEExam/.DS_Store` 與 `LionDEExam/~$_考題卷_資料工程師TakeHome.docx` 也存在於目錄，
分別是作業系統 metadata 與 Word 鎖定檔；兩者不是題目內容，保留原位但不納入原始題目
manifest 或完整性結論。`AGENTS.md` 與 `SPEC.md` 位於 repo 根目錄，不在 `LionDEExam/`。

主考題 Word 經 OOXML 讀取為 93 個 paragraph、2 張 table、1 個 section；另渲染為 4 頁做
唯讀檢視。渲染環境缺少部分中文字型而出現缺字，但 OOXML 文字抽取完整可讀。未重新儲存
或修改 Word 文件。

## Part A CSV inventory

| 檔案 | bytes | rows | 欄位 |
|---|---:|---:|---|
| `dataset/orders_base.csv` | 12,431,524 | 100,040 | `order_id`, `member_id`, `product_id`, `channel`, `order_status`, `quantity`, `currency`, `amount`, `coupon_discount`, `order_created_at`, `departure_date`, `updated_at` |
| `dataset/orders_incremental_day1.csv` | 570,402 | 4,615 | 同 `orders_base.csv` 12 欄 |
| `dataset/orders_incremental_day2.csv` | 580,790 | 4,700 | 同 `orders_base.csv` 12 欄 |
| `dataset/orders_incremental_day3.csv` | 570,105 | 4,615 | 同 `orders_base.csv` 12 欄 |
| `dataset/members.csv` | 620,035 | 8,991 | `member_id`, `member_name`, `member_level`, `city`, `birth_date`, `register_date`, `extract_date` |
| `dataset/products.csv` | 18,898 | 300 | `product_id`, `product_name`, `product_type`, `destination_country`, `destination_city`, `trip_days`, `base_price_twd`, `is_active` |
| `dataset/fx_rates.csv` | 3,170 | 134 | `rate_date`, `currency`, `rate_to_twd` |

少量格式觀察（不是品質結論）：前兩筆 order sample 的 timestamp 為 ISO 8601 並含 `+08:00`；
日期欄位 sample 使用 `YYYY-MM-DD`；識別碼 sample 帶固定文字前綴；字串 sample 同時包含中文與
Latin 字元；數值在 CSV 中以文字表示。是否所有列均遵循這些格式，留待 Phase 1 驗證。

## Module E inventory

| 檔案 | bytes | rows / items | 欄位或結構 |
|---|---:|---:|---|
| `module_E/warehouse/dim_date.csv` | 2,005 | 61 rows | 6 欄：`date_key` 至 `is_weekend` |
| `module_E/warehouse/dim_member.csv` | 30,705 | 580 rows | 7 欄：`member_sk` 至 `is_current` |
| `module_E/warehouse/dim_product.csv` | 4,251 | 100 rows | 5 欄：`product_sk` 至 `destination_country` |
| `module_E/warehouse/fact_order.csv` | 1,079,303 | 20,000 rows | 9 欄：`order_id` 至 `coupon_discount_twd` |
| `module_E/questions.json` | 2,450 | 15 questions | 5 個 `semantic_definitions` |
| `module_E/llm_answers.json` | 5,597 | 12 answers | 每筆含 question mapping、SQL、result、explanation |

## 原始檔 SHA-256 manifest

[`docs/source_manifest.sha256`](source_manifest.sha256) 固定記錄 Phase 0 首次讀取時取得的 19 個
原始題目 SHA-256；不包含 `.DS_Store`、Word 鎖定檔、規格、報告或產出。Repo 尚無 Git commit，
所以空白的 `git diff` 不能單獨證明 untracked 原始檔未修改。實際驗證使用：

```bash
make source-integrity
```

此 manifest 僅用於原始檔 byte-level 完整性，不是資料內容或業務 reconciliation checksum。
2026-08-25 最終 Phase 0 驗收實際執行結果：manifest 19 筆全部回報 `OK`；其中正式考題
Word 的 SHA-256 為 `a708fecdbc833dc497416caa1fc0987da768cb33a48a6c8c4282b5e0a59b104d`。
