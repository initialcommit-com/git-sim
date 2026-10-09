# git-sim for Emacs

Simulate a Git command, check whether a risky one is safe, or watch your repo live, without leaving Emacs. Works in Emacs 27.1 and newer.

```
M-x git-sim-simulate   RET rebase main          opens the graph in your browser
M-x git-sim-preflight  RET reset --hard HEAD~1  shows the pre-flight report in a buffer (q closes it)
M-x git-sim-live                                watches this repo live in your browser
M-x git-sim-live-stop                           stops live mode
```

If you have a region selected, or the cursor is on a line with a Git command in it (like a README or a script), that command is offered as the default. A leading `$`, `git`, or `git-sim` is dropped. In a Magit buffer, the branch or commit at point is offered instead, as `merge <branch>` or `reset <commit>`.

Commands run in the directory of the current file, so open any file in the repo you want to simulate.

## Installation

**1. Install git-sim**

```console
$ pipx install git-sim
```

Or `pip install git-sim`, or `uv tool install git-sim`. git-sim needs Python 3.10 to 3.14 and Git. Some minimal Linux systems also need a few graphics libraries, see [Requirements](https://github.com/initialcommit-com/git-sim#requirements). Check that it worked:

```console
$ git-sim --version
```

**2. Install git-sim.el**

On Emacs 29 or newer, run this once with `M-:` (or put it in your init file):

```elisp
(package-vc-install
 '(git-sim :url "https://github.com/initialcommit-com/git-sim"
           :lisp-dir "integrations/emacs"))
```

On any version, you can download the file instead:

```console
$ mkdir -p ~/.emacs.d/lisp
$ curl -o ~/.emacs.d/lisp/git-sim.el https://raw.githubusercontent.com/initialcommit-com/git-sim/main/integrations/emacs/git-sim.el
```

Then add this to your init file:

```elisp
(add-to-list 'load-path "~/.emacs.d/lisp")
(require 'git-sim)
```

**3. Add key bindings (optional)**

```elisp
(global-set-key (kbd "C-c g s") #'git-sim-simulate)
(global-set-key (kbd "C-c g p") #'git-sim-preflight)
(global-set-key (kbd "C-c g l") #'git-sim-live)

(with-eval-after-load 'magit
  (define-key magit-mode-map (kbd "C-c s") #'git-sim-simulate)
  (define-key magit-mode-map (kbd "C-c p") #'git-sim-preflight)
  (define-key magit-mode-map (kbd "C-c l") #'git-sim-live))
```

## Settings

Set these with `M-x customize-group RET git-sim` or `setq`:

- `git-sim-executable`: where git-sim is, if it's not on your `PATH` (default `"git-sim"`)
- `git-sim-arguments`: extra options for every simulation and for live mode, for example `'("--all")`
- `git-sim-live-arguments`: extra options for live mode only, for example `'("--no-zones")`

## Good to know

- Simulations open in the [git-sim viewer](https://initialcommit.com/tools/git-sim/viewer) by default. Your repo's data stays in the link's `#fragment`, which your browser never sends to the site. To open the saved page offline instead, add `"--open-in" "local"` to `git-sim-arguments`.
- Pre-flight waits for git-sim to finish before showing the report, which usually takes a second or two.
- The command is split on spaces, so a quoted message like `commit -m "two words"` won't come through as one argument.
- git-sim never changes your repo. It only reads it.
