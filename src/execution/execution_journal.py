"""Phase 9 durable execution journal.

Atomic JSON append-only journal persisted in a Git-ignored runtime directory.
Every attempted, approved, rejected and completed execution is recorded.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.execution.models import ExecutionRecord, ExecutionState


@dataclass
class JournalEntry:
    execution_id: str
    record: ExecutionRecord
    written_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self.record)
        # Convert datetimes/Decimals to strings for JSON.
        for k, v in list(d.items()):
            if isinstance(v, datetime):
                d[k] = v.isoformat() if v else None
            elif isinstance(v, Decimal):
                d[k] = str(v)
            elif isinstance(v, bytes):
                d[k] = v.decode("utf-8", errors="replace")
        d["written_at"] = self.written_at.isoformat()
        return d


class ExecutionJournal:
    """Append-only durable execution journal."""

    def __init__(self, directory: str = ".execution_journal") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._path = self.directory / "journal.jsonl"

    def append(self, record: ExecutionRecord) -> None:
        entry = JournalEntry(
            execution_id=record.execution_id,
            record=record,
            written_at=datetime.now(timezone.utc),
        )
        line = json.dumps(entry.to_dict(), sort_keys=True)
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def load_all(self) -> List[ExecutionRecord]:
        records: List[ExecutionRecord] = []
        if not self._path.exists():
            return records
        with open(self._path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    records.append(self._dict_to_record(data))
                except json.JSONDecodeError:
                    # Corrupt line: skip but keep journal intact.
                    continue
        return records

    def get(self, execution_id: str) -> Optional[ExecutionRecord]:
        for record in self.load_all():
            if record.execution_id == execution_id:
                return record
        return None

    def _dict_to_record(self, data: Dict[str, Any]) -> ExecutionRecord:
        return ExecutionRecord(
            execution_id=data["execution_id"],
            signal_id=data["signal_id"],
            strategy_name=data["strategy_name"],
            strategy_version=data["strategy_version"],
            symbol=data["symbol"],
            side=data["side"],
            volume=Decimal(data["volume"]),
            entry_price=Decimal(data["entry_price"])
            if data.get("entry_price") is not None
            else None,
            stop_loss_price=Decimal(data["stop_loss_price"])
            if data.get("stop_loss_price") is not None
            else None,
            take_profit_price=Decimal(data["take_profit_price"])
            if data.get("take_profit_price") is not None
            else None,
            state=ExecutionState(data["state"]),
            mode=data["mode"],
            magic_number=int(data["magic_number"]),
            comment=data.get("comment", ""),
            created_at=self._parse_dt(data.get("created_at")),
            submitted_at=self._parse_dt(data.get("submitted_at")),
            filled_at=self._parse_dt(data.get("filled_at")),
            broker_order_ticket=data.get("broker_order_ticket"),
            broker_deal_ticket=data.get("broker_deal_ticket"),
            broker_request_id=data.get("broker_request_id"),
            filled_volume=Decimal(data["filled_volume"])
            if data.get("filled_volume") is not None
            else None,
            filled_price=Decimal(data["filled_price"])
            if data.get("filled_price") is not None
            else None,
            remaining_volume=Decimal(data["remaining_volume"])
            if data.get("remaining_volume") is not None
            else None,
            broker_retcode=data.get("broker_retcode"),
            broker_external_code=data.get("broker_external_code"),
            broker_comment=data.get("broker_comment"),
            execution_timestamp=self._parse_dt(data.get("execution_timestamp")),
            request_fingerprint=data.get("request_fingerprint", ""),
            authorization_token=data.get("authorization_token"),
            reconciliation_status=data.get("reconciliation_status", "unreconciled"),
            reason=data.get("reason"),
            metadata=data.get("metadata", {}),
        )

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    def count_by_state(self, state: ExecutionState) -> int:
        return sum(1 for r in self.load_all() if r.state == state)

    def count_today(self) -> int:
        today = datetime.now(timezone.utc).date()
        count = 0
        for r in self.load_all():
            try:
                if r.created_at.date() == today:
                    count += 1
            except AttributeError:
                continue
        return count
