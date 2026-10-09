" git-sim for Vim (8.1 or newer): simulate, pre-flight, and follow the
" repository live, without leaving the editor. A thin client over the git-sim
" command line, which must be installed (pipx install git-sim).
"
"   :GitSim rebase main          simulate a command (opens in the browser)
"   :GitSim                      ...the command on the current line / selection
"   :GitSim preflight reset --hard HEAD~1
"                                the pre-flight report, in a split
"   :GitSim live                 follow this repository live (browser page)
"   :GitSim live stop
"
"   let g:git_sim_executable = 'git-sim'   " where git-sim is
"   let g:git_sim_args = ['--all']         " extra global options for every run
"   let g:git_sim_live_args = ['--no-zones']
"
" Neovim users: the Lua plugin in ../nvim does the same with a floating window.

if exists('g:loaded_git_sim') | finish | endif
let g:loaded_git_sim = 1

let g:git_sim_executable = get(g:, 'git_sim_executable', 'git-sim')
let g:git_sim_args = get(g:, 'git_sim_args', [])
let g:git_sim_live_args = get(g:, 'git_sim_live_args', [])

let s:live_job = v:null

" The git command on the given lines, without a prompt, "git" or "git-sim".
function! s:CommandFromLines(first, last) abort
  let l:text = join(getline(a:first, a:last), ' ')
  let l:text = substitute(l:text, '^\s*[$#>]\+\s*', '', '')
  let l:text = substitute(l:text, '^\s*git-sim\s\+', '', '')
  let l:text = substitute(l:text, '^\s*git\s\+', '', '')
  return trim(l:text)
endfunction

function! s:RepoDir() abort
  let l:dir = expand('%:p:h')
  return isdirectory(l:dir) ? l:dir : getcwd()
endfunction

function! s:Argv(extra) abort
  return [expand(g:git_sim_executable)] + g:git_sim_args + a:extra
endfunction

function! s:Notify(msg) abort
  echomsg 'git-sim: ' . a:msg
endfunction

" :GitSim [preflight | live [stop] | <git command>]. With no git command, the
" one on the current line or the selected lines.
function! s:Run(args, first, last) abort
  let l:command = trim(a:args)
  if l:command ==# ''
    let l:command = s:CommandFromLines(a:first, a:last)
  endif
  let l:words = split(l:command)
  let l:verb = get(l:words, 0, '')
  if l:verb ==# 'live'
    return get(l:words, 1, '') ==# 'stop' ? s:LiveStop() : s:LiveStart(l:words[1:])
  endif
  if l:verb ==# 'preflight'
    let l:rest = l:words[1:]
    if empty(l:rest)
      let l:rest = split(substitute(s:CommandFromLines(a:first, a:last), '^preflight\s*', '', ''))
    endif
    return s:Preflight(l:rest)
  endif
  return s:Simulate(l:words)
endfunction

" Simulate: git-sim opens the graph in the browser; the result is reported here.
function! s:Simulate(words) abort
  if empty(a:words)
    return s:Notify('nothing to simulate: give a command or put the cursor on one')
  endif
  let l:command = join(a:words)
  let l:out = []
  let l:opts = {
        \ 'cwd': s:RepoDir(),
        \ 'out_cb': {ch, msg -> add(l:out, msg)},
        \ 'err_cb': {ch, msg -> add(l:out, msg)},
        \ 'exit_cb': {job, code -> code == 0
        \     ? s:Notify('simulated git ' . l:command)
        \     : s:Notify('git ' . l:command . ' failed: ' . join(filter(copy(l:out), 'v:val !=# ""'), ' | '))},
        \ }
  if job_status(job_start(s:Argv(a:words), l:opts)) ==# 'fail'
    call s:Notify('could not start ' . g:git_sim_executable . ': is git-sim installed?')
  endif
endfunction

" Pre-flight: the report in a scratch split (q closes).
function! s:Preflight(words) abort
  if empty(a:words)
    return s:Notify('nothing to check: give a command or put the cursor on one')
  endif
  let l:command = join(a:words)
  let l:cd = has('win32') ? 'cd /d ' : 'cd '
  let l:lines = systemlist(l:cd . shellescape(s:RepoDir()) . ' && ' . shellescape(expand(g:git_sim_executable))
        \ . ' preflight ' . join(map(copy(a:words), 'shellescape(v:val)')))
  botright new
  setlocal buftype=nofile bufhidden=wipe noswapfile nomodifiable
  setlocal filetype=git-sim
  silent file `='git-sim preflight: git ' . l:command`
  setlocal modifiable
  call setline(1, l:lines)
  setlocal nomodifiable
  execute 'resize ' . min([len(l:lines) + 1, &lines / 2])
  nnoremap <buffer> <silent> q :close<CR>
endfunction

" Live: git-sim serves the page and opens the browser; the job runs until stopped.
function! s:LiveStart(extra) abort
  if s:live_job isnot v:null && job_status(s:live_job) ==# 'run'
    return s:Notify('live mode is already running (:GitSim live stop ends it)')
  endif
  let l:opts = {
        \ 'cwd': s:RepoDir(),
        \ 'err_cb': {ch, msg -> msg =~# '^\s\+http' ? s:Notify('live at ' . trim(msg)) : 0},
        \ 'exit_cb': {job, code -> s:Notify('live mode ended' . (code > 0 ? ' (exit ' . code . ')' : ''))},
        \ }
  let s:live_job = job_start(s:Argv(['live'] + g:git_sim_live_args + a:extra), l:opts)
  if job_status(s:live_job) !=# 'run'
    let s:live_job = v:null
    return s:Notify('could not start git-sim live: is git-sim installed?')
  endif
  call s:Notify('live mode started; the page opens in your browser')
endfunction

function! s:LiveStop() abort
  if s:live_job is v:null || job_status(s:live_job) !=# 'run'
    let s:live_job = v:null
    return s:Notify('live mode is not running')
  endif
  call job_stop(s:live_job)
  let s:live_job = v:null
endfunction

command! -nargs=* -range GitSim call <SID>Run(<q-args>, <line1>, <line2>)
