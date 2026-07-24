---
name: security-review
description: "Security analysis skill: reason about vulnerabilities, attack surface, and remediation using the repo's security context and code. Invoke for vuln/CVE/exploit/remediation questions"
license: MIT
allowed-tools: ""
metadata:
  author: HackDeepWiki
  version: "1.0.0"
---

# Security Review — Vulnerability Analysis Skill

Use this skill for questions about vulnerabilities, CVEs, attack surface, or
remediation in the repository under analysis. HackDeepWiki ships a dependency
CVE scanner and a web vulnerability scanner, and can inject a saved security
report into context -- this skill structures how to reason over that evidence.

## Workflow

### 1. Scope the question
- Identify whether the ask is about dependencies (CVE), the app's own code,
  a web-exposed surface, or the saved vuln report.
- Note the language/framework/ecosystem, since exploitability is ecosystem-specific.

### 2. Ground in evidence
- Prefer the injected security report and the repo's code over general knowledge.
- For a CVE: state the affected component/version, the vector, and whether the
  repo's dependency tree actually includes a vulnerable version.
- For a code-level issue: cite the file/function and the specific misuse
  (not just the CWE label).

### 3. Assess impact and exploitability
- Distinguish theoretical vs. reachable: is the vulnerable code path actually
  exposed given the app's config, auth, and network position?
- Rate severity with reasoning (CVSS-style factors: attack vector, complexity,
  privileges, user interaction, scope, confidentiality/integrity/availability).

### 4. Recommend remediation
- Give the concrete fix (pin/upgrade version, sanitize input, enforce auth,
  drop the unsafe API) -- not just "update your dependencies".
- Note any breaking-change risk of the fix and a safe order of operations.

## Guardrails
- Never claim a vulnerability is present without citing the evidence (version
  match, code path, or report line). Never claim it's absent without checking.
- This is defensive analysis for the repo's owner; do not produce exploit
  payloads, only impact + remediation.

## When to Invoke
- "Is this repo vulnerable to X?" / "Explain CVE-YYYY-NNNN for this project"
- "What's the attack surface of [component]?"
- "How do I fix [finding] from the security report?"
