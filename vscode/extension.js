// git-sim for VS Code: a thin client over the git-sim command line.
//
// Nothing about Git is reimplemented here. Simulations come from
// `git-sim --img-format html <command>` (a self-contained interactive page,
// shown in an editor tab) and pre-flight checks from `git-sim preflight --json`
// (the same deterministic analysis the MCP server and the agent hook use).
// The extension picks the repository, asks for the command, runs git-sim in
// that repository and shows what comes back.

'use strict';

const vscode = require('vscode');
const cp = require('child_process');
const fs = require('fs');
const path = require('path');

const RECENT_KEY = 'git-sim.recent';
const RECENT_MAX = 20;
const LEARN_URL = 'https://initialcommit.com/learn/git';
const TOOL_URL = 'https://initialcommit.com/tools/git-sim';
const INSTALL_URL = 'https://github.com/initialcommit-com/git-sim#installation';

let output;      // the "git-sim" output channel: every command run, stdout and stderr
let statusItem;  // the status bar entry
let available;   // whether the executable answered --version

// ---------------------------------------------------------------------------
// settings and the executable
// ---------------------------------------------------------------------------
function config() {
  return vscode.workspace.getConfiguration('git-sim');
}

function executable() {
  const exe = (config().get('executable') || 'git-sim').trim();
  return exe || 'git-sim';
}

// Run git-sim with the given arguments in a directory. Resolves with
// {code, stdout, stderr}; rejects only when the process could not start.
function runGitSim(args, cwd, timeoutMs) {
  const exe = executable();
  const env = Object.assign({}, process.env, { git_sim_auto_open: 'false' });
  const useShell = process.platform === 'win32' && /\.(cmd|bat)$/i.test(exe);
  output.appendLine(`$ ${exe} ${args.map(quoteForLog).join(' ')}    (in ${cwd})`);
  return new Promise((resolve, reject) => {
    let stdout = '', stderr = '', done = false;
    const child = cp.spawn(exe, args, { cwd, env, windowsHide: true, shell: useShell });
    const timer = setTimeout(() => {
      if (done) return;
      done = true;
      child.kill();
      reject(new Error(`git-sim did not finish within ${Math.round(timeoutMs / 1000)}s`));
    }, timeoutMs);
    child.stdout.on('data', d => { stdout += d.toString(); });
    child.stderr.on('data', d => { stderr += d.toString(); });
    child.on('error', err => {
      if (done) return;
      done = true; clearTimeout(timer);
      reject(err);
    });
    child.on('close', code => {
      if (done) return;
      done = true; clearTimeout(timer);
      if (stdout.trim()) output.appendLine(stdout.trimEnd());
      if (stderr.trim()) output.appendLine(stderr.trimEnd());
      resolve({ code, stdout, stderr });
    });
  });
}

