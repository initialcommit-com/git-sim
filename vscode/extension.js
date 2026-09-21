// git-sim for VS Code: a thin client over the git-sim command line.
//
// Nothing about Git is reimplemented here. Simulations come from
// `git-sim --img-format html <command>` (a self-contained interactive page,
// shown in an editor tab), pre-flight checks from `git-sim preflight --json`
// (the same deterministic analysis the MCP server and the agent hook use), and
// the live graph from `git-sim live --json` (one JSON line per change in the
// repository, fed to git-sim's own live page in a webview). The extension
// picks the repository, asks for the command, runs git-sim in that repository
// and shows what comes back.

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
  // The walkthrough's first step completes on this context key.
  vscode.commands.executeCommand('setContext', 'git-sim.available', !!available);
}

// Open a terminal with the install command typed, for the walkthrough and
// the "not found" message: pipx when it is there, pip otherwise.
function commandInstallGitSim() {
  const terminal = vscode.window.createTerminal({ name: 'git-sim' });
  terminal.show();
  terminal.sendText('pipx install git-sim || pip install git-sim', false);
  vscode.window.showInformationMessage('Press Enter in the terminal to install git-sim. The status bar will show "git-sim" once it is found.');
  // look again once the user has had a chance to run it
  const timer = setInterval(() => { checkAvailable().then(() => { if (available) { clearInterval(timer); startInbox(currentContext); } }); }, 5000);
  setTimeout(() => clearInterval(timer), 5 * 60 * 1000);
}
let currentContext = null;

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
// live: the repository as it changes, in an editor tab or the sidebar
// ---------------------------------------------------------------------------
// `git-sim live --json` watches a repository and prints one JSON line per
// change, each naming the animated graph it wrote (the drawing before the
// change merged with the one after). A LiveSession owns that process for one
// repository and feeds every webview showing it: the live page git-sim ships
// (`git-sim live --print-page`) runs unchanged inside the webview, receiving
// through postMessage what a browser would get from the command's server.
const liveSessions = new Map();   // "<repo>|<zones>" -> LiveSession
const livePanels = new Map();     // repo -> WebviewPanel
const livePages = new Map();      // "<repo>|<light>" -> page HTML

class LiveSession {
  constructor(repo, zones) {
    this.repo = repo;
    this.zones = zones;
    this.items = [];
    this.svgs = new Map();
    this.views = new Set();
    this.proc = null;
    this.buffer = '';
    this.stopping = false;
  }

  static key(repo, zones) { return `${repo}|${zones ? 1 : 0}`; }

  start() {
    const exe = executable();
    const args = [...(config().get('extraArgs') || []), '-d'];
    if (lightMode()) args.push('--light-mode');
    args.push('live', '--json', this.zones ? '--zones' : '--no-zones',
      '--interval', String(Math.max(0.2, Number(config().get('liveInterval')) || 1)), '-C', this.repo);
    const env = Object.assign({}, process.env, { git_sim_auto_open: 'false' });
    const useShell = process.platform === 'win32' && /\.(cmd|bat)$/i.test(exe);
    output.appendLine(`$ ${exe} ${args.map(quoteForLog).join(' ')}    (live, in ${this.repo})`);
    try {
      this.proc = cp.spawn(exe, args, { cwd: this.repo, env, windowsHide: true, shell: useShell, stdio: ['pipe', 'pipe', 'pipe'] });
    } catch (e) {
      this.broadcast({ type: 'status', connected: false, text: `git-sim could not start: ${e.message}` });
      return;
    }
    this.proc.stdout.setEncoding('utf8');
    this.proc.stdout.on('data', chunk => {
      this.buffer += chunk;
      let nl;
      while ((nl = this.buffer.indexOf('\n')) >= 0) {
        const line = this.buffer.slice(0, nl).trim();
        this.buffer = this.buffer.slice(nl + 1);
        if (line) this.handleLine(line);
      }
    });
    this.proc.stderr.on('data', d => { const s = String(d).trimEnd(); if (s) output.appendLine(s); });
    this.proc.on('error', err => {
      this.proc = null;
      this.broadcast({ type: 'status', connected: false, text: `git-sim could not start: ${err.message}` });
      if (err.code === 'ENOENT') explainMissing(err);
    });
    this.proc.on('close', code => {
      this.proc = null;
      if (!this.stopping) this.broadcast({ type: 'status', connected: false, text: `git-sim live stopped (exit ${code})` });
    });
  }

