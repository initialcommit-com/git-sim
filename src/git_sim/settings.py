import pathlib
from typing import List, Optional, Union

from pydantic_settings import BaseSettings

from git_sim.enums import StyleOptions, ColorByOptions, ImgFormat, OpenIn, VideoFormat
from git_sim.paths import default_media_root


class Settings(BaseSettings):
    allow_no_commits: bool = False
    animate: bool = False
    auto_open: bool = True
    n_default: int = 5
    n: int = 5
    files: Union[List[pathlib.Path], None] = None
    # The interactive page is the default output; jpg/png give a plain image.
    img_format: ImgFormat = ImgFormat.HTML
    INFO_STRING: str = "Simulating:"
    # Light is the default palette; --dark-mode / git_sim_dark_mode picks the dark
    # one. --light-mode is kept for scripts written when dark was the default:
    # explicitly false it means dark, otherwise it changes nothing (see .light).
    dark_mode: bool = False
    light_mode: Optional[bool] = None
    transparent_bg: bool = False
    logo: pathlib.Path = pathlib.Path(__file__).parent.resolve() / "logo.png"
    low_quality: bool = False
    max_branches_per_commit: int = 1
    max_tags_per_commit: int = 1
    # git-sim_media is created here: the user's cache area, outside any
    # repository (see paths.py). --media-dir / git_sim_media_dir override it.
    media_dir: pathlib.Path = default_media_root()
    outro_bottom_text: str = "Learn more at initialcommit.com"
    outro_top_text: str = "Thanks for using Initial Commit!"
    # Newest commit on the left, arrows pointing right toward parents, so
    # history reads left to right. --no-reverse restores the older layout.
    reverse: bool = True
    show_intro: bool = False
    show_outro: bool = False
    speed: float = 1.5
    title: str = "Git-Sim, by initialcommit.com"
    video_format: VideoFormat = VideoFormat.MP4
    stdout: bool = False
    output_only_path: bool = False
    quiet: bool = False
    invert_branches: bool = False
    hide_merged_branches: bool = False
    all: bool = False
    color_by: Union[ColorByOptions, None] = None
    highlight_commit_messages: bool = False
    style: Union[StyleOptions, None] = StyleOptions.CLEAN
    font: str = "Monospace"
    font_context: bool = False
    show_command_as_title: bool = True
    # Hosted viewer that "Copy link" on an interactive page points at. The
    # graph travels in the URL fragment, so the host never receives it.
    viewer_url: str = "https://initialcommit.com/tools/git-sim"
    # Where the interactive page opens: the hosted viewer above (the page is
    # still saved locally) or the saved file. git_sim_open_in=local switches.
    open_in: OpenIn = OpenIn.HOSTED

    @property
    def light(self) -> bool:
        """Whether drawings use the light palette (the default)."""
        return not self.dark_mode and self.light_mode is not False

    class Config:
        env_prefix = "git_sim_"


settings = Settings()