function quoteForLog(s) {
  return /[\s"']/.test(s) ? JSON.stringify(s) : s;
}

async function checkAvailable() {
  try {
    const r = await runGitSim(['--version'], process.cwd(), 15000);
    available = r.code === 0;
    const version = (r.stdout.match(/\d+\.\d+\.\d+/) || [''])[0];
    statusItem.text = '$(beaker) git-sim';
    statusItem.tooltip = available ? `git-sim ${version}: simulate a Git command` : 'git-sim is installed but did not answer --version';
    statusItem.backgroundColor = undefined;
  } catch (e) {
    available = false;
    statusItem.text = '$(beaker) git-sim: not found';
    statusItem.tooltip = `Could not run "${executable()}". Install git-sim (pipx install git-sim) or set git-sim.executable.`;
    statusItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
  }
  statusItem.show();
}

async function explainMissing(err) {
  const notFound = err && err.code === 'ENOENT';
  const message = notFound
    ? `git-sim was not found ("${executable()}"). Install it with pipx install git-sim, or point the git-sim.executable setting at it.`
    : `git-sim could not be started: ${err.message}`;
  const pick = await vscode.window.showErrorMessage(message, 'Install instructions', 'Open settings');
  if (pick === 'Install instructions') vscode.env.openExternal(vscode.Uri.parse(INSTALL_URL));
  if (pick === 'Open settings') vscode.commands.executeCommand('workbench.action.openSettings', 'git-sim.executable');
}

// ---------------------------------------------------------------------------
// the repository and the command
// ---------------------------------------------------------------------------
function isRepo(dir) {
  try { return fs.existsSync(path.join(dir, '.git')); } catch (e) { return false; }
}

// Walk up from a file to the folder holding .git (a file inside a repo).
function repoRootOf(file) {
  let dir = path.dirname(file);
  for (let i = 0; i < 40; i++) {
    if (isRepo(dir)) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
  return null;
}

async function pickRepo() {
  const folders = (vscode.workspace.workspaceFolders || []).map(f => f.uri.fsPath);
  const editor = vscode.window.activeTextEditor;
  if (editor && editor.document.uri.scheme === 'file') {
    const root = repoRootOf(editor.document.uri.fsPath);
    if (root) return root;
  }
  const repos = folders.filter(isRepo);
  if (repos.length === 1) return repos[0];
  if (repos.length > 1) {
    const pick = await vscode.window.showQuickPick(
      repos.map(r => ({ label: path.basename(r), description: r, root: r })),
      { placeHolder: 'Which repository?' });
    return pick ? pick.root : null;
  }
  if (folders.length === 1) return folders[0];  // let git-sim say it is not a repository
  vscode.window.showErrorMessage('Open a folder with a Git repository first.');
  return null;
}

function cleanCommand(text) {
  let s = (text || '').trim().replace(/\r?\n/g, ' ');
  s = s.replace(/^\$\s*/, '');             // a copied prompt
  s = s.replace(/^git-sim\s+/, '').replace(/^git\s+/, '');
  return s.trim();
}

// The box opens with "git-sim " already typed and the cursor after it, so the
// user finishes the command the way they would in a terminal. A previous
// command (a selection, a recent one) is filled in and selected, so typing
// replaces it while the prefix stays.
const PREFIX = 'git-sim ';

async function askCommand(prefill, verb) {
  const rest = cleanCommand(prefill || '');
  const value = PREFIX + rest;
  const text = await vscode.window.showInputBox({
    title: `git-sim: ${verb} a Git command`,
    prompt: 'Finish the command as you would in a terminal, for example: git-sim reset --hard HEAD~1',
    value,
    valueSelection: [PREFIX.length, value.length],
    ignoreFocusOut: true,
    validateInput: v => cleanCommand(v) ? null : 'Add the git command to run, for example: rebase main'
  });
  return text === undefined ? null : cleanCommand(text);
}

// Split a command line into words, keeping quoted strings together.
function words(command) {
  const out = [];
  let cur = '', q = null;
  for (const ch of command) {
    if (q) { if (ch === q) q = null; else cur += ch; }
    else if (ch === '"' || ch === "'") q = ch;
    else if (/\s/.test(ch)) { if (cur) { out.push(cur); cur = ''; } }
    else cur += ch;
  }
  if (cur) out.push(cur);
  return out;
}

function selectedText() {
  const editor = vscode.window.activeTextEditor;
  if (editor && !editor.selection.isEmpty) return editor.document.getText(editor.selection);
  const terminal = vscode.window.activeTerminal;
  if (terminal && typeof terminal.selection === 'string' && terminal.selection.trim()) return terminal.selection;
  return '';
}

function rememberRecent(context, command) {
  const recent = (context.globalState.get(RECENT_KEY) || []).filter(c => c !== command);
  recent.unshift(command);
  context.globalState.update(RECENT_KEY, recent.slice(0, RECENT_MAX));
}

function lightMode() {
  if (!config().get('followEditorTheme')) return false;
  const kind = vscode.window.activeColorTheme.kind;
  return kind === vscode.ColorThemeKind.Light || kind === vscode.ColorThemeKind.HighContrastLight;
}

function timeoutMs() {
  return Math.max(5, Number(config().get('timeoutSeconds')) || 90) * 1000;
}

// git-sim reports refusals on stdout as "git-sim error: ..." and exits.
function gitSimError(result) {
  const m = (result.stdout + '\n' + result.stderr).match(/git-sim error:\s*(.+)/);
  if (m) return m[1].trim();
  if (result.code !== 0) {
    const tail = (result.stderr || result.stdout).trim().split(/\r?\n/).slice(-3).join(' ');
    return tail || `git-sim exited with code ${result.code}`;
  }
  return null;
}

// ---------------------------------------------------------------------------
// simulate: the interactive page in an editor tab
// ---------------------------------------------------------------------------
async function simulate(context, command, repo) {
  const args = [...(config().get('extraArgs') || []), '--img-format', 'html', '--output-only-path'];
  if (lightMode()) args.push('--light-mode');
  args.push(...words(command));
  let result;
  try {
    result = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `git-sim: simulating git ${command}` },
      () => runGitSim(args, repo, timeoutMs()));
  } catch (e) {
    if (e.code === 'ENOENT') return explainMissing(e);
    return vscode.window.showErrorMessage(`git-sim: ${e.message}`);
  }
  const err = gitSimError(result);
  if (err) return vscode.window.showErrorMessage(`git-sim: ${err}`);
  const lines = result.stdout.trim().split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const page = lines.reverse().find(l => /\.html?$/i.test(l));
  if (!page || !fs.existsSync(page)) {
    output.show(true);
    return vscode.window.showErrorMessage('git-sim finished but no page was written; see the git-sim output channel.');
  }
  rememberRecent(context, command);
  if (config().get('openInBrowser')) {
    return vscode.env.openExternal(vscode.Uri.file(page));
  }
  showPage(context, page, `git ${command}`);
}

