from __future__ import annotations

import json
from pathlib import Path
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pandas as pd


ADDRESS_SORT_FIELDS = {
    "seen_count",
    "last_seen_at",
    "last_block_height",
    "account_value",
    "effective_position_value",
    "abs_effective_position_value",
    "hyperdash_account_value",
    "ethAddress",
}


def safe_address(address: str) -> str:
    return address.lower().strip()


def _nested_number(record: dict[str, Any], *path: str) -> float:
    current: Any = record
    for key in path:
        if not isinstance(current, dict):
            return 0.0
        current = current.get(key)
    try:
        return float(current or 0)
    except (TypeError, ValueError):
        return 0.0


def _address_sort_value(record: dict[str, Any], sort_by: str) -> Any:
    if sort_by == "account_value":
        # 兼容旧 Mongo 字段、早期冗余字段和 Hyperdash 导入字段。
        return (
            _nested_number(record, "marginSummary", "accountValue")
            or _nested_number(record, "accountValue")
            or _nested_number(record, "hyperdash_account_value")
        )
    if sort_by == "hyperdash_account_value":
        return _nested_number(record, "hyperdash_account_value")
    if sort_by == "effective_position_value":
        return _nested_number(record, "effective_position_value")
    if sort_by == "abs_effective_position_value":
        return abs(_nested_number(record, "effective_position_value"))
    if sort_by in {"seen_count", "last_block_height"}:
        return _nested_number(record, sort_by)
    if sort_by == "last_seen_at":
        return str(record.get("last_seen_at") or record.get("updated_at") or "")
    if sort_by == "ethAddress":
        return str(record.get("ethAddress") or "")
    return 0


def sort_address_records(
    records: list[dict[str, Any]],
    *,
    sort_by: str = "seen_count",
    descending: bool = True,
) -> list[dict[str, Any]]:
    if sort_by not in ADDRESS_SORT_FIELDS:
        raise ValueError(f"不支持的地址排序字段：{sort_by}")

    def key(record: dict[str, Any]) -> tuple[Any, float, str, str]:
        return (
            _address_sort_value(record, sort_by),
            _nested_number(record, "seen_count"),
            str(record.get("last_seen_at") or record.get("updated_at") or ""),
            str(record.get("ethAddress") or ""),
        )

    return sorted(records, key=key, reverse=descending)


