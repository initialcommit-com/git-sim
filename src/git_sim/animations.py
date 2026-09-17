"""Turn a constructed scene into a file on disk.

Static images (the default) are rasterized by the built-in skia renderer.
Animated output (--animate) is rendered by Manim, which lives in the 'extras'
install, so everything Manim-related is imported lazily.
"""

import datetime
import os
import subprocess
import sys
import time

from git_sim.enums import VideoFormat
from git_sim.settings import settings


def handle_animations(scene, command_name: str) -> None:
    if settings.animate:
        _render_video(scene, command_name)
    else:
        _render_image(scene, command_name)


def _timestamp() -> str:
    return datetime.datetime.fromtimestamp(time.time()).strftime("%m-%d-%y_%H-%M-%S")


def _img_format() -> str:
    fmt = settings.img_format
    return fmt.value if hasattr(fmt, "value") else str(fmt)


def _announce(kind: str, path: str) -> None:
    if not settings.stdout and not settings.output_only_path and not settings.quiet:
        print(f"Output {kind} location:", path)
    elif not settings.stdout and settings.output_only_path and not settings.quiet:
        print(path)


def _auto_open(path: str, opener) -> None:
    if settings.auto_open and not settings.stdout:
        try:
            opener(path)
        except FileNotFoundError:
            print(
                "Error automatically opening media, please manually open the image or video file to view."
            )


# --------------------------------------------------------------------- static
def _render_image(scene, command_name: str) -> None:
    from git_sim.render import open_file
    from git_sim.render.constants import (
        DEFAULT_PIXEL_HEIGHT,
        DEFAULT_PIXEL_WIDTH,
        LOW_QUALITY_PIXEL_HEIGHT,
        LOW_QUALITY_PIXEL_WIDTH,
    )

    scene.render()

    images_dir = os.path.join(str(settings.media_dir), "images")
    os.makedirs(images_dir, exist_ok=True)
    fmt = _img_format()
    image_file_path = os.path.join(
        images_dir, f"git-sim-{command_name}_{_timestamp()}.{fmt}"
    )
    if settings.low_quality:
        width, height = LOW_QUALITY_PIXEL_WIDTH, LOW_QUALITY_PIXEL_HEIGHT
    else:
        width, height = DEFAULT_PIXEL_WIDTH, DEFAULT_PIXEL_HEIGHT

    data = scene.render_image(
        image_file_path,
        pixel_width=width,
        pixel_height=height,
        background="#FFFFFF" if settings.light_mode else "#000000",
        transparent=settings.transparent_bg,
        fmt=fmt,
    )

    _announce("image", image_file_path)
    if settings.stdout and not settings.quiet:
        sys.stdout.buffer.write(data)
    _auto_open(image_file_path, open_file)


# ------------------------------------------------------------------- animated
def _render_video(scene, command_name: str) -> None:
    from manim.utils.file_ops import open_file

    scene.render()
    movie_path = str(scene.renderer.file_writer.movie_file_path)

    if settings.video_format == VideoFormat.WEBM:
        webm_file_path = movie_path[:-3] + "webm"
        cmd = (
            f"ffmpeg -y -i {movie_path} -hide_banner -loglevel error "
            f"-c:v libvpx-vp9 -crf 50 -b:v 0 -b:a 128k -c:a libopus {webm_file_path}"
        )
        print("Converting video output to .webm format...")
        p = subprocess.Popen(cmd, shell=True)
        p.wait()
        # If the conversion succeeded, drop the .mp4.
        if os.path.exists(webm_file_path):
            os.remove(movie_path)
            scene.renderer.file_writer.movie_file_path = webm_file_path
            movie_path = webm_file_path

    _announce("video", movie_path)
    _auto_open(movie_path, open_file)
