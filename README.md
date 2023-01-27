# git-sim
Visually simulate Git operations in your own repos with a single terminal command.

This generates an image (default) or video visualization depicting the Git command's behavior.

Command syntax is based directly on Git's command-line syntax, so using git-sim is as familiar as possible.

Example: `$ git-sim merge <branch>`

![git-sim-merge_01-05-23_09-44-46](https://user-images.githubusercontent.com/49353917/210939840-1d51493a-6cac-43fd-9d12-3d2948d32c61.jpg)

## Use cases
- Visualize Git commands to understand their effects on your repo before actually running them
- Prevent unexpected working directory and repository states by simulating before running
- Share visualizations (jpg image or mp4 video) of your Git commands with your team, or the world
- Save visualizations as a part of your team documentation to document workflow and prevent recurring issues
- Create static Git diagrams (jpg) or dynamic animated videos (mp4) to speed up content creation
- Help visual learners understand how Git commands work

## Features
- Run a one-liner git-sim command in the terminal to generate a custom Git command visualization (.jpg) from your repo
- Supported commands: `log`, `status`, `add`, `restore`, `commit`, `stash`, `branch`, `tag`, `reset`, `revert`, `merge`, `rebase`, `cherry-pick`
- Generate an animated video (.mp4) instead of a static image using the `--animate` flag (note: significant performance slowdown, it is recommended to use `--low-quality` to speed up testing and remove when ready to generate presentation-quality video)
- Choose between dark mode (default) and light mode
- Animation only: Add custom branded intro/outro sequences if desired
- Animation only: Speed up or slow down animation speed as desired

## Quickstart

1) **Install Manim and its dependencies for your OS / environment:**
    - [Install Manim on Windows](https://docs.manim.community/en/stable/installation/windows.html)
    - [Install Manim on MacOS](https://docs.manim.community/en/stable/installation/macos.html)
    - [Install Manim on Linux](https://docs.manim.community/en/stable/installation/linux.html)
    - [Install Manim in Conda](https://docs.manim.community/en/stable/installation/conda.html)

2) Install `git-sim`:

```console
$ pip3 install git-sim
```

Note: For MacOS, it is recommended to **NOT** use the system Python to install Git-Sim, and instead use [Homebrew](https://brew.sh) to install a version of Python to work with Git-Sim. Virtual environments should work too.

3) Browse to the Git repository you want to simulate Git commands in:

```console
$ cd path/to/git/repo
```

4) Run the program:

```console
$ git-sim [global options] <subcommand> [subcommand options]
```

5) Simulated output will be created as a `.jpg` file. Output files are named using the subcommand executed combined with a timestamp, and by default are stored in a subdirectory called `git-sim_media/`. The location of this subdirectory is customizable using the command line flag `--media-dir=path/to/output`. Note that when the `--animate` global flag is used, render times will be much longer and a `.mp4` video output file will be produced.

6) See global help for list of global options/flags and subcommands:

```console
$ git-sim -h
```

7) See subcommand help for list of options/flags for a specific subcommand:

```console
$ git-sim <subcommand> -h
```

