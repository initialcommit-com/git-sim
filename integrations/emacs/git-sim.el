;;; git-sim.el --- Simulate, pre-flight and follow Git with git-sim  -*- lexical-binding: t; -*-

;; Author: Initial Commit <jacob@initialcommit.io>
;; URL: https://github.com/initialcommit-com/git-sim
;; Version: 0.1.0
;; Package-Requires: ((emacs "27.1"))
;; Keywords: vc, git, tools

;;; Commentary:

;; git-sim in Emacs: simulate a Git command on a before / after graph of the
;; repository, pre-flight a risky one for the facts, or follow the repository
;; live, from the editor.  A thin client over the `git-sim' command line, which
;; must be installed (pipx install git-sim).
;;
;;   M-x git-sim-simulate   RET rebase main      the graph opens in the browser
;;   M-x git-sim-preflight  RET reset --hard HEAD~1
;;                                              the report, in a buffer
;;   M-x git-sim-live                            follow this repository live
;;   M-x git-sim-live-stop
;;
;; With a region active, or on a line that holds a git command, the command is
;; taken from there (a leading "$", "git" or "git-sim" is dropped).
;;
;; Magit users: bind the commands in `magit-mode-map', for example
;;   (with-eval-after-load 'magit
;;     (define-key magit-mode-map (kbd "C-c s") #'git-sim-simulate)
;;     (define-key magit-mode-map (kbd "C-c p") #'git-sim-preflight)
;;     (define-key magit-mode-map (kbd "C-c l") #'git-sim-live))
;; and `git-sim-simulate' on a Magit section offers the commit or branch at
;; point as the default argument.

;;; Code:

(defgroup git-sim nil
  "See what Git is doing to your repository with git-sim."
  :group 'vc
  :prefix "git-sim-")

(defcustom git-sim-executable "git-sim"
  "The git-sim program."
  :type 'string)

(defcustom git-sim-arguments nil
  "Extra global options for every run, for example (\"--all\")."
  :type '(repeat string))

(defcustom git-sim-live-arguments nil
  "Extra options for `git-sim live', for example (\"--no-zones\")."
  :type '(repeat string))

(defvar git-sim--live-process nil "The running `git-sim live' process, if any.")

(defun git-sim--repository ()
  "The directory git-sim runs in: the current file's, else `default-directory'."
  (or (and buffer-file-name (file-name-directory buffer-file-name))
      default-directory))

(defun git-sim--clean (text)
  "TEXT without a leading prompt, git or git-sim."
  (let ((s (string-trim text)))
    (setq s (replace-regexp-in-string "\\`[$#>]+[ \t]*" "" s))
    (setq s (replace-regexp-in-string "\\`git-sim[ \t]+" "" s))
    (setq s (replace-regexp-in-string "\\`git[ \t]+" "" s))
    (string-trim s)))

(defun git-sim--default-command ()
  "A git command found at point: the region, a Magit object, or the line."
  (cond
   ((use-region-p)
    (git-sim--clean (buffer-substring-no-properties (region-beginning) (region-end))))
   ((and (fboundp 'magit-branch-at-point) (magit-branch-at-point))
    (concat "merge " (magit-branch-at-point)))
   ((and (fboundp 'magit-commit-at-point) (magit-commit-at-point))
    (concat "reset " (magit-commit-at-point)))
   ((let ((line (thing-at-point 'line t)))
      (and line (string-match-p "\\(git\\|git-sim\\)[ \t]" line)
           (git-sim--clean line))))
   (t "")))

(defun git-sim--read-command (prompt)
  "Ask for a git command, offering what is at point."
  (let ((default (git-sim--default-command)))
    (git-sim--clean
     (read-string (if (string-empty-p default) prompt (format "%s (%s): " (string-trim-right prompt ": ") default))
                  nil 'git-sim-history default))))

(defun git-sim--words (command)
  (split-string command "[ \t]+" t))

;;;###autoload
(defun git-sim-simulate (command)
  "Simulate the git COMMAND on this repository; the graph opens in the browser."
  (interactive (list (git-sim--read-command "git-sim: ")))
  (when (string-empty-p command)
    (user-error "git-sim: give a command, for example rebase main"))
  (let* ((default-directory (git-sim--repository))
         (buffer (generate-new-buffer " *git-sim*"))
         (process (apply #'start-process "git-sim" buffer git-sim-executable
                         (append git-sim-arguments (git-sim--words command)))))
    (set-process-sentinel
     process
     (lambda (proc _event)
       (when (memq (process-status proc) '(exit signal))
         (let ((code (process-exit-status proc))
               (output (with-current-buffer (process-buffer proc)
                         (string-trim (buffer-string)))))
           (kill-buffer (process-buffer proc))
           (if (zerop code)
               (message "git-sim: simulated git %s" command)
             (message "git-sim: git %s failed: %s" command output))))))
    (message "git-sim: simulating git %s..." command)))

;;;###autoload
(defun git-sim-preflight (command)
  "Show what the git COMMAND would do: risk, facts, losses, how to undo it."
  (interactive (list (git-sim--read-command "git-sim preflight: ")))
  (when (string-empty-p command)
    (user-error "git-sim: give a command, for example reset --hard HEAD~1"))
  (let* ((default-directory (git-sim--repository))
         (buffer (get-buffer-create (format "*git-sim preflight: git %s*" command))))
    (with-current-buffer buffer
      (let ((inhibit-read-only t))
        (erase-buffer)
        (apply #'call-process git-sim-executable nil buffer nil
               "preflight" (git-sim--words command))
        (goto-char (point-min)))
      (special-mode))
    (pop-to-buffer buffer)))

;;;###autoload
(defun git-sim-live ()
  "Follow this repository live: git-sim serves the page and opens the browser."
  (interactive)
  (if (and git-sim--live-process (process-live-p git-sim--live-process))
      (message "git-sim: live mode is already running (git-sim-live-stop ends it)")
    (let ((default-directory (git-sim--repository)))
      (setq git-sim--live-process
            (apply #'start-process "git-sim live" " *git-sim live*" git-sim-executable
                   (append git-sim-arguments (list "live") git-sim-live-arguments)))
      (set-process-filter
       git-sim--live-process
       (lambda (proc text)
         (when (string-match "^[ \t]+\\(https?://[^ \n]+\\)" text)
           (message "git-sim: live at %s" (match-string 1 text)))
         (with-current-buffer (process-buffer proc) (goto-char (point-max)) (insert text))))
      (set-process-sentinel
       git-sim--live-process
       (lambda (proc _event)
         (when (memq (process-status proc) '(exit signal))
           (setq git-sim--live-process nil)
           (message "git-sim: live mode ended"))))
      (message "git-sim: live mode started; the page opens in your browser"))))

;;;###autoload
(defun git-sim-live-stop ()
  "Stop live mode."
  (interactive)
  (if (and git-sim--live-process (process-live-p git-sim--live-process))
      (progn (interrupt-process git-sim--live-process)
             (run-at-time 2 nil (lambda () (when (and git-sim--live-process (process-live-p git-sim--live-process))
                                             (kill-process git-sim--live-process)))))
    (message "git-sim: live mode is not running")))

(provide 'git-sim)
;;; git-sim.el ends here
