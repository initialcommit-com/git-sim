import datetime
import os
import pathlib
import time

import cv2
from manim import Scene
from manim import config as manim_config
from manim.utils.file_ops import open_file

from git_sim.settings import Settings


def handle_animations(scene: Scene) -> None:

    manim_config.media_dir = os.path.join(
        os.path.expanduser(pathlib.Path()), "git-sim_media"
    )
    manim_config.verbosity = "ERROR"

    scene.render()

    if not Settings.animate:
        video = cv2.VideoCapture(str(scene.renderer.file_writer.movie_file_path))
        success, image = video.read()
        if success:
            t = datetime.datetime.fromtimestamp(time.time()).strftime(
                "%m-%d-%y_%H-%M-%S"
            )
            image_file_name = "git-sim-log_" + t + ".jpg"
            image_file_path = os.path.join(
                os.path.join(manim_config.media_dir, "images"), image_file_name
            )
            cv2.imwrite(image_file_path, image)
        else:
            raise

    if Settings.auto_open:
        try:
            if Settings.animate:
                open_file(scene.renderer.file_writer.movie_file_path)
            else:
                open_file(image_file_path)
        except FileNotFoundError:
            print(
                "Error automatically opening media, please manually open the image or video file to view."
            )
