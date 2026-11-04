from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from ios_control_bridge import browser


class FakeResponse:
    def __init__(self, body, status=200, url="https://example.com/", content_type="text/html; charset=utf-8"):
        self.body = body
        self.status = status
        self.url = url
        self.headers = {"content-type": content_type}

    def read(self, size=-1):
        return self.body if size is None or size < 0 else self.body[:size]

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


SEARCH_HTML = b"""<html><body>
<a class="result__a" href="https://example.com/one">Example One</a>
<a class="result__snippet">First result</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Ftwo">Example Two</a>
<a class="result__snippet">Second result</a>
</body></html>"""


class BrowserBoundaryTests(unittest.TestCase):
    def test_search_parses_provider_results(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse(SEARCH_HTML)):
            output = browser.search({"query": "example", "limit": 5})
        self.assertEqual(output["status"], "verified")
        results = output["data"]["results"]
        self.assertEqual(results[0]["title"], "Example One")
        self.assertEqual(results[0]["url"], "https://example.com/one")
        self.assertEqual(results[1]["url"], "https://example.org/two")
        self.assertEqual(output["data"]["provider"], "DuckDuckGo HTML")

    def test_search_rejects_invalid_query_and_limit(self):
        self.assertEqual(browser.search({"query": ""})["reason"], "invalid_query")
        self.assertEqual(browser.search({"query": "x", "limit": 0})["reason"], "invalid_limit")

    def test_search_falls_back_to_bing(self):
        bing = b"""<html><body><li class="b_algo"><h2><a href="https://example.net/result">Bing result</a></h2>
        <p>Bing snippet</p></li></body></html>"""
        responses = [FakeResponse(b"<html><body>no results</body></html>"), FakeResponse(bing)]
        with patch("urllib.request.urlopen", side_effect=responses):
            output = browser.search({"query": "example"})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["provider"], "Bing HTML")
        self.assertEqual(output["data"]["results"][0]["title"], "Bing result")
        self.assertEqual(output["data"]["results"][0]["url"], "https://example.net/result")

    def test_search_without_results_is_partial(self):
        empty = b"<html><body>no results</body></html>"
        with patch("urllib.request.urlopen", side_effect=[FakeResponse(empty), FakeResponse(empty)]):
            output = browser.search({"query": "example"})
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["reason"], "no_search_results")

    def test_read_extracts_text_and_title(self):
        body = b"<html><head><title>Page title</title><script>bad()</script></head><body><p>Hello</p><p>World</p></body></html>"
        with patch("urllib.request.urlopen", return_value=FakeResponse(body, url="https://example.com/final")):
            output = browser.read({"url": "https://example.com"})
        self.assertEqual(output["status"], "verified")
        self.assertEqual(output["data"]["title"], "Page title")
        self.assertEqual(output["data"]["text"], "Hello\nWorld")
        self.assertEqual(output["data"]["final_url"], "https://example.com/final")
        self.assertNotIn("bad()", output["data"]["text"])

    def test_read_rejects_non_http_url(self):
        self.assertEqual(browser.read({"url": "file:///etc/passwd"})["reason"], "unsupported_url_scheme")

    def test_network_error_is_unavailable(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            output = browser.read({"url": "https://example.com"})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "network_error")

    def test_open_missing_helper_is_unavailable(self):
        with patch("ios_control_bridge.browser.open_helper_path", return_value=Path("/nonexistent")), \
             patch("subprocess.run", side_effect=AssertionError("unexpected helper")):
            output = browser.open_url({"url": "https://example.com"})
        self.assertEqual(output["status"], "unavailable")
        self.assertEqual(output["reason"], "native_helper_missing")

    def test_open_reports_launch_services_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "icb-open-url"
            helper.touch()
            payload = {"schema": browser.OPEN_URL_SCHEMA, "source": browser.OPEN_URL_SOURCE,
                       "status": "verified", "url": "https://example.com", "opened": True}
            process = subprocess.CompletedProcess([], 0, json.dumps(payload), "")
            with patch("ios_control_bridge.browser.open_helper_path", return_value=helper), \
                 patch("subprocess.run", return_value=process) as call:
                output = browser.open_url({"url": "https://example.com"})
            self.assertEqual(output["status"], "verified")
            self.assertTrue(output["data"]["opened"])
            self.assertEqual(call.call_args.args[0][1], "https://example.com")


if __name__ == "__main__":
    unittest.main()
