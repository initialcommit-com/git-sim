import datetime
import os
import pathlib
import sys
import time

import typer

import git_sim.commands
from git_sim.settings import ColorByOptions, ImgFormat, VideoFormat, settings

app = typer.Typer(context_settings={"help_option_names": ["-h", "--help"]})


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
        help="Output format for the image files.",
    ),
    light_mode: bool = typer.Option(
        settings.light_mode,
        "--light-mode",
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
        "--reverse",
        "-r",
        help="Display commit history in the reverse direction",
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
        help="Write raw image data to stdout while suppressing all other program output",
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
        help="Show the version of git-sim and exit.",
        callback=version_callback,
    ),
):
    import git
    from manim import WHITE, config

    settings.animate = animate
    settings.n = n
    settings.auto_open = auto_open
    settings.img_format = img_format
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

    try:
        if sys.platform == "linux" or sys.platform == "darwin":
            repo_name = git.repo.Repo(
                search_parent_directories=True
            ).working_tree_dir.split("/")[-1]
        elif sys.platform == "win32":
            repo_name = git.repo.Repo(
                search_parent_directories=True
            ).working_tree_dir.split("\\")[-1]
    except git.InvalidGitRepositoryError as e:
        repo_name = ""

    settings.media_dir = os.path.join(settings.media_dir, repo_name)

    config.media_dir = settings.media_dir
    config.verbosity = "ERROR"

    if settings.low_quality:
        config.quality = "low_quality"

    if settings.light_mode:
        config.background_color = WHITE

    if settings.transparent_bg:
        settings.img_format = ImgFormat.png

    t = datetime.datetime.fromtimestamp(time.time()).strftime("%m-%d-%y_%H-%M-%S")
    config.output_file = "git-sim-" + ctx.invoked_subcommand + "_" + t + ".mp4"


app.command()(git_sim.commands.add)
app.command()(git_sim.commands.branch)
app.command()(git_sim.commands.checkout)
app.command()(git_sim.commands.cherry_pick)
app.command()(git_sim.commands.clean)
app.command()(git_sim.commands.clone)
app.command()(git_sim.commands.commit)
app.command()(git_sim.commands.fetch)
app.command()(git_sim.commands.log)
app.command()(git_sim.commands.merge)
app.command()(git_sim.commands.mv)
app.command()(git_sim.commands.pull)
app.command()(git_sim.commands.push)
app.command()(git_sim.commands.rebase)
app.command()(git_sim.commands.reset)
app.command()(git_sim.commands.restore)
app.command()(git_sim.commands.revert)
app.command()(git_sim.commands.rm)
app.command()(git_sim.commands.stash)
app.command()(git_sim.commands.status)
app.command()(git_sim.commands.switch)
app.command()(git_sim.commands.tag)


if __name__ == "__main__":
    app()
