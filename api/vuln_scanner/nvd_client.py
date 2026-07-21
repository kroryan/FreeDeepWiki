"""Optional NVD/NIST CVE enrichment.

OSV.dev already aggregates NVD data, so this is strictly optional. It only
runs when the user supplies an NVD API key *and* some findings are missing a
numeric CVSS score; it fills in ``cvss_score`` (and ``severity`` as a
fallback) from the NVD 2.0 CVE API.

NVD rate limits are strict (50 requests / 30s with a key, 5 without), so this
client is deliberately conservative: one request per CVE id, a small sleep
between calls, a hard cap on lookups, and every failure is swallowed
(non-fatal -- the OSV data is already there).
"""

from __future__ import annotations

import logging
import time
from typing import List, Optional

import requests

from api.vuln_scanner.models import CVEFinding, severity_from_score

logger = logging.getLogger(__name__)

NVD_CVE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
_TIMEOUT = 30
_MAX_LOOKUPS = 40
_DELAY_BETWEEN_CALLS = 1.2  # seconds (keeps us under NVD's 50/30s with-key cap)


def make_enricher(api_key: Optional[str]) -> Optional["callable"]:
    """Return a callable ``(findings: List[CVEFinding]) -> None`` that fills
    missing CVSS scores from NVD, or ``None`` if no key / nothing to do."""
    if not api_key:
        return None

    def _enrich(findings: List[CVEFinding]) -> None:
        # only CVE-prefixed ids are in NVD; only enrich findings w/o a score
        targets = [
            f for f in findings
            if f.cvss_score is None and f.id.upper().startswith("CVE-")
        ][:_MAX_LOOKUPS]
        if not targets:
            return
        headers = {"apiKey": api_key} if api_key else {}
        done = 0
        for finding in targets:
            if done >= _MAX_LOOKUPS:
                break
            try:
                resp = requests.get(
                    NVD_CVE_URL,
                    params={"cveId": finding.id},
                    headers=headers,
                    timeout=_TIMEOUT,
                )
                done += 1
                if resp.status_code != 200:
                    time.sleep(_DELAY_BETWEEN_CALLS)
                    continue
                data = resp.json()
                vulns = data.get("vulnerabilities") or []
                if not vulns:
                    time.sleep(_DELAY_BETWEEN_CALLS)
                    continue
                cve = (vulns[0] or {}).get("cve") or {}
                metrics = cve.get("metrics") or {}
                # prefer CVSS v3.1, then v3.0, then v2
                for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                    block = metrics.get(key)
                    if block and isinstance(block, list):
                        data0 = block[0].get("cvssData") or {}
                        score = data0.get("baseScore")
                        if isinstance(score, (int, float)):
                            finding.cvss_score = float(score)
                            if finding.severity in ("UNKNOWN", ""):
                                finding.severity = severity_from_score(finding.cvss_score)
                            break
            except Exception as exc:  # noqa: BLE001 - non-fatal
                logger.debug("NVD lookup %s failed: %s", finding.id, exc)
            finally:
                time.sleep(_DELAY_BETWEEN_CALLS)

    return _enrich