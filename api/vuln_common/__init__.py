"""Shared helpers used by both vulnerability scanners (api.vuln_scanner for
dependency CVEs, api.web_vuln_scanner for website security). Currently just
the remediation-plan builder; anything else genuinely shared between the two
scanner families (not scanner-specific) belongs here rather than being
duplicated or awkwardly imported cross-package.
"""

from api.vuln_common.remediation import RemediationPlan, RemediationStep, build_remediation_plan

__all__ = ["RemediationPlan", "RemediationStep", "build_remediation_plan"]
