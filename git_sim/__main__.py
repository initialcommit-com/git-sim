import argparse
import datetime
import os
import pathlib
import subprocess
import sys
import time

import typer

import git_sim.add
import git_sim.log
import git_sim.restore
import git_sim.status
from git_sim.settings import Settings

app = typer.Typer()
app.command()(git_sim.log.log)
app.command()(git_sim.status.status)
app.command()(git_sim.add.add)
app.command()(git_sim.restore.restore)


@app.callback()
def main(
    title: str = typer.Option(
        default=Settings.title,
        help="Custom title to display at the beginning of the animation",
    ),
    animate: bool = typer.Option(
        default=Settings.animate,
        help="Animate the simulation and output as an mp4 video",
    ),
    outro_top_text: str = typer.Option(
        default=Settings.outro_top_text,
        help="Custom text to display above the logo during the outro",
    ),
    outro_bottom_text: str = typer.Option(
        default=Settings.outro_bottom_text,
        help="Custom text to display below the logo during the outro",
    ),
    low_quality: bool = typer.Option(
        default=Settings.low_quality,
        help="Render output video in low quality, useful for faster testing",
    ),
    auto_open: bool = typer.Option(
        default=Settings.auto_open,
        help="Enable / disable the automatic opening of the image/video file after generation",
    ),
    light_mode: bool = typer.Option(
        default=Settings.light_mode, help="Enable light-mode with white background"
    ),
    logo: pathlib.Path = typer.Option(
        default=Settings.logo,
        help="The path to a custom logo to use in the animation intro/outro",
    ),
    show_intro: bool = typer.Option(
        default=Settings.show_intro,
        help="Add an intro sequence with custom logo and title",
    ),
    show_outtro: bool = typer.Option(
        default=Settings.show_outro,
        help="Add an outro sequence with custom logo and text",
    ),
    media_dir: pathlib.Path = typer.Option(
        default=Settings.media_dir,
        help="The path to output the animation data and video file",
    ),
    speed: float = typer.Option(
        default=Settings.speed,
        help="A multiple of the standard 1x animation speed (ex: 2 = twice as fast, 0.5 = half as fast)",
    ),
    max_branches_per_commit: int = typer.Option(
        default=Settings.max_branches_per_commit,
        help="Maximum number of branch labels to display for each commit",
    ),
    max_tags_per_commit: int = typer.Option(
        default=Settings.max_tags_per_commit,
        help="Maximum number of tags to display for each commit",
    ),
    reverse: bool = typer.Option(
        default=Settings.reverse,
        help="Display commit history in the reverse direction",
    ),
):
    Settings.animate = animate
    Settings.title = title
    Settings.outro_top_text = outro_top_text
    Settings.outro_bottom_text = outro_bottom_text
    Settings.low_quality = low_quality
    Settings.auto_open = auto_open
    Settings.light_mode = light_mode
    Settings.logo = logo
    Settings.show_intro = show_intro
    Settings.show_outro = show_outtro
    Settings.media_dir = media_dir
    Settings.speed = speed
    Settings.max_branches_per_commit = max_branches_per_commit
    Settings.max_tags_per_commit = max_tags_per_commit
    Settings.reverse = reverse


if __name__ == "__main__":
    app()


# def main():
#     parser = argparse.ArgumentParser(
#         "git-sim", formatter_class=argparse.ArgumentDefaultsHelpFormatter
#     )


#     subparsers = parser.add_subparsers(dest="subcommand", help="subcommand help")


#     commit = subparsers.add_parser("commit", help="commit -h")
#     commit.add_argument(
#         "-m",
#         "--message",
#         help="The commit message of the new commit",
#         type=str,
#         default="New commit",
#     )

#     stash = subparsers.add_parser("stash", help="stash -h")
#     stash.add_argument(
#         "name", nargs="*", help="The name of the file to stash changes for", type=str
#     )

#     branch = subparsers.add_parser("branch", help="branch -h")
#     branch.add_argument("name", help="The name of the new branch", type=str)

#     tag = subparsers.add_parser("tag", help="tag -h")
#     tag.add_argument("name", help="The name of the new tag", type=str)