  handleLine(line) {
    let msg;
    try { msg = JSON.parse(line); } catch (e) { output.appendLine(line); return; }
    if (msg.event === 'start') { this.dir = msg.dir; output.appendLine(`live: watching ${msg.repo}, changes saved under ${msg.dir}`); return; }
    if (msg.event !== 'snapshot') return;
    let svg;
    try { svg = fs.readFileSync(msg.svg, 'utf8'); } catch (e) { output.appendLine(`live: could not read ${msg.svg}`); return; }
    const item = { index: msg.index, label: msg.label, detail: msg.detail, time: msg.time, page: msg.page };
    this.items.push(item);
    this.svgs.set(item.index, svg);
    while (this.items.length > 300) { const dropped = this.items.shift(); this.svgs.delete(dropped.index); }
    this.broadcast({ type: 'snapshot', item, svg });
  }

  attach(webview) {
    this.views.add(webview);
    webview.postMessage({ type: 'history', items: this.items.map(i => Object.assign({}, i, { svg: this.svgs.get(i.index) })) }).then(undefined, () => {});
    if (!this.proc && !this.stopping) this.start();
  }

  detach(webview) {
    this.views.delete(webview);
    if (!this.views.size) this.stop();
  }

  clear(keep) {
    this.items = this.items.filter(i => i.index >= keep);
    Array.from(this.svgs.keys()).forEach(k => { if (k < keep) this.svgs.delete(k); });
  }

  broadcast(msg) {
    this.views.forEach(v => v.postMessage(msg).then(undefined, () => {}));
  }

  stop() {
    this.stopping = true;
    liveSessions.delete(LiveSession.key(this.repo, this.zones));
    const proc = this.proc;
    if (!proc) return;
    this.proc = null;
    try { proc.stdin.end(); } catch (e) {}  // git-sim live exits when its stdin closes
    setTimeout(() => {
      try {
        if (process.platform === 'win32') cp.spawn('taskkill', ['/pid', String(proc.pid), '/T', '/F'], { windowsHide: true });
        else proc.kill();
      } catch (e) {}
    }, 1500);
  }
}

function liveSession(repo, zones) {
  const key = LiveSession.key(repo, zones);
  let session = liveSessions.get(key);
  if (!session) {
    session = new LiveSession(repo, zones);
    liveSessions.set(key, session);
    session.start();
  }
  return session;
}

function liveZones(where) {
  const mode = config().get('liveZones') || 'tab';
  return mode === 'always' || (mode === 'tab' && where === 'tab');
}

// The live page, from git-sim itself, with the webview's content-security policy.
async function livePageHtml(repo) {
  const key = `${repo}|${lightMode() ? 1 : 0}`;
  if (livePages.has(key)) return livePages.get(key);
  const args = [];
  if (lightMode()) args.push('--light-mode');
  args.push('live', '--print-page', '-C', repo);
  const r = await runGitSim(args, repo, timeoutMs());
  if (r.code !== 0 || !/<html/i.test(r.stdout)) throw new Error(gitSimError(r) || 'git-sim did not print the live page (live mode needs a git-sim that has the "live" command; update it with pipx upgrade git-sim)');
  const csp = '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data: https:; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; font-src data:;">';
  const html = r.stdout.replace(/<head[^>]*>/i, m => m + csp);
  livePages.set(key, html);
  return html;
}

