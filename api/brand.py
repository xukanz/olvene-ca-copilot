"""Brand knowledge loaded by key (no vector retrieval, 方案规划 §6)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import yaml

from .config import get_settings


@dataclass(frozen=True)
class Brand:
    brand_id: str
    guide_md: str
    rules: dict
    catalog: dict
    festivals: list[dict]
    version: str

    # ------------------------------------------------------------ catalog lookups
    @property
    def products(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.catalog.get("products", [])}

    @property
    def events(self) -> dict[str, dict]:
        return {e["id"]: e for e in self.catalog.get("events", [])}

    @property
    def boutiques(self) -> dict[str, dict]:
        return {b["id"]: b for b in self.catalog.get("boutiques", [])}

    def product_names(self) -> dict[str, list[str]]:
        """id -> names a message could use to refer to the product."""
        out: dict[str, list[str]] = {}
        for p in self.catalog.get("products", []):
            names = [p["name_cn"], p["name_en"]]
            out[p["id"]] = [n for n in names if n]
        return out

    def known_prices(self) -> set[int]:
        prices = set()
        for p in self.catalog.get("products", []):
            for k in ("price", "price_from"):
                if k in p:
                    prices.add(int(p[k]))
        return prices

    def festivals_near(self, today: str, before: int = 3, after: int = 21) -> list[dict]:
        d = date.fromisoformat(today)
        out = []
        for f in self.festivals:
            fd = f["date"] if isinstance(f["date"], date) else date.fromisoformat(str(f["date"]))
            if d - timedelta(days=before) <= fd <= d + timedelta(days=after):
                out.append({**f, "date": fd.isoformat(), "days_from_today": (fd - d).days})
        return out


@lru_cache(maxsize=8)
def load_brand(brand_id: str = "olvene", brand_dir: str | None = None) -> Brand:
    root = Path(brand_dir) if brand_dir else get_settings().brand_dir
    guide = (root / "brand_guide.md").read_text(encoding="utf-8")
    rules_raw = (root / "brand_rules.yaml").read_text(encoding="utf-8")
    catalog_raw = (root / "catalog.yaml").read_text(encoding="utf-8")
    fest_path = root / "festivals.yaml"
    festivals = yaml.safe_load(fest_path.read_text(encoding="utf-8")) if fest_path.exists() else []
    digest = hashlib.sha1((guide + rules_raw + catalog_raw).encode()).hexdigest()[:8]
    return Brand(
        brand_id=brand_id,
        guide_md=guide,
        rules=yaml.safe_load(rules_raw),
        catalog=yaml.safe_load(catalog_raw),
        festivals=festivals or [],
        version=f"{brand_id}@{digest}",
    )
