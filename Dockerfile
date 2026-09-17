FROM python:3

WORKDIR /usr/src/git-sim

RUN apt update

RUN apt -y install build-essential python3-dev libcairo2-dev libpango1.0-dev ffmpeg

# Static images need only the core install; 'extras' adds Manim for --animate.
RUN pip3 install "git-sim[extras]"

ENTRYPOINT [ "git-sim" ]