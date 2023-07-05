import os, subprocess
from pathlib import Path
from shlex import split

import numpy as np

from PIL import Image, ImageChops


def compare_images(path_gen, path_ref):
    """Compare a generated image against a reference image.

    This is a simple pixel-by-pixel comparison, with a threshold for
      an allowable difference.

    Parameters: file path to generated and reference image files
    Returns: True/ False
    """
    # Verify that the path to the generated file exists.
    assert '.png' in str(path_gen)
    assert path_gen.exists()

    img_gen = Image.open(path_gen)
    img_ref = Image.open(path_ref)

    img_diff = ImageChops.difference(img_gen, img_ref)

    # We're only concerned with pixels that differ by a total of 20 or more
    #   over all RGB values.
    # Convert the image data to a NumPy array for processing.
    data_diff = np.array(img_diff)

    # Calculate the sum along the color axis (axis 2) and then check
    # if the sum is greater than or equal to 20. This will return a 2D
    # boolean array where True represents pixels that differ significantly.
    pixels_diff = np.sum(data_diff, axis=2) >= 20

    # Calculate the ratio of pixels that differ significantly.
    ratio_diff = np.mean(pixels_diff)

    # Images are similar if only a small % of pixels differ significantly.
    #   This value can be increased if tests are failing when they shouldn't.
    #   It can be decreased if tests are passing when they shouldn't.
    if ratio_diff < 0.0075:
        return True
    else:
        print("bad pixel ratio:", ratio_diff)
        return False


def get_cmd_parts(raw_command):
    """
    Convert a raw git-sim command to the full version we need to use
      when testing, then split the full command into parts for use in
      subprocess.run(). This allows test functions to explicitly state
      the actual command that users would run.

    For example, the command:
        `git-sim log`
    becomes:
        `</path/to/git-sim> -d --output-only-path --img-format=png log`

    This prevents images from auto-opening, simplifies parsing output to
      identify the images we need to check, and prefers png for test runs.

    Returns: list of command parts, ready to be run with subprocess.run()
    """
    # Add the global flags needed for testing.
    cmd = raw_command.replace(
        "git-sim", "git-sim -d --output-only-path --img-format=png --font='Courier New'"
    )

    # Replace `git-sim` with the full path to the binary.
    #  as_posix() is needed for Windows compatibility.
    git_sim_path = get_venv_path() / "git-sim"
    cmd = cmd.replace("git-sim", git_sim_path.as_posix())

    return split(cmd)


def run_git_reset(tmp_repo):
    """Run `git reset`, in order to induce a failure.

    This is particularly useful when testing the image comparison algorithm.
    - Running `git reset` makes many of the generated images different.
    - For example, `git-sim log` then generates a valid image, but it doesn't
      match the reference image.

    Note: tmp_repo is a required argument, to make sure this command is not
      accidentally called in a different directory.
    """
    cmd = "git reset --hard 60bce95465a890960adcacdcd7fa726d6fad4cf3"
    cmd_parts = split(cmd)

    os.chdir(tmp_repo)
    subprocess.run(cmd_parts)


def get_venv_path():
    """Get the path to the active virtual environment.

    We actually need the bin/ or Scripts/ dir, not just the path to venv/.
    """
    if os.name == "nt":
        return Path(os.environ.get("VIRTUAL_ENV")) / "Scripts"
    else:
        return Path(os.environ.get("VIRTUAL_ENV")) / "bin"
