from ingestor.normalize import canonicalize_url


def test_canonicalize_removes_utm():
    url = "https://example.com/path?utm_source=google&b=1"
    assert canonicalize_url(url) == "https://example.com/path?b=1"