## Requirements
* Python 3.7 or greater
* Pip (Package manager for Python)
* [Manim (Community version)](https://www.manim.community/)

## Commands
Basic usage is similar to Git itself - `git-sim` takes a familiar set of subcommands including "log", "status", "add", "restore", "commit", "stash", "branch", "tag", "reset", "revert", "merge", "rebase", "cherry-pick", along with corresponding options.

```console
$ git-sim [global options] <subcommand> [subcommand options]
```

The `[global options]` apply to the overarching `git-sim` simulation itself, including:

`--light-mode`: Use a light mode color scheme instead of default dark mode.
`--animate`: Instead of outputting a static image, animate the Git command behavior in a .mp4 video.
`--reverse`: Display commit history in the reverse direction.

Animation-only global options (to be used in conjunction with `--animate`):

`--speed=n`: Set the multiple of animation speed of the output simulation, `n` can be an integer or float, default is 1.
`--low-quality`: Render the animation in low quality to speed up creation time, recommended for non-presentation use.
`--show-intro`: Add an intro sequence with custom logo and title.
`--show-outro`: Add an outro sequence with custom logo and text.
`--title=title`: Custom title to display at the beginning of the animation.
`--logo=logo.png`: The path to a custom logo to use in the animation intro/outro.
`--outro-top-text`: Custom text to display above the logo during the outro.
`--outro-bottom-text`: Custom text to display below the logo during the outro.

The `[subcommand options]` are like regular Git options specific to the specified subcommand (see below for a full list).

The following is a list of Git commands that can be simulated and their corresponding options/flags.

### git log
Usage: `git-sim log`

- Simulated output will show the most recent 5 commits on the active branch by default

![git-sim-log_01-05-23_22-02-39](https://user-images.githubusercontent.com/49353917/210940300-aadd14c6-72ab-4529-a1be-b494ed5dd4c9.jpg)

### git status
Usage: `git-sim status`

- Simulated output will show the state of the working directory, staging area, and untracked files
- Note that simulated output will also show the most recent 5 commits on the active branch

![git-sim-status_01-05-23_22-06-28](https://user-images.githubusercontent.com/49353917/210940685-735665e2-fa12-4043-979c-54c295b13800.jpg)

### git add
Usage: `git-sim add <file 1> <file 2> ... <file n>`

- Specify one or more `<file>` as a *modified* working directory file, or an untracked file
- Simulated output will show files being moved to the staging area
- Note that simulated output will also show the most recent 5 commits on the active branch

![git-sim-add_01-05-23_22-07-40](https://user-images.githubusercontent.com/49353917/210940814-7e8dc318-6116-4e56-b415-bc547401a56a.jpg)

### git restore
Usage: `git-sim restore <file 1> <file 2> ... <file n>`

- Specify one or more `<file>` as a *modified* working directory file, or staged file
- Simulated output will show files being moved back to the working directory or discarded changes
- Note that simulated output will also show the most recent 5 commits on the active branch

![git-sim-restore_01-05-23_22-09-14](https://user-images.githubusercontent.com/49353917/210941009-e6bf7271-ce9b-4e41-9a0b-24cc4b8d3b15.jpg)

### git commit
Usage: `git-sim commit -m "Commit message"`

- Simulated output will show the new commit added to the tip of the active branch
- Specify your commit message after the -m option
- HEAD and the active branch will be moved to the new commit
- Simulated output will show files in the staging area being included in the new commit

![git-sim-commit_01-05-23_22-10-21](https://user-images.githubusercontent.com/49353917/210941149-d83677a1-3ab7-4880-bc0f-871b1f150087.jpg)

### git stash
Usage: `git-sim stash <file>`

- Specify one or more `<file>` as a *modified* working directory file, or staged file
- If no `<file>` is specified, all available working directory and staged files will be included
- Simulated output will show files being moved to the Git stash
- Note that simulated output will also show the most recent 5 commits on the active branch

![git-sim-stash_01-05-23_22-11-18](https://user-images.githubusercontent.com/49353917/210941254-69c80b63-5c06-411a-a36a-1454b2906ee8.jpg)

### git branch
Usage: `git-sim branch <new branch name>`

- Specify `<new branch name>` as the name of the new branch to simulate creation of
- Simulated output will show the newly create branch ref along with most recent 5 commits on the active branch

![git-sim-branch_01-05-23_22-13-17](https://user-images.githubusercontent.com/49353917/210941509-2a42a7a4-2168-4f62-913f-3f6fe74a0684.jpg)

### git tag
Usage: `git-sim tag <new tag name>`

- Specify `<new tag name>` as the name of the new tag to simulate creation of
- Simulated output will show the newly create tag ref along with most recent 5 commits on the active branch

![git-sim-tag_01-05-23_22-14-18](https://user-images.githubusercontent.com/49353917/210941647-79376ff7-2941-42b3-964a-b1d3a404a4fe.jpg)

### git reset
Usage: `git-sim reset <reset-to> [--mixed|--soft|--hard]`

- Specify `<reset-to>` as any commit id, branch name, tag, or other ref to simulate reset to from the current HEAD (default: `HEAD`)
- As with a normal git reset command, default reset mode is `--mixed`, but can be specified using `--soft`, `--hard`, or `--mixed`
- Simulated output will show branch/HEAD resets and resulting state of the working directory, staging area, and whether any file changes would be deleted by running the actual command

![git-sim-reset_01-05-23_22-15-49](https://user-images.githubusercontent.com/49353917/210941835-80f032d2-4f06-4032-8dd0-98c8a2569049.jpg)

### git revert
Usage: `git-sim revert <to-revert>`

- Specify `<to-revert>` as any commit id, branch name, tag, or other ref to simulate revert for
- Simulated output will show the new commit which reverts the changes from `<to-revert>`
- Simulated output will include the next 4 most recent commits on the active branch

![git-sim-revert_01-05-23_22-16-59](https://user-images.githubusercontent.com/49353917/210941979-6db8b55c-2881-41d8-9e2e-6263b1dece13.jpg)

### git merge
Usage: `git-sim merge <branch>`

- Specify `<branch>` as the branch name to merge into the active branch
- Simulated output will depict a fast-forward merge if possible
- Otherwise, a three-way merge will be depicted
- To force a merge commit when a fast-forward is possible, use `--no-ff`

![git-sim-merge_01-05-23_09-44-46](https://user-images.githubusercontent.com/49353917/210942030-c7229488-571a-4943-a1f4-c6e4a0c8ccf3.jpg)

### git rebase
Usage: `git-sim rebase <new-base>`

- Specify `<new-base>` as the branch name to rebase the active branch onto

![git-sim-rebase_01-05-23_09-53-34](https://user-images.githubusercontent.com/49353917/210942598-4ff8d1e6-464d-48f3-afb9-f46f7ec4828c.jpg)

### git cherry-pick
Usage: `git-sim cherry-pick <commit>`

- Specify `<commit>` as a ref (branch name/tag) or commit ID to cherry-pick onto the active branch

![git-sim-cherry-pick_01-05-23_22-23-08](https://user-images.githubusercontent.com/49353917/210942811-fa5155b1-4c6f-4afc-bea2-d39b4cd594aa.jpg)

## Video animation examples
```console
$ git-sim --animate reset HEAD^
```

https://user-images.githubusercontent.com/49353917/210943230-f38d879b-bb0d-4d42-a196-f24efb9e351a.mp4

```console
$ git checkout main
$ git-sim --animate merge dev
```

https://user-images.githubusercontent.com/49353917/210943418-22c2cd11-be96-41bc-b621-7018eebc6bc0.mp4

```console
$ git checkout dev
$ git-sim --animate rebase main
```

https://user-images.githubusercontent.com/49353917/210943815-4b8be2da-18da-4c42-927a-61cf9a22834e.mp4

```console
$ git checkout main
$ git-sim --animate cherry-pick dev
```

https://user-images.githubusercontent.com/49353917/210944001-77bd0130-306b-40a8-ba0b-22e50172802b.mp4

## Basic command examples
Simulate the output of the git log command:

```console
$ cd path/to/git/repo
$ git-sim log
```

Simulate the output of the git status command:

```console
$ git-sim status
```

Simulate adding a file to the Git staging area:

```console
$ git-sim add filename.ext
```

Simulate restoring a file from the Git staging area:

```console
$ git-sim restore filename.ext
```

Simulate creating a new commit based on currently staged changes:

```console
$ git-sim commit -m "Commit message"
```

Simulate stashing all working directory and staged changes:

```console
$ git-sim stash
```

Simulate creating a new Git branch:

```console
$ git-sim branch new-branch-name
```

Simulate creating a new Git tag:

```console
$ git-sim tag new-tag-name
```

Simulate a hard reset of the current branch HEAD to the previous commit:

```console
$ git-sim reset HEAD^ --hard
```

Simulate reverting the changes in an older commit:

```console
$ git-sim revert HEAD~7
```

Simulate merging a branch into the active branch:

```console
$ git-sim merge feature1
```

Simulate rebasing the active branch onto a new base:

```console
$ git-sim rebase main
```

Simulate cherry-picking a commit from another branch onto the active branch:

```console
$ git-sim cherry-pick 0ae641
```

## Command examples with extra options/flags
Use light mode for white background and black text, instead of the default black background with white text:

```console
$ git-sim --light-mode status
```

Animate the simulated output as a .mp4 video file:

```console
$ git-sim --animate add filename.ext
```

Add an intro and outro with custom text and logo (must include `--animate`):

```console
$ git-sim --animate --show-intro --show-outro --outro-top-text="My Git Repo" --outro-bottom-text="Thanks for watching!" --logo=path/to/logo.png status
```

Customize the output image/video directory location:

```console
$ git-sim --media-dir=path/to/output status
```

Optionally, set the environment variable `git_sim_media_dir` to set a global default media directory, to be used if no `--media-dir` is provided. Simulated output images/videos will be placed in this location, in subfolders named with the corresponding repo's name.

```console
$ export git_sim_media_dir=path/to/media/directory
$ git-sim status
```
Note: `--media-dir` takes precedence over the environment variable. If you set the environment and still provide the argument, you'll find the media in the path provided by `--media-dir`.

Generate output video in low quality to speed up rendering time (useful for repeated testing, must include `--animate`):

```console
$ git-sim --animate --low-quality status
```

## Installation
See **Quickstart** section for details on installing manim and other dependencies. Then run:

```console
$ pip3 install git-sim
```

## Learn More
Learn more about this tool on the [git-sim project page](https://initialcommit.com/tools/git-sim).

## Authors
**Jacob Stopak** - on behalf of [Initial Commit](https://initialcommit.com)
