# git-sim for Vim

Simulate a Git command, check whether a risky one is safe, or watch your repo live, without leaving Vim. Works in Vim 8.1 and newer. For Neovim, use the [Neovim plugin](../nvim) instead.

Everything goes through one command, `:GitSim`, which works like the `git-sim` command line:

```
:GitSim rebase main                    opens the graph in your browser
:GitSim                                simulates the Git command on the current line or selection
:GitSim preflight reset --hard HEAD~1  shows the pre-flight report in a split (q closes it)
:GitSim preflight                      pre-flights the command on the current line or selection
:GitSim live                           watches this repo live in your browser
:GitSim live stop                      stops live mode
```

With no command, `:GitSim` takes it from the line under the cursor, or from the lines you've selected (`:'<,'>GitSim`), so you can run a command straight from a README or a script. A leading `$`, `git`, or `git-sim` is dropped, so a line like `$ git-sim preflight reset --hard HEAD~1` works too.

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

**2. Install the plugin**

With [vim-plug](https://github.com/junegunn/vim-plug), add this to your `.vimrc` and run `:PlugInstall`:

```vim
Plug 'initialcommit-com/git-sim', { 'rtp': 'integrations/vim' }
```

Without a plugin manager, download the plugin into its own folder in Vim's package directory, which Vim loads every time it starts:

```console
$ mkdir -p ~/.vim/pack/git-sim/start/git-sim/plugin
$ curl -o ~/.vim/pack/git-sim/start/git-sim/plugin/git-sim.vim https://raw.githubusercontent.com/initialcommit-com/git-sim/main/integrations/vim/plugin/git-sim.vim
```

On Windows, use `~/vimfiles` instead of `~/.vim`. To update the plugin later, run the `curl` command again. To remove it, delete `~/.vim/pack/git-sim`.

**3. Add mappings (optional)**

```vim
nnoremap <leader>gs :GitSim<CR>
vnoremap <leader>gs :GitSim<CR>
nnoremap <leader>gp :GitSim preflight<CR>
vnoremap <leader>gp :GitSim preflight<CR>
nnoremap <leader>gl :GitSim live<CR>
```

## Settings

Put these in your `.vimrc`:

```vim
let g:git_sim_executable = 'git-sim'      " where git-sim is, if it's not on your PATH
let g:git_sim_args = ['--all']            " extra options for every simulation and for live mode
let g:git_sim_live_args = ['--no-zones']  " extra options for live mode only
```

You can also pass live mode options directly, like `:GitSim live --no-zones`.

## Good to know

- Simulations open in the [git-sim viewer](https://initialcommit.com/tools/git-sim/viewer) by default. Your repo's data stays in the link's `#fragment`, which your browser never sends to the site. To open the saved page offline instead, set `let g:git_sim_args = ['--open-in', 'local']`.
- The command is split on spaces, so a quoted message like `commit -m "two words"` won't come through as one argument.
- git-sim never changes your repo. It only reads it.
