"""Search doctor distinguishes HTTP reachability from usable retrieval."""
import io
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import cli
import diagnostics
import search_diagnostics as search


def test_certificate_error_does_not_claim_reachability():
    report = search.classify_response("bing", 0, "", error="certificate_error")
    assert report["outcome"] == "certificate_error"
    assert not report["reachable"] and not report["usable"]


def test_zscaler_block_is_distinct_from_origin_refusal():
    assert search.classify_response("duckduckgo", 403, "", server="Zscaler/6.2")["outcome"] == "proxy_block"
    assert search.classify_response("duckduckgo", 403, "", server="nginx")["outcome"] == "http_error"


def test_http_200_redirect_page_is_not_usable_search():
    report = search.classify_response("google", 200, '<title>Google Search</title><p>Click here to redirect for pizza recipe</p>')
    assert report["reachable"]
    assert not report["usable"]
    assert report["outcome"] == "no_usable_results"


def test_provider_results_require_a_source_locator():
    cases = {
        "google": '<a href="https://example.org/recipe"><h3>Recipe</h3></a>',
        "bing": '<li class="b_algo"><h2><a href="https://example.org/recipe">Recipe</a></h2></li>',
        "duckduckgo": '<div class="result__title"><a class="result__a" href="https://example.org/recipe">Recipe</a></div>',
    }
    for provider, body in cases.items():
        report = search.classify_response(provider, 200, body)
        assert report["usable"] and report["result_count"] == 1
        assert not search.classify_response(provider, 200, body.replace("https://example.org/recipe", "javascript:void(0)"))["usable"]


def test_curl_uses_ca_and_bounded_verified_https_without_leaking_errors():
    def run(command, **kwargs):
        assert command[1] == "-q"
        assert command[command.index("--cacert") + 1] == "enterprise.pem"
        assert "--insecure" not in command and "-k" not in command
        assert command[command.index("--proto-redir") + 1] == "=https"
        assert kwargs["timeout"] == 10
        Path(command[command.index("--output") + 1]).write_text("PRIVATE-BLOCK-PAGE")
        return SimpleNamespace(returncode=60, stdout="000", stderr="PRIVATE-ERROR")
    with patch.object(search, "configured_ca_bundle", return_value="enterprise.pem"), \
         patch.object(search.subprocess, "run", side_effect=run):
        report = search._probe_curl("bing", "curl")
    assert report["outcome"] == "certificate_error"
    assert "PRIVATE" not in json.dumps(report)


def test_curl_timeout_and_missing_executable_are_reported():
    assert search._probe_curl("bing", None)["outcome"] == "curl_unavailable"
    with patch.object(search.subprocess, "run", side_effect=subprocess.TimeoutExpired("curl", 10)):
        assert search._probe_curl("bing", "curl")["outcome"] == "timeout"


def test_failed_search_suggests_mcp_without_changing_setup():
    native = {"usable": False, "outcome": "proxy_block"}
    direct = {"usable": False, "outcome": "no_usable_results"}
    with patch.object(search, "_probe_scout", return_value=native), \
         patch.object(search, "_probe_curl", return_value=direct):
        result = search.collect_search_diagnostics()
    assert not result["default_scout_usable"]
    assert not result["any_curl_search_usable"]
    assert any("Firecrawl MCP" in recommendation for recommendation in result["recommendations"])


def test_worker_diagnostics_remain_offline_unless_search_requested():
    with patch.object(search, "collect_search_diagnostics", return_value={"checked": True}) as probe:
        report = diagnostics.collect_diagnostics("codex")
        assert report["search"]["checked"] is False
        probe.assert_not_called()
        assert diagnostics.collect_diagnostics("codex", check_search=True)["search"]["checked"]
        probe.assert_called_once()


def test_doctor_cli_requests_search_without_worker_or_goal():
    with patch.object(sys, "argv", ["mimir", "--doctor"]), \
         patch.object(diagnostics, "collect_diagnostics", return_value={"search": {"checked": True}}) as collect, \
         patch.object(cli, "run_mimir") as worker, patch("sys.stdout", new_callable=io.StringIO):
        cli.main()
    assert collect.call_args.kwargs["check_search"] is True
    worker.assert_not_called()
