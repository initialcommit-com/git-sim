# skia-python has wheels up to Python 3.14, so python:3 (3.15 soon) can't install it
FROM python:3.14

# skia (static images) loads libEGL, libGL, and fontconfig; Manim (--animate)
# builds against cairo and pango and records with FFmpeg
RUN apt-get update && apt-get -y install \
    libegl1 libgl1 libfontconfig1 fonts-dejavu-core \
    build-essential python3-dev libcairo2-dev libpango1.0-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# The repo is mounted from the host, so Git sees a different owner and
# would refuse to read it without this
RUN git config --system --add safe.directory '*'

WORKDIR /usr/src/git-sim

# Static images need only the core install; 'extras' adds Manim for --animate.
# The tests build with a Git URL here to check the commit being tested.
ARG PACKAGE="git-sim[extras]"
RUN pip3 install "$PACKAGE"

ENTRYPOINT [ "git-sim" ]
