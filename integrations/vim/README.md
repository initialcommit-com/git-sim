# git-sim.vim

git-sim in Vim 8.1 or newer: simulate a Git command, pre-flight it, or follow
the repository live, from the editor. A thin client over the `git-sim`
command line, which must be installed (`pipx install git-sim`). Neovim users
want the Lua plugin in [../nvim](../nvim) instead (this one loads there too,
but the Lua one has the floating window).

```
:GitSim rebase main             simulate; the graph opens in the browser
:GitSim                         simulate the command on the current line or selection
:GitSimPreflight reset --hard HEAD~1
                                the pre-flight report in a split (q closes)
:GitSimLive                     follow this repository live (browser page)
:GitSimLiveStop
```

`:GitSim` with no arguments takes the command from the current line or the
visual selection (`:'<,'>GitSim`), dropping a leading `$`, `git` or `git-sim`.

## Install

Copy `plugin/git-sim.vim` into `~/.vim/plugin/`, or with vim-plug once this
folder is its own repository (`initialcommit-com/git-sim.vim`):

```vim
Plug 'initialcommit-com/git-sim.vim'
```

Options, in `.vimrc`:

```vim
let g:git_sim_executable = 'git-sim'     " where git-sim is, if not on the PATH
let g:git_sim_args = ['--all']           " extra global options for every run
let g:git_sim_live_args = ['--no-zones']
nnoremap <leader>gs :GitSim<CR>
vnoremap <leader>gs :GitSim<CR>
nnoremap <leader>gp :GitSimPreflight<CR>
nnoremap <leader>gl :GitSimLive<CR>
```
