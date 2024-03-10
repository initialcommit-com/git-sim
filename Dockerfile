FROM python:3.10-bullseye

RUN apt-get update && apt-get upgrade -y

RUN apt-get -y install --no-install-recommends \
        build-essential \
        ffmpeg \
        libcairo2-dev \
        libpango1.0-dev

COPY setup.py README.md MANIFEST.in /app/

COPY git_sim /app/git_sim

RUN pip install /app

WORKDIR /usr/src/git-sim

ENTRYPOINT [ "git-sim" ]