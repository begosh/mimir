"""Bounded public search probes; no model calls or configuration changes."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import time
from urllib.parse import quote, urlparse

from research_scout import configured_ca_bundle

PROBE_QUERY = "Neapolitan pizza recipe"
SEARCH_URLS = {
    "duckduckgo": "https://html.duckduckgo.com/html/?q=",
    "bing": "https://www.bing.com/search?q=",
    "google": "https://www.google.com/search?q=",
}


def classify_response(provider, status, body, *, server="", error=None):
    """HTTP success alone is not usable search evidence. Never return raw HTML."""
    result = {"http_status": status or None, "reachable": bool(status),
              "usable": False, "result_count": 0}
    if error:
        return dict(result, outcome=error)
    if status != 200:
        outcome = "proxy_block" if status in (403, 451) and "zscaler" in (server + body).lower() else "http_error"
        return dict(result, outcome=outcome)
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(body, "html.parser")
    selector = {"duckduckgo": ".result__title .result__a",
                "bing": "li.b_algo h2 a", "google": "a:has(h3)"}[provider]
    locators = set()
    for anchor in soup.select(selector):
        href = anchor.get("href", "")
        parsed = urlparse(href)
        # DDG redirect and Google /url results still carry a source locator.
        if (parsed.scheme in ("http", "https") and parsed.netloc) or href.startswith(("/url?", "//duckduckgo.com/l/?")):
            locators.add(href)
    result.update(result_count=len(locators), usable=bool(locators))
    return dict(result, outcome="usable_results" if locators else "no_usable_results")


def _probe_curl(provider, executable):
    started = time.monotonic()
    report = {"provider": provider, "method": "curl"}
    if not executable:
        return dict(report, outcome="curl_unavailable", usable=False, reachable=False)
    with TemporaryDirectory(prefix="mimir-search-") as directory:
        body_path, headers_path = Path(directory) / "body.html", Path(directory) / "headers.txt"
        command = [executable, "-q", "--silent", "--show-error", "--location",
                   "--proto", "=https", "--proto-redir", "=https",
                   "--connect-timeout", "4", "--max-time", "8", "--max-filesize", "1048576",
                   "--output", str(body_path), "--dump-header", str(headers_path),
                   "--write-out", "%{http_code}"]
        bundle = configured_ca_bundle()
        if bundle:
            command += ["--cacert", bundle]
        command.append(SEARCH_URLS[provider] + quote(PROBE_QUERY))
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            status = int(completed.stdout[-3:]) if completed.stdout[-3:].isdigit() else 0
            error = {60: "certificate_error", 77: "certificate_error", 28: "timeout",
                     63: "response_too_large"}.get(completed.returncode)
            if completed.returncode and not error:
                error = "transport_error"
            body = body_path.read_bytes()[:1048576].decode("utf-8", errors="replace") if body_path.exists() else ""
            headers = headers_path.read_text(errors="replace") if headers_path.exists() else ""
            report.update(classify_response(provider, status, body, server=headers, error=error),
                          exit_code=completed.returncode)
        except subprocess.TimeoutExpired:
            report.update(outcome="timeout", usable=False, reachable=False)
        except OSError:
            report.update(outcome="transport_error", usable=False, reachable=False)
    return dict(report, duration_seconds=round(time.monotonic() - started, 3))


def _probe_scout():
    """Exercise the same HTTP client and TLS settings as the active scout."""
    import research_scout
    started = time.monotonic()
    report = {"provider": "duckduckgo", "method": "native_scout"}
    if not research_scout.HAS_CURL_CFFI:
        return dict(report, outcome="dependencies_missing", usable=False, reachable=False)
    try:
        response = research_scout.cffi_requests.get(
            SEARCH_URLS["duckduckgo"] + quote(PROBE_QUERY), impersonate="chrome120",
            timeout=8, verify=configured_ca_bundle() or True,
            headers={"Accept-Language": "en-US,en;q=0.9,sv;q=0.8"})
        report.update(classify_response("duckduckgo", response.status_code, response.text[:1048576],
                                        server=response.headers.get("server", "")))
    except Exception as exc:
        name = type(exc).__name__.lower()
        error = "certificate_error" if "certificate" in name else "timeout" if "timeout" in name else "transport_error"
        report.update(outcome=error, usable=False, reachable=False)
    return dict(report, duration_seconds=round(time.monotonic() - started, 3))


def collect_search_diagnostics():
    executable = shutil.which("curl.exe") or shutil.which("curl")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        native = pool.submit(_probe_scout)
        direct = [pool.submit(_probe_curl, provider, executable) for provider in SEARCH_URLS]
        probes = [native.result(), *(future.result() for future in direct)]
    native_usable = probes[0]["usable"]
    direct_usable = any(probe["usable"] for probe in probes[1:])
    recommendations = []
    if any(probe["outcome"] == "certificate_error" for probe in probes):
        recommendations.append("Check the configured enterprise CA bundle and the failing client's trust chain; keep TLS verification enabled.")
    if not native_usable:
        recommendations.append("The default scout returned no usable results. Consider Firecrawl MCP for search and selected page retrieval; test it on this machine before enabling it. https://docs.firecrawl.dev/mcp-server/keyless")
    if direct_usable and not native_usable:
        recommendations.append("An alternative curl probe returned results; the current scout is still unready and does not automatically change providers.")
    return {"checked": True, "query": PROBE_QUERY, "default_scout_usable": native_usable,
            "any_curl_search_usable": direct_usable, "probes": probes,
            "duration_seconds": round(time.monotonic() - started, 3),
            "recommendations": recommendations,
            "verification": "Public search probes only; no model calls, MCP setup, login or configuration changes. A probe does not establish source authority or future availability."}
