import pathlib

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
from git_sim.settings import ImgFormat, VideoFormat, settings

app = typer.Typer(context_settings={"help_option_names": ["-h", "--help"]})


@app.callback(no_args_is_help=True)
def main(
    animate: bool = typer.Option(
        settings.animate,
        help="Animate the simulation and output as an mp4 video",
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
):
    settings.animate = animate
    settings.auto_open = auto_open
    settings.img_format = img_format
    settings.light_mode = light_mode
    settings.logo = logo
    settings.low_quality = low_quality
    settings.max_branches_per_commit = max_branches_per_commit
    settings.max_tags_per_commit = max_tags_per_commit
    settings.media_dir = media_dir
    settings.outro_bottom_text = outro_bottom_text
    settings.outro_top_text = outro_top_text
    settings.reverse = reverse
    settings.show_intro = show_intro
    settings.show_outro = show_outro
    settings.speed = speed
    settings.title = title
    settings.video_format = video_format


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
