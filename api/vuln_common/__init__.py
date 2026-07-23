"""Shared helpers used by both vulnerability scanners (api.vuln_scanner for
dependency CVEs, api.web_vuln_scanner for website security). Currently the
remediation-plan and exploitation-plan builders; anything else genuinely
shared between the two scanner families (not scanner-specific) belongs here
rather than being duplicated or awkwardly imported cross-package.
"""

from api.vuln_common.exploitation import ExploitationPlan, ExploitationStep, build_exploitation_plan
from api.vuln_common.remediation import RemediationPlan, RemediationStep, build_remediation_plan

__all__ = [
    "RemediationPlan", "RemediationStep", "build_remediation_plan",
    "ExploitationPlan", "ExploitationStep", "build_exploitation_plan",
]
