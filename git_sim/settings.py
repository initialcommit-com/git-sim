import pathlib
from typing import List, Union

from pydantic_settings import BaseSettings

from git_sim.enums import StyleOptions, ColorByOptions, ImgFormat, VideoFormat


class Settings(BaseSettings):
    allow_no_commits: bool = False
    animate: bool = False
    auto_open: bool = True
    n_default: int = 5
    n: int = 5
    files: Union[List[pathlib.Path], None] = None
    hide_first_tag: bool = False
    img_format: ImgFormat = ImgFormat.JPG
    INFO_STRING: str = "Simulating: git"
    light_mode: bool = False
    transparent_bg: bool = False
    logo: pathlib.Path = pathlib.Path(__file__).parent.resolve() / "logo.png"
    low_quality: bool = False
    max_branches_per_commit: int = 1
    max_tags_per_commit: int = 1
    media_dir: pathlib.Path = pathlib.Path().cwd()
    outro_bottom_text: str = "Learn more at initialcommit.com"
    outro_top_text: str = "Thanks for using Initial Commit!"
    reverse: bool = False
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

    class Config:
        env_prefix = "git_sim_"


settings = Settings()