// The page is self-contained (inline styles, script and graph). A webview needs a
// content-security policy that allows those inline parts and nothing external.
function showPage(context, page, title) {
  let html = fs.readFileSync(page, 'utf8');
  const csp = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data: https:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; font-src data:;">';
  html = /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, m => m + csp) : csp + html;
  const panel = vscode.window.createWebviewPanel('git-sim.page', `git-sim: ${title}`, vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
  panel.iconPath = vscode.Uri.file(path.join(context.extensionPath, 'media', 'icon.png'));
  panel.webview.html = html;
  return panel;
}

// ---------------------------------------------------------------------------
// pre-flight: the report in an editor tab
// ---------------------------------------------------------------------------
async function preflight(context, command, repo) {
  let result;
  try {
    result = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `git-sim: checking git ${command}` },
      () => runGitSim(['preflight', '--json', '--', ...words(command)], repo, timeoutMs()));
  } catch (e) {
    if (e.code === 'ENOENT') return explainMissing(e);
    return vscode.window.showErrorMessage(`git-sim: ${e.message}`);
  }
  let report;
  try {
    const start = result.stdout.indexOf('{');
    report = JSON.parse(result.stdout.slice(start));
  } catch (e) {
    const err = gitSimError(result) || 'the pre-flight report could not be read';
    output.show(true);
    return vscode.window.showErrorMessage(`git-sim: ${err}`);
  }
  rememberRecent(context, command);
  const panel = vscode.window.createWebviewPanel('git-sim.preflight', `pre-flight: git ${command}`, vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
  panel.iconPath = vscode.Uri.file(path.join(context.extensionPath, 'media', 'icon.png'));
  panel.webview.html = preflightHtml(report, command);
  panel.webview.onDidReceiveMessage(msg => {
    if (msg && msg.type === 'simulate') simulate(context, command, repo);
    if (msg && msg.type === 'copy') vscode.env.clipboard.writeText(`git ${command}`).then(() => vscode.window.setStatusBarMessage('git-sim: command copied', 2000));
    if (msg && msg.type === 'learn') vscode.env.openExternal(vscode.Uri.parse(LEARN_URL));
  });
  const risk = report.risk || 'safe';
  if (risk === 'destructive') {
    const items = (report.would_lose || []).slice(0, 3).join('; ');
    vscode.window.showWarningMessage(`git ${command} is destructive${items ? ': ' + items : ''}`);
  }
}

