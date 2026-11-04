"""Bounded network browser operations with an explicit provider and URL."""
from html.parser import HTMLParser
import html
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .result import EXIT_CODES, result

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OPEN_URL_SCHEMA = "ios-control-bridge.browser.v1"
OPEN_URL_SOURCE = "LSApplicationWorkspace"

SEARCH_PROVIDER = "DuckDuckGo HTML"
SEARCH_ENDPOINT = "https://html.duckduckgo.com/html/"
BING_PROVIDER = "Bing HTML"
BING_ENDPOINT = "https://www.bing.com/search"
USER_AGENT = "ios-control-bridge/0.5 (+local CLI)"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_SEARCH_LIMIT = 5
DEFAULT_READ_CHARS = 20000


class SearchParser(HTMLParser):
    def __init__(self, limit):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results = []
        self._current = None
        self._mode = None

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if "result__a" in classes and len(self.results) < self.limit:
            self._current = {"title": "", "url": _clean_url(attributes.get("href") or ""), "snippet": ""}
            self._mode = "title"
        elif "result__snippet" in classes and self._current is not None:
            self._mode = "snippet"

    def handle_data(self, data):
        if self._current is None or self._mode is None:
            return
        if self._mode == "title":
            self._current["title"] += data
        elif self._mode == "snippet":
            self._current["snippet"] += data

    def handle_endtag(self, tag):
        if tag != "a":
            return
        if self._mode == "title" and self._current is not None:
            self._current["title"] = " ".join(self._current["title"].split())
            self._mode = None
        elif self._mode == "snippet" and self._current is not None:
            self._current["snippet"] = " ".join(self._current["snippet"].split())
            if self._current["url"]:
                self.results.append(self._current)
            self._current = None
            self._mode = None


class BingParser(HTMLParser):
    def __init__(self, limit):
        super().__init__(convert_charrefs=True)
        self.limit = limit
        self.results = []
        self._current = None
        self._mode = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "li":
            classes = (attributes.get("class") or "").split()
            if "b_algo" in classes and len(self.results) < self.limit:
                self._current = {"title": "", "url": "", "snippet": ""}
                self._mode = None
                return
        if self._current is None:
            return
        if tag == "a" and not self._current["url"]:
            self._current["url"] = html.unescape(attributes.get("href") or "")
            self._mode = "title"
        elif tag == "p" and not self._current["snippet"]:
            self._mode = "snippet"

    def handle_data(self, data):
        if self._current is None or self._mode is None:
            return
        if self._mode == "title":
            self._current["title"] += data
        elif self._mode == "snippet":
            self._current["snippet"] += data

    def handle_endtag(self, tag):
        if self._current is None:
            return
        if tag == "a" and self._mode == "title":
            self._current["title"] = " ".join(self._current["title"].split())
            self._mode = None
        elif tag == "p" and self._mode == "snippet":
            self._current["snippet"] = " ".join(self._current["snippet"].split())
            self._mode = None
        elif tag == "li":
            if self._current["url"]:
                self.results.append(self._current)
            self._current = None
            self._mode = None


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self._skip = 0
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "template"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"):
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "template") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"):
            self._parts.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        else:
            self._parts.append(data)

    def text(self):
        lines = []
        for line in "".join(self._parts).splitlines():
            cleaned = " ".join(line.split())
            if cleaned:
                lines.append(cleaned)
        return "\n".join(lines)


def open_helper_path():
    configured = os.environ.get("ICB_OPEN_URL_HELPER")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "build/native/icb-open-url"


def _clean_url(href):
    href = html.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlsplit(href)
    if parsed.path == "/l/":
        target = urllib.parse.parse_qs(parsed.query).get("uddg")
        if target:
            return target[0]
    return href


def _fetch(url, max_bytes, timeout):
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.1",
    })
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(max_bytes + 1)
        return {
            "final_url": response.geturl(),
            "status": response.status,
            "content_type": response.headers.get("content-type", ""),
            "body": body,
        }


def _network_failure(operation, error, request_id):
    if isinstance(error, urllib.error.HTTPError):
        return result(operation, "unavailable", reason="http_error",
                      data={"status": error.code}, request_id=request_id)
    if isinstance(error, TimeoutError):
        return result(operation, "unavailable", reason="network_timeout", request_id=request_id)
    return result(operation, "unavailable", reason="network_error",
                  data={"error": str(error)[:300]}, request_id=request_id)


