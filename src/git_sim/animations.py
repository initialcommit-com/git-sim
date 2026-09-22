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
import urllib.parse

from git_sim.enums import VideoFormat
from git_sim.settings import settings
from git_sim.theme import theme_for


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


def _talking() -> bool:
    return not settings.stdout and not settings.output_only_path and not settings.quiet


def _open_page(scene, page_path: str, theme) -> None:
    """Open the interactive page: in the hosted viewer (default) or the saved
    file. The hosted link carries the graph in its #fragment, which never
    reaches the server; only the command and a short text graph go in the
    query string, for the preview card."""
    from git_sim.enums import OpenIn
    from git_sim.render import open_file
    from git_sim.render.html import viewer_link
    from git_sim.render.scene import open_url

    if not settings.auto_open or settings.stdout:
        return
    hosted = settings.open_in == OpenIn.HOSTED and getattr(scene, "rendered_svg", None)
    if not hosted:
        _auto_open(page_path, open_file)
        return
    # share=False: the command rides in the fragment and no text graph is
    # sent, so the server learns nothing about the repository. Only the
    # page's own Share button builds links that carry preview-card data.
    url = viewer_link(
        scene.rendered_svg,
        title=getattr(scene, "cmd", ""),
        theme_name=theme.name,
        viewer_url=settings.viewer_url,
        local_path=os.path.basename(page_path),
        share=False,
    )
    try:
        open_url(url)
    except Exception:
        _auto_open(page_path, open_file)
        return
    if _talking():
        host = urllib.parse.urlsplit(settings.viewer_url).netloc or settings.viewer_url
        print(
            f"Opened in the git-sim viewer at {host}. Nothing about you, your repository "
            "or your code was sent there: the graph travels inside the link's #fragment, "
            "which stays in your browser. To open the saved page instead, pass "
            "--open-in local or set git_sim_open_in=local."
        )


def _share_summary(scene, max_lines: int = 12) -> str:
    """A short plain-text commit graph for the preview card of a shared link.
    Small enough to travel in a query string (a few hundred bytes compressed);
    the full interactive graph goes in the URL fragment, never to the server."""
    repo = getattr(scene, "repo", None)
    if repo is None:
        return ""
    try:
        out = repo.git.log("--graph", "--oneline", "--decorate=short", f"-n{max_lines}")
    except Exception:
        return ""
    lines = [line[:90] for line in out.splitlines()[: max_lines + 6]]
    return "\n".join(lines)


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

    theme = theme_for(settings.light)
    if fmt == "html":
        data = scene.render_html(
            image_file_path,
            pixel_width=width,
            pixel_height=height,
            theme=theme,
            title=getattr(scene, "cmd", ""),
            extra_mobjects=getattr(scene, "removed_mobjects", ()),
            summary=_share_summary(scene),
            viewer_url=settings.viewer_url,
        )
    elif fmt == "svg":
        # The graph alone, with the before / after data the viewer plays: what
        # a blog or documentation page embeds with git-sim-embed.js.
        from git_sim.render.html import FONT_STACK

        # --font puts the user's family first, with the viewer's stack as the
        # fallback; --transparent-bg leaves the background out altogether.
        font_stack = FONT_STACK
        if settings.font and settings.font.lower() not in ("monospace", ""):
            font_stack = f'"{settings.font}",{FONT_STACK}'
        svg = scene.render_svg(
            width,
            height,
            background=None if settings.transparent_bg else theme.bg,
            font_stack=font_stack,
            extra_mobjects=getattr(scene, "removed_mobjects", ()),
            theme_name=theme.name,
        )
        data = svg.encode("utf-8")
        os.makedirs(os.path.dirname(os.path.abspath(image_file_path)), exist_ok=True)
        with open(image_file_path, "wb") as f:
            f.write(data)
        scene.rendered_svg = svg
    else:
        data = scene.render_image(
            image_file_path,
            pixel_width=width,
            pixel_height=height,
            background=theme.bg,
            transparent=settings.transparent_bg,
            fmt=fmt,
        )

    _announce(
        "page" if fmt == "html" else "graph" if fmt == "svg" else "image",
        image_file_path,
    )
    if settings.stdout and not settings.quiet:
        sys.stdout.buffer.write(data)
    if fmt == "html":
        _open_page(scene, image_file_path, theme)
    elif fmt == "svg":
        pass  # a file for a page to embed; nothing to open
    else:
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