function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function preflightHtml(r, command) {
  const risk = r.risk || 'safe';
  const label = { safe: 'Safe', caution: 'Caution', destructive: 'Destructive' }[risk] || risk;
  const list = (title, items, cls) => (items && items.length)
    ? `<section><h2>${esc(title)}</h2><ul class="${cls || ''}">${items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></section>` : '';
  const worktree = r.worktree && r.worktree.path ? `<p class="fine">Checked in worktree ${esc(r.worktree.path)}${r.worktree.branch ? ' on ' + esc(r.worktree.branch) : ''}.</p>` : '';
  return `<!DOCTYPE html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline';">
<style>
  :root { color-scheme: light dark; }
  body { font: 13px/1.5 var(--vscode-font-family); color: var(--vscode-foreground); padding: 18px 22px 30px; max-width: 880px; }
  .head { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 6px; }
  .risk { font: 700 11px/1 var(--vscode-editor-font-family); letter-spacing: .12em; text-transform: uppercase; padding: 7px 11px; border-radius: 999px; color: #fff; }
  .risk.safe { background: #10b981; } .risk.caution { background: #d97706; } .risk.destructive { background: #dc2626; }
  h1 { font: 600 18px/1.3 var(--vscode-editor-font-family); margin: 0; }
  .summary { font-size: 15px; margin: 10px 0 18px; }
  h2 { font-size: 12px; letter-spacing: .1em; text-transform: uppercase; opacity: .7; margin: 18px 0 6px; }
  ul { margin: 0; padding-left: 20px; } li { margin: 3px 0; }
  ul.lose li { color: var(--vscode-errorForeground); }
  pre { font: 12px/1.45 var(--vscode-editor-font-family); background: var(--vscode-textCodeBlock-background); padding: 12px 14px; border-radius: 8px; overflow-x: auto; }
  .actions { display: flex; gap: 8px; margin: 22px 0 0; flex-wrap: wrap; }
  button { font: inherit; padding: 7px 14px; border-radius: 4px; border: 1px solid var(--vscode-button-border, transparent); cursor: pointer; background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground); }
  button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
  button:hover { filter: brightness(1.1); }
  .fine { opacity: .7; font-size: 12px; }
  .error { color: var(--vscode-errorForeground); }
</style></head><body>
<div class="head"><span class="risk ${esc(risk)}">${esc(label)}</span><h1>git ${esc(command)}</h1></div>
${r.error ? `<p class="error">${esc(r.error)}</p>` : ''}
${r.summary ? `<p class="summary">${esc(r.summary)}</p>` : ''}
${worktree}
${list('What happens', r.facts)}
${list('What you would lose', r.would_lose, 'lose')}
${list('How to undo it', r.recovery)}
${list('Warnings', r.warnings)}
${r.text_graph ? `<section><h2>Commit graph</h2><pre>${esc(r.text_graph)}</pre></section>` : ''}
<div class="actions">
  <button class="primary" id="simulate">Simulate it</button>
  <button id="copy">Copy the command</button>
  <button id="learn">Learn this command</button>
</div>
<p class="fine">Computed by git-sim from the repository itself; nothing was run or changed.</p>
<script>
  const vscode = acquireVsCodeApi();
  for (const id of ['simulate', 'copy', 'learn']) document.getElementById(id).addEventListener('click', () => vscode.postMessage({ type: id }));
</script>
</body></html>`;
}

// ---------------------------------------------------------------------------
// the inbox: pages the agent hook writes, opened here
// ---------------------------------------------------------------------------
// When Copilot is about to run a risky git command, git-sim's hook renders the
// interactive page and leaves a small JSON note in <git-sim_media>/inbox. The
// extension watches that folder and opens each page in a tab, so the
// simulation appears inside the editor instead of a separate image viewer.
let inboxWatcher = null;

