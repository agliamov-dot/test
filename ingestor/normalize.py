from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
import hashlib


DROP_PARAMS_PREFIXES = ["utm_", "gclid", "fbclid", "mc_cid", "mc_eid"]


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.hostname.lower() if parts.hostname else ""
    if parts.port and not (
        (scheme == "http" and parts.port == 80)
        or (scheme == "https" and parts.port == 443)
    ):
        netloc += f":{parts.port}"
    path = parts.path or "/"
    query = "&".join(
        p
        for p in parts.query.split("&")
        if p and not any(p.startswith(pref) for pref in DROP_PARAMS_PREFIXES)
    )
    return urlunsplit((scheme, netloc, path, query, ""))


def sha256_bytes(data: str) -> bytes:
    return hashlib.sha256(data.encode("utf-8")).digest()
