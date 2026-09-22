"""Read a git-sim SVG back into what it says.

The exporter tags every meaningful element with data-* attributes (see
git_sim/render/svg.py and the viewer in render/html.py). This turns those
tags into a plain dictionary the tests can reason about and compare against
goldens: the title, the commits and their parents, the ref labels and what
happened to them, the file entries in the zone table, the notes.

Positions and sizes are left out on purpose: they depend on fonts and on
layout tuning, which is not what a regression test of git semantics is about.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List

SVG = "{http://www.w3.org/2000/svg}"


def _text_of(el) -> str:
    return "".join(el.itertext()).strip()


def parse(path) -> Dict:
    root = ET.parse(path).getroot()
    model: Dict = {
        "title": "",
        "commits": {},  # sha -> {parents, phase, kind, message, author, recolored, step}
        "labels": {},  # sha -> [texts]
        "refs": {},  # name -> {kind, phase, moved, count}
        "files": [],  # {name, column, phase, moved}
        "notes": [],
        "edges": {"before": 0, "after": 0, "removed": 0, "origin": 0},
        "texts": [],
        "phases": {"before": 0, "after": 0, "removed": 0},
        "steps": 0,
    }
    texts: List[str] = []
    for el in root.iter():
        role = el.get("data-role")
        phase = el.get("data-phase")
        if el.tag == f"{SVG}text":
            t = _text_of(el)
            if t:
                texts.append(t)
        if phase in model["phases"]:
            model["phases"][phase] += 1
        step = el.get("data-step")
        if step and step.isdigit():
            model["steps"] = max(model["steps"], int(step))
        if not role:
            continue
        if role == "title" and el.tag == f"{SVG}text":
            model["title"] = _text_of(el)
        elif role == "commit":
            sha = el.get("data-sha", "")
            if sha and sha not in model["commits"]:
                model["commits"][sha] = {
                    "parents": (el.get("data-parents") or "").split(),
                    "phase": phase or "before",
                    "kind": el.get("data-kind", "commit"),
                    "message": el.get("data-message", ""),
                    "author": el.get("data-author", ""),
                    "recolored": el.get("data-before-fill") is not None,
                    "step": int(el.get("data-step") or 0),
                }
        elif role == "commit-label":
            sha = el.get("data-sha", "")
            if sha and el.tag == f"{SVG}text":
                model["labels"].setdefault(sha, []).append(_text_of(el))
        elif role == "ref":
            name = el.get("data-name")
            if not name:
                continue
            entry = model["refs"].setdefault(
                name, {"kind": el.get("data-kind", ""), "phase": phase or "before", "moved": False, "count": 0}
            )
            entry["count"] += 1
            if el.get("data-dx") is not None:
                entry["moved"] = True
            if phase == "after":
                entry["phase"] = "after"
            elif phase == "removed":
                entry["phase"] = "removed"
        elif role == "file" and el.tag == f"{SVG}text":
            model["files"].append(
                {
                    "name": el.get("data-name", _text_of(el)),
                    "column": el.get("data-column", ""),
                    "phase": phase or "before",
                    "moved": el.get("data-dx") is not None,
                }
            )
        elif role == "note" and el.tag == f"{SVG}text":
            model["notes"].append(_text_of(el))
        elif role == "edge":
            kind = el.get("data-kind", "")
            if kind == "origin":
                model["edges"]["origin"] += 1
            elif phase in model["edges"]:
                model["edges"][phase] += 1
    model["texts"] = texts
    return model


def commits_by_phase(model, phase) -> Dict:
    return {s: c for s, c in model["commits"].items() if c["phase"] == phase}


def files_in(model, column, phase=None) -> List[str]:
    return sorted(
        f["name"]
        for f in model["files"]
        if f["column"].lower().startswith(column.lower()) and (phase is None or f["phase"] == phase)
    )


def has_text(model, needle) -> bool:
    n = needle.lower()
    return any(n in t.lower() for t in model["texts"])


_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:tmp|Users|home|var|private)/)[^\s'\"]+")


def _stable(text: str) -> str:
    """Absolute paths (a temp directory, a remote's location) vary per run;
    a golden should not."""
    return _PATH.sub("<path>", text)


def golden_form(model) -> Dict:
    """The model with commits keyed by message instead of sha, so a golden
    survives regeneration of the sample repository, and without the free
    text, which is what the other assertions cover."""
    by_sha = {sha: _stable(c["message"]) or sha[:7] for sha, c in model["commits"].items()}
    commits = {}
    for sha, c in model["commits"].items():
        key = by_sha[sha]
        if key in commits:  # two commits with one message: keep both, disambiguated
            key = f"{key} ({sha[:7]})"
        commits[key] = {
            "parents": sorted(by_sha.get(p, "?") for p in c["parents"]),
            "phase": c["phase"],
            "kind": c["kind"],
            "recolored": c["recolored"],
            "step": c["step"],
        }
    files = [dict(f, name=_stable(f["name"])) for f in model["files"]]
    return {
        "title": _stable(re.sub(r"\s+", " ", model["title"])),
        "commits": dict(sorted(commits.items())),
        "refs": dict(sorted(model["refs"].items())),
        "files": sorted(files, key=lambda f: (f["column"], f["name"], f["phase"])),
        "notes": [_stable(n) for n in model["notes"]],
        "edges": model["edges"],
        "steps": model["steps"],
    }