class FileStore:
    def __init__(self, root: str | Path = "data") -> None:
        self.root = Path(root)
        self.address_book_path = self.root / "addresses.json"
        self.address_book_csv_path = self.root / "addresses.csv"
        self.address_book_txt_path = self.root / "addresses.txt"
        self.fills_dir = self.root / "fills"
        self.states_dir = self.root / "states"
        self.results_dir = self.root / "results"
        self.reports_dir = self.root / "reports"
        for directory in [self.fills_dir, self.states_dir, self.results_dir, self.reports_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def fills_path(self, address: str) -> Path:
        return self.fills_dir / f"{safe_address(address)}.json"

    def state_path(self, address: str) -> Path:
        return self.states_dir / f"{safe_address(address)}.json"

    def result_path(self, address: str) -> Path:
        return self.results_dir / f"{safe_address(address)}.json"

    def load_address_records(self) -> list[dict[str, Any]]:
        if not self.address_book_path.exists():
            return []
        data = json.loads(self.address_book_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError(f"{self.address_book_path} 必须是 JSON list")
        return data

    def save_address_records(self, records: list[dict[str, Any]]) -> None:
        records = sorted(records, key=lambda item: item.get("ethAddress", ""))
        self.address_book_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        pd.DataFrame(records).to_csv(self.address_book_csv_path, index=False)
        self.address_book_txt_path.write_text(
            "\n".join(record["ethAddress"] for record in records if record.get("ethAddress")) + "\n",
            encoding="utf-8",
        )

    def upsert_addresses(
        self,
        addresses: list[str] | set[str],
        *,
        source: str,
        metadata_by_address: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        metadata_by_address = metadata_by_address or {}
        now = datetime.now(timezone.utc).isoformat()
        counts = Counter(safe_address(address) for address in addresses if address)
        counts.pop("", None)
        records_by_address = {
            safe_address(record["ethAddress"]): record
            for record in self.load_address_records()
            if record.get("ethAddress")
        }

        new_count = 0
        updated_count = 0
        for address, seen_count in counts.items():
            metadata = metadata_by_address.get(address, {})
            record = records_by_address.get(address)
            if record is None:
                record = {
                    "ethAddress": address,
                    "sources": [],
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "seen_count": 0,
                }
                records_by_address[address] = record
                new_count += 1
            else:
                updated_count += 1
                record["last_seen_at"] = now

            sources = set(record.get("sources", []))
            sources.add(source)
            record["sources"] = sorted(sources)
            record["last_source"] = source
            record["seen_count"] = int(record.get("seen_count", 0)) + seen_count
            for key, value in metadata.items():
                if key == "last_block_height" and record.get(key) is not None:
                    record[key] = max(int(record[key]), int(value))
                else:
                    record[key] = value

        self.save_address_records(list(records_by_address.values()))
        return {"new": new_count, "updated": updated_count, "total": len(records_by_address)}

    def load_address_book_addresses(
        self,
        *,
        limit: int | None = None,
        sort_by: str = "seen_count",
        descending: bool = True,
    ) -> list[str]:
        records = self.load_address_records()
        records = sort_address_records(records, sort_by=sort_by, descending=descending)
        addresses = [record["ethAddress"] for record in records if record.get("ethAddress")]
        return addresses[:limit] if limit else addresses

    def load_fills(self, address: str) -> list[dict[str, Any]]:
        path = self.fills_path(address)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def save_fills(self, address: str, fills: list[dict[str, Any]]) -> None:
        path = self.fills_path(address)
        path.write_text(json.dumps(fills, ensure_ascii=False, indent=2), encoding="utf-8")

    def merge_save_fills(self, address: str, new_fills: list[dict[str, Any]]) -> list[dict[str, Any]]:
        existing = self.load_fills(address)
        # tid 是 Hyperliquid fills 的天然去重键；无 tid 的异常数据保留原样。
        by_tid = {item.get("tid"): item for item in existing if item.get("tid") is not None}
        no_tid = [item for item in existing if item.get("tid") is None]
        for fill in new_fills:
            tid = fill.get("tid")
            if tid is None:
                no_tid.append(fill)
            else:
                by_tid[tid] = fill
        merged = list(by_tid.values()) + no_tid
        merged.sort(key=lambda item: item.get("time", 0))
        self.save_fills(address, merged)
        return merged

    def last_fill_time(self, address: str) -> int:
        fills = self.load_fills(address)
        return max((int(fill.get("time", 0)) for fill in fills), default=0)

    def save_state(self, address: str, state: dict[str, Any]) -> None:
        self.state_path(address).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_result(self, address: str, result: dict[str, Any]) -> None:
        self.result_path(address).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_result(self, address: str) -> dict[str, Any] | None:
        path = self.result_path(address)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def load_all_results(self) -> list[dict[str, Any]]:
        results = []
        for path in sorted(self.results_dir.glob("*.json")):
            results.append(json.loads(path.read_text(encoding="utf-8")))
        return results

    def export_reports(self, results: list[dict[str, Any]], population: dict[str, Any]) -> dict[str, Path]:
        summary_rows = [result["summary"] for result in results]
        trade_rows = []
        asset_rows = []
        for result in results:
            address = result["summary"]["address"]
            for trade in result["trades"]:
                trade_rows.append({"address": address, **trade})
            for coin, stats in result["per_asset"].items():
                asset_rows.append({"address": address, "coin": coin, **stats})

        paths = {
            "summary_csv": self.reports_dir / "summary.csv",
            "trades_csv": self.reports_dir / "trades.csv",
            "per_asset_csv": self.reports_dir / "per_asset.csv",
            "population_json": self.reports_dir / "population.json",
        }
        pd.DataFrame(summary_rows).to_csv(paths["summary_csv"], index=False)
        pd.DataFrame(trade_rows).to_csv(paths["trades_csv"], index=False)
        pd.DataFrame(asset_rows).to_csv(paths["per_asset_csv"], index=False)
        paths["population_json"].write_text(json.dumps(population, ensure_ascii=False, indent=2), encoding="utf-8")
        return paths


def load_addresses(addresses: str | None = None, address_file: str | None = None) -> list[str]:
    loaded: list[str] = []
    if addresses:
        loaded.extend(part.strip() for part in addresses.split(",") if part.strip())
    if address_file:
        path = Path(address_file)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    loaded.append(item["ethAddress"] if isinstance(item, dict) and "ethAddress" in item else str(item))
            else:
                raise ValueError("JSON 地址文件必须是 list")
        else:
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                loaded.append(line.split(",")[0].strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for address in loaded:
        key = safe_address(address)
        if key not in seen:
            seen.add(key)
            deduped.append(address)
    return deduped