def search(params, request_id=None):
    operation = "browser.search"
    extra = set(params) - {"query", "limit"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    query = params.get("query")
    if not isinstance(query, str) or not 1 <= len(query) <= 256:
        return result(operation, "error", reason="invalid_query", request_id=request_id)
    limit = params.get("limit", DEFAULT_SEARCH_LIMIT)
    if type(limit) is not int or not 1 <= limit <= 20:
        return result(operation, "error", reason="invalid_limit", request_id=request_id)
    attempts = []
    results = []
    provider = None
    endpoint = None
    final_url = None
    for name, provider_endpoint, url, parser_class in (
        (SEARCH_PROVIDER, SEARCH_ENDPOINT, SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({"q": query}),
         SearchParser),
        (BING_PROVIDER, BING_ENDPOINT, BING_ENDPOINT + "?" + urllib.parse.urlencode({"q": query, "count": str(limit)}),
         BingParser),
    ):
        try:
            response = _fetch(url, MAX_RESPONSE_BYTES, 20)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            attempts.append({"provider": name, "error": type(error).__name__})
            continue
        if not 200 <= response["status"] < 300:
            attempts.append({"provider": name, "status": response["status"]})
            continue
        parser = parser_class(limit)
        try:
            parser.feed(response["body"][:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace"))
        except (ValueError, RuntimeError):
            attempts.append({"provider": name, "error": "parse_error"})
            continue
        attempts.append({"provider": name, "status": response["status"], "results": len(parser.results)})
        if parser.results:
            results = parser.results[:limit]
            provider = name
            endpoint = provider_endpoint
            final_url = response["final_url"]
            break
    if not results:
        return result(operation, "partial", request_id=request_id, complete=False,
                      data={"query": query, "results": [], "count": 0, "attempts": attempts},
                      reason="no_search_results", source=SEARCH_PROVIDER)
    return result(operation, "verified", request_id=request_id, complete=len(results) < limit,
                  data={"query": query, "results": results, "count": len(results),
                        "provider": provider, "endpoint": endpoint, "final_url": final_url,
                        "attempts": attempts},
                  source=provider)


def read(params, request_id=None):
    operation = "browser.read"
    extra = set(params) - {"url", "max_chars"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    url = params.get("url")
    if not isinstance(url, str) or not url:
        return result(operation, "error", reason="invalid_url", request_id=request_id)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return result(operation, "error", reason="unsupported_url_scheme", request_id=request_id)
    max_chars = params.get("max_chars", DEFAULT_READ_CHARS)
    if type(max_chars) is not int or not 100 <= max_chars <= 100000:
        return result(operation, "error", reason="invalid_max_chars", request_id=request_id)
    try:
        response = _fetch(url, MAX_RESPONSE_BYTES, 20)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return _network_failure(operation, error, request_id)
    content_type = response["content_type"].split(";")[0].strip().lower()
    if content_type and not (content_type.startswith("text/") or content_type in
                             ("application/xhtml+xml", "application/json")):
        return result(operation, "unavailable", reason="unsupported_content_type",
                      data={"content_type": content_type}, request_id=request_id)
    body = response["body"]
    truncated_response = len(body) > MAX_RESPONSE_BYTES
    body = body[:MAX_RESPONSE_BYTES]
    charset = "utf-8"
    for parameter in response["content_type"].split(";")[1:]:
        key, _, value = parameter.strip().partition("=")
        if key.lower() == "charset" and value:
            charset = value.strip("\"'")
    try:
        text = body.decode(charset, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    parser = TextParser()
    try:
        parser.feed(text)
    except (ValueError, RuntimeError):
        return result(operation, "error", reason="html_parse_error", request_id=request_id)
    extracted = parser.text()
    truncated_chars = len(extracted) > max_chars
    extracted = extracted[:max_chars]
    return result(operation, "verified" if not (truncated_response or truncated_chars) else "partial",
                  request_id=request_id, complete=not (truncated_response or truncated_chars),
                  data={"url": url, "final_url": response["final_url"], "status": response["status"],
                        "title": " ".join(parser.title.split()), "text": extracted,
                        "content_type": content_type, "bytes": len(body),
                        "truncated": truncated_response or truncated_chars,
                        "max_chars": max_chars},
                  source="remote_http")


def open_url(params, request_id=None):
    operation = "browser.open"
    extra = set(params) - {"url"}
    if extra:
        return result(operation, "error", reason="unknown_parameters", request_id=request_id)
    url = params.get("url")
    if not isinstance(url, str) or not url:
        return result(operation, "error", reason="invalid_url", request_id=request_id)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return result(operation, "error", reason="unsupported_url_scheme", request_id=request_id)
    helper = open_helper_path()
    if not helper.is_file():
        return result(operation, "unavailable", reason="native_helper_missing", request_id=request_id)
    try:
        completed = subprocess.run([str(helper), url], capture_output=True, text=True,
                                   timeout=15, check=False)
    except subprocess.TimeoutExpired:
        return result(operation, "unavailable", reason="native_process_timeout", request_id=request_id)
    except OSError:
        return result(operation, "unavailable", reason="native_process_unavailable", request_id=request_id)
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, ValueError):
        return result(operation, "error", reason="invalid_native_json", request_id=request_id)
    if not isinstance(payload, dict) or payload.get("schema") != OPEN_URL_SCHEMA:
        return result(operation, "error", reason="native_schema_mismatch", request_id=request_id)
    if payload.get("source") != OPEN_URL_SOURCE:
        return result(operation, "error", reason="native_source_mismatch", request_id=request_id)
    if payload.get("url") != url:
        return result(operation, "error", reason="native_url_mismatch", request_id=request_id)
    if payload.get("status") not in EXIT_CODES:
        return result(operation, "error", reason="native_status_invalid", request_id=request_id)
    if completed.returncode != EXIT_CODES[payload["status"]]:
        return result(operation, "error", reason="native_exit_status_mismatch", request_id=request_id)
    if payload["status"] == "verified" and payload.get("opened") is not True:
        return result(operation, "error", reason="native_open_inconsistent", request_id=request_id)
    return result(operation, payload["status"], data=payload, reason=payload.get("reason"),
                  source=OPEN_URL_SOURCE, request_id=request_id,
                  complete=payload["status"] == "verified")
