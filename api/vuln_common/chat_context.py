"""Builds a compact, chat-prompt-sized summary of a repo's saved security
scan(s) (dependency CVE scan and/or website security scan) -- used when the
user opts into "Include security analysis" in the chat UI, so the LLM can
answer questions like "what's my most critical vulnerability" without the
user having to paste the report in manually.

Reports can run to 50+ findings with verbose LLM-generated impact/
exploitability/remediation text per finding -- injecting the raw JSON would
blow the prompt budget. This truncates per-finding text and caps the finding
count, always showing the worst-severity findings first.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

MAX_FINDINGS_SHOWN = 25
MAX_FIELD_CHARS = 220

SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4, "UNKNOWN": 5}


def _truncate(text: Optional[str], limit: int = MAX_FIELD_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def _sorted_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(findings, key=lambda f: SEVERITY_RANK.get(f.get("severity", "UNKNOWN"), 99))


def _format_counts(counts: Dict[str, Any]) -> str:
    parts = [f"{sev}: {n}" for sev, n in counts.items() if n]
    return ", ".join(parts) if parts else "none"


def build_dependency_section(report: Dict[str, Any]) -> str:
    lines = ["## Dependency Vulnerability Scan (Security Analysis)"]
    lines.append(f"Scanned at: {report.get('generated_at', 'unknown')}")
    lines.append(f"Total findings: {report.get('total_findings', 0)} ({_format_counts(report.get('counts', {}))})")
    lines.append(f"Dependencies scanned: {report.get('total_dependencies_scanned', 0)}")

    all_findings = _sorted_findings(report.get("all_findings") or [])
    shown = all_findings[:MAX_FINDINGS_SHOWN]
    if shown:
        lines.append("\n### Findings (worst severity first):")
        for f in shown:
            pkg = f"{f.get('package_name', '?')}@{f.get('installed_version', '?')}"
            cve = f.get("id", "?")
            fixed = f.get("fixed_version")
            remediation = f.get("ai_remediation") or f.get("summary") or ""
            lines.append(
                f"- [{f.get('severity', 'UNKNOWN')}] {cve} in {pkg}"
                + (f" (fix: upgrade to {fixed})" if fixed else "")
                + (f" -- {_truncate(remediation)}" if remediation else "")
            )
        remaining = len(all_findings) - len(shown)
        if remaining > 0:
            lines.append(f"...and {remaining} more finding(s) not shown here (see the full report in the Security Analysis tab).")

    plan = report.get("remediation_plan") or {}
    if plan.get("summary"):
        lines.append(f"\n### Suggested Solutions summary:\n{_truncate(plan['summary'], 500)}")

    exploit_plan = report.get("exploitation_plan") or {}
    if exploit_plan.get("summary"):
        lines.append(f"\n### Exploitation Playbook summary:\n{_truncate(exploit_plan['summary'], 500)}")

    return "\n".join(lines)


def build_website_section(report: Dict[str, Any]) -> str:
    lines = ["## Website Security Scan"]
    lines.append(f"Site: {report.get('site_url', 'unknown')}")
    lines.append(f"Scanned at: {report.get('generated_at', 'unknown')}")
    lines.append(f"Total findings: {report.get('total_findings', 0)} ({_format_counts(report.get('counts', {}))})")
    lines.append(f"Pages scanned: {report.get('pages_scanned', 0)}")
    lines.append(f"Deep scan (Docker toolkit) ran: {'yes' if report.get('deep_scan_ran') else 'no'}")
    techs = report.get("detected_technologies") or []
    if techs:
        lines.append("Detected technologies: " + ", ".join(t.get("name", "?") for t in techs))

    all_findings = _sorted_findings(report.get("all_findings") or [])
    shown = all_findings[:MAX_FINDINGS_SHOWN]
    if shown:
        lines.append("\n### Findings (worst severity first):")
        for f in shown:
            title = f.get("title", "?")
            cat = f.get("category", "?")
            url = f.get("url", "")
            remediation = f.get("remediation") or f.get("description") or ""
            lines.append(
                f"- [{f.get('severity', 'INFO')}] ({cat}) {title}"
                + (f" -- {url}" if url else "")
                + (f" -- {_truncate(remediation)}" if remediation else "")
            )
        remaining = len(all_findings) - len(shown)
        if remaining > 0:
            lines.append(f"...and {remaining} more finding(s) not shown here (see the full report in the Website Security tab).")

    plan = report.get("remediation_plan") or {}
    if plan.get("summary"):
        lines.append(f"\n### Suggested Solutions summary:\n{_truncate(plan['summary'], 500)}")

    exploit_plan = report.get("exploitation_plan") or {}
    if exploit_plan.get("summary"):
        lines.append(f"\n### Exploitation Playbook summary:\n{_truncate(exploit_plan['summary'], 500)}")

    return "\n".join(lines)


def build_security_context_text(
    vuln_report: Optional[Dict[str, Any]],
    web_vuln_report: Optional[Dict[str, Any]],
) -> str:
    """Combine whichever report(s) exist into one prompt-ready block. Returns
    an empty string if neither is available (caller skips the wrapper tag
    entirely in that case)."""
    sections = []
    if vuln_report:
        sections.append(build_dependency_section(vuln_report))
    if web_vuln_report:
        sections.append(build_website_section(web_vuln_report))
    return "\n\n".join(sections)
