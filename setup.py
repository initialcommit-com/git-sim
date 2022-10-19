import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="git-sim",
    version="0.0.1",
    author="Jacob Stopak",
    author_email="jacob@initialcommit.io",
    description="Simulate git commands with a visualization before running them",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://initialcommit.com/tools/git-sim",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
    install_requires=[
        'gitpython',
        'manim'
    ],
    keywords='git sim simulation simulate git-simulate git-simulation git-sim manim animation gitanimation',
    project_urls={
        'Homepage': 'https://initialcommit.com/tools/git-sim',
    },
    entry_points={
        'console_scripts': [
            'git-sim=git_sim.__main__:main',
        ],
    },
    include_package_data=True
)
