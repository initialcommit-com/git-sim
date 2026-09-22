import contextlib
import datetime
import importlib.util
import os
import pathlib
import sys
import time
from pathlib import Path

import typer

from fontTools.ttLib import TTFont

import git_sim.commands
from git_sim.settings import (
    ColorByOptions,
    StyleOptions,
    ImgFormat,
    OpenIn,
    VideoFormat,
    settings,
)

app = typer.Typer(context_settings={"help_option_names": ["-h", "--help"]})


def get_font_name(font_path):
    """Get the name of a font from its .ttf file."""
    font = TTFont(font_path)
    return font["name"].getName(4, 3, 1, 1033).toUnicode()


def version_callback(value: bool) -> None:
    if value:
        print(f"git-sim version {git_sim.__version__}")
        raise typer.Exit()


@app.callback(no_args_is_help=True)
def main(
    ctx: typer.Context,
    animate: bool = typer.Option(
        settings.animate,
        help="Animate the simulation and output as an mp4 video",
    ),
    n: int = typer.Option(
        settings.n,
        "-n",
        help="Number of commits to display from each branch head",
    ),
    auto_open: bool = typer.Option(
        settings.auto_open,
        "--auto-open",
        " /-d",
        help="Enable / disable the automatic opening of the image/video file after generation",
    ),
    img_format: ImgFormat = typer.Option(
        settings.img_format,
        help="Output format: html (default; a self-contained interactive page with hover details, zoom and a Before / After slider), or jpg / png for a plain image.",
    ),
    interactive: bool = typer.Option(
        False,
        "--interactive",
        help="Write the interactive HTML page. This is already the default; the flag is kept for scripts written before it was (same as --img-format html).",
    ),
    open_in: OpenIn = typer.Option(
        settings.open_in,
        "--open-in",
        help="Where the interactive page opens: hosted (default) shows it in the git-sim viewer at initialcommit.com, with the graph carried in the link's #fragment so it never reaches the server; local opens the saved .html file. Set git_sim_open_in=local to make local the default. The page is saved locally either way.",
    ),
    light_mode: bool = typer.Option(
        settings.light_mode,
        help="Enable light-mode with white background",
    ),
    transparent_bg: bool = typer.Option(
        settings.transparent_bg,
        "--transparent-bg",
        help="Make background transparent",
    ),
    logo: pathlib.Path = typer.Option(
        settings.logo,
        help="The path to a custom logo to use in the animation intro/outro",
    ),
    low_quality: bool = typer.Option(
        settings.low_quality,
        "--low-quality",
        help="Render output video in low quality, useful for faster testing",
    ),
    max_branches_per_commit: int = typer.Option(
        settings.max_branches_per_commit,
        help="Maximum number of branch labels to display for each commit",
    ),
    max_tags_per_commit: int = typer.Option(
        settings.max_tags_per_commit,
        help="Maximum number of tags to display for each commit",
    ),
    media_dir: pathlib.Path = typer.Option(
        settings.media_dir,
        help="The path to output the animation data and video file",
    ),
    outro_bottom_text: str = typer.Option(
        settings.outro_bottom_text,
        help="Custom text to display below the logo during the outro",
    ),
    outro_top_text: str = typer.Option(
        settings.outro_top_text,
        help="Custom text to display above the logo during the outro",
    ),
    reverse: bool = typer.Option(
        settings.reverse,
        "--reverse/--no-reverse",
        "-r",
        help=(
            "Lay commits out newest-first with arrows pointing right toward parents "
            "(default). --no-reverse puts the newest commit on the right instead."
        ),
    ),
    show_intro: bool = typer.Option(
        settings.show_intro,
        help="Add an intro sequence with custom logo and title",
    ),
    show_outro: bool = typer.Option(
        settings.show_outro,
        help="Add an outro sequence with custom logo and text",
    ),
    speed: float = typer.Option(
        settings.speed,
        help="A multiple of the standard 1x animation speed (ex: 2 = twice as fast, 0.5 = half as fast)",
    ),
    title: str = typer.Option(
        settings.title,
        help="Custom title to display at the beginning of the animation",
    ),
    video_format: VideoFormat = typer.Option(
        settings.video_format.value,
        help="Output format for the animation files.",
        case_sensitive=False,
    ),
    stdout: bool = typer.Option(
        settings.stdout,
        help="Write raw image data to stdout while suppressing all other program output (png unless --img-format jpg is given)",
    ),
    output_only_path: bool = typer.Option(
        settings.output_only_path,
        help="Only output the path to the generated media file to stdout (useful for other programs to ingest)",
    ),
    quiet: bool = typer.Option(
        settings.quiet,
        "--quiet",
        "-q",
        help="Suppress all output except errors",
    ),
    invert_branches: bool = typer.Option(
        settings.invert_branches,
        help="Invert positioning of branches by reversing order of multiple parents where applicable",
    ),
    hide_merged_branches: bool = typer.Option(
        settings.hide_merged_branches,
        help="Hide commits from merged branches, i.e. only display mainline commits",
    ),
    all: bool = typer.Option(
        settings.all,
        help="Display all local branches in the log output",
    ),
    color_by: ColorByOptions = typer.Option(
        settings.color_by,
        help="Color commits by parameter",
    ),
    highlight_commit_messages: bool = typer.Option(
        settings.highlight_commit_messages,
        help="Make the displayed commit messages more prominent",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show the version of git-sim and exit",
        callback=version_callback,
    ),
    style: StyleOptions = typer.Option(
        settings.style.value,
        help="Graphical style of the output image or animated video",
    ),
    font: str = typer.Option(
        settings.font,
        help="Font family used to display rendered text",
    ),
    show_command_as_title: bool = typer.Option(
        settings.show_command_as_title,
        help="Use the simulated git command as the title of the output image or animated video",
    ),
):
    import git

    if animate and importlib.util.find_spec("manim") is None:
        from git_sim.backend import MISSING_ANIMATION_MESSAGE

        typer.echo(MISSING_ANIMATION_MESSAGE, err=True)
        raise typer.Exit(code=1)

    settings.animate = animate
    settings.n = n
    settings.auto_open = auto_open
    settings.img_format = ImgFormat.HTML if interactive else img_format
    settings.open_in = open_in
    settings.light_mode = light_mode
    settings.transparent_bg = transparent_bg
    settings.logo = logo
    settings.low_quality = low_quality
    settings.max_branches_per_commit = max_branches_per_commit
    settings.max_tags_per_commit = max_tags_per_commit
    settings.media_dir = os.path.join(os.path.expanduser(media_dir), "git-sim_media")
    settings.outro_bottom_text = outro_bottom_text
    settings.outro_top_text = outro_top_text
    settings.reverse = reverse
    settings.show_intro = show_intro
    settings.show_outro = show_outro
    settings.speed = speed
    settings.title = title
    settings.video_format = video_format
    settings.stdout = stdout
    settings.output_only_path = output_only_path
    settings.quiet = quiet
    settings.invert_branches = invert_branches
    settings.hide_merged_branches = hide_merged_branches
    settings.all = all
    settings.color_by = color_by
    settings.highlight_commit_messages = highlight_commit_messages
    settings.style = style
    settings.show_command_as_title = show_command_as_title

    # The backend (skia for images, Manim for --animate) is chosen from
    # settings.animate on first import, so import it only now.
    from git_sim.backend import m

    # If font is a path, register it with the backend and use its family name.
    if Path(font).exists():
        font_path = Path(font)
        settings.font_context = m.register_font(font_path)
        settings.font = get_font_name(font_path)
    else:
        settings.font_context = contextlib.nullcontext()
        settings.font = font

    try:
        found = git.repo.Repo(search_parent_directories=True)
        # A bare repository has no working tree; its own directory names it.
        where = found.working_tree_dir or found.git_dir
        repo_name = os.path.basename(os.path.normpath(where)) if where else ""
    except git.InvalidGitRepositoryError as e:
        repo_name = ""

    settings.media_dir = os.path.join(settings.media_dir, repo_name)

    # JPEG has no transparency; the other formats keep the one they were given.
    if settings.transparent_bg and settings.img_format == ImgFormat.JPG:
        settings.img_format = ImgFormat.PNG

    # A pipe wants picture bytes, not a web page.
    if settings.stdout and settings.img_format == ImgFormat.HTML:
        settings.img_format = ImgFormat.PNG

    if settings.animate:
        from manim import config

        from git_sim.theme import theme_for

        config.media_dir = settings.media_dir
        config.verbosity = "ERROR"

        if settings.low_quality:
            config.quality = "low_quality"

        config.background_color = theme_for(settings.light_mode).bg

        t = datetime.datetime.fromtimestamp(time.time()).strftime("%m-%d-%y_%H-%M-%S")
        config.output_file = "git-sim-" + ctx.invoked_subcommand + "_" + t + ".mp4"


