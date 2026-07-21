"""Basic website security scanner -- a separate module from
``api.vuln_scanner`` (which scans a codebase's *dependency* manifests) since
the domain here is different: findings are keyed by URL/check, not by
package. Not a Redamon-level pentest tool; this is a lightweight pass over
the crawled site checking for commonly-missed, easy-to-fix issues:

    - Missing/misconfigured security headers (CSP, HSTS, X-Frame-Options, ...)
    - Cookies without Secure/HttpOnly/SameSite
    - TLS certificate issues (expired, self-signed, weak protocol)
    - Commonly-exposed sensitive paths (.env, .git/, wp-config.php.bak, ...)
    - Technology fingerprints cross-referenced against OSV.dev for known CVEs
      in the detected version (reuses api.vuln_scanner.osv_client's query
      shape), plus an optional LLM pass that can propose additional
      candidate CVEs OSV didn't surface or flag likely false positives.

Runs against the already-crawled site (no extra requests beyond the header/
cookie/TLS checks and the sensitive-path probes) -- see
``api.web_vuln_scanner.orchestrator.run_web_vuln_scan``.
"""

from api.web_vuln_scanner.models import WebFinding, WebVulnReport
from api.web_vuln_scanner.orchestrator import run_web_vuln_scan

__all__ = ["WebFinding", "WebVulnReport", "run_web_vuln_scan"]
