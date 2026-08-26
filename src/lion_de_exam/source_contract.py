"""Phase 1 typed contracts for the immutable Part A CSV sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
TIMESTAMP_OFFSET_PATTERN = (
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(Z|[+-][0-9]{2}:[0-9]{2})$"
)
BIRTH_DATE_SENTINEL = "1900-01-01"


@dataclass(frozen=True)
class ColumnContract:
    name: str
    logical_type: str
    duckdb_type: str
    nullable: bool
    description: str
    domain: tuple[str, ...] = ()
    pattern: str | None = None
    sensitive: bool = False
    decimal_scale: int | None = None
    accepted_raw_formats: tuple[str, ...] = ()
    canonical_typed_format: str | None = None
    normalization_assumption: str | None = None
    normalization_quality_flag: str | None = None
    semantic_sentinel_values: tuple[str, ...] = ()
    canonical_nullable: bool | None = None
    semantic_normalization: str | None = None
    semantic_quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceContract:
    dataset: str
    files: tuple[str, ...]
    business_key: tuple[str, ...]
    columns: tuple[ColumnContract, ...]


def column(
    name: str,
    logical_type: str,
    duckdb_type: str,
    description: str,
    *,
    nullable: bool = False,
    domain: tuple[str, ...] = (),
    pattern: str | None = None,
    sensitive: bool = False,
    decimal_scale: int | None = None,
    accepted_raw_formats: tuple[str, ...] = (),
    canonical_typed_format: str | None = None,
    normalization_assumption: str | None = None,
    normalization_quality_flag: str | None = None,
    semantic_sentinel_values: tuple[str, ...] = (),
    canonical_nullable: bool | None = None,
    semantic_normalization: str | None = None,
    semantic_quality_flags: tuple[str, ...] = (),
) -> ColumnContract:
    return ColumnContract(
        name=name,
        logical_type=logical_type,
        duckdb_type=duckdb_type,
        nullable=nullable,
        description=description,
        domain=domain,
        pattern=pattern,
        sensitive=sensitive,
        decimal_scale=decimal_scale,
        accepted_raw_formats=accepted_raw_formats,
        canonical_typed_format=canonical_typed_format,
        normalization_assumption=normalization_assumption,
        normalization_quality_flag=normalization_quality_flag,
        semantic_sentinel_values=semantic_sentinel_values,
        canonical_nullable=canonical_nullable,
        semantic_normalization=semantic_normalization,
        semantic_quality_flags=semantic_quality_flags,
    )


ORDER_COLUMNS = (
    column("order_id", "business_key", "VARCHAR", "訂單來源識別碼", pattern=r"^ORD[0-9]{8}$"),
    column(
        "member_id", "foreign_business_key", "VARCHAR", "會員來源識別碼", pattern=r"^M[0-9]{6}$"
    ),
    column(
        "product_id", "foreign_business_key", "VARCHAR", "產品來源識別碼", pattern=r"^P[0-9]{5}$"
    ),
    column("channel", "categorical", "VARCHAR", "訂購通路", domain=("app", "web", "門市", "電銷")),
    column(
        "order_status",
        "categorical",
        "VARCHAR",
        "訂單事件狀態",
        domain=("created", "paid", "completed", "cancelled"),
    ),
    column("quantity", "integer", "INTEGER", "訂購數量"),
    column(
        "currency",
        "currency_code",
        "VARCHAR",
        "原幣別；NTD 僅在本來源正規化為 canonical TWD",
        domain=("JPY", "NTD", "TWD", "USD"),
        normalization_assumption="NTD is a source-specific alias of TWD; preserve raw currency",
    ),
    column("amount", "decimal", "DECIMAL(24,4)", "原幣別金額", decimal_scale=4),
    column("coupon_discount", "decimal", "DECIMAL(24,4)", "題目定義為 TWD 的折扣", decimal_scale=4),
    column(
        "order_created_at",
        "timestamp_with_timezone",
        "TIMESTAMPTZ",
        "訂單建立時間；來源預期帶 offset",
        pattern=TIMESTAMP_OFFSET_PATTERN,
        accepted_raw_formats=("ISO_8601_WITH_OFFSET", "YYYY/MM/DD HH:MM:SS"),
        canonical_typed_format="TIMESTAMPTZ",
        normalization_assumption=(
            "Only for this documented source, timezone-less YYYY/MM/DD HH:MM:SS is interpreted "
            "as Asia/Taipei based on Taiwan business context and updated_at +08:00 evidence"
        ),
        normalization_quality_flag="timezone_assumed=true",
    ),
    column("departure_date", "date", "DATE", "出發日", pattern=DATE_PATTERN),
    column(
        "updated_at",
        "timestamp_with_timezone",
        "TIMESTAMPTZ",
        "訂單事件更新時間；來源預期帶 offset",
        pattern=TIMESTAMP_OFFSET_PATTERN,
        accepted_raw_formats=("ISO_8601_WITH_OFFSET",),
        canonical_typed_format="TIMESTAMPTZ",
    ),
)


CONTRACTS: tuple[SourceContract, ...] = (
    SourceContract(
        dataset="orders",
        files=(
            "orders_base.csv",
            "orders_incremental_day1.csv",
            "orders_incremental_day2.csv",
            "orders_incremental_day3.csv",
        ),
        business_key=("order_id",),
        columns=ORDER_COLUMNS,
    ),
    SourceContract(
        dataset="members",
        files=("members.csv",),
        business_key=("member_id", "extract_date"),
        columns=(
            column(
                "member_id", "business_key", "VARCHAR", "會員來源識別碼", pattern=r"^M[0-9]{6}$"
            ),
            column("member_name", "text", "VARCHAR", "會員姓名", sensitive=True),
            column(
                "member_level",
                "categorical",
                "VARCHAR",
                "會員等級",
                domain=("一般", "銀卡", "金卡", "白金"),
            ),
            column("city", "text", "VARCHAR", "居住城市"),
            column(
                "birth_date",
                "date",
                "DATE",
                "出生日期；raw parse-valid sentinel 需與 canonical identity value 分離",
                nullable=True,
                pattern=DATE_PATTERN,
                sensitive=True,
                semantic_sentinel_values=(BIRTH_DATE_SENTINEL,),
                canonical_nullable=True,
                semantic_normalization=(
                    "Preserve raw value; normalize source sentinel 1900-01-01 to canonical NULL. "
                    "A member with sentinel plus exactly one distinct non-sentinel date may use "
                    "that non-sentinel date as a correction/restatement candidate. Two or more "
                    "distinct non-sentinel dates are identity ambiguity and require quarantine."
                ),
                semantic_quality_flags=("birth_date_sentinel", "birth_date_unknown"),
            ),
            column("register_date", "date", "DATE", "註冊日期", pattern=DATE_PATTERN),
            column("extract_date", "date", "DATE", "快照萃取日期", pattern=DATE_PATTERN),
        ),
    ),
    SourceContract(
        dataset="products",
        files=("products.csv",),
        business_key=("product_id",),
        columns=(
            column(
                "product_id", "business_key", "VARCHAR", "產品來源識別碼", pattern=r"^P[0-9]{5}$"
            ),
            column("product_name", "text", "VARCHAR", "產品名稱"),
            column("product_type", "categorical", "VARCHAR", "產品類型"),
            column("destination_country", "text", "VARCHAR", "目的地國家"),
            column("destination_city", "text", "VARCHAR", "目的地城市"),
            column("trip_days", "integer", "INTEGER", "行程天數"),
            column("base_price_twd", "decimal", "DECIMAL(24,4)", "TWD 牌價", decimal_scale=4),
            column("is_active", "categorical", "VARCHAR", "產品啟用旗標", domain=("N", "Y")),
        ),
    ),
    SourceContract(
        dataset="fx_rates",
        files=("fx_rates.csv",),
        business_key=("rate_date", "currency"),
        columns=(
            column("rate_date", "date", "DATE", "匯率適用日期", pattern=DATE_PATTERN),
            column("currency", "currency_code", "VARCHAR", "原幣別代碼", domain=("JPY", "USD")),
            column(
                "rate_to_twd",
                "decimal",
                "DECIMAL(24,8)",
                "一單位原幣乘此 rate 換算為 TWD",
                decimal_scale=8,
            ),
        ),
    ),
)


CONTRACT_BY_DATASET = {contract.dataset: contract for contract in CONTRACTS}


def normalize_birth_date(raw_value: str | None) -> dict[str, object]:
    """Apply the Phase 1 birth-date semantic contract while retaining the raw value."""
    if raw_value is None or raw_value.strip() == "":
        return {
            "raw_birth_date": raw_value,
            "birth_date": None,
            "birth_date_sentinel": False,
            "birth_date_unknown": True,
        }
    parsed = date.fromisoformat(raw_value)
    sentinel = raw_value == BIRTH_DATE_SENTINEL
    return {
        "raw_birth_date": raw_value,
        "birth_date": None if sentinel else parsed,
        "birth_date_sentinel": sentinel,
        "birth_date_unknown": sentinel,
    }


def canonical_contract() -> dict[str, object]:
    """Return a JSON-serializable contract with deterministic record ordering."""
    return {
        "contract_status": "phase_1_correction_implementation_complete_acceptance_pending",
        "row_count_definition": "CSV data rows excluding the header row",
        "raw_value_policy": (
            "Raw CSV text and raw semantic values remain immutable; typed/canonical values "
            "are derived separately and preserve lineage."
        ),
        "sources": [asdict(contract) for contract in CONTRACTS],
    }
