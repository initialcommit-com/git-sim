import datetime
import inspect
import os
import subprocess
import sys
import time

import cv2
import git.repo
from manim import WHITE, Scene
from manim.utils.file_ops import open_file

from git_sim.settings import settings
from git_sim.enums import VideoFormat


def handle_animations(scene: Scene) -> None:
    scene.render()

    if settings.video_format == VideoFormat.WEBM:
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
            t = datetime.datetime.fromtimestamp(time.time()).strftime(
                "%m-%d-%y_%H-%M-%S"
            )
            image_file_name = (
                "git-sim-"
                + inspect.stack()[2].function
                + "_"
                + t
                + "."
                + settings.img_format
            )
            image_file_path = os.path.join(
                os.path.join(settings.media_dir, "images"), image_file_name
            )
            if settings.transparent_bg:
                unsharp_image = cv2.GaussianBlur(image, (0, 0), 3)
                image = cv2.addWeighted(image, 1.5, unsharp_image, -0.5, 0)

                tmp = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                if settings.light_mode:
                    _, alpha = cv2.threshold(tmp, 225, 255, cv2.THRESH_BINARY_INV)
                else:
                    _, alpha = cv2.threshold(tmp, 25, 255, cv2.THRESH_BINARY)
                b, g, r = cv2.split(image)
                rgba = [b, g, r, alpha]
                image = cv2.merge(rgba, 4)
            cv2.imwrite(image_file_path, image)
            if (
                not settings.stdout
                and not settings.output_only_path
                and not settings.quiet
            ):
                print("Output image location:", image_file_path)
            elif (
                not settings.stdout and settings.output_only_path and not settings.quiet
            ):
                print(image_file_path)
            if settings.stdout and not settings.quiet:
                sys.stdout.buffer.write(cv2.imencode(".jpg", image)[1].tobytes())
    else:
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print("Output video location:", scene.renderer.file_writer.movie_file_path)
        elif not settings.stdout and settings.output_only_path and not settings.quiet:
            print(scene.renderer.file_writer.movie_file_path)

    if settings.auto_open and not settings.stdout:
        try:
            if not settings.animate:
                open_file(image_file_path)
            else:
                open_file(scene.renderer.file_writer.movie_file_path)
        except FileNotFoundError:
            print(
                "Error automatically opening media, please manually open the image or video file to view."
            )