// Save bytes the page hands over (a recorded video, a session file): a
// webview cannot download, so the page posts them and the editor asks where.
async function saveFromPage(name, data, mime) {
  const filters = /\.mp4$/i.test(name) ? { 'MP4 video': ['mp4'] } : /\.webm$/i.test(name) ? { 'WebM video': ['webm'] } : { 'HTML page': ['html'] };
  const folders = vscode.workspace.workspaceFolders || [];
  const target = await vscode.window.showSaveDialog({
    defaultUri: vscode.Uri.file(path.join(folders.length ? path.dirname(folders[0].uri.fsPath) : require('os').homedir(), name)),
    filters, saveLabel: 'Save'
  });
  if (!target) return;
  const bytes = Buffer.isBuffer(data) ? data : Buffer.from(data, 'base64');
  await vscode.workspace.fs.writeFile(target, bytes);
  const pick = await vscode.window.showInformationMessage(`Saved ${path.basename(target.fsPath)} (${(bytes.length / 1024).toFixed(0)} KB)`, 'Show in folder');
  if (pick === 'Show in folder') vscode.commands.executeCommand('revealFileInOS', target);
}

// The whole session as one page: git-sim keeps session.html current in the
// session folder, so saving is a copy.
async function saveSessionOf(session) {
  const file = session.dir && path.join(session.dir, 'session.html');
  if (!file || !fs.existsSync(file)) { vscode.window.showWarningMessage('git-sim has not written this session yet; make a change first.'); return; }
  const stamp = path.basename(session.dir);
  await saveFromPage(`${path.basename(session.repo)}-live-${stamp}.html`, fs.readFileSync(file), 'text/html');
}

function wireLiveWebview(webview, repo, zones, onDispose) {
  const session = liveSession(repo, zones);
  const sub = webview.onDidReceiveMessage(msg => {
    if (!msg || !msg.type) return;
    if (msg.type === 'ready') session.attach(webview);
    else if (msg.type === 'clear') session.clear(Number(msg.keep) || 0);
    else if (msg.type === 'openPage' && msg.page) vscode.env.openExternal(vscode.Uri.file(msg.page));
    else if (msg.type === 'saveSession') saveSessionOf(session).catch(e => vscode.window.showErrorMessage(`git-sim: ${e.message}`));
    else if (msg.type === 'saveFile' && msg.name && msg.data) saveFromPage(msg.name, msg.data, msg.mime).catch(e => vscode.window.showErrorMessage(`git-sim: ${e.message}`));
  });
  onDispose(() => { sub.dispose(); session.detach(webview); });
}

// Recorded sessions: git-sim lists them (`live --sessions --json`), each a
// self-contained page that the ordinary page viewer shows.
async function commandLiveSessions(context) {
  const repo = await pickRepo();
  if (!repo) return;
  let result;
  try { result = await runGitSim(['live', '--sessions', '--json', '-C', repo], repo, timeoutMs()); }
  catch (e) { return e.code === 'ENOENT' ? explainMissing(e) : vscode.window.showErrorMessage(`git-sim: ${e.message}`); }
  const sessions = result.stdout.split(/\r?\n/).map(l => l.trim()).filter(Boolean).map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(s => s && s.event === 'session');
  if (!sessions.length) return vscode.window.showInformationMessage('No recorded live sessions for this repository yet. Open the live graph and make a change.');
  const pick = await vscode.window.showQuickPick(
    sessions.map(s => ({
      label: `$(pulse) ${new Date(s.started * 1000).toLocaleString()}`,
      description: `${s.changes} change${s.changes === 1 ? '' : 's'}`,
      detail: s.dir, session: s
    })),
    { placeHolder: 'Which recorded session?' });
  if (!pick) return;
  const panel = showPage(context, pick.session.page, `live session ${new Date(pick.session.started * 1000).toLocaleDateString()}`);
  panel.webview.onDidReceiveMessage(msg => {
    if (msg && msg.type === 'saveFile' && msg.name && msg.data) saveFromPage(msg.name, msg.data, msg.mime).catch(e => vscode.window.showErrorMessage(`git-sim: ${e.message}`));
  });
}

