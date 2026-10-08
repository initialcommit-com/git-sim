import os

# Typer colors its help when GITHUB_ACTIONS or FORCE_COLOR is set, and the
# escape codes split words like "--verbose" that the tests look for. It reads
# this when it is first imported, so it is set before any test imports it.
os.environ["_TYPER_FORCE_DISABLE_TERMINAL"] = "1"
