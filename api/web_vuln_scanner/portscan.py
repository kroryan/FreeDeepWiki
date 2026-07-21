"""Port/service scanning: uses the system's nmap binary when available
(TCP connect scan -- no root/Npcap required on either OS), and falls back to
a pure-stdlib socket-based scanner when it isn't. This is the one place in
the web vuln scanner that could tempt bundling a binary; deliberately never
does, to keep the AppImage/exe portable on both OSes with zero extra
install step -- nmap is purely an enhancement when the user's system
already has it.

Both paths only ever open a plain TCP connection (no raw sockets, no SYN
scanning, no OS fingerprinting) -- equivalent to what a browser does when it
connects to a port, well within "basic hygiene scan" territory.
"""

from __future__ import annotations

import logging
import shutil
import socket
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from api.web_vuln_scanner.models import WebFinding

logger = logging.getLogger(__name__)

# Common ports worth flagging if unexpectedly open on a public web host --
# database/admin/remote-access services that should not be internet-facing.
_RISKY_PORTS: Dict[int, str] = {
    21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP",
    111: "rpcbind", 135: "MSRPC", 139: "NetBIOS", 445: "SMB",
    1433: "MSSQL", 1723: "PPTP", 3306: "MySQL", 3389: "RDP",
    5432: "PostgreSQL", 5900: "VNC", 6379: "Redis", 9200: "Elasticsearch",
    27017: "MongoDB",
}
# Expected/benign on a web host -- never flagged even if open.
_EXPECTED_PORTS = {80, 443}

_SCAN_PORTS = sorted(set(_RISKY_PORTS) | _EXPECTED_PORTS)
_NMAP_TIMEOUT = 30
_SOCKET_TIMEOUT = 1.5


def _nmap_binary() -> Optional[str]:
    return shutil.which("nmap")


def _scan_with_nmap(host: str) -> Optional[Dict[int, str]]:
    """Returns {port: state} for open ports via system nmap, or None if nmap
    isn't available or the scan failed for any reason (caller falls back)."""
    binary = _nmap_binary()
    if not binary:
        return None
    ports_arg = ",".join(str(p) for p in _SCAN_PORTS)
    try:
        result = subprocess.run(
            [binary, "-sT", "-Pn", "-p", ports_arg, "-T4",
             "--host-timeout", "20s", "-oX", "-", host],
            capture_output=True, text=True, timeout=_NMAP_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("nmap scan failed for %s: %s", host, exc)
        return None

    try:
        root = ET.fromstring(result.stdout)
    except ET.ParseError:
        return None

    open_ports: Dict[int, str] = {}
    for port_el in root.iter("port"):
        state_el = port_el.find("state")
        if state_el is None or state_el.get("state") != "open":
            continue
        try:
            port_num = int(port_el.get("portid"))
        except (TypeError, ValueError):
            continue
        service_el = port_el.find("service")
        service_name = service_el.get("name") if service_el is not None else ""
        open_ports[port_num] = service_name or ""
    return open_ports


def _scan_with_sockets(host: str) -> Dict[int, str]:
    """Pure-stdlib fallback: attempt a TCP connect to each candidate port.
    Slower than nmap (no async batching, sequential) but has zero external
    dependencies and works identically on Windows/Linux/macOS."""
    open_ports: Dict[int, str] = {}
    for port in _SCAN_PORTS:
        try:
            with socket.create_connection((host, port), timeout=_SOCKET_TIMEOUT):
                open_ports[port] = ""
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    return open_ports


def scan_ports(host: str) -> List[WebFinding]:
    """Scan a small set of commonly-risky ports on ``host`` and return a
    finding for each unexpectedly-open one (never for 80/443 -- those are
    expected on a web host)."""
    findings: List[WebFinding] = []
    open_ports = _scan_with_nmap(host)
    engine = "nmap"
    if open_ports is None:
        open_ports = _scan_with_sockets(host)
        engine = "socket fallback"

    for port, service in open_ports.items():
        if port in _EXPECTED_PORTS:
            continue
        label = _RISKY_PORTS.get(port, service or f"port {port}")
        findings.append(WebFinding(
            id=f"open-port-{port}",
            category="exposure",
            severity="HIGH" if port in (22, 3306, 3389, 5432, 6379, 9200, 27017) else "MEDIUM",
            title=f"Port {port} ({label}) is open",
            description=(
                f"{label} appears to be reachable on {host}:{port} ({engine}). "
                "Administrative/database/remote-access services should not be "
                "exposed directly to the internet."
            ),
            evidence=f"port {port} open ({service or 'unknown service'})",
            remediation=(
                f"Firewall port {port} to trusted IPs only, or bind the {label} "
                "service to a private/internal network interface."
            ),
        ))
    return findings
