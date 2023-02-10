import datetime
import inspect
import os
import pathlib
import subprocess
import sys
import time

import cv2
import git.repo
from manim import WHITE, Scene, config
from manim.utils.file_ops import open_file

from git_sim.settings import settings


def handle_animations(scene: Scene) -> None:
    if sys.platform == "linux" or sys.platform == "darwin":
        repo_name = git.repo.Repo(
            search_parent_directories=True
        ).working_tree_dir.split("/")[-1]
    elif sys.platform == "win32":
        repo_name = git.repo.Repo(
            search_parent_directories=True
        ).working_tree_dir.split("\\")[-1]

    config.media_dir = os.path.join(
        os.path.expanduser(settings.media_dir), "git-sim_media"
    )
    config.verbosity = "ERROR"

    if settings.low_quality:
        config.quality = "low_quality"

    if settings.light_mode:
        config.background_color = WHITE

    t = datetime.datetime.fromtimestamp(time.time()).strftime("%m-%d-%y_%H-%M-%S")
    config.output_file = "git-sim-" + inspect.stack()[1].function + "_" + t + ".mp4"

    scene.render()

    if settings.video_format == "webm":
        webm_file_path = str(scene.renderer.file_writer.movie_file_path)[:-3] + "webm"
        cmd = f"ffmpeg -y -i {scene.renderer.file_writer.movie_file_path} -hide_banner -loglevel error -c:v libvpx-vp9 -crf 50 -b:v 0 -b:a 128k -c:a libopus {webm_file_path}"
        print("Converting video output to .webm format...")
        # Start ffmpeg conversion
        p = subprocess.Popen(cmd, shell=True)
        p.wait()
        # if the conversion is successful, delete the .mp4
        if os.path.exists(webm_file_path):
            os.remove(scene.renderer.file_writer.movie_file_path)
            scene.renderer.file_writer.movie_file_path = webm_file_path

    if not settings.animate:
        video = cv2.VideoCapture(str(scene.renderer.file_writer.movie_file_path))
        success, image = video.read()
        if success:
            image_file_name = (
                "git-sim-"
                + inspect.stack()[1].function
                + "_"
                + t
                + "."
                + settings.img_format
            )
            image_file_path = os.path.join(
                os.path.join(config.media_dir, "images"), image_file_name
            )
            cv2.imwrite(image_file_path, image)
            print("Output image location:", image_file_path)
    else:
        print("Output video location:", scene.renderer.file_writer.movie_file_path)

    if settings.auto_open:
        try:
            if not settings.animate:
                open_file(image_file_path)
            else:
                open_file(scene.renderer.file_writer.movie_file_path)
        except FileNotFoundError:
            print(
                "Error automatically opening media, please manually open the image or video file to view."
            )
