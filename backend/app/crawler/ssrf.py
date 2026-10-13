import socket
import ipaddress
from contextlib import contextmanager
from urllib.parse import urlparse


class SSRFError(Exception):
    """Raised when a URL is rejected by SSRF protection."""
    pass


# ---------------------------------------------------------------------------
# DNS pinning to close the validate -> connect TOCTOU / DNS-rebinding gap.
#
# Without pinning, validate_url_safety() resolves the hostname to safe IPs,
# but httpx then resolves the *same* hostname again at connect time. An
# attacker with fast-flux DNS (TTL 0, alternating public/private answers)
# can pass validation and then make the real connection go to
# 127.0.0.1 / 169.254.169.254 / 10/8.
#
# Fix: while a fetch is in progress, patch socket.getaddrinfo so every
# resolution (validation AND connect, including asyncio's loop.getaddrinfo
# which delegates to socket.getaddrinfo) returns the SAME validated IPs.
# ---------------------------------------------------------------------------

_original_getaddrinfo = socket.getaddrinfo
_pinned_hosts: dict[str, list[str]] = {}
_pinning_depth = 0


def _build_pinned_addrinfo(host: str, port, ips: list[str], family=0, type=0, proto=0):
    results = []
    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if isinstance(ip, ipaddress.IPv4Address):
            fam = socket.AF_INET
            sockaddr = (ip_str, port if port is not None else 0)
        else:
            fam = socket.AF_INET6
            sockaddr = (ip_str, port if port is not None else 0, 0, 0)
        if family != 0 and family != fam:
            continue
        socktype = type if type != 0 else socket.SOCK_STREAM
        results.append((fam, socktype, proto, "", sockaddr))
    if not results:
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known (pinned)")
    return results


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    # Normalize host to string for lookup.
    key = host.lower() if isinstance(host, str) else host

    if isinstance(host, str) and key in _pinned_hosts:
        return _build_pinned_addrinfo(host, port, _pinned_hosts[key], family, type, proto)

    # Not pinned: resolve for real, but fail closed on unsafe IPs so a
    # redirect to an internal host cannot slip through at socket level
    # even if a request hook is missed.
    results = _original_getaddrinfo(host, port, family, type, proto, flags)
    for entry in results:
        sockaddr = entry[4]
        ip_str = sockaddr[0] if sockaddr else ""
        try:
            ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not is_safe_ip(ip_str):
            raise socket.gaierror(
                socket.EAI_NONAME,
                f"SSRF blocked: {host} resolves to unsafe IP {ip_str}",
            )
    return results


@contextmanager
def dns_pinning():
    """Pin DNS for the duration of one fetch (validation + connect)."""
    global _pinning_depth
    _pinning_depth += 1
    socket.getaddrinfo = _patched_getaddrinfo  # type: ignore[assignment]
    try:
        yield
    finally:
        _pinning_depth -= 1
        if _pinning_depth <= 0:
            _pinning_depth = 0
            socket.getaddrinfo = _original_getaddrinfo  # type: ignore[assignment]
            _pinned_hosts.clear()


def _pin_host(hostname: str, ips: list[str]) -> None:
    if _pinning_depth > 0 and hostname:
        key = hostname.lower()
        if key not in _pinned_hosts:
            # First validated answer wins for this fetch.
            _pinned_hosts[key] = list(ips)


def is_safe_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
        
    if ip.is_loopback:
        return False
    if ip.is_private:
        return False
    if ip.is_link_local:
        return False
    if ip.is_multicast:
        return False
    if ip.is_reserved:
        return False
    if ip.is_unspecified:
        return False
        
    # Additional specific blocklists can be added here if needed,
    # but the above properties cover standard private/internal ranges
    # including 169.254.169.254 (link-local).
        
    return True


def resolve_hostname(hostname: str) -> list[str]:
    try:
        # socket.getaddrinfo returns a list of tuples: 
        # (family, type, proto, canonname, sockaddr)
        # sockaddr is a tuple (ip, port) for IPv4 or (ip, port, flowinfo, scopeid) for IPv6
        addresses = socket.getaddrinfo(hostname, None)
        ips = set()
        for addr in addresses:
            ips.add(addr[4][0])
        return list(ips)
    except socket.gaierror:
        return []


ALLOWED_PORTS = {80, 443}


def _check_port(parsed) -> None:
    # Reject URLs probing non-web ports (worker as port scanner /
    # slowloris via tarpitted ports). Default ports have port None.
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid port in URL")
    if port is not None and port not in ALLOWED_PORTS:
        raise ValueError(f"Port {port} is not allowed (only 80/443)")


def validate_website_url_syntax(url: str) -> str:
    """
    Fast syntactic check for user-supplied website URLs (no DNS).
    Returns stripped URL or raises ValueError.
    Blocks non-http(s), missing host, embedded credentials,
    non-web ports, and literal private/loopback IPs.
    Full DNS resolution happens later in validate_url_safety
    (fetcher + robots) at crawl time.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        raise ValueError("Website URL must not be empty")

    parsed = urlparse(cleaned)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Invalid scheme: {parsed.scheme or '(missing)'}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Missing hostname")

    if parsed.username or parsed.password:
        raise ValueError("URL must not contain credentials")

    _check_port(parsed)

    # If hostname is a literal IP, reject unsafe ones now.
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass  # not a literal IP — DNS check deferred to crawl time
    else:
        if not is_safe_ip(hostname):
            raise ValueError(f"URL resolves to unsafe IP address: {hostname}")

    return cleaned


def validate_url_safety(url: str):
    """
    Validates a URL against SSRF threats by parsing the hostname and
    resolving its IP addresses to ensure they are public/safe.
    Raises SSRFError if unsafe.
    """
    parsed = urlparse(url)
    
    if parsed.scheme not in {"http", "https"}:
        raise SSRFError(f"Invalid scheme: {parsed.scheme}")
        
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("Missing hostname")

    try:
        _check_port(parsed)
    except ValueError as error:
        raise SSRFError(str(error))

    # If the hostname is literally an IP address, urlparse leaves it in hostname.
    # We can check it directly, but resolve_hostname also works for raw IPs
    # by just echoing back the IP (since getaddrinfo parses it).

    ips = resolve_hostname(hostname)
    if not ips:
        raise SSRFError(f"Could not resolve hostname: {hostname}")

    for ip in ips:
        if not is_safe_ip(ip):
            raise SSRFError(f"URL {url} resolves to unsafe IP address: {ip}")

    # Pin the validated answer so the subsequent connect (which re-resolves
    # the same hostname) uses these exact IPs — closing DNS rebinding.
    _pin_host(hostname, ips)

    return True
