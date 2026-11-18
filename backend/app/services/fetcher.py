"""Server-side URL fetching with SSRF protection and main-content extraction.

The server fetches URLs that users type, so without guards anyone could make it request
internal addresses (cloud metadata at 169.254.169.254, localhost admin ports, the LAN).
Every hop -- including each redirect -- is checked to resolve only to public IPs.

Known gap: DNS rebinding (the host resolves to a public IP for our check and a private one
for the actual connection). Closing it means pinning the resolved IP for the connection,
which is noted in the README as a production change.
"""

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

TIMEOUT_SECONDS = 10
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_CONTENT_TYPES = {"text/html", "application/xhtml+xml", "text/plain"}
USER_AGENT = "KnowledgeInbox/1.0"


class FetchError(Exception):
    """A URL could not be fetched; the message is safe to show to the user."""


@dataclass(frozen=True)
class FetchedPage:
    title: str | None
    text: str


def assert_public_host(host: str) -> None:
    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host '{host}'") from exc

    for address in addresses:
        ip = ipaddress.ip_address(address[4][0].split("%")[0])
        if not ip.is_global:
            raise FetchError("URL points to a private or local address, which is not allowed")


def fetch_url(url: str, transport: httpx.BaseTransport | None = None) -> FetchedPage:
    try:
        with httpx.Client(
            timeout=TIMEOUT_SECONDS,
            follow_redirects=False,  # redirects are followed manually so each hop is checked
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                _check_url(url)
                with client.stream("GET", url) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers["location"])
                        continue
                    return _read_page(response, url)
    except httpx.TimeoutException as exc:
        raise FetchError("The page took too long to respond") from exc
    except httpx.HTTPError as exc:
        raise FetchError(f"Could not reach the URL ({type(exc).__name__})") from exc

    raise FetchError(f"Too many redirects (more than {MAX_REDIRECTS})")


def extract(html: str, url: str) -> FetchedPage:
    """Main article text without navigation, footers and boilerplate."""
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True) or ""
    metadata = trafilatura.extract_metadata(html)
    title = metadata.title if metadata and metadata.title else None
    return FetchedPage(title=title, text=text.strip())


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("Only http and https URLs are supported")
    if not parts.hostname:
        raise FetchError("URL has no host")
    assert_public_host(parts.hostname)


def _read_page(response: httpx.Response, url: str) -> FetchedPage:
    if response.status_code in (401, 403):
        # Many sites refuse automated clients. We identify honestly rather than spoof a browser.
        raise FetchError(
            f"The site refused automated access (HTTP {response.status_code}). Copy and paste the text as a note instead."
        )
    if response.status_code >= 400:
        raise FetchError(f"The page returned HTTP {response.status_code}")

    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise FetchError(
            f"Unsupported content type '{content_type or 'unknown'}': only web pages and plain text can be saved"
        )

    body = bytearray()
    for block in response.iter_bytes():
        body.extend(block)
        if len(body) > MAX_BYTES:
            raise FetchError(f"Page is larger than {MAX_BYTES // (1024 * 1024)} MB")

    text = body.decode(response.encoding or "utf-8", errors="replace")
    if content_type == "text/plain":
        return FetchedPage(title=None, text=text.strip())
    return extract(text, url)
