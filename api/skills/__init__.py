"""Skills system (Fase 6) -- SKILL.md discovery + prompt injection.

Mirrors OpenDeepWiki's skills (``src/OpenDeepWiki/skills/<name>/SKILL.md``):
a skill is a markdown file with YAML frontmatter (name, description,
allowed-tools, metadata) + a body of instructions the model follows when the
skill applies. Portable -- just markdown files + a stdlib YAML-ish parser, no
dependency (frontmatter is simple enough to parse without a YAML lib; if the
project already pulls PyYAML elsewhere that path is taken too).

A skill is NOT code -- it's a reasoning workflow the LLM is told to follow
(e.g. "think": restate -> hypothesize -> analyze -> validate -> synthesize).
The loader discovers all SKILL.md files under the bundled skills dir AND a
user skills dir (so users add their own without rebuilding), parses them, and
``render_skills_block()`` emits a ``<skills>`` block for the system prompt
listing each skill's name + description + when-to-invoke, so the model can
self-select the right workflow.

Skills are opt-in per chat (a flag on the request), because injecting every
skill's description into every prompt wastes context for chats that don't
need structured reasoning.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Bundled skills ship next to this module as <name>/SKILL.md, so the bundled
# dir IS this module's own directory. User skills live under the data root so
# a user can drop a <name>/SKILL.md there without an AppImage rebuild.
_BUNDLED_DIR = os.path.dirname(os.path.abspath(__file__))
_USER_DIR_NAME = "skills"  # <data_root>/skills


def _user_skills_dir() -> str:
    try:
        from api.data_root import get_data_root
        return os.path.join(get_data_root(), _USER_DIR_NAME)
    except Exception:  # noqa: BLE001
        return ""


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a simple YAML-ish frontmatter block (key: value, with quoted
    values and a top-level ``metadata:`` sub-map). Returns (fields, body).
    Deliberately not a full YAML parser -- SKILL.md frontmatter is a flat
    key: value list with an optional metadata sub-map, and pulling PyYAML as
    a hard dep just for this is overkill (and a packaging consideration)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), m.group(2)
    fields: dict = {}
    metadata: dict = {}
    in_metadata = False
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith(" "):  # nested under metadata:
            if in_metadata:
                sub = line.strip()
                if ":" in sub:
                    k, v = sub.split(":", 1)
                    metadata[k.strip()] = _unquote(v.strip())
            continue
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip()
        v = v.strip()
        if k == "metadata":
            in_metadata = True
            continue
        in_metadata = False
        fields[k] = _unquote(v)
    if metadata:
        fields["metadata"] = metadata
    return fields, body.strip()


def _unquote(v: str) -> str:
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        return v[1:-1]
    return v


def _load_one(path: str) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"could not read skill {path}: {e}")
        return None
    fields, body = _parse_frontmatter(text)
    name = fields.get("name") or os.path.basename(os.path.dirname(path))
    if not name:
        return None
    return {
        "name": name,
        "description": fields.get("description", ""),
        "allowed_tools": fields.get("allowed-tools", ""),
        "body": body,
        "path": path,
    }


def list_skills() -> list[dict]:
    """Discover every SKILL.md under the bundled + user skills dirs. User
    skills override bundled ones of the same name (so a user can replace a
    default skill). Returns [{name, description, allowed_tools, body, path}]."""
    found: dict[str, dict] = {}
    for base in (_BUNDLED_DIR, _user_skills_dir()):
        if not base or not os.path.isdir(base):
            continue
        for entry in os.listdir(base):
            skill_md = os.path.join(base, entry, "SKILL.md")
            if os.path.isfile(skill_md):
                skill = _load_one(skill_md)
                if skill:
                    found[skill["name"]] = skill  # user dir (later) overrides bundled
    return list(found.values())


def render_skills_block(selected: Optional[list[str]] = None) -> str:
    """Emit a ``<skills>`` block for the system prompt. If ``selected`` is
    given, only those skills are included (explicit opt-in); otherwise all
    discovered skills are listed by name+description so the model can
    self-select. Returns '' if no skills exist (so callers can always
    concatenate it)."""
    skills = list_skills()
    if not skills:
        return ""
    if selected:
        want = {s.lower() for s in selected}
        skills = [s for s in skills if s["name"].lower() in want]
    if not skills:
        return ""
    lines = ["<skills>", "You may apply a skill -- a structured reasoning workflow -- when the task fits. "
             "Follow the chosen skill's workflow; do not narrate that you are using it unless asked."]
    for s in skills:
        lines.append(f"\n### skill: {s['name']}")
        if s["description"]:
            lines.append(f"{s['description']}")
        # Include the workflow body so the model has the actual steps, not
        # just a one-liner. Trimmed to keep the prompt bounded.
        body = s["body"]
        if len(body) > 2000:
            body = body[:2000] + "\n... (truncated)"
        lines.append(body)
    lines.append("</skills>")
    return "\n".join(lines)
