"""LOKO Security — SSRF validation for user-supplied URLs (Lot LLM §6.5).

Reusable validation shared by:
- FAQ web crawler (existing)
- BYO LLM base_url validation
- Webhook escalation URL validation (PRO-4)

In server mode:
- HTTPS only (except explicit allowlist)
- Private/loopback/link-local/metadata IPs rejected
- DNS resolution validated before request

In desktop mode:
- HTTP allowed (for local Ollama/vLLM)
- Private IPs allowed
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class SSRFError(Exception):
    """Raised when a URL fails SSRF validation."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"SSRF blocked: {reason} (url={url})")


def _is_server_mode() -> bool:
    return os.environ.get("LOKO_MODE", "desktop").lower() == "server"


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, link-local, or metadata."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # fail-closed: unparseable = reject

    if addr.is_loopback:
        return True
    if addr.is_private:
        return True
    if addr.is_link_local:
        return True
    if addr.is_reserved:
        return True

    # AWS/GCP/Azure metadata endpoint
    if ip_str in ("169.254.169.254", "fd00:ec2::254"):
        return True

    return False


def validate_url(
    url: str,
    *,
    allow_http: bool = False,
    allowed_ports: set[int] | None = None,
) -> str:
    """Validate a URL against SSRF attacks.

    Parameters
    ----------
    url : str
        The URL to validate.
    allow_http : bool
        Allow http:// scheme (only in desktop mode by default).
    allowed_ports : set[int] | None
        Allowed ports. None = all ports allowed.
        In server mode, defaults to {443} if not specified.

    Returns
    -------
    str
        The validated URL (unchanged).

    Raises
    ------
    SSRFError
        If the URL is not safe.
    """
    server_mode = _is_server_mode()

    parsed = urlparse(url)

    # Scheme validation
    if parsed.scheme == "https":
        pass
    elif parsed.scheme == "http":
        if server_mode and not allow_http:
            raise SSRFError(url, "HTTP not allowed in server mode — use HTTPS")
    else:
        raise SSRFError(url, f"Unsupported scheme: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError(url, "No hostname in URL")

    # Port validation
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if server_mode and allowed_ports is None:
        allowed_ports = {443}
    if allowed_ports is not None and port not in allowed_ports:
        raise SSRFError(url, f"Port {port} not allowed (allowed: {allowed_ports})")

    # DNS resolution + private IP check (server mode only)
    if server_mode:
        try:
            resolved = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror:
            raise SSRFError(url, f"DNS resolution failed for {hostname}")

        for family, _type, _proto, _canonname, sockaddr in resolved:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str):
                raise SSRFError(
                    url,
                    f"Resolved to private/reserved IP {ip_str} — "
                    "not allowed in server mode",
                )

    return url


def resolve_and_pin(url: str) -> tuple[str, str]:
    """Resolve hostname and return (pinned_url, original_host) for DNS rebinding protection.

    The returned URL has the hostname replaced with the resolved IP,
    and the Host header should be set to original_host.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    if not hostname:
        raise SSRFError(url, "No hostname")

    try:
        infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise SSRFError(url, f"DNS resolution failed for {hostname}")

    if not infos:
        raise SSRFError(url, f"No DNS results for {hostname}")

    ip_str = infos[0][4][0]

    if _is_server_mode() and _is_private_ip(ip_str):
        raise SSRFError(url, f"Resolved to private IP {ip_str}")

    # Rebuild URL with IP
    if ":" in ip_str:  # IPv6
        netloc = f"[{ip_str}]:{port}"
    else:
        netloc = f"{ip_str}:{port}"

    pinned = parsed._replace(netloc=netloc).geturl()
    return pinned, hostname
