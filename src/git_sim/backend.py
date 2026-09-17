"""Select the drawing backend for the subcommand scenes.

Static images (the default) are drawn by git_sim.render, a manim-compatible
geometry layer rasterized with skia. Animated output (--animate) uses Manim,
which is only present in the 'extras' install. The choice is made from
settings.animate the first time this module is imported, which happens after
the CLI callback has applied the command-line options.

Scenes do ``from git_sim.backend import m`` and use ``m`` exactly as they
would use ``import manim as m``.
"""

from git_sim.settings import settings

MISSING_ANIMATION_MESSAGE = """\
git-sim: --animate requires Manim, which is part of the 'extras' install:

    pip install "git-sim[extras]"

Static images, the pre-flight engine, the MCP server (git-sim-mcp) and the
Claude Code hook (git-sim-hook) work without it."""


def _select():
    if settings.animate:
        try:
            import manim as backend
        except ImportError as exc:  # pragma: no cover - depends on the install
            raise SystemExit(MISSING_ANIMATION_MESSAGE) from exc
        return backend
    import git_sim.render as backend

    return backend


m = _select()
