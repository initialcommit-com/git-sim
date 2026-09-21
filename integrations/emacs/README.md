# git-sim.el

git-sim in Emacs 27.1 or newer: simulate a Git command on a before / after
graph of the repository, pre-flight a risky one, or follow the repository
live. A thin client over the `git-sim` command line, which must be installed
(`pipx install git-sim`).

```
M-x git-sim-simulate   RET rebase main          the graph opens in the browser
M-x git-sim-preflight  RET reset --hard HEAD~1  the report, in a buffer (q closes)
M-x git-sim-live                                follow this repository live
M-x git-sim-live-stop
```

With a region active, or on a line holding a git command, the command is
offered as the default (a leading `$`, `git` or `git-sim` is dropped). In a
Magit buffer, the branch or commit at point is offered: `merge <branch>`,
`reset <commit>`.

## Install

Copy `git-sim.el` somewhere on your `load-path`, or with `use-package` once
this folder is its own repository (`initialcommit-com/git-sim.el`):

```elisp
(use-package git-sim
  :vc (:url "https://github.com/initialcommit-com/git-sim.el")   ; Emacs 30
  :custom
  (git-sim-arguments '("--all"))
  :bind (("C-c g s" . git-sim-simulate)
         ("C-c g p" . git-sim-preflight)
         ("C-c g l" . git-sim-live)))

(with-eval-after-load 'magit
  (define-key magit-mode-map (kbd "C-c s") #'git-sim-simulate)
  (define-key magit-mode-map (kbd "C-c p") #'git-sim-preflight))
```

Customize `git-sim-executable`, `git-sim-arguments` and `git-sim-live-arguments`.
