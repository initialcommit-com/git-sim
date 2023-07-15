# Contributing to Git-Sim

Thanks for checking out Git-Sim and for your interest in contributing! I hope
that we can work together to build an incredible tool for developers to
visualize Git commands.

## Reporting bugs

To report a bug you found, please open a [GitHub issue](https://github.com/initialcommit-com/git-sim/issues/new)
and describe the error or problem in detail. Please check [existing issues](https://github.com/initialcommit-com/git-sim/issues)
to make sure it hasn't already been reported.

When submitting a new issue, it helps to include:

1) The steps you took that lead to the issue
2) Any error message(s) that you received
3) A description of any unexpected behavior
4) The version of Git-Sim you're running
5) The version of Python you're running and whether it's system-level or in a virtual environment
6) The operating system and version you're running

## Suggesting enhancements or new features

If you've got a cool idea for a feature that you'd like to see implemented in
Git-Sim, we'd love to hear about it!

To suggest an enhancement or new feature, please open a [GitHub issue](https://github.com/initialcommit-com/git-sim/issues/new)
and describe your proposed idea in detail. Please include why you think this
idea would be beneficial to the Git-Sim user base.

## Your first code contribution

Note: Git-Sim is a new project so these steps are not fully optimized yet, but
they should get you going.

To start contributing code to Git-Sim, you'll need to perform the following
steps:

1) Install [manim and manim dependencies for your OS](https://www.manim.community/)
2) [Fork the Git-Sim codebase](https://github.com/initialcommit-com/git-sim/fork)
so that you have a copy on GitHub that you can clone and work with
3) Clone the codebase down to your local machine
4) Checkout and commit new work to the `dev` branch
5) If you previously installed Git-Sim normally using pip, uninstall it first using:

```console
$ pip uninstall git-sim
```

6) To run the code locally from source, install the development package by running:

```console
$ cd path/to/git-sim
$ python -m pip install -e .[dev]
```

> Explanation: `python -m pip` uses the `pip` module of the currently active python interpreter.
>
> `install -e .[dev]` is the command that `pip` executes, where
>
> `-e` means to make it an [editable install](https://setuptools.pypa.io/en/latest/userguide/development_mode.html),
>
> the dot `.` refers to the current directory,
>
> and `[dev]` tells pip to install the "`dev`" [Extras](https://packaging.python.org/en/latest/tutorials/installing-packages/#installing-extras) (which are defined in the `project.optional-dependencies` section of [`pyproject.toml`](./pyproject.toml)).

This will install sources from your cloned repo such that you can edit the source and the changes are reflected instantly.

If you already have the dependencies, you can ignore those using the `--no-deps` flag:

```console
$ python -m pip install --no-deps -e .
```

7) You can run your local Git-Sim commands from within other local repos like this:

```console
$ git-sim [global options] <subcommand> [subcommand options]
```

For example, you can simulate the `git add` command locally like this:

```console
$ cd path/to/any/local/git/repo
$ git-sim --animate add newfile.txt
```

8) After pushing your code changes up to your fork, [submit a pull request to the `dev` branch](https://github.com/initialcommit-com/git-sim/compare) for me
to review your code, provide feedback, and merge it into the codebase!

## Code style guide

Since Git-Sim is a new project, we don't have an official code style set in
stone. For now just try and make your new code fit in with the existing style
you find in the codebase, and we'll update this section later if that changes.

## Code Formatting

This project uses the [`black`](https://github.com/psf/black) code formatter to keep all code in a constistent format.

Please install it in your development environment and run `black path/to/changed/files` before committing any changes.

## Commit conventions

We have a few simple rules for Git-Sim commit messages:

1) Write commit messages in the [imperative mood](https://initialcommit.com/blog/Git-Commit-Message-Imperative-Mood)
2) Add a signoff trailer to your commits by using the `-s` flag when you make
your commits, like this:

```
$ git commit -sm "Fixed xyz..."
```

## Questions

If you have any additional questions about contributing to Git-Sim, feel free
to [send me an email at jacob@initialcommit.io](mailto:jacob@initialcommit.io).
