import socket

import httpx
import pytest

from app.services import fetcher
from app.services.fetcher import FetchError, assert_public_host, extract, fetch_url

ARTICLE_HTML = """
<html><head><title>Zebra launch</title></head>
<body>
  <nav>Home | About | Contact</nav>
  <article>
    <h1>Zebra launch</h1>
    <p>Turium AI announced Zebra, an enterprise assistant that answers questions over company
    documents and always shows the source of every answer. The team says grounding answers in
    source documents is what makes enterprise users trust the system enough to rely on it.</p>
    <p>The product supports both structured and unstructured data and enforces access controls
    so people only see answers drawn from documents they are allowed to read.</p>
  </article>
  <footer>Copyright 2026</footer>
</body></html>
"""

real_getaddrinfo = socket.getaddrinfo


@pytest.fixture
def fake_public_dns(monkeypatch):
    """Resolve example.com to a public IP without touching the network."""

    def getaddrinfo(host, *args, **kwargs):
        if host == "example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(fetcher.socket, "getaddrinfo", getaddrinfo)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "10.0.0.5", "169.254.169.254", "::1"])
def test_rejects_private_hosts(host):
    with pytest.raises(FetchError, match="private or local"):
        assert_public_host(host)


def test_rejects_non_http_scheme():
    with pytest.raises(FetchError, match="http"):
        fetch_url("file:///etc/passwd")


def test_extract_pulls_main_text():
    page = extract(ARTICLE_HTML, "https://example.com/zebra")

    assert page.title == "Zebra launch"
    assert "always shows the source of every answer" in page.text
    assert "Copyright 2026" not in page.text


def test_fetch_html_page(fake_public_dns):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, html=ARTICLE_HTML)
    )

    page = fetch_url("https://example.com/zebra", transport=transport)

    assert page.title == "Zebra launch"
    assert "access controls" in page.text


def test_unsupported_content_type(fake_public_dns):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})
    )

    with pytest.raises(FetchError) as err:
        fetch_url("https://example.com/file.pdf", transport=transport)
    assert "content type" in str(err.value).lower()


def test_redirect_to_private_blocked(fake_public_dns):
    transport = httpx.MockTransport(
        lambda request: httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
    )

    with pytest.raises(FetchError, match="private or local"):
        fetch_url("https://example.com/redirect", transport=transport)


def test_http_error_status(fake_public_dns):
    transport = httpx.MockTransport(lambda request: httpx.Response(404))

    with pytest.raises(FetchError, match="404"):
        fetch_url("https://example.com/missing", transport=transport)


@pytest.mark.parametrize("status", [401, 403])
def test_blocked_by_site_suggests_note(fake_public_dns, status):
    transport = httpx.MockTransport(lambda request: httpx.Response(status))

    with pytest.raises(FetchError, match="paste the text as a note"):
        fetch_url("https://example.com/protected", transport=transport)


def test_oversized_body_rejected(fake_public_dns, monkeypatch):
    monkeypatch.setattr(fetcher, "MAX_BYTES", 100)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, text="a" * 500)
    )

    with pytest.raises(FetchError, match="larger than"):
        fetch_url("https://example.com/big.txt", transport=transport)