#     reset = subparsers.add_parser("reset", help="reset -h")
#     reset.add_argument(
#         "commit",
#         nargs="?",
#         help="The ref (branch/tag), or commit ID to simulate reset to",
#         type=str,
#         default="HEAD",
#     )
#     reset.add_argument(
#         "--mode",
#         help="Either mixed (default), soft, or hard",
#         type=str,
#         default="default",
#     )
#     reset.add_argument(
#         "--soft",
#         help="Simulate a soft reset, shortcut for --mode=soft",
#         action="store_true",
#     )
#     reset.add_argument(
#         "--mixed",
#         help="Simulate a mixed reset, shortcut for --mode=mixed",
#         action="store_true",
#     )
#     reset.add_argument(
#         "--hard",
#         help="Simulate a soft reset, shortcut for --mode=hard",
#         action="store_true",
#     )

#     revert = subparsers.add_parser("revert", help="revert -h")
#     revert.add_argument(
#         "commit",
#         nargs="?",
#         help="The ref (branch/tag), or commit ID to simulate revert",
#         type=str,
#         default="HEAD",
#     )

#     merge = subparsers.add_parser("merge", help="merge -h")
#     merge.add_argument(
#         "branch",
#         nargs=1,
#         type=str,
#         help="The name of the branch to merge into the active checked-out branch",
#     )
#     merge.add_argument(
#         "--no-ff",
#         help="Simulate creation of a merge commit in all cases, even when the merge could instead be resolved as a fast-forward",
#         action="store_true",
#     )

#     rebase = subparsers.add_parser("rebase", help="rebase -h")
#     rebase.add_argument(
#         "branch",
#         nargs=1,
#         type=str,
#         help="The branch to simulate rebasing the checked-out commit onto",
#     )

#     cherrypick = subparsers.add_parser("cherry-pick", help="cherry-pick -h")
#     cherrypick.add_argument(
#         "commit",
#         nargs=1,
#         type=str,
#         help="The ref (branch/tag), or commit ID to simulate cherry-pick onto active branch",
#     )

#     if len(sys.argv) == 1:
#         parser.print_help()
#         sys.exit(1)

#     args = parser.parse_args()

#     if sys.platform == "linux" or sys.platform == "darwin":
#         repo_name = git.Repo(search_parent_directories=True).working_tree_dir.split(
#             "/"
#         )[-1]
#     elif sys.platform == "win32":
#         repo_name = git.Repo(search_parent_directories=True).working_tree_dir.split(
#             "\\"
#         )[-1]

#     config.media_dir = os.path.join(os.path.expanduser(args.media_dir), "git-sim_media")
#     config.verbosity = "ERROR"

#     # If the env variable is set and no argument provided, use the env variable value
#     if os.getenv("git_sim_media_dir") and args.media_dir == ".":
#         config.media_dir = os.path.join(
#             os.path.expanduser(os.getenv("git_sim_media_dir")),
#             "git-sim_media",
#             repo_name,
#         )

#     if args.low_quality:
#         config.quality = "low_quality"

#     if args.light_mode:
#         config.background_color = WHITE

#     scene = gs.get_scene_for_command(args=args)

#     scene.render()

#     if not args.animate:
#         video = cv2.VideoCapture(str(scene.renderer.file_writer.movie_file_path))
#         success, image = video.read()
#         if success:
#             t = datetime.datetime.fromtimestamp(time.time()).strftime(
#                 "%m-%d-%y_%H-%M-%S"
#             )
#             image_file_name = "git-sim-" + args.subcommand + "_" + t + ".jpg"
#             image_file_path = os.path.join(
#                 os.path.join(config.media_dir, "images"), image_file_name
#             )
#             cv2.imwrite(image_file_path, image)

#     if not args.disable_auto_open:
#         try:
#             if not args.animate:
#                 open_media_file(image_file_path)
#             else:
#                 open_media_file(scene.renderer.file_writer.movie_file_path)
#         except FileNotFoundError:
#             print(
#                 "Error automatically opening media, please manually open the image or video file to view."
#             )


# if __name__ == "__main__":
#     main()
