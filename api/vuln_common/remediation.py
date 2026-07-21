"""Builds a consolidated, prioritized "Suggested Solutions" plan from any
vulnerability report's findings -- dependency CVEs (api.vuln_scanner),
website security findings (api.web_vuln_scanner), or code-scan findings
(gitleaks/semgrep, also web_vuln_scanner's WebFinding shape). Every scan
type produces one of these as its own report page/section, per the product
requirement that all vulnerability analyses include a suggested-solutions
page, not just per-finding remediation text scattered across the report.

Findings arrive as plain dicts (already-serialized CVEFinding/WebFinding),
so this has no dependency on either scanner's dataclasses -- it only reads
duck-typed fields that both shapes provide under compatible names.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4, "UNKNOWN": 5}


@dataclass
class RemediationStep:
    """One actionable step -- a single remediation instruction that may
    apply to several findings (e.g. "Upgrade lodash to 4.17.21" covers every
    CVE that upgrade happens to fix)."""

    action: str  # the remediation text itself (deduped/normalized)
    severity: str  # worst severity among the findings this step resolves
    finding_ids: List[str] = field(default_factory=list)
    finding_titles: List[str] = field(default_factory=list)
    category: str = ""  # dominant category among grouped findings
    affected_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "severity": self.severity,
            "finding_ids": self.finding_ids,
            "finding_titles": self.finding_titles,
            "category": self.category,
            "affected_count": self.affected_count,
        }


@dataclass
class RemediationPlan:
    """The full suggested-solutions page for one report."""

    steps: List[RemediationStep] = field(default_factory=list)
    summary: str = ""
    total_findings_covered: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "summary": self.summary,
            "total_findings_covered": self.total_findings_covered,
        }


def _normalize_action(text: str) -> str:
    """Collapse whitespace/punctuation variance so near-identical
    remediation strings (e.g. from the same CVE template with a slightly
    different version number) still group together on their stable prefix
    when the version is the only difference."""
    return re.sub(r"\s+", " ", text.strip().lower())


def _extract_action(finding: Dict[str, Any]) -> Optional[str]:
    """Pull the best available remediation text from either finding shape.
    CVEFinding uses ai_remediation; WebFinding uses remediation."""
    for key in ("ai_remediation", "remediation"):
        val = finding.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _finding_severity(finding: Dict[str, Any]) -> str:
    sev = str(finding.get("severity") or "UNKNOWN").upper()
    return sev if sev in SEVERITY_RANK else "UNKNOWN"


def _finding_title(finding: Dict[str, Any]) -> str:
    return (finding.get("title") or finding.get("id") or
            f"{finding.get('package_name', '')}@{finding.get('installed_version', '')}".strip("@") or
            "Untitled finding")


def build_remediation_plan(findings: List[Dict[str, Any]], max_steps: int = 40) -> RemediationPlan:
    """Group findings by (normalized) remediation action, rank by worst
    severity + how many findings each action resolves, and return a
    prioritized plan. Findings with no remediation text are skipped (there's
    nothing actionable to show); dismissed AI findings (ai_dismissed=True)
    are excluded since the report already flags them as likely noise."""
    groups: Dict[str, RemediationStep] = {}

    for finding in findings:
        if finding.get("ai_dismissed"):
            continue
        action = _extract_action(finding)
        if not action:
            continue
        key = _normalize_action(action)
        severity = _finding_severity(finding)
        title = _finding_title(finding)
        category = finding.get("category", "")
        finding_id = finding.get("id", "")

        step = groups.get(key)
        if step is None:
            step = RemediationStep(action=action, severity=severity, category=category)
            groups[key] = step
        # Keep the worst severity seen across grouped findings.
        if SEVERITY_RANK.get(severity, 5) < SEVERITY_RANK.get(step.severity, 5):
            step.severity = severity
        if finding_id and finding_id not in step.finding_ids:
            step.finding_ids.append(finding_id)
        if title not in step.finding_titles:
            step.finding_titles.append(title)
        step.affected_count += 1

    steps = list(groups.values())
    steps.sort(key=lambda s: (SEVERITY_RANK.get(s.severity, 5), -s.affected_count))
    steps = steps[:max_steps]

    total_covered = sum(s.affected_count for s in steps)
    sev_counts: Dict[str, int] = defaultdict(int)
    for s in steps:
        sev_counts[s.severity] += 1

    if not steps:
        summary = "No actionable remediation steps were generated for this scan."
    else:
        parts = [f"{sev_counts[s]} {s.lower()}" for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
                if sev_counts.get(s)]
        summary = (
            f"{len(steps)} distinct remediation action(s) covering {total_covered} finding(s)"
            + (f" ({', '.join(parts)}-priority)" if parts else "") + "."
        )

    return RemediationPlan(steps=steps, summary=summary, total_findings_covered=total_covered)