async function startInbox(context) {
  if (inboxWatcher) { try { inboxWatcher.close(); } catch (e) {} inboxWatcher = null; }
  if (!config().get('openHookSimulations')) return;
  let root;
  try {
    const r = await runGitSim(['media-dir'], process.cwd(), 20000);
    root = r.stdout.trim().split(/\r?\n/).pop();
  } catch (e) { return; }  // no git-sim: the status bar already says so
  if (!root) return;
  const inbox = path.join(root, 'inbox');
  try { fs.mkdirSync(inbox, { recursive: true }); } catch (e) { return; }
  const seen = new Set();
  const open = file => {
    if (seen.has(file) || !/\.json$/i.test(file)) return;
    seen.add(file);
    const full = path.join(inbox, file);
    setTimeout(() => {  // the hook renames the file into place; give it a moment
      let note;
      try { note = JSON.parse(fs.readFileSync(full, 'utf8')); } catch (e) { seen.delete(file); return; }
      try { fs.unlinkSync(full); } catch (e) {}
      if (note && note.page && fs.existsSync(note.page)) {
        showPage(context, note.page, note.command || 'simulation');
        output.appendLine(`opened from the agent hook: ${note.command || ''} -> ${note.page}`);
      }
    }, 150);
  };
  // notes left while the editor was not watching: open recent ones, drop the rest
  try {
    for (const file of fs.readdirSync(inbox)) {
      const full = path.join(inbox, file);
      const age = Date.now() - fs.statSync(full).mtimeMs;
      if (age < 60000) open(file); else { try { fs.unlinkSync(full); } catch (e) {} }
    }
  } catch (e) {}
  try {
    inboxWatcher = fs.watch(inbox, (event, file) => { if (file) open(file); });
    inboxWatcher.on('error', () => {});
    context.subscriptions.push({ dispose: () => { try { inboxWatcher && inboxWatcher.close(); } catch (e) {} } });
    output.appendLine(`watching ${inbox} for simulations from the agent hook`);
  } catch (e) {
    output.appendLine(`could not watch ${inbox}: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// commands
// ---------------------------------------------------------------------------
async function commandSimulate(context, prefill) {
  const repo = await pickRepo();
  if (!repo) return;
  const command = await askCommand(prefill, 'Simulate');
  if (!command) return;
  await simulate(context, command, repo);
}

async function commandPreflight(context, prefill) {
  const repo = await pickRepo();
  if (!repo) return;
  const command = await askCommand(prefill, 'Pre-flight');
  if (!command) return;
  await preflight(context, command, repo);
}

async function commandRecent(context) {
  const recent = context.globalState.get(RECENT_KEY) || [];
  if (!recent.length) return commandSimulate(context);
  const pick = await vscode.window.showQuickPick(
    recent.map(c => ({ label: `git ${c}`, command: c })).concat([{ label: '$(edit) Type another command...', command: null }]),
    { placeHolder: 'Simulate which command?' });
  if (!pick) return;
  if (pick.command === null) return commandSimulate(context);
  const repo = await pickRepo();
  if (repo) await simulate(context, pick.command, repo);
}

function commandInstallAgents() {
  const terminal = vscode.window.createTerminal({ name: 'git-sim' });
  terminal.show();
  terminal.sendText(`${executable()} install`);
}

function activate(context) {
  output = vscode.window.createOutputChannel('git-sim');
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  statusItem.command = 'git-sim.simulate';
  statusItem.name = 'git-sim';
  context.subscriptions.push(output, statusItem);
  checkAvailable().then(() => { if (available) startInbox(context); });

  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg('git-sim.simulate', () => commandSimulate(context, selectedText()));
  reg('git-sim.preflight', () => commandPreflight(context, selectedText()));
  reg('git-sim.simulateRecent', () => commandRecent(context));
  reg('git-sim.showLog', async () => { const repo = await pickRepo(); if (repo) await simulate(context, 'log', repo); });
  reg('git-sim.simulateSelection', () => commandSimulate(context, selectedText()));
  reg('git-sim.preflightSelection', () => commandPreflight(context, selectedText()));
  reg('git-sim.installAgents', commandInstallAgents);
  reg('git-sim.openLearn', () => vscode.env.openExternal(vscode.Uri.parse(LEARN_URL)));

  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(e => {
    if (e.affectsConfiguration('git-sim.executable')) checkAvailable().then(() => { if (available) startInbox(context); });
    else if (e.affectsConfiguration('git-sim.openHookSimulations')) startInbox(context);
  }));
}

function deactivate() {}

module.exports = { activate, deactivate, _internal: { words, cleanCommand, gitSimError } };
