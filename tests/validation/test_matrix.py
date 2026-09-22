"""Every case in the matrix: run git-sim, check the drawing against git, and
compare the model with its golden."""

from __future__ import annotations

import pathlib

import pytest

import oracle as o
from cases import CASES, TODO_FILE


def _placeholders(case, shapes, tmp_path):
    """Fill {todo}, {worktree_path}, {remote_url} in the arguments."""
    values = {}
    if any("{todo}" in a for a in case.args):
        repo = shapes.get(case.shape).path
        c1, c2 = o.rev_parse(repo, "HEAD~1"), o.rev_parse(repo, "HEAD")
        todo = tmp_path / "todo.txt"
        todo.write_text(TODO_FILE.format(c1=c1, c2=c2), encoding="utf-8")
        values["todo"] = str(todo)
    if any("{worktree_path}" in a for a in case.args):
        values["worktree_path"] = shapes.get(case.shape).result["worktrees"][0]
    if any("{remote_url}" in a for a in case.args):
        remote = pathlib.Path(shapes.get("ahead").result["remote"]["path"])
        values["remote_url"] = "file:///" + str(remote).replace("\\", "/")
    return [a.format(**values) if "{" in a else a for a in case.args]


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_case(case, shapes, gitsim, golden, tmp_path, request):
    if case.slow:
        request.applymarker(pytest.mark.slow)
    shape = shapes.get(case.shape)
    args = _placeholders(case, shapes, tmp_path)
    run = gitsim.run(shape.path, *args, fmt=case.fmt, globals_=case.globals_)
    if case.error:
        run.failed(case.error)
        return
    run.ok()
    if case.check is not None:
        case.check(run.model, shape.path)
    golden(case.id, run.model)
