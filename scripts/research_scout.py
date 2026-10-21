"""
scripts/research_scout.py
Omni-Channel Epistemic Research Scout for M Í M I R.
Dynamically determines the most authoritative sources for ANY question
(GitHub, Official Docs, RFCs, HackerNews, PubMed, Open Web, Specialist Forums, ArXiv)
with zero hardcoded lock-in.
"""

from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from mimir_config import is_english_text
from typing import Any, Dict, List, Optional

try:
    from bs4 import BeautifulSoup
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False


@dataclass
class SourceDirective:
    """A dynamically planned search directive for a specific knowledge venue."""
    channel_name: str  # e.g. 'Official Docs / Spec', 'Code Repos', 'Peer Review', 'Practitioner Debate'
    search_query: str
    target_site: Optional[str] = None  # e.g. 'github.com', 'news.ycombinator.com', None for open web
    engine: str = "web"  # 'web' | 'arxiv' | 'direct'


@dataclass
class ResearchItem:
    channel: str
    title: str
    url: str
    summary: str
    author_or_meta: str = ""
    relevance_score: float = 1.0

    @property
    def source_type(self) -> str:
        return self.channel


@dataclass
class IntelligenceBrief:
    topic: str
    items: List[ResearchItem] = field(default_factory=list)
    distilled_insights: List[str] = field(default_factory=list)

    @property
    def arxiv_papers(self) -> List[ResearchItem]:
        return [i for i in self.items if "arxiv" in i.channel.lower() or "arxiv.org" in i.url]

    @property
    def web_discussions(self) -> List[ResearchItem]:
        return [i for i in self.items if "arxiv" not in i.channel.lower() and "arxiv.org" not in i.url]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "items": [asdict(i) for i in self.items],
            "distilled_insights": self.distilled_insights,
        }

    def to_compact_markdown(self) -> str:
        is_en = is_english_text(self.topic)
        header = f"### Dynamic Intelligence Discovery: {self.topic}\n"
        lines = [header]
        if not self.items:
            lines.append("_No external data gathered._\n")
            return "\n".join(lines)

        by_channel: Dict[str, List[ResearchItem]] = {}
        for it in self.items:
            by_channel.setdefault(it.channel, []).append(it)

        for channel, items in by_channel.items():
            lines.append(f"**[{channel}]:**")
            for it in items[:3]:
                meta = f" ({it.author_or_meta})" if it.author_or_meta else ""
                url_part = f" [Länk]({it.url})" if it.url else ""
                lines.append(f"- **{it.title}**{meta}: {it.summary[:200]}...{url_part}")
            lines.append("")

        if self.distilled_insights:
            lines.append("**Extraherade Kärnprinciper:**")
            for ins in self.distilled_insights:
                lines.append(f"- {ins}")
            lines.append("")

        return "\n".join(lines)


