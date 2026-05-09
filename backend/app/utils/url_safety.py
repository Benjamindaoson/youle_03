"""URL safety checks — blocks requests to private/internal network addresses.

Adapted from hermes-agent (MIT) © Nous Research — ``tools/url_safety.py``.

Prevents SSRF (Server-Side Request Forgery) where a malicious prompt or
skill could trick the agent into fetching internal resources like cloud
metadata endpoints (169.254.169.254), localhost services, or private
network hosts.

Configuration:
    YOULE_ALLOW_PRIVATE_URLS=true|false  (default: false; safe)

Even when private resolution is allowed, cloud-metadata hostnames /
IPs (169.254.169.254, metadata.google.internal, ECS task metadata,
Alibaba 100.100.100.200, …) are **always** blocked.

Limitations (documented, not fixable at pre-flight level):
  - DNS rebinding (TOCTOU): an attacker-controlled DNS server with TTL=0
    can return a public IP for the check, then a private IP for the
    actual connection.  Fixing this requires connection-level validation
    (egress proxy like Stripe's Smokescreen, or libraries that pass an
    already-resolved IP to httpx).
  - Redirect-based bypass: callers that follow redirects must re-validate
    each hop (httpx ``event_hooks={"response": [validate_redirect_hook]}``).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_BLOCKED_HOSTNAMES = frozenset({
    "metadata.google.internal",
    "metadata.goog",
})

_ALWAYS_BLOCKED_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure/DO/Oracle metadata
    ipaddress.ip_address("169.254.170.2"),    # AWS ECS task metadata
    ipaddress.ip_address("169.254.169.253"),  # Azure IMDS wire server
    ipaddress.ip_address("fd00:ec2::254"),    # AWS metadata (IPv6)
    ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud metadata
})
_ALWAYS_BLOCKED_NETWORKS = (
    ipaddress.ip_network("169.254.0.0/16"),
)

# 100.64.0.0/10 (CGNAT / Shared Address Space, RFC 6598) is NOT covered by
# ipaddress.is_private — must be blocked explicitly.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _global_allow_private_urls() -> bool:
    """Return True when the deployment opted out of private-IP blocking."""
    return os.getenv("YOULE_ALLOW_PRIVATE_URLS", "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
        return True
    if ip.is_multicast or ip.is_unspecified:
        return True
    if ip in _CGNAT_NETWORK:
        return True
    return False


def is_always_blocked_url(url: str) -> bool:
    """Return True when *url* targets a non-negotiable always-blocked endpoint.

    Use this as the security floor — cloud metadata IPs / hostnames have no
    legitimate agent use regardless of routing or the
    ``YOULE_ALLOW_PRIVATE_URLS`` toggle.  Callers that bypass the full
    :func:`is_safe_url` (e.g. routing private URLs through a sidecar) must
    still enforce this floor.
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        if not hostname:
            return False

        if hostname in _BLOCKED_HOSTNAMES:
            logger.warning(
                "Blocked request to internal hostname (always-blocked floor): %s",
                hostname,
            )
            return True

        try:
            ip: ipaddress._BaseAddress | None = ipaddress.ip_address(hostname)
        except ValueError:
            ip = None

        if ip is not None:
            if ip in _ALWAYS_BLOCKED_IPS or any(
                ip in net for net in _ALWAYS_BLOCKED_NETWORKS
            ):
                logger.warning(
                    "Blocked request to cloud metadata address "
                    "(always-blocked floor): %s",
                    hostname,
                )
                return True
            return False

        try:
            addr_info = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM,
            )
        except socket.gaierror:
            return False

        for _family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                resolved = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if resolved in _ALWAYS_BLOCKED_IPS or any(
                resolved in net for net in _ALWAYS_BLOCKED_NETWORKS
            ):
                logger.warning(
                    "Blocked request to cloud metadata address "
                    "(always-blocked floor): %s -> %s",
                    hostname, ip_str,
                )
                return True

        return False

    except Exception as exc:
        logger.debug("is_always_blocked_url error for %s: %s", url, exc)
        return False


def is_safe_url(url: str) -> bool:
    """Return True iff the URL target is not a private/internal address.

    Resolves the hostname to an IP and checks against private ranges.
    Fails closed: DNS errors and unexpected exceptions block the request.

    When ``YOULE_ALLOW_PRIVATE_URLS=true``, private-IP blocking is skipped
    but cloud-metadata endpoints remain blocked.
    """
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").strip().lower().rstrip(".")
        if not hostname:
            return False

        if hostname in _BLOCKED_HOSTNAMES:
            logger.warning("Blocked request to internal hostname: %s", hostname)
            return False

        allow_all_private = _global_allow_private_urls()

        try:
            addr_info = socket.getaddrinfo(
                hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM,
            )
        except socket.gaierror:
            logger.warning("Blocked request — DNS resolution failed for: %s", hostname)
            return False

        for _family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            # Always-blocked floor — even with toggle on
            if ip in _ALWAYS_BLOCKED_IPS or any(
                ip in net for net in _ALWAYS_BLOCKED_NETWORKS
            ):
                logger.warning(
                    "Blocked request to cloud metadata address: %s -> %s",
                    hostname, ip_str,
                )
                return False

            if not allow_all_private and _is_blocked_ip(ip):
                logger.warning(
                    "Blocked request to private/internal address: %s -> %s",
                    hostname, ip_str,
                )
                return False

        if allow_all_private:
            logger.debug(
                "Allowing private/internal resolution (YOULE_ALLOW_PRIVATE_URLS): %s",
                hostname,
            )

        return True

    except Exception as exc:
        logger.warning("Blocked request — URL safety check error for %s: %s", url, exc)
        return False
