from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.db import connect


class TrustRegistry:
    def __init__(
        self,
        path: Path,
        signal_weights: dict[str, float] | None = None,
        demotion_threshold: float = 0.40,
        min_evidence: float = 3.0,
        decay_half_life_days: float = 30.0,
    ) -> None:
        self.path = path
        self.signal_weights = signal_weights or {
            "probe": 1.0,
            "call": 1.0,
            "schema": 0.5,
            "rating": 0.75,
            "contradiction": 2.0,
        }
        self.demotion_threshold = demotion_threshold
        self.min_evidence = min_evidence
        self.decay_half_life_days = decay_half_life_days
        self._lock = threading.RLock()
        self._connection = connect(path)
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS trust_state (
                provider_id TEXT PRIMARY KEY,
                successes REAL NOT NULL DEFAULT 0,
                failures REAL NOT NULL DEFAULT 0,
                probes INTEGER NOT NULL DEFAULT 0,
                calls INTEGER NOT NULL DEFAULT 0,
                schema_pass INTEGER NOT NULL DEFAULT 0,
                ratings_sum REAL NOT NULL DEFAULT 0,
                ratings_count INTEGER NOT NULL DEFAULT 0,
                contradictions INTEGER NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0.5,
                demoted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trust_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_id TEXT NOT NULL,
                signal TEXT NOT NULL,
                success INTEGER NOT NULL,
                weight REAL NOT NULL,
                successes REAL NOT NULL,
                failures REAL NOT NULL,
                score REAL NOT NULL,
                reason TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trust_history
                ON trust_history(provider_id, id);
            CREATE TABLE IF NOT EXISTS trust_capability (
                provider_id TEXT NOT NULL,
                capability TEXT NOT NULL,
                successes REAL NOT NULL DEFAULT 0,
                failures REAL NOT NULL DEFAULT 0,
                probes INTEGER NOT NULL DEFAULT 0,
                calls INTEGER NOT NULL DEFAULT 0,
                schema_pass INTEGER NOT NULL DEFAULT 0,
                ratings_sum REAL NOT NULL DEFAULT 0,
                ratings_count INTEGER NOT NULL DEFAULT 0,
                contradictions INTEGER NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0.5,
                demoted INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (provider_id, capability)
            );
            """
        )
        self._connection.commit()

    def _ensure(self, provider_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            INSERT INTO trust_state (provider_id, updated_at)
            VALUES (?, ?)
            ON CONFLICT(provider_id) DO NOTHING
            """,
            (provider_id, now),
        )

    def _row(self, provider_id: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM trust_state WHERE provider_id = ?", (provider_id,)
        ).fetchone()
        return dict(row) if row else None

    def _ensure_capability(self, provider_id: str, capability: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            INSERT INTO trust_capability (provider_id, capability, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(provider_id, capability) DO NOTHING
            """,
            (provider_id, capability, now),
        )

    def _row_capability(self, provider_id: str, capability: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT * FROM trust_capability WHERE provider_id = ? AND capability = ?",
            (provider_id, capability),
        ).fetchone()
        return dict(row) if row else None

    def _decay(self, row: dict[str, Any]) -> float:
        if self.decay_half_life_days <= 0 or not row.get("updated_at"):
            return 1.0
        try:
            updated = datetime.fromisoformat(str(row["updated_at"]))
            age_days = (datetime.now(UTC) - updated).total_seconds() / 86400.0
        except (TypeError, ValueError):
            return 1.0
        age_days = max(0.0, age_days)
        return 0.5 ** (age_days / self.decay_half_life_days)

    def _state(self, row: dict[str, Any]) -> dict[str, Any]:
        successes = float(row["successes"])
        failures = float(row["failures"])
        decay = self._decay(row)
        decayed_successes = successes * decay
        decayed_failures = failures * decay
        score = (decayed_successes + 1.0) / (decayed_successes + decayed_failures + 2.0)
        evidence = successes + failures
        demoted = bool(evidence >= self.min_evidence and score < self.demotion_threshold)
        return {
            "provider_id": row["provider_id"],
            "successes": round(successes, 3),
            "failures": round(failures, 3),
            "score": round(score, 4),
            "evidence": round(successes + failures, 3),
            "probes": int(row["probes"]),
            "calls": int(row["calls"]),
            "schema_pass": int(row["schema_pass"]),
            "ratings_sum": round(float(row["ratings_sum"]), 3),
            "ratings_count": int(row["ratings_count"]),
            "contradictions": int(row["contradictions"]),
            "demoted": demoted,
            "updated_at": row["updated_at"],
        }


    def _update_capability_row(
        self,
        provider_id: str,
        capability: str,
        signal: str,
        success: bool,
        applied_weight: float,
        reason: str,
        source: str,
        now: str,
    ) -> None:
        self._ensure_capability(provider_id, capability)
        row = self._row_capability(provider_id, capability)
        if row is None:
            raise RuntimeError(f"trust capability row missing for {provider_id}:{capability}")
        successes = float(row["successes"])
        failures = float(row["failures"])
        if success:
            successes += applied_weight
        else:
            failures += applied_weight
        probes = int(row["probes"]) + (1 if signal == "probe" else 0)
        calls = int(row["calls"]) + (1 if signal == "call" else 0)
        schema_pass = int(row["schema_pass"]) + (1 if signal == "schema" and success else 0)
        ratings_sum = float(row["ratings_sum"])
        ratings_count = int(row["ratings_count"])
        if signal == "rating":
            ratings_sum += applied_weight if success else 0.0
            ratings_count += 1
        contradictions = int(row["contradictions"]) + (1 if signal == "contradiction" else 0)
        score = (successes + 1.0) / (successes + failures + 2.0)
        evidence = successes + failures
        demoted = int(evidence >= self.min_evidence and score < self.demotion_threshold)
        self._connection.execute(
            """
            UPDATE trust_capability SET
                successes = ?, failures = ?, probes = ?, calls = ?,
                schema_pass = ?, ratings_sum = ?, ratings_count = ?,
                contradictions = ?, score = ?, demoted = ?, updated_at = ?
            WHERE provider_id = ? AND capability = ?
            """,
            (
                successes,
                failures,
                probes,
                calls,
                schema_pass,
                ratings_sum,
                ratings_count,
                contradictions,
                score,
                demoted,
                now,
                provider_id,
                capability,
            ),
        )

    def update(
        self,
        provider_id: str,
        signal: str,
        success: bool,
        weight: float | None = None,
        reason: str = "",
        source: str = "execution",
        capability: str | None = None,
    ) -> dict[str, Any]:
        applied_weight = float(
            self.signal_weights.get(signal, 1.0) if weight is None else weight
        )
        with self._lock:
            self._ensure(provider_id)
            row = self._row(provider_id)
            if row is None:
                raise RuntimeError(f"trust row missing for {provider_id}")
            successes = float(row["successes"])
            failures = float(row["failures"])
            if success:
                successes += applied_weight
            else:
                failures += applied_weight
            probes = int(row["probes"]) + (1 if signal == "probe" else 0)
            calls = int(row["calls"]) + (1 if signal == "call" else 0)
            schema_pass = int(row["schema_pass"]) + (
                1 if signal == "schema" and success else 0
            )
            ratings_sum = float(row["ratings_sum"])
            ratings_count = int(row["ratings_count"])
            if signal == "rating":
                ratings_sum += applied_weight if success else 0.0
                ratings_count += 1
            contradictions = int(row["contradictions"]) + (
                1 if signal == "contradiction" else 0
            )
            score = (successes + 1.0) / (successes + failures + 2.0)
            evidence = successes + failures
            demoted = int(
                evidence >= self.min_evidence and score < self.demotion_threshold
            )
            now = datetime.now(UTC).isoformat()
            self._connection.execute(
                """
                UPDATE trust_state SET
                    successes = ?, failures = ?, probes = ?, calls = ?,
                    schema_pass = ?, ratings_sum = ?, ratings_count = ?,
                    contradictions = ?, score = ?, demoted = ?, updated_at = ?
                WHERE provider_id = ?
                """,
                (
                    successes,
                    failures,
                    probes,
                    calls,
                    schema_pass,
                    ratings_sum,
                    ratings_count,
                    contradictions,
                    score,
                    demoted,
                    now,
                    provider_id,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO trust_history (
                    provider_id, signal, success, weight, successes, failures,
                    score, reason, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    provider_id,
                    signal,
                    int(success),
                    applied_weight,
                    successes,
                    failures,
                    score,
                    reason,
                    source,
                    now,
                ),
            )
            if capability is not None:
                self._update_capability_row(
                    provider_id, capability, signal, success, applied_weight, reason, source, now
                )
            self._connection.commit()
            updated = self._row(provider_id)
        if updated is None:
            raise RuntimeError(f"trust update failed for {provider_id}")
        return self._state(updated)

    def record_probe(
        self, provider_id: str, success: bool, reason: str = "", source: str = "auditor", capability: str | None = None
    ) -> dict[str, Any]:
        return self.update(provider_id, "probe", success, reason=reason, source=source, capability=capability)

    def record_call(
        self, provider_id: str, success: bool, reason: str = "", source: str = "client", capability: str | None = None
    ) -> dict[str, Any]:
        return self.update(provider_id, "call", success, reason=reason, source=source, capability=capability)

    def record_schema(
        self, provider_id: str, success: bool, reason: str = "", source: str = "client", capability: str | None = None
    ) -> dict[str, Any]:
        return self.update(provider_id, "schema", success, reason=reason, source=source, capability=capability)

    def record_rating(
        self,
        provider_id: str,
        rating: float,
        reason: str = "developer rating",
        source: str = "interface",
        capability: str | None = None,
    ) -> dict[str, Any]:
        return self.update(
            provider_id,
            "rating",
            success=rating >= 0.5,
            weight=rating,
            reason=reason,
            source=source,
            capability=capability,
        )

    def record_contradiction(
        self, provider_id: str, reason: str = "", source: str = "auditor", capability: str | None = None
    ) -> dict[str, Any]:
        return self.update(
            provider_id,
            "contradiction",
            success=False,
            reason=reason,
            source=source,
            capability=capability,
        )

    def get(self, provider_id: str, capability: str | None = None) -> dict[str, Any]:
        with self._lock:
            if capability is not None:
                row = self._row_capability(provider_id, capability)
                if row is None:
                    row = self._row(provider_id)
            else:
                row = self._row(provider_id)
        if row is None:
            return {
                "provider_id": provider_id,
                "successes": 0.0,
                "failures": 0.0,
                "score": 0.5,
                "evidence": 0.0,
                "probes": 0,
                "calls": 0,
                "schema_pass": 0,
                "ratings_sum": 0.0,
                "ratings_count": 0,
                "contradictions": 0,
                "demoted": False,
                "updated_at": None,
            }
        return self._state(row)

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM trust_state ORDER BY provider_id"
            ).fetchall()
        return [self._state(dict(row)) for row in rows]

    def history(self, provider_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM trust_history
                WHERE provider_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (provider_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def is_demoted(self, provider_id: str) -> bool:
        return bool(self.get(provider_id)["demoted"])

    def replay(self, provider_id: str) -> dict[str, Any]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM trust_history WHERE provider_id = ? ORDER BY id",
                (provider_id,),
            ).fetchall()
        successes = 0.0
        failures = 0.0
        for row in rows:
            if row["success"]:
                successes += float(row["weight"])
            else:
                failures += float(row["weight"])
        score = (successes + 1.0) / (successes + failures + 2.0)
        current = self.get(provider_id)
        return {
            "provider_id": provider_id,
            "replayed_successes": round(successes, 3),
            "replayed_failures": round(failures, 3),
            "replayed_score": round(score, 4),
            "current_score": current["score"],
            "matches": abs(round(score, 4) - float(current["score"])) < 1e-9,
            "updates": len(rows),
        }

    def reset(self) -> None:
        with self._lock:
            self._connection.execute("DELETE FROM trust_state")
            self._connection.execute("DELETE FROM trust_history")
            self._connection.commit()