function noteHtml(text) {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline';"><style>body{font:13px/1.5 var(--vscode-font-family);color:var(--vscode-descriptionForeground);padding:14px}</style></head><body>${esc(text)}</body></html>`;
}

async function openLivePanel(context, repo) {
  const existing = livePanels.get(repo);
  if (existing) { existing.reveal(); return existing; }
  let html;
  try { html = await livePageHtml(repo); } catch (e) {
    if (e.code === 'ENOENT') return explainMissing(e);
    return vscode.window.showErrorMessage(`git-sim: ${e.message}`);
  }
  const panel = vscode.window.createWebviewPanel('git-sim.live', `git-sim live: ${path.basename(repo)}`, vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true, localResourceRoots: [] });
  panel.iconPath = vscode.Uri.file(path.join(context.extensionPath, 'media', 'icon.png'));
  panel.webview.html = html;
  livePanels.set(repo, panel);
  wireLiveWebview(panel.webview, repo, liveZones('tab'), fn => panel.onDidDispose(() => { livePanels.delete(repo); fn(); }));
  return panel;
}

// The repository the sidebar view follows: the active file's, else the first
// workspace folder that is one. Chosen without asking, since the view opens on
// its own when the window is restored.
function quietRepo() {
  const editor = vscode.window.activeTextEditor;
  if (editor && editor.document.uri.scheme === 'file') {
    const root = repoRootOf(editor.document.uri.fsPath);
    if (root) return root;
  }
  const folders = (vscode.workspace.workspaceFolders || []).map(f => f.uri.fsPath);
  return folders.find(isRepo) || null;
}

class LiveViewProvider {
  constructor(context) { this.context = context; }

  async resolveWebviewView(view) {
    view.webview.options = { enableScripts: true, localResourceRoots: [] };
    const repo = quietRepo();
    if (!repo) {
      view.webview.html = noteHtml('Open a folder with a Git repository, and git-sim will follow it here as it changes.');
      return;
    }
    let html;
    try { html = await livePageHtml(repo); } catch (e) {
      view.webview.html = noteHtml(`git-sim could not draw the live graph: ${e.message}`);
      return;
    }
    view.title = `Live graph: ${path.basename(repo)}`;
    view.webview.html = html;
    wireLiveWebview(view.webview, repo, liveZones('sidebar'), fn => view.onDidDispose(fn));
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
  currentContext = context;
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
  reg('git-sim.installGitSim', commandInstallGitSim);
  reg('git-sim.openLearn', () => vscode.env.openExternal(vscode.Uri.parse(LEARN_URL)));
  reg('git-sim.live', async () => { const repo = await pickRepo(); if (repo) await openLivePanel(context, repo); });
  reg('git-sim.liveSidebar', () => vscode.commands.executeCommand('git-sim.liveView.focus'));
  reg('git-sim.liveSessions', () => commandLiveSessions(context));
  context.subscriptions.push(vscode.window.registerWebviewViewProvider('git-sim.liveView', new LiveViewProvider(context),
    { webviewOptions: { retainContextWhenHidden: true } }));

  context.subscriptions.push(vscode.workspace.onDidChangeConfiguration(e => {
    if (e.affectsConfiguration('git-sim.executable')) { livePages.clear(); checkAvailable().then(() => { if (available) startInbox(context); }); }
    else if (e.affectsConfiguration('git-sim.openHookSimulations')) startInbox(context);
  }));
  context.subscriptions.push(vscode.window.onDidChangeActiveColorTheme(() => livePages.clear()));
  context.subscriptions.push({ dispose: () => liveSessions.forEach(s => s.stop()) });
}

function deactivate() {
  liveSessions.forEach(s => s.stop());
}

module.exports = { activate, deactivate, _internal: { words, cleanCommand, gitSimError, LiveSession } };
