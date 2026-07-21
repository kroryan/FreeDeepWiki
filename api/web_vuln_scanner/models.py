"""Data models for the website security scanner. Mirrors the shape of
``api.vuln_scanner.models`` (dataclasses + to_dict/from_dict, same severity
scale) but findings are keyed by URL + check, not by package."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

SEVERITY_RANKS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

# Web-check categories, used to route findings into report sections.
CATEGORY_HEADERS = "headers"
CATEGORY_COOKIES = "cookies"
CATEGORY_TLS = "tls"
CATEGORY_EXPOSURE = "exposure"  # exposed sensitive paths
CATEGORY_CVE = "cve"  # technology fingerprint -> known CVE


@dataclass
class WebFinding:
    id: str  # stable slug, e.g. "missing-hsts", "exposed-.env", or a CVE id
    category: str  # headers | cookies | tls | exposure | cve
    severity: str = "INFO"  # CRITICAL | HIGH | MEDIUM | LOW | INFO
    title: str = ""
    description: str = ""
    url: str = ""  # the specific page/endpoint this finding applies to
    evidence: str = ""  # short raw evidence (header value, response snippet, ...)
    remediation: str = ""
    references: List[str] = field(default_factory=list)
    # Only populated for category == "cve"
    cve_id: Optional[str] = None
    cvss_score: Optional[float] = None
    technology: Optional[str] = None
    technology_version: Optional[str] = None
    # LLM-assisted CVE correlation: the deterministic OSV-based pass may miss
    # CVEs that don't match on exact version fingerprints, or surface ones
    # that don't actually apply -- the LLM can propose additional candidates
    # (ai_proposed=True) or flag a low-confidence dismissal (ai_dismissed=True
    # with ai_dismiss_reason explaining why), same idea as the user's request
    # for the dependency scanner. Human-reviewable, never silently mutates
    # deterministic findings.
    ai_proposed: bool = False
    ai_dismissed: bool = False
    ai_dismiss_reason: str = ""
    ai_notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WebVulnReport:
    site_url: str = ""
    owner: str = ""
    repo: str = ""
    language: str = "en"
    generated_at: str = ""
    provider: str = ""
    model: str = ""
    pages_scanned: int = 0
    counts: Dict[str, int] = field(default_factory=lambda: {s: 0 for s in SEVERITY_RANKS})
    total_findings: int = 0
    header_findings: List[Dict[str, Any]] = field(default_factory=list)
    cookie_findings: List[Dict[str, Any]] = field(default_factory=list)
    tls_findings: List[Dict[str, Any]] = field(default_factory=list)
    exposure_findings: List[Dict[str, Any]] = field(default_factory=list)
    cve_findings: List[Dict[str, Any]] = field(default_factory=list)
    all_findings: List[Dict[str, Any]] = field(default_factory=list)
    detected_technologies: List[Dict[str, Any]] = field(default_factory=list)  # [{name, version}]
    ai_analyzed: bool = False
    # Consolidated, prioritized "Suggested Solutions" page -- see
    # api.vuln_common.remediation.build_remediation_plan.
    remediation_plan: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebVulnReport":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**filtered)
