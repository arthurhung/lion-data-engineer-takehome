"""Phase 3 incremental, idempotent and replayable local ETL."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import duckdb

from lion_de_exam.incremental_reconciliation import (
    EVIDENCE_FILES,
    analytical_snapshot,
    snapshot_sha256,
    write_phase3_evidence,
)
from lion_de_exam.reconciliation import DEFAULT_VALIDATION_SQL
from lion_de_exam.warehouse import DEFAULT_DATASET_ROOT, PROJECT_ROOT, build_base_warehouse

ORDER_HEADER = (
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
)


@dataclass(frozen=True)
class BatchSpec:
    order: int
    name: str
    file_name: str


BATCHES = (
    BatchSpec(0, "base", "orders_base.csv"),
    BatchSpec(1, "day1", "orders_incremental_day1.csv"),
    BatchSpec(2, "day2", "orders_incremental_day2.csv"),
    BatchSpec(3, "day3", "orders_incremental_day3.csv"),
)
REFERENCE_FILES = {
    "members.csv": "member_snapshot",
    "products.csv": "product_master",
    "fx_rates.csv": "fx_rate",
}
REFERENCE_HEADERS = {
    "members.csv": (
        "member_id",
        "member_name",
        "member_level",
        "city",
        "birth_date",
        "register_date",
        "extract_date",
    ),
    "products.csv": (
        "product_id",
        "product_name",
        "product_type",
        "destination_country",
        "destination_city",
        "trip_days",
        "base_price_twd",
        "is_active",
    ),
    "fx_rates.csv": ("rate_date", "currency", "rate_to_twd"),
}


@dataclass(frozen=True)
class FileMetadata:
    source_file: str
    file_sha256: str
    schema_sha256: str
    byte_size: int
    row_count: int


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_csv(path: Path, expected_header: tuple[str, ...]) -> FileMetadata:
    if not path.is_file():
        raise FileNotFoundError(f"Missing source file: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = tuple(next(reader))
        if header != expected_header:
            raise ValueError(f"Header mismatch for {path.name}: {header}")
        row_count = sum(1 for _ in reader)
    schema_sha256 = hashlib.sha256(
        json.dumps(header, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    return FileMetadata(path.name, _hash_file(path), schema_sha256, path.stat().st_size, row_count)


def _sql(name: str) -> str:
    return (PROJECT_ROOT / "sql" / name).read_text(encoding="utf-8")


def _literal(value: str) -> str:
    return value.replace("'", "''")


def _record_attempt(
    connection: duckdb.DuckDBPyConnection,
    batch_order: int,
    metadata: FileMetadata,
    status: str = "RUNNING",
) -> int:
    _interrupt_stale_attempts(connection)
    return connection.execute(
        "INSERT INTO audit.batch_attempt(batch_order,source_file,file_sha256,status) "
        "VALUES (?,?,?,?) RETURNING attempt_id",
        [batch_order, metadata.source_file, metadata.file_sha256, status],
    ).fetchone()[0]


def _interrupt_stale_attempts(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        "UPDATE audit.batch_attempt SET status='INTERRUPTED',finished_at=current_timestamp,"
        "failure_message='superseded stale RUNNING attempt; single-writer recovery' "
        "WHERE status='RUNNING'"
    )


def _finish_attempt(
    connection: duckdb.DuckDBPyConnection,
    attempt_id: int,
    status: str,
    failure: str | None = None,
) -> None:
    connection.execute(
        "UPDATE audit.batch_attempt SET status=?,finished_at=current_timestamp,failure_message=? "
        "WHERE attempt_id=?",
        [status, failure, attempt_id],
    )


def _register_file(
    connection: duckdb.DuckDBPyConnection,
    metadata: FileMetadata,
    dataset_role: str,
    batch_order: int,
) -> None:
    connection.execute(
        "INSERT INTO audit.source_file_registry(source_file,dataset_role,batch_order,file_sha256,"
        "schema_sha256,byte_size,source_row_count) VALUES (?,?,?,?,?,?,?)",
        [
            metadata.source_file,
            dataset_role,
            batch_order,
            metadata.file_sha256,
            metadata.schema_sha256,
            metadata.byte_size,
            metadata.row_count,
        ],
    )


def _refresh_analytical_state(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(_sql("incremental_order_staging.sql"))
    for table in (
        "quality.quarantine_row",
        "quality.entity_disposition",
        "quality.entity_rule",
        "quality.issue_hit",
    ):
        connection.execute(f"DELETE FROM {table}")
    connection.execute(_sql("quality_gates.sql"))
    connection.execute(_sql("incremental_dimensions.sql"))
    connection.execute(_sql("incremental_fact_order.sql"))
    connection.execute(DEFAULT_VALIDATION_SQL.read_text(encoding="utf-8"))
    connection.execute(_sql("incremental_validation.sql"))
    failures = connection.execute(
        "SELECT check_id,violation_count FROM quality.validation_result "
        "WHERE violation_count<>0 ORDER BY check_id"
    ).fetchall()
    if failures:
        raise RuntimeError(f"Incremental validation failed: {failures}")


def refresh_member_projection(connection: duckdb.DuckDBPyConnection) -> None:
    """Reproject cumulative member snapshots for synthetic incremental SCD2 verification."""
    connection.execute(_sql("incremental_member_staging.sql"))
    for table in (
        "quality.quarantine_row",
        "quality.entity_disposition",
        "quality.entity_rule",
        "quality.issue_hit",
    ):
        connection.execute(f"DELETE FROM {table}")
    connection.execute(_sql("quality_gates.sql"))
    connection.execute(_sql("incremental_member_scd2.sql"))
    connection.execute(_sql("incremental_dimensions.sql"))
    connection.execute(_sql("incremental_fact_order.sql"))


def _insert_reconciliation(
    connection: duckdb.DuckDBPyConnection, batch: BatchSpec
) -> str:
    snapshot = analytical_snapshot(connection, batch.order, batch.name)
    checksum = snapshot_sha256(snapshot)
    connection.execute(
        "INSERT INTO audit.batch_reconciliation VALUES (?,?,?,?)",
        [
            batch.order,
            batch.name,
            checksum,
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
        ],
    )
    return checksum


def initialize_phase3(
    database: Path, dataset_root: Path = DEFAULT_DATASET_ROOT
) -> dict[str, object]:
    if database.exists():
        raise FileExistsError(f"Refusing to overwrite existing warehouse: {database}")
    build_base_warehouse(database, dataset_root=dataset_root)
    connection = duckdb.connect(str(database))
    committed = False
    transaction_open = False
    attempt_id: int | None = None
    try:
        connection.execute("SET TimeZone='UTC'")
        connection.execute(_sql("incremental_schema.sql"))
        base_metadata = inspect_csv(dataset_root / BATCHES[0].file_name, ORDER_HEADER)
        attempt_id = _record_attempt(connection, 0, base_metadata)
        connection.execute("BEGIN TRANSACTION")
        transaction_open = True
        _register_file(connection, base_metadata, "order_event", 0)
        for file_name, role in REFERENCE_FILES.items():
            metadata = inspect_csv(dataset_root / file_name, REFERENCE_HEADERS[file_name])
            _register_file(connection, metadata, role, 0)
        _refresh_analytical_state(connection)
        checksum = _insert_reconciliation(connection, BATCHES[0])
        connection.execute("COMMIT")
        transaction_open = False
        committed = True
        _finish_attempt(connection, attempt_id, "SUCCEEDED")
        return {"batch": "base", "status": "SUCCEEDED", "analytical_sha256": checksum}
    except Exception as exc:
        if transaction_open:
            connection.execute("ROLLBACK")
        if attempt_id is not None:
            try:
                _finish_attempt(connection, attempt_id, "FAILED", str(exc))
            except Exception:
                pass
        raise
    finally:
        connection.close()
        if not committed and database.exists():
            database.unlink()


def _check_registry(
    connection: duckdb.DuckDBPyConnection, metadata: FileMetadata
) -> tuple[str, str] | None:
    return connection.execute(
        "SELECT file_sha256,schema_sha256 FROM audit.source_file_registry WHERE source_file=?",
        [metadata.source_file],
    ).fetchone()


def _attempt_has_different_hash(
    connection: duckdb.DuckDBPyConnection, metadata: FileMetadata
) -> bool:
    return connection.execute(
        "SELECT count(*)>0 FROM audit.batch_attempt "
        "WHERE source_file=? AND file_sha256<>?",
        [metadata.source_file, metadata.file_sha256],
    ).fetchone()[0]


def process_order_batch(
    database: Path,
    batch: BatchSpec,
    source_path: Path,
    *,
    fail_after_refresh: bool = False,
) -> dict[str, object]:
    if not database.is_file():
        raise FileNotFoundError(f"Phase 3 warehouse does not exist: {database}")
    metadata = inspect_csv(source_path, ORDER_HEADER)
    if metadata.source_file != batch.file_name:
        raise ValueError(
            f"Logical filename mismatch: expected {batch.file_name}, got {metadata.source_file}"
        )
    connection = duckdb.connect(str(database))
    attempt_id: int | None = None
    transaction_open = False
    try:
        connection.execute("SET TimeZone='UTC'")
        existing = _check_registry(connection, metadata)
        if existing is None and _attempt_has_different_hash(connection, metadata):
            _interrupt_stale_attempts(connection)
            raise ValueError(
                "logical filename was previously attempted with different SHA-256"
            )
        attempt_id = _record_attempt(connection, batch.order, metadata)
        if existing:
            if existing != (metadata.file_sha256, metadata.schema_sha256):
                message = "logical filename already registered with different SHA-256 or schema"
                _finish_attempt(connection, attempt_id, "FAILED", message)
                raise ValueError(message)
            _finish_attempt(connection, attempt_id, "SKIPPED_ALREADY_APPLIED")
            checksum = connection.execute(
                "SELECT analytical_sha256 FROM audit.batch_reconciliation WHERE batch_order=?",
                [batch.order],
            ).fetchone()[0]
            return {
                "batch": batch.name,
                "status": "SKIPPED_ALREADY_APPLIED",
                "analytical_sha256": checksum,
            }

        prior = connection.execute(
            "SELECT count(*) FROM audit.batch_reconciliation WHERE batch_order=?",
            [batch.order - 1],
        ).fetchone()[0]
        later = connection.execute(
            "SELECT count(*) FROM audit.batch_reconciliation WHERE batch_order>=?",
            [batch.order],
        ).fetchone()[0]
        if not prior or later:
            message = f"Batch {batch.name} is not the strict next unapplied batch"
            _finish_attempt(connection, attempt_id, "FAILED", message)
            raise ValueError(message)

        connection.execute("BEGIN TRANSACTION")
        transaction_open = True
        _register_file(connection, metadata, "order_event", batch.order)
        rendered = (
            _sql("incremental_order_ingest.sql")
            .replace("{{source_path}}", _literal(str(source_path.resolve())))
            .replace("{{source_file}}", _literal(metadata.source_file))
            .replace("{{batch_order}}", str(batch.order))
        )
        connection.execute(rendered)
        _refresh_analytical_state(connection)
        if fail_after_refresh:
            raise RuntimeError("synthetic failure after analytical refresh")
        checksum = _insert_reconciliation(connection, batch)
        connection.execute("COMMIT")
        transaction_open = False
        _finish_attempt(connection, attempt_id, "SUCCEEDED")
        return {"batch": batch.name, "status": "SUCCEEDED", "analytical_sha256": checksum}
    except Exception as exc:
        if transaction_open:
            connection.execute("ROLLBACK")
        if attempt_id is not None:
            row = connection.execute(
                "SELECT status FROM audit.batch_attempt WHERE attempt_id=?", [attempt_id]
            ).fetchone()
            if row and row[0] == "RUNNING":
                _finish_attempt(connection, attempt_id, "FAILED", str(exc))
        raise
    finally:
        connection.close()


def _verify_base_replay(database: Path, dataset_root: Path) -> dict[str, object]:
    connection = duckdb.connect(str(database))
    attempt_id: int | None = None
    try:
        metadata = inspect_csv(dataset_root / BATCHES[0].file_name, ORDER_HEADER)
        attempt_id = _record_attempt(connection, 0, metadata)
        inputs = [metadata]
        inputs.extend(
            inspect_csv(dataset_root / file_name, REFERENCE_HEADERS[file_name])
            for file_name in REFERENCE_FILES
        )
        for item in inputs:
            existing = _check_registry(connection, item)
            expected = (item.file_sha256, item.schema_sha256)
            if existing != expected:
                message = (
                    f"{item.source_file} is not registered with the same SHA-256 and schema"
                )
                _finish_attempt(connection, attempt_id, "FAILED", message)
                raise ValueError(message)
        _finish_attempt(connection, attempt_id, "SKIPPED_ALREADY_APPLIED")
        checksum = connection.execute(
            "SELECT analytical_sha256 FROM audit.batch_reconciliation WHERE batch_order=0"
        ).fetchone()[0]
        return {"batch": "base", "status": "SKIPPED_ALREADY_APPLIED", "analytical_sha256": checksum}
    except Exception as exc:
        if attempt_id is not None:
            row = connection.execute(
                "SELECT status FROM audit.batch_attempt WHERE attempt_id=?", [attempt_id]
            ).fetchone()
            if row and row[0] == "RUNNING":
                _finish_attempt(connection, attempt_id, "FAILED", str(exc))
        raise
    finally:
        connection.close()


def run_all(database: Path, dataset_root: Path = DEFAULT_DATASET_ROOT) -> list[dict[str, object]]:
    results = []
    if database.exists():
        results.append(_verify_base_replay(database, dataset_root))
    else:
        results.append(initialize_phase3(database, dataset_root))
    for batch in BATCHES[1:]:
        results.append(process_order_batch(database, batch, dataset_root / batch.file_name))
    return results


def current_state_checksum(database: Path) -> str:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        snapshot = analytical_snapshot(connection, 3, "day3")
        return snapshot_sha256(snapshot)
    finally:
        connection.close()


def rerun_proof(
    database: Path, dataset_root: Path = DEFAULT_DATASET_ROOT
) -> dict[str, object]:
    before = current_state_checksum(database)
    individual = [
        process_order_batch(database, batch, dataset_root / batch.file_name)
        for batch in BATCHES[1:]
    ]
    after_individual = current_state_checksum(database)
    sequence = run_all(database, dataset_root)
    after_sequence = current_state_checksum(database)
    if len({before, after_individual, after_sequence}) != 1:
        raise RuntimeError("Analytical state changed during replay proof")
    return {
        "schema_version": 3,
        "individual_increment_replays": [
            {"batch": item["batch"], "status": item["status"]} for item in individual
        ],
        "full_sequence_replay": [
            {"batch": item["batch"], "status": item["status"]} for item in sequence
        ],
        "before_sha256": before,
        "after_individual_sha256": after_individual,
        "after_full_sequence_sha256": after_sequence,
        "analytical_state_unchanged": True,
    }


def build_and_write(
    database: Path, evidence_dir: Path, dataset_root: Path = DEFAULT_DATASET_ROOT
) -> str:
    run_all(database, dataset_root)
    proof = rerun_proof(database, dataset_root)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        return write_phase3_evidence(connection, evidence_dir, proof)
    finally:
        connection.close()


def acceptance(canonical_evidence_dir: Path | None = None) -> str:
    with tempfile.TemporaryDirectory(prefix="lion-phase3-acceptance-") as directory:
        root = Path(directory)
        evidence_dirs = []
        bundles = []
        for run in ("run1", "run2"):
            database = root / f"{run}.duckdb"
            evidence = root / f"{run}-evidence"
            bundles.append(build_and_write(database, evidence))
            evidence_dirs.append(evidence)
        if bundles[0] != bundles[1]:
            raise RuntimeError("Clean-run canonical evidence bundle checksums differ")
        names = (*EVIDENCE_FILES, "evidence_manifest.json")
        for name in names:
            if (evidence_dirs[0] / name).read_bytes() != (evidence_dirs[1] / name).read_bytes():
                raise RuntimeError(f"Clean-run evidence differs: {name}")
            if canonical_evidence_dir and (canonical_evidence_dir / name).is_file():
                committed = (canonical_evidence_dir / name).read_bytes()
                generated = (evidence_dirs[0] / name).read_bytes()
                if committed != generated:
                    raise RuntimeError(f"Committed canonical evidence differs: {name}")
        return bundles[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 3 incremental ETL")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--output-db", type=Path, required=True)
    build.add_argument("--evidence-dir", type=Path, required=True)
    replay = subparsers.add_parser("rerun-proof")
    replay.add_argument("--output-db", type=Path, required=True)
    replay.add_argument("--evidence-dir", type=Path, required=True)
    check = subparsers.add_parser("acceptance")
    check.add_argument("--canonical-evidence-dir", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        checksum = build_and_write(args.output_db, args.evidence_dir)
    elif args.command == "rerun-proof":
        proof = rerun_proof(args.output_db)
        connection = duckdb.connect(str(args.output_db), read_only=True)
        try:
            checksum = write_phase3_evidence(connection, args.evidence_dir, proof)
        finally:
            connection.close()
    else:
        checksum = acceptance(args.canonical_evidence_dir)
    print(f"canonical_evidence_sha256={checksum}")
    print(f"phase3_{args.command}=passed")


if __name__ == "__main__":
    main()
