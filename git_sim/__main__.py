import argparse
import datetime
import os
import pathlib
import subprocess
import sys
import time

import typer

import git_sim.log
import git_sim.status
from git_sim.settings import Settings

app = typer.Typer()

app.add_typer(git_sim.log.app)
app.add_typer(git_sim.status.app)

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
):
    Settings.animate = animate
    Settings.title = title
    Settings.outro_top_text = outro_top_text
    Settings.outro_bottom_text = outro_bottom_text
    Settings.low_quality = low_quality
    Settings.auto_open = auto_open
    Settings.light_mode = light_mode


if __name__ == "__main__":
    app()


# import argparse
# import datetime
# import os
# import pathlib
# import sys
# import time

# import cv2
# import git
# from manim import WHITE, config
# from manim.utils.file_ops import open_file as open_media_file

# import git_sim.git_sim as gs
# from git_sim.git_sim_log import GitSimLog


# def main():
#     parser = argparse.ArgumentParser(
#         "git-sim", formatter_class=argparse.ArgumentDefaultsHelpFormatter
#     )
#     parser.add_argument(
#         "--logo",
#         help="The path to a custom logo to use in the animation intro/outro",
#         type=str,
#         default=os.path.join(str(pathlib.Path(__file__).parent.resolve()), "logo.png"),
#     )
#     parser.add_argument(
#         "--show-intro",
#         help="Add an intro sequence with custom logo and title",
#         action="store_true",
#     )
#     parser.add_argument(
#         "--show-outro",
#         help="Add an outro sequence with custom logo and text",
#         action="store_true",
#     )
#     parser.add_argument(
#         "--media-dir",
#         help="The path to output the animation data and video file",
#         type=str,
#         default=".",
#     )
#     parser.add_argument(
#         "--speed",
#         help="A multiple of the standard 1x animation speed (ex: 2 = twice as fast, 0.5 = half as fast)",
#         type=float,
#         default=1.5,
#     )
#     parser.add_argument(
#         "--max-branches-per-commit",
#         help="Maximum number of branch labels to display for each commit",
#         type=int,
#         default=1,
#     )
#     parser.add_argument(
#         "--max-tags-per-commit",
#         help="Maximum number of tags to display for each commit",
#         type=int,
#         default=1,
#     )
#     parser.add_argument(
#         "-r",
#         "--reverse",
#         help="Display commit history in the reverse direction",
#         action="store_true",
#     )

#     subparsers = parser.add_subparsers(dest="subcommand", help="subcommand help")

#     log = subparsers.add_parser("log", help="log -h")
#     log.add_argument(
#         "--commits",
#         help="The number of commits to display in the simulated log output",
#         type=int,
#         default=5,
#         choices=range(1, 13),
#     )

#     status = subparsers.add_parser("status", help="status -h")

#     add = subparsers.add_parser("add", help="add -h")
#     add.add_argument(
#         "name",
#         nargs="+",
#         help="The names of one or more files to add to Git's staging area",
#         type=str,
#     )

#     restore = subparsers.add_parser("restore", help="restore -h")
#     restore.add_argument(
#         "name", nargs="+", help="The names of one or more files to restore", type=str
#     )

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
