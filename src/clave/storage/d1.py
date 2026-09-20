"""Cloudflare D1 REST client for experiment and dataset metadata tracking.

Executes queries against Cloudflare D1's serverless SQLite HTTP API,
governed by AC-DATA-04, AC-DATA-05, AC-DATA-06, and AC-DATA-07.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from clave.errors import ClaveError
from clave.storage.config import D1Config


class D1Error(ClaveError):
    """An operation against Cloudflare D1 SQL database failed."""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS datasets (
    digest TEXT PRIMARY KEY,
    seed INTEGER,
    config_digest TEXT,
    example_count INTEGER,
    train_examples INTEGER,
    validation_examples INTEGER,
    test_examples INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS training_runs (
    run_id TEXT PRIMARY KEY,
    candidate TEXT,
    dataset_digest TEXT,
    config_digest TEXT,
    epochs INTEGER,
    final_loss REAL,
    machine TEXT,
    checkpoint_r2_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS benchmarks (
    benchmark_id TEXT PRIMARY KEY,
    world_digest TEXT,
    configuration_name TEXT,
    overall_accuracy REAL,
    misroute_rate REAL,
    decision_latency_p99_seconds REAL,
    passed INTEGER,
    pack_r2_key TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class D1Client:
    """Client for Cloudflare D1 serverless SQLite via Cloudflare v4 REST API."""

    def __init__(self, config: D1Config) -> None:
        self.config = config
        self.endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{config.account_id}/"
            f"d1/database/{config.database_id}/query"
        )

    def execute(
        self, sql: str, params: list[Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a single SQL statement against D1.

        Args:
            sql: SQL statement to execute.
            params: Optional positional parameters.

        Returns:
            The list of result rows as dictionaries.

        Raises:
            D1Error: If execution fails or HTTP returns non-200.
        """
        payload = json.dumps({"sql": sql, "params": params or []}).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {self.config.api_token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="replace")
            raise D1Error(f"D1 HTTP {err.code}: {err.reason} - {err_body}") from err
        except urllib.error.URLError as err:
            raise D1Error(f"connection error contacting D1: {err.reason}") from err

        if not data.get("success"):
            errors = data.get("errors", [])
            raise D1Error(f"D1 query error: {errors}")

        result_blocks = data.get("result", [])
        if not result_blocks:
            return []
        first = result_blocks[0]
        if not first.get("success", False):
            raise D1Error(f"D1 statement error: {first.get('error', 'unknown error')}")
        rows: list[dict[str, Any]] = first.get("results", [])
        return rows

    def init_schema(self) -> None:
        """Create tables for datasets, training_runs, and benchmarks if missing."""
        statements = [
            """
            CREATE TABLE IF NOT EXISTS datasets (
                digest TEXT PRIMARY KEY,
                seed INTEGER,
                config_digest TEXT,
                example_count INTEGER,
                train_examples INTEGER,
                validation_examples INTEGER,
                test_examples INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS training_runs (
                run_id TEXT PRIMARY KEY,
                candidate TEXT,
                dataset_digest TEXT,
                config_digest TEXT,
                epochs INTEGER,
                final_loss REAL,
                machine TEXT,
                checkpoint_r2_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS benchmarks (
                benchmark_id TEXT PRIMARY KEY,
                world_digest TEXT,
                configuration_name TEXT,
                overall_accuracy REAL,
                misroute_rate REAL,
                decision_latency_p99_seconds REAL,
                passed INTEGER,
                pack_r2_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """,
        ]
        for stmt in statements:
            self.execute(stmt.strip())

    def record_dataset(
        self,
        digest: str,
        seed: int,
        config_digest: str,
        example_count: int,
        train_examples: int,
        validation_examples: int,
        test_examples: int,
    ) -> None:
        """Record dataset metadata in D1 (AC-DATA-04)."""
        sql = """
        INSERT INTO datasets (
            digest, seed, config_digest, example_count,
            train_examples, validation_examples, test_examples
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(digest) DO UPDATE SET
            seed=excluded.seed,
            config_digest=excluded.config_digest,
            example_count=excluded.example_count,
            train_examples=excluded.train_examples,
            validation_examples=excluded.validation_examples,
            test_examples=excluded.test_examples
        """
        self.execute(
            sql,
            [
                digest,
                seed,
                config_digest,
                example_count,
                train_examples,
                validation_examples,
                test_examples,
            ],
        )

    def record_training_run(
        self,
        run_id: str,
        candidate: str,
        dataset_digest: str,
        config_digest: str,
        epochs: int,
        final_loss: float,
        machine: str,
        checkpoint_r2_key: str,
    ) -> None:
        """Record candidate training run convergence in D1 (AC-DATA-05)."""
        sql = """
        INSERT INTO training_runs (
            run_id, candidate, dataset_digest, config_digest,
            epochs, final_loss, machine, checkpoint_r2_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            candidate=excluded.candidate,
            dataset_digest=excluded.dataset_digest,
            config_digest=excluded.config_digest,
            epochs=excluded.epochs,
            final_loss=excluded.final_loss,
            machine=excluded.machine,
            checkpoint_r2_key=excluded.checkpoint_r2_key
        """
        self.execute(
            sql,
            [
                run_id,
                candidate,
                dataset_digest,
                config_digest,
                epochs,
                final_loss,
                machine,
                checkpoint_r2_key,
            ],
        )

    def record_benchmark(
        self,
        benchmark_id: str,
        world_digest: str,
        configuration_name: str,
        overall_accuracy: float,
        misroute_rate: float,
        decision_latency_p99_seconds: float,
        passed: bool,
        pack_r2_key: str,
    ) -> None:
        """Record validation benchmark results in D1 (AC-DATA-06)."""
        sql = """
        INSERT INTO benchmarks (
            benchmark_id, world_digest, configuration_name,
            overall_accuracy, misroute_rate, decision_latency_p99_seconds,
            passed, pack_r2_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(benchmark_id) DO UPDATE SET
            world_digest=excluded.world_digest,
            configuration_name=excluded.configuration_name,
            overall_accuracy=excluded.overall_accuracy,
            misroute_rate=excluded.misroute_rate,
            decision_latency_p99_seconds=excluded.decision_latency_p99_seconds,
            passed=excluded.passed,
            pack_r2_key=excluded.pack_r2_key
        """
        self.execute(
            sql,
            [
                benchmark_id,
                world_digest,
                configuration_name,
                overall_accuracy,
                misroute_rate,
                decision_latency_p99_seconds,
                1 if passed else 0,
                pack_r2_key,
            ],
        )

    def list_training_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        """List historical training runs (AC-DATA-07)."""
        sql = """
        SELECT run_id, candidate, dataset_digest, config_digest,
               epochs, final_loss, machine, checkpoint_r2_key, created_at
        FROM training_runs
        ORDER BY created_at DESC
        LIMIT ?
        """
        return self.execute(sql, [limit])

    def list_benchmarks(self, limit: int = 20) -> list[dict[str, Any]]:
        """List historical validation benchmarks (AC-DATA-07)."""
        sql = """
        SELECT benchmark_id, world_digest, configuration_name,
               overall_accuracy, misroute_rate, decision_latency_p99_seconds,
               passed, pack_r2_key, created_at
        FROM benchmarks
        ORDER BY created_at DESC
        LIMIT ?
        """
        return self.execute(sql, [limit])

    def list_datasets(self, limit: int = 20) -> list[dict[str, Any]]:
        """List registered datasets."""
        sql = """
        SELECT digest, seed, config_digest, example_count,
               train_examples, validation_examples, test_examples, created_at
        FROM datasets
        ORDER BY created_at DESC
        LIMIT ?
        """
        return self.execute(sql, [limit])