app.command()(git_sim.commands.add)
app.command()(git_sim.commands.branch)
app.command()(git_sim.commands.checkout)
app.command()(git_sim.commands.cherry_pick)
app.command()(git_sim.commands.clean)
app.command()(git_sim.commands.clone)
app.command()(git_sim.commands.commit)
app.command()(git_sim.commands.config)
app.command()(git_sim.commands.fetch)
app.command()(git_sim.commands.init)
app.command()(git_sim.commands.log)
app.command()(git_sim.commands.merge)
app.command()(git_sim.commands.mv)
app.command()(git_sim.commands.pull)
app.command()(git_sim.commands.push)
app.command()(git_sim.commands.rebase)
app.command()(git_sim.commands.remote)
app.command()(git_sim.commands.reset)
app.command()(git_sim.commands.restore)
app.command()(git_sim.commands.revert)
app.command()(git_sim.commands.rm)
app.command()(git_sim.commands.stash)
app.command()(git_sim.commands.status)
app.command()(git_sim.commands.switch)
app.command()(git_sim.commands.tag)
app.command()(git_sim.commands.worktree)
app.command()(git_sim.commands.reflog)
app.command()(git_sim.commands.submodule)

# Agent integration and the pre-flight check (not git subcommands).
from git_sim.install import aliases, install, uninstall  # noqa: E402
from git_sim.live import live  # noqa: E402
from git_sim.paths import media_dir  # noqa: E402
from git_sim.preflight_cli import preflight  # noqa: E402

app.command()(install)
app.command()(uninstall)
app.command()(aliases)
app.command()(media_dir)
app.command()(live)
# git's own options (--hard, -f, ...) must pass through to the command being checked
app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)(preflight)


if __name__ == "__main__":
    app()
