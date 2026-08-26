from __future__ import annotations

import csv
from pathlib import Path

import pytest

from lion_de_exam.warehouse import build_base_warehouse


@pytest.fixture(scope="session")
def phase2_warehouse(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    root = tmp_path_factory.mktemp("phase2-actual")
    database = root / "actual.duckdb"
    evidence = root / "evidence"
    build_base_warehouse(database, evidence_dir=evidence)
    return database, evidence


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


@pytest.fixture(scope="session")
def synthetic_phase2_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("phase2-synthetic")
    data = root / "dataset"
    data.mkdir()
    _write_csv(
        data / "members.csv",
        [
            "member_id",
            "member_name",
            "member_level",
            "city",
            "birth_date",
            "register_date",
            "extract_date",
        ],
        [
            ["M000001", "Member 1", "一般", "台北", "1900-01-01", "2020-01-01", "2026-04-30"],
            ["M000001", "Member 1", "一般", "台北", "1980-01-02", "2020-01-01", "2026-05-31"],
            ["M000002", "Member 2", "銀卡", "台南", "1900-01-01", "2020-01-01", "2026-04-30"],
            ["M000003", "Member 3", "一般", "台北", "1981-01-01", "2020-01-01", "2026-04-30"],
            ["M000003", "Member 3", "一般", "台北", "1982-01-01", "2020-01-01", "2026-05-31"],
            ["M000004", "Member 4", "一般", "台北", "1980-01-01", "2020-01-01", "2026-04-30"],
            ["M000004", "Member 4", "一般", "台北", "1980-01-01", "2020-01-01", "2026-04-30"],
            ["M000005", "Member 5", "一般", "台北", "1980-01-01", "2020-01-01", "2026-04-30"],
            ["M000005", "Member 5", "銀卡", "台北", "1980-01-01", "2020-01-01", "2026-05-31"],
            ["M000005", "Member 5", "金卡", "台中", "1980-01-01", "2020-01-01", "2026-05-31"],
            ["M000005", "Member 5", "金卡", "台中", "1980-01-01", "2020-01-01", "2026-06-30"],
            ["M000006", "Member 6", "一般", "台北", "1980-01-01", "2020-01-01", "2026-04-30"],
            ["M000006", "Member 6", "金卡", "高雄", "1980-01-01", "2020-01-01", "2026-05-31"],
        ],
    )
    _write_csv(
        data / "products.csv",
        [
            "product_id",
            "product_name",
            "product_type",
            "destination_country",
            "destination_city",
            "trip_days",
            "base_price_twd",
            "is_active",
        ],
        [
            ["P00001", "Product 1", "tour", "TW", "Taipei", 1, "100.0000", "Y"],
            ["P00002", "Product 2", "tour", "TW", "Tainan", 1, "100.0000", "Y"],
        ],
    )
    fx_rows: list[list[object]] = []
    for rate_date in ("2026-05-01", "2026-06-15", "2026-06-30"):
        fx_rows.extend([[rate_date, "USD", "2.00000000"], [rate_date, "JPY", "0.20000000"]])
    _write_csv(data / "fx_rates.csv", ["rate_date", "currency", "rate_to_twd"], fx_rows)

    def order(
        order_id: str,
        *,
        member: str = "M000001",
        product: str = "P00001",
        status: str = "created",
        currency: str = "TWD",
        quantity: str = "1",
        amount: str = "100.0000",
        coupon: str = "0.0000",
        created: str = "2026-05-01T08:00:00+08:00",
        updated: str = "2026-05-01T08:01:00+08:00",
    ) -> list[object]:
        return [
            order_id,
            member,
            product,
            "web",
            status,
            quantity,
            currency,
            amount,
            coupon,
            created,
            "2026-07-01",
            updated,
        ]

    duplicate = order("ORD00000001")
    rows = [
        duplicate,
        duplicate.copy(),
        order("ORD00000002", product="P00001", updated="2026-05-01T09:00:00+08:00"),
        order("ORD00000002", product="P00002", updated="2026-05-01T09:00:00+08:00"),
        order("ORD00000003", product="P00001", updated="2026-05-01T09:00:00+08:00"),
        order("ORD00000003", product="P00002", updated="2026-05-01T10:00:00+08:00"),
        order("ORD00000004", status="created", updated="2026-05-01T09:00:00+08:00"),
        order("ORD00000004", status="paid", updated="2026-05-01T10:00:00+08:00"),
        order("ORD00000005", product="P99999"),
        order(
            "ORD00000006",
            member="M000005",
            created="2026-06-15T08:00:00+08:00",
            updated="2026-06-15T08:01:00+08:00",
        ),
        order(
            "ORD00000007",
            member="M000005",
            created="2026-06-30T08:00:00+08:00",
            updated="2026-06-30T08:01:00+08:00",
        ),
        order("ORD00000008", currency="NTD"),
        order("ORD00000009", currency="USD", amount="50.0000"),
        order("ORD00000010", currency="JPY", amount="500.0000"),
        order("ORD00000011", currency="EUR"),
        order("ORD00000012", amount="-1.0000"),
        order("ORD00000013", coupon="-1.0000"),
        order("ORD00000014", amount="1000.0000"),
        order("ORD00000015", amount="100.0050"),
        order("ORD00000016", status="completed", updated="2026-05-01T09:00:00+08:00"),
        order("ORD00000016", status="paid", updated="2026-05-01T10:00:00+08:00"),
        order("ORD00000017", quantity="2", amount="100.0000"),
        order(
            "ORD00000018",
            created="2026-05-01T00:00:00Z",
            updated="2026-05-01T09:00:00+08:00",
        ),
        order(
            "ORD00000018",
            created="2026-05-01T08:00:00+08:00",
            updated="2026-05-01T10:00:00+08:00",
        ),
        order(
            "ORD00000019",
            created="2026/05/01 08:00:00",
            updated="2026-05-01T09:00:00+08:00",
        ),
        order(
            "ORD00000019",
            created="2026-05-01T08:00:00+08:00",
            updated="2026-05-01T10:00:00+08:00",
        ),
        order(
            "ORD00000020",
            created="2026-05-01T08:00:00+08:00",
            updated="2026-05-01T09:00:00+08:00",
        ),
        order(
            "ORD00000020",
            created="2026-05-01T09:00:00+08:00",
            updated="2026-05-01T10:00:00+08:00",
        ),
    ]
    _write_csv(
        data / "orders_base.csv",
        [
            "order_id",
            "member_id",
            "product_id",
            "channel",
            "order_status",
            "quantity",
            "currency",
            "amount",
            "coupon_discount",
            "order_created_at",
            "departure_date",
            "updated_at",
        ],
        rows,
    )
    database = root / "synthetic.duckdb"
    build_base_warehouse(database, dataset_root=data)
    return database
