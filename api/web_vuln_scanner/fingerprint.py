"""Lightweight technology fingerprinting from response headers and page HTML,
then cross-referencing detected (name, version) pairs against OSV.dev the
same way api.vuln_scanner.osv_client does for code dependencies.

Only fingerprints technologies that map onto an OSV-queryable ecosystem
(npm, PyPI, ...) or a small hardcoded table of well-known CMS/server CVEs --
correlating "Apache/2.4.49" from a Server header to CVE-2021-41773 is only
possible for the handful of products this table knows about; there is no
general database for that class of software the way OSV covers packages.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from api.web_vuln_scanner.models import WebFinding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JS library fingerprints -- version is usually right in the filename
# (jquery-3.4.1.min.js) or a leading comment. These map to npm packages OSV
# already tracks CVEs for.
# ---------------------------------------------------------------------------

_JS_LIB_FILENAME_RE = re.compile(
    r'(jquery|bootstrap|lodash|angular|handlebars|moment|underscore|backbone)'
    r'[.-]?(\d+\.\d+\.\d+)',
    re.IGNORECASE,
)

_JS_LIB_TO_NPM = {
    "jquery": "jquery",
    "bootstrap": "bootstrap",
    "lodash": "lodash",
    "angular": "angular",
    "handlebars": "handlebars",
    "moment": "moment",
    "underscore": "underscore",
    "backbone": "backbone",
}

# ---------------------------------------------------------------------------
# CMS / generator meta tag -> npm-ish name is not applicable (WordPress etc.
# aren't npm packages), so these use a small curated table of well-known,
# high-impact CVEs instead. Deliberately short and conservative -- this is a
# hygiene check, not a CVE database reimplementation.
# ---------------------------------------------------------------------------

_META_GENERATOR_RE = re.compile(r'<meta\s+name=["\']generator["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE)

_KNOWN_SERVER_CVES = [
    # (Server header substring match, version regex, CVE id, severity, description)
    (re.compile(r'^Apache/2\.4\.4[9]', re.IGNORECASE), None,
     "CVE-2021-41773", "CRITICAL", "Apache HTTP Server 2.4.49 path traversal / RCE (CVE-2021-41773)."),
    (re.compile(r'^Apache/2\.4\.50', re.IGNORECASE), None,
     "CVE-2021-42013", "CRITICAL", "Apache HTTP Server 2.4.50 path traversal / RCE (CVE-2021-42013, incomplete fix for CVE-2021-41773)."),
    (re.compile(r'^nginx/1\.(?:[0-9]|1[0-6])\.', re.IGNORECASE), None,
     "CVE-2021-23017", "HIGH", "nginx resolver off-by-one heap write (CVE-2021-23017) affects nginx < 1.20.1/1.21.0."),
]


def fingerprint_page(html: str, headers: Dict[str, str]) -> List[Tuple[str, Optional[str]]]:
    """Return [(technology, version_or_none), ...] detected from one page."""
    found: List[Tuple[str, Optional[str]]] = []

    for m in _JS_LIB_FILENAME_RE.finditer(html):
        name = m.group(1).lower()
        version = m.group(2)
        found.append((name, version))

    gen_match = _META_GENERATOR_RE.search(html)
    if gen_match:
        found.append(("generator:" + gen_match.group(1).strip(), None))

    server = headers.get("Server") or headers.get("server")
    if server:
        found.append(("server:" + server, None))

    x_powered_by = headers.get("X-Powered-By") or headers.get("x-powered-by")
    if x_powered_by:
        found.append(("x-powered-by:" + x_powered_by, None))

    return found


def known_server_cves(server_header: str) -> List[WebFinding]:
    """Match a raw Server header against the small curated CVE table."""
    findings: List[WebFinding] = []
    for pattern, _version_re, cve_id, severity, description in _KNOWN_SERVER_CVES:
        if pattern.search(server_header):
            findings.append(WebFinding(
                id=f"server-cve-{cve_id.lower()}",
                category="cve",
                severity=severity,
                title=f"{cve_id}: {description}",
                description=description,
                evidence=server_header,
                cve_id=cve_id,
                technology=server_header,
                remediation=f"Upgrade the server software referenced in the Server header ({server_header}) past the vulnerable version.",
                references=[f"https://osv.dev/vulnerability/{cve_id}"],
            ))
    return findings


def js_libs_to_osv_queries(technologies: List[Tuple[str, Optional[str]]]) -> List[Dict[str, str]]:
    """Turn detected (js_lib_name, version) pairs into OSV querybatch queries
    for the npm ecosystem, deduped."""
    queries = []
    seen = set()
    for name, version in technologies:
        npm_name = _JS_LIB_TO_NPM.get(name.lower())
        if not npm_name or not version:
            continue
        key = (npm_name, version)
        if key in seen:
            continue
        seen.add(key)
        queries.append({"name": npm_name, "version": version})
    return queries
