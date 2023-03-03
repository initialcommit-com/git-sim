import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="git-sim",
    version="0.2.6",
    author="Jacob Stopak",
    author_email="jacob@initialcommit.io",
    description="Simulate Git commands on your own repos by generating an image (default) or video visualization depicting the command's behavior.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://initialcommit.com/tools/git-sim",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.7",
    install_requires=[
        "gitpython",
        "manim",
        "opencv-python-headless",
        "typer",
        "pydantic",
        "git-dummy",
    ],
    keywords="git sim simulation simulate git-simulate git-simulation git-sim manim animation gitanimation image video dryrun dry-run",
    project_urls={
        "Homepage": "https://initialcommit.com/tools/git-sim",
        "Source": "https://github.com/initialcommit-com/git-sim",
    },
    entry_points={
        "console_scripts": [
            "git-sim=git_sim.__main__:app",
            "git-dummy=git_dummy.__main__:app",
        ],
    },
    include_package_data=True,
)
