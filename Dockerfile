FROM python:3

WORKDIR /usr/src/git-sim

RUN apt update

RUN apt -y install build-essential python3-dev libcairo2-dev libpango1.0-dev ffmpeg

# The image is for rendering, so install the 'full' tier (core + Manim).
RUN pip3 install "git-sim[full]"

ENTRYPOINT [ "git-sim" ]