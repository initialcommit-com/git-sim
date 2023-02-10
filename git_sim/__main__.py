import argparse
import datetime
import os
import pathlib
import subprocess
import sys
import time

import typer

import git_sim.add
import git_sim.branch
import git_sim.cherrypick
import git_sim.commit
import git_sim.log
import git_sim.merge
import git_sim.rebase
import git_sim.reset
import git_sim.restore
import git_sim.revert
import git_sim.stash
import git_sim.status
import git_sim.tag
from git_sim.settings import ImgFormat, Settings, VideoFormat

app = typer.Typer()


@app.callback(no_args_is_help=True)
def main(
    animate: bool = typer.Option(
        Settings.animate,
        help="Animate the simulation and output as an mp4 video",
    ),
    auto_open: bool = typer.Option(
        Settings.auto_open,
        "--auto-open",
        " /-d",
        help="Enable / disable the automatic opening of the image/video file after generation",
    ),
    img_format: ImgFormat = typer.Option(
        Settings.img_format,
        help="Output format for the image files.",
    ),
    light_mode: bool = typer.Option(
        Settings.light_mode,
        "--light-mode",
        help="Enable light-mode with white background",
    ),
    logo: pathlib.Path = typer.Option(
        Settings.logo,
        help="The path to a custom logo to use in the animation intro/outro",
    ),
    low_quality: bool = typer.Option(
        Settings.low_quality,
        "--low-quality",
        help="Render output video in low quality, useful for faster testing",
    ),
    max_branches_per_commit: int = typer.Option(
        Settings.max_branches_per_commit,
        help="Maximum number of branch labels to display for each commit",
    ),
    max_tags_per_commit: int = typer.Option(
        Settings.max_tags_per_commit,
        help="Maximum number of tags to display for each commit",
    ),
    media_dir: pathlib.Path = typer.Option(
        Settings.media_dir,
        help="The path to output the animation data and video file",
    ),
    outro_bottom_text: str = typer.Option(
        Settings.outro_bottom_text,
        help="Custom text to display below the logo during the outro",
    ),
    outro_top_text: str = typer.Option(
        Settings.outro_top_text,
        help="Custom text to display above the logo during the outro",
    ),
    reverse: bool = typer.Option(
        Settings.reverse,
        "--reverse",
        "-r",
        help="Display commit history in the reverse direction",
    ),
    show_intro: bool = typer.Option(
        Settings.show_intro,
        help="Add an intro sequence with custom logo and title",
    ),
    show_outro: bool = typer.Option(
        Settings.show_outro,
        help="Add an outro sequence with custom logo and text",
    ),
    speed: float = typer.Option(
        Settings.speed,
        help="A multiple of the standard 1x animation speed (ex: 2 = twice as fast, 0.5 = half as fast)",
    ),
    title: str = typer.Option(
        Settings.title,
        help="Custom title to display at the beginning of the animation",
    ),
    video_format: VideoFormat = typer.Option(
        Settings.video_format.value,
        help="Output format for the animation files.",
        case_sensitive=False,
    ),
):
    Settings.animate = animate
    Settings.auto_open = auto_open
    Settings.img_format = img_format
    Settings.light_mode = light_mode
    Settings.logo = logo
    Settings.low_quality = low_quality
    Settings.max_branches_per_commit = max_branches_per_commit
    Settings.max_tags_per_commit = max_tags_per_commit
    Settings.media_dir = media_dir
    Settings.outro_bottom_text = outro_bottom_text
    Settings.outro_top_text = outro_top_text
    Settings.reverse = reverse
    Settings.show_intro = show_intro
    Settings.show_outro = show_outro
    Settings.speed = speed
    Settings.title = title
    Settings.video_format = video_format


app.command()(git_sim.add.add)
app.command()(git_sim.branch.branch)
app.command()(git_sim.cherrypick.cherry_pick)
app.command()(git_sim.commit.commit)
app.command()(git_sim.log.log)
app.command()(git_sim.merge.merge)
app.command()(git_sim.rebase.rebase)
app.command()(git_sim.reset.reset)
app.command()(git_sim.restore.restore)
app.command()(git_sim.revert.revert)
app.command()(git_sim.stash.stash)
app.command()(git_sim.status.status)
app.command()(git_sim.tag.tag)


if __name__ == "__main__":
    app()
