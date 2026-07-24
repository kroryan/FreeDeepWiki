---
name: think
description: "Deliberate reasoning skill: enforce multi-step analysis, hypothesis testing, and option evaluation before answering complex questions"
license: MIT
allowed-tools: ""
metadata:
  author: HackDeepWiki
  version: "1.0.0"
---

# Think — Deliberate Reasoning Skill

Use this skill whenever a task requires careful judgment, non-trivial trade-offs, or multi-hop reasoning. Follow the deliberate workflow before responding.

## Reasoning Workflow

### 1. Understand the problem
- Restate the goal in your own words and confirm the success criteria.
- List known inputs, missing data, and explicit constraints.
- Flag ambiguities that must be resolved or acknowledged.

### 2. Generate candidate hypotheses
- Brainstorm at least two distinct approaches, explanations, or solution paths.
- Note the core assumption powering each option.
- Explain why each option could plausibly work and where it might fail.

### 3. Analyze and compare
- Move from surface observations → pattern recognition → assumption stress-tests → deeper insights.
- Trace your reasoning step-by-step; avoid skipping links in the logic chain.
- Compare options on impact, feasibility, risks, and alignment with constraints.

### 4. Validate and correct
- Cross-check reasoning against established facts, data, or prior decisions.
- Probe edge cases and counter-examples; document how they affect conclusions.
- If you spot a flaw, explicitly call it out and adjust.

### 5. Synthesize a conclusion
- Integrate the strongest insights from the surviving options.
- Summarize decisive evidence, trade-offs, and residual uncertainties.
- Deliver a recommendation with clear next steps or safeguards.

## Guardrails
- Fight confirmation bias: actively look for evidence that disproves each hypothesis.
- Admit uncertainty instead of inventing facts.
- Stay scoped: solve the asked question first before exploring tangents.

## When to Invoke
- Architecture, system design, or technology selection questions.
- Root-cause investigations of complex bugs or incidents.
- Multi-factor analytical questions (forecasting, prioritization).
- Any scenario demanding high precision or auditability.
