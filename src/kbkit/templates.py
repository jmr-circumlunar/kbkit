"""Render a note from a named vault template in a write transaction."""

from __future__ import annotations

import json
import re
from pathlib import Path
from string import Template

from .frontmatter import validate_frontmatter
from .profile import load_profile
from .prototype_markdown import parse_document
from .selector import markdown_path


_PLACEHOLDER = re.compile(r"([A-Za-z_][A-Za-z_0-9-]*:[ \t]*)\$\{([A-Za-z_][A-Za-z_0-9]*)\}([ \t]*(?:#[^\r\n]*)?)(\r?\n)")


def render_template(root: Path, name: str, variables: dict[str, str]) -> str:
    profile = load_profile(root)
    if not isinstance(name, str) or name not in profile.templates:
        raise ValueError("choose a named template from [templates] in the vault profile")
    if not isinstance(variables, dict) or any(not isinstance(value, str) for value in variables.values()):
        raise ValueError("template variables must map names to strings")
    document = parse_document(markdown_path(root, profile.templates[name]).read_bytes())
    if document.body_offset <= 3:
        raise ValueError("a note template must have a complete frontmatter block")
    rendered = []
    try:
        for line in document.prefix.decode("utf-8-sig").splitlines(keepends=True):
            if "${" not in line:
                rendered.append(line)
                continue
            match = _PLACEHOLDER.fullmatch(line)
            if not match:
                raise ValueError("frontmatter placeholders must occupy the complete scalar value")
            value = json.dumps(variables[match[2]], ensure_ascii=False)
            rendered.append(match[1] + value + match[3] + match[4])
        rendered.append(Template(document.body.decode("utf-8")).substitute(variables))
    except KeyError as error:
        raise ValueError(f"missing template variable: {error.args[0]}") from error
    result = "".join(rendered)
    parsed = parse_document(result.encode("utf-8"))
    issues = validate_frontmatter(parsed.raw, profile=profile, document=parsed)
    problems = [item["field"] for item in issues
                if item["rule"] not in {"FM-UNKNOWN", "LIFE-003"} and item["rule"] not in profile.disabled_rules]
    missing = [key for key in profile.gates.required_fields if not (parsed.fields.get(key) or parsed.lists.get(key))]
    if problems or missing:
        raise ValueError("invalid or missing template fields: " + ", ".join(sorted(set(problems + missing))))
    return result
