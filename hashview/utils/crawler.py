"""CeWL-style website word crawler for the (DYNAMIC) Website Keywords wordlist.

``crawl_website_keywords(start_url, settings)`` performs a depth-limited,
same-host breadth-first crawl of ``start_url``, extracts visible-text words
(ignoring <script>/<style>), filters by minimum length, optionally lowercases
them, and returns a de-duplicated ``set`` of words.

Implementation notes:
  - Uses ``requests`` (already a dependency) + the stdlib ``html.parser`` — no
    BeautifulSoup/lxml needed.
  - Pages at each depth level are fetched concurrently with a thread pool.
  - ``verify=False`` (target sites in an engagement frequently have self-signed
    certs; mirrors the agent's HTTP layer) with urllib3 warnings suppressed.
  - Bounded by a per-request timeout, the configured crawl depth, and a hard
    ``MAX_PAGES`` cap so a large/looping site can't run unbounded.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlparse

import requests
import urllib3

from hashview.models import DEFAULT_CRAWL_USER_AGENT

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Safety cap on total distinct pages fetched per crawl.
MAX_PAGES = 1000
# Per-request timeout (connect, read) in seconds.
REQUEST_TIMEOUT = 15
_WORD_RE = re.compile(r'[A-Za-z0-9]+')


class _TextLinkParser(HTMLParser):
    """Collect visible text (excluding <script>/<style>) and <a href> links."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.text_parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self._skip_depth += 1
        elif tag == 'a':
            for key, val in attrs:
                if key == 'href' and val:
                    self.links.append(val)

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data:
            self.text_parts.append(data)


def _canon(url):
    """Drop the URL fragment so #anchors don't create duplicate pages."""
    return urldefrag(url)[0]


def _extract_words(text, min_len, force_lower):
    out = set()
    for token in _WORD_RE.findall(text):
        if len(token) >= min_len:
            out.add(token.lower() if force_lower else token)
    return out


def _fetch_and_parse(url, headers, host):
    """Fetch one page; return (text, [same-host absolute links]). Never raises."""
    try:
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT,
                            verify=False, allow_redirects=True)
        ctype = (resp.headers.get('Content-Type') or '').lower()
        if ctype and 'html' not in ctype:
            return '', []          # skip non-HTML (images, pdfs, …)
        html = resp.text
    except Exception:
        return '', []

    parser = _TextLinkParser()
    try:
        parser.feed(html)
    except Exception:
        pass

    links = []
    for href in parser.links:
        try:
            absolute = _canon(urljoin(url, href))
        except Exception:
            continue
        parsed = urlparse(absolute)
        if parsed.scheme in ('http', 'https') and parsed.netloc == host:
            links.append(absolute)
    return ' '.join(parser.text_parts), links


def crawl_website_keywords(start_url, settings):
    """Crawl ``start_url`` and return a de-duplicated set of keywords.

    ``settings`` is a Settings row (or any object) exposing the crawl_* fields;
    missing/None values fall back to the documented defaults.
    """
    # NOTE: use explicit None checks (not ``x or default``) so a legitimate 0
    # depth — "only the start page" — isn't treated as missing.
    min_len = getattr(settings, 'crawl_min_word_length', None)
    if min_len is None:
        min_len = 8
    user_agent = getattr(settings, 'crawl_user_agent', None) or DEFAULT_CRAWL_USER_AGENT
    force_lower = getattr(settings, 'crawl_force_lowercase', True)
    if force_lower is None:
        force_lower = True
    depth = getattr(settings, 'crawl_depth', None)
    if depth is None:
        depth = 2
    threads = getattr(settings, 'crawl_threads', None)
    if not threads or threads < 1:
        threads = 5

    parsed_start = urlparse(start_url or '')
    if parsed_start.scheme not in ('http', 'https') or not parsed_start.netloc:
        return set()
    host = parsed_start.netloc
    headers = {'User-Agent': user_agent}

    words = set()
    visited = {_canon(start_url)}
    frontier = [_canon(start_url)]

    # level 0 = the start page; levels 1..depth = followed links
    for level in range(depth + 1):
        if not frontier:
            break
        with ThreadPoolExecutor(max_workers=max(1, threads)) as pool:
            futures = {pool.submit(_fetch_and_parse, url, headers, host): url for url in frontier}
            next_frontier = []
            for future in as_completed(futures):
                text, links = future.result()
                words |= _extract_words(text, min_len, force_lower)
                if level < depth:
                    for link in links:
                        if link not in visited and len(visited) < MAX_PAGES:
                            visited.add(link)
                            next_frontier.append(link)
        frontier = next_frontier

    return words
