"""Immutable, task-scoped evidence snapshots and bounded literal queries."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import urllib.parse
import urllib.request


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class SourceStore:
    def __init__(self, records=()):
        self.records = {}
        for record in records:
            item = dict(record)
            if set(item) != {"id", "locator", "retrieved_at", "retrieval_type", "text", "sha256"}:
                raise ValueError("Invalid captured source fields")
            if not all(isinstance(v, str) for v in item.values()):
                raise ValueError("Captured source fields must be strings")
            if item["retrieval_type"] not in {"local_file", "web_page"}:
                raise ValueError("Unsupported capture retrieval type")
            if not item["id"] or item["id"] in self.records:
                raise ValueError("Source identifiers must be unique and nonempty")
            if hashlib.sha256(item["text"].encode()).hexdigest() != item["sha256"]:
                raise ValueError("Source content identity changed")
            self.records[item["id"]] = item

    @classmethod
    def capture(cls, manifest):
        """Capture explicit local files or HTTPS URLs on an explicit domain allowlist."""
        path = Path(manifest).resolve(strict=True)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if set(data) - {"sources", "allowed_domains"} or not isinstance(data.get("sources"), list):
            raise ValueError("Source manifest requires a sources list")
        records = []
        if not 1 <= len(data["sources"]) <= 64:
            raise ValueError("A source manifest requires 1-64 explicit records")
        for item in data["sources"]:
            if not isinstance(item, dict) or set(item) not in ({"id", "path"}, {"id", "url"}):
                raise ValueError("Each source requires id and either path or url")
            if "path" in item:
                target = (path.parent / item["path"]).resolve(strict=True)
                if target.stat().st_size > 20_000_000:
                    raise ValueError("Source exceeds 20 MB capture limit")
                text = target.read_text(encoding="utf-8-sig")
                locator, retrieval_type = str(target), "local_file"
            else:
                parsed = urllib.parse.urlsplit(item["url"])
                domains = data.get("allowed_domains", [])
                if not isinstance(domains, list) or any(not isinstance(d, str) for d in domains):
                    raise ValueError("HTTPS sources require an explicit domain list")
                if parsed.scheme != "https" or parsed.hostname not in domains or parsed.username or parsed.password or parsed.port not in (None, 443):
                    raise ValueError("Source URL is outside the explicit HTTPS domain allowlist")
                class NoRedirect(urllib.request.HTTPRedirectHandler):
                    def redirect_request(self, *args, **kwargs):
                        return None
                opener = urllib.request.build_opener(NoRedirect)
                with opener.open(urllib.request.Request(item["url"], headers={"User-Agent": "Mimir-source-capture/1"}), timeout=15) as response:
                    raw = response.read(20_000_001)
                    if len(raw) > 20_000_000:
                        raise ValueError("HTTPS source exceeds 20 MB capture limit")
                    text = raw.decode(response.headers.get_content_charset() or "utf-8")
                locator, retrieval_type = item["url"], "web_page"
            records.append({"id": item["id"], "locator": locator,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "retrieval_type": retrieval_type, "text": text,
                            "sha256": hashlib.sha256(text.encode()).hexdigest()})
        return cls(records)

    @property
    def digest(self):
        return identity(self.to_list())

    def to_list(self):
        return [dict(self.records[k]) for k in sorted(self.records)]

    def list_sources(self):
        return [{k: v for k, v in r.items() if k != "text"} | {"chars": len(r["text"])}
                for r in self.to_list()]

    def validate_citations(self, result):
        """Prove capture membership and excerpt identity, never claim entailment."""
        for cited in result.get("sources", []):
            matches = [r for r in self.records.values() if cited["locator"] == r["locator"]
                       or cited["locator"].startswith(r["locator"] + ":L")
                       or cited["locator"].startswith(r["locator"] + "#")]
            if not any(cited["retrieved_at"] == r["retrieved_at"]
                       and cited["retrieval_type"] == r["retrieval_type"]
                       and cited["support_excerpt"] and cited["support_excerpt"] in r["text"] for r in matches):
                raise ValueError("Source citation is not a matching captured excerpt and retrieval record")

    def read_span(self, source_id, start, end):
        source = self.records[source_id]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(source["text"]):
            raise ValueError("Invalid source span")
        if end - start > 16000:
            raise ValueError("Source span exceeds 16000 characters")
        return {"source_id": source_id, "start": start, "end": end,
                "text": source["text"][start:end], "locator": source["locator"],
                "retrieved_at": source["retrieved_at"], "sha256": source["sha256"]}

    def search_sources(self, query, limit=20):
        if not isinstance(query, str) or not 1 <= len(query) <= 200:
            raise ValueError("Literal search requires 1–200 characters")
        if type(limit) is not int or not 1 <= limit <= 40:
            raise ValueError("Search limit must be 1–40")
        hits = []
        for source in self.to_list():
            start = 0
            while len(hits) < limit:
                pos = source["text"].find(query, start)
                if pos < 0:
                    break
                hits.append(self.read_span(source["id"], max(0, pos - 200),
                                           min(len(source["text"]), pos + len(query) + 200)))
                start = pos + len(query)
            if len(hits) == limit:
                break
        return hits