class ResearchScout:
    """
    Source-Agnostic Omni-Channel Scout.
    Dynamically identifies where the ground truth resides for any domain
    and fetches evidence without vendor lock-in.
    """

    def __init__(self, timeout_sec: int = 12):
        self.timeout_sec = timeout_sec

    def plan_sources_heuristic(self, topic: str, custom_domains: Optional[List[str]] = None) -> List[SourceDirective]:
        """
        Dynamically derives targeted venues based on semantic domain analysis.
        """
        is_en = is_english_text(topic)
        directives: List[SourceDirective] = []
        t_lower = topic.lower()

        if custom_domains:
            for domain in custom_domains:
                directives.append(
                    SourceDirective(
                        channel_name=f"Custom ({domain})",
                        search_query=topic,
                        target_site=domain,
                        engine="web",
                    )
                )

        # 1. Code / Architecture / Technical
        if any(w in t_lower for w in ["kod", "code", "arkitektur", "api", "protokoll", "system", "caching", "databas", "microservice"]):
            directives.append(SourceDirective(
                channel_name="Source Code & Reference Architecture",
                search_query=f"{topic} architecture implementation",
                target_site="github.com",
                engine="web",
            ))
            directives.append(SourceDirective(
                channel_name="Engineering Debate & Post-Mortems",
                search_query=f"{topic} in production",
                target_site="news.ycombinator.com",
                engine="web",
            ))

        # 2. Science / Research / Mathematics
        if any(w in t_lower for w in ["forskning", "paper", "arxiv", "teori", "matematik", "algoritm", "modell", "ai", "llm", "rlm"]):
            directives.append(SourceDirective(
                channel_name="Academic Preprints (arXiv)",
                search_query=topic,
                engine="arxiv",
            ))

        # 3. Community / Real-world Field Experience
        if any(w in t_lower for w in ["erfarenhet", "problem", "bugg", "bästa sättet", "community", "hur gör man"]):
            directives.append(SourceDirective(
                channel_name="Community & Field Experience",
                search_query=f"{topic} discussions best practices",
                engine="web",
            ))

        # 4. Universal Open Web Deep Dive (always included for breadth)
        directives.append(SourceDirective(
            channel_name="Primary Specs & Documentation",
            search_query=f"{topic} documentation specification overview",
            engine="web",
        ))

        seen = set()
        unique_directives = []
        for d in directives:
            key = (d.channel_name, d.target_site, d.search_query[:30])
            if key not in seen:
                seen.add(key)
                unique_directives.append(d)

        return unique_directives[:4]

    async def plan_sources_with_agent(self, topic: str, swarm: Any) -> List[SourceDirective]:
        """
        Uses a micro-agent to formulate optimal source venues for any arbitrary domain.
        """
        prompt = f"""
        You are Mímir Epistemic Intelligence Planner.
        OBJECTIVE: "{topic}"

        Where does the foremost authoritative expertise, empirical truth, and definitive primary documentation
        exist for this exact domain? (e.g. GitHub for software, PubMed/bioRxiv for biomedicine, SEC/central banks for finance,
        formal RFCs/specs for protocols, or specialized engineering post-mortems).

        Generate 3 distinct search directives strictly in valid JSON:
        {{
            "directives": [
                {{
                    "channel_name": "e.g. Source Code & Repos / Biomedical Studies / Official Specs / Engineering Debates",
                    "search_query": "Optimized, keyword-dense search query in English",
                    "target_site": "optional specific authoritative domain like github.com, news.ycombinator.com, or null",
                    "engine": "web or arxiv"
                }}
            ]
        }}
        """
        try:
            res = await swarm.spawn(prompt=prompt, role="Source-Planner", effort="low")
            if isinstance(res.data, dict) and "directives" in res.data:
                parsed = []
                for d in res.data["directives"]:
                    parsed.append(SourceDirective(
                        channel_name=d.get("channel_name", "Webbkälla"),
                        search_query=d.get("search_query", topic),
                        target_site=d.get("target_site"),
                        engine=d.get("engine", "web"),
                    ))
                if parsed:
                    return parsed
        except Exception:
            pass

        return self.plan_sources_heuristic(topic)

    def search_arxiv(self, query: str, max_results: int = 3) -> List[ResearchItem]:
        """Queries arXiv's open API."""
        clean_query = re.sub(r"[^\w\s]", " ", query).strip()
        encoded = urllib.parse.quote(clean_query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"

        items = []
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MimirOmniScout/2.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            atom_ns = "{http://www.w3.org/2005/Atom}"

            for entry in root.findall(f"{atom_ns}entry"):
                title_elem = entry.find(f"{atom_ns}title")
                summary_elem = entry.find(f"{atom_ns}summary")
                id_elem = entry.find(f"{atom_ns}id")
                published_elem = entry.find(f"{atom_ns}published")

                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else "Untitled"
                summary = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None and summary_elem.text else ""
                paper_url = id_elem.text.strip() if id_elem is not None and id_elem.text else ""
                published = published_elem.text[:10] if published_elem is not None and published_elem.text else ""

                items.append(
                    ResearchItem(
                        channel="Akademisk Forskning (arXiv)",
                        title=title,
                        url=paper_url,
                        summary=summary,
                        author_or_meta=f"Preprint ({published})",
                    )
                )
        except Exception:
            pass

        return items

    def search_web_directive(self, directive: SourceDirective, max_results: int = 3) -> List[ResearchItem]:
        """
        Executes a targeted search using DuckDuckGo via curl_cffi with browser TLS impersonation.
        Supports targeting ANY website or open web.
        """
        if not HAS_CURL_CFFI:
            return []

        search_term = directive.search_query
        if directive.target_site:
            search_term = f"site:{directive.target_site} {directive.search_query}"

        encoded = urllib.parse.quote(search_term)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"

        items = []
        try:
            res = cffi_requests.get(
                url,
                impersonate="chrome120",
                timeout=self.timeout_sec,
                headers={"Accept-Language": "en-US,en;q=0.9,sv;q=0.8"},
            )
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                results = soup.select(".result")

                for r in results[:max_results]:
                    title_a = r.select_one(".result__title .result__a")
                    snippet_div = r.select_one(".result__snippet")

                    if title_a and snippet_div:
                        title = title_a.get_text(strip=True)
                        raw_url = title_a.get("href", "")
                        match = re.search(r"uddg=([^&]+)", raw_url)
                        actual_url = urllib.parse.unquote(match.group(1)) if match else raw_url
                        snippet = snippet_div.get_text(strip=True)

                        site_label = directive.target_site or urllib.parse.urlparse(actual_url).netloc
                        items.append(
                            ResearchItem(
                                channel=directive.channel_name,
                                title=title,
                                url=actual_url,
                                summary=snippet,
                                author_or_meta=site_label,
                            )
                        )
        except Exception:
            pass

        return items

    def conduct_deep_scout(
        self,
        topic: str,
        custom_domains: Optional[List[str]] = None,
        swarm: Optional[Any] = None,
    ) -> IntelligenceBrief:
        brief = IntelligenceBrief(topic=topic)
        directives = self.plan_sources_heuristic(topic, custom_domains=custom_domains)

        for d in directives:
            if d.engine == "arxiv":
                papers = self.search_arxiv(d.search_query, max_results=2)
                brief.items.extend(papers)
            else:
                web_items = self.search_web_directive(d, max_results=2)
                brief.items.extend(web_items)

        return brief
