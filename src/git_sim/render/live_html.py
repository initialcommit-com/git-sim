"""The live page: the interactive viewer plus a strip of the changes seen so
far, fed by ``git-sim live``.

One page, three hosts. Served by the command's own local server it talks to
that server with relative URLs (``/history`` for the list so far, ``/svg/<n>``
for a graph, ``/events`` for pushes). Hosted on initialcommit.com it is the
same page with the local server's address in the fragment (``#live=http://
127.0.0.1:PORT&k=KEY``): the graphs still come from the user's machine and the
site only serves the page, as with shared simulations. Inside the VS Code
extension's webview it receives the same data through postMessage instead,
and knows it is there because ``acquireVsCodeApi`` exists. Everything else
(playing each change as it lands, stepping back through earlier ones,
replaying the whole session) is the page's own.

Every request to the local server carries the session key git-sim printed
and put in the page, so a stranger's web page cannot read the repository
graph off localhost. ``export_viewer_assets`` (render/html.py) writes the
strip's markup, stylesheet and script for the website repository, so the
hosted copy is the same code.
"""

import html
import json

from git_sim.render.html import (
    DEFAULT_VIEWER_URL,
    VIEWER_CSS,
    VIEWER_JS,
    header_markup,
)
from git_sim.theme import DARK

LIVE_CSS = """
#live{position:sticky;top:var(--live-top,64px);z-index:2;display:flex;align-items:center;gap:10px;padding:8px 14px;background:var(--bg);border-bottom:1px solid var(--rule);font:12px/1 var(--font);color:var(--muted)}
#liveDot{flex:none;width:9px;height:9px;border-radius:50%;background:var(--muted);box-shadow:0 0 0 0 transparent}
#liveDot.on{background:#22c55e;animation:pulse 1.6s ease-out infinite}
#liveDot.off{background:#ef4444}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.55)}100%{box-shadow:0 0 0 9px rgba(34,197,94,0)}}
#liveStatus{flex:none;font-weight:600;color:var(--text);white-space:nowrap}
#chips{flex:1;display:flex;gap:6px;overflow-x:auto;scrollbar-width:thin;padding:2px 0}
#chips::-webkit-scrollbar{height:6px}
#chips::-webkit-scrollbar-thumb{background:var(--rule);border-radius:999px}
.chip{flex:none;display:inline-flex;align-items:center;gap:6px;max-width:260px;border:1px solid var(--rule);background:var(--panel);color:var(--text);border-radius:999px;padding:6px 10px;font:12px/1 var(--font);cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.chip b{color:var(--muted);font-weight:600}
.chip small{color:var(--muted);font-size:11px}
.chip:hover{border-color:var(--accent)}
.chip.cur{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent) inset}
.chip.fresh{animation:land .9s ease-out}
@keyframes land{0%{background:color-mix(in srgb,var(--accent) 45%,transparent)}100%{background:var(--panel)}}
#live .tools{flex:none;display:flex;gap:6px}
#live .tools button{border:1px solid var(--rule);background:transparent;color:var(--muted);border-radius:999px;padding:6px 10px;font:600 12px/1 var(--font);cursor:pointer}
#live .tools button:hover{color:var(--text);border-color:var(--text)}
#live .tools button.on{color:var(--accent);border-color:var(--accent)}
#live .tools button:disabled{opacity:.45;cursor:default}
#live .tools .ico{display:none;font-size:13px}
#empty{max-width:600px;margin:64px auto;padding:0 18px;text-align:center;color:var(--muted);font:14px/1.6 var(--font)}
#empty b{color:var(--text)}
#empty code{font:13px/1.4 var(--font);color:var(--text);background:var(--panel);border:1px solid var(--rule);border-radius:5px;padding:1px 6px}
#empty a{color:var(--accent)}
#empty .go{display:inline-block;margin-top:14px;padding:9px 16px;border-radius:999px;border:1px solid var(--accent);color:var(--accent);font:700 13px/1 var(--font);text-decoration:none}
/* A still graph (nothing changed in it) needs no scrubber: give its room back
   so the bar fits a sidebar. */
[data-live] #controls.off{display:none}
@media (max-width:820px){#live{padding:6px 10px}#liveStatus{display:none}#live .tools button{padding:6px 8px}}
@media (max-width:560px){#bar{gap:6px}#bar .right{gap:2px}#share{padding:8px 10px}.end{display:none}#scrub{width:min(34vw,520px)}
  #live .tools .txt{display:none}#live .tools .ico{display:inline}#live .tools button{padding:6px 9px}.chip{max-width:180px}}
"""

LIVE_JS = r"""
// git-sim live page. One copy lives in the git-sim package
// (git_sim/render/live_html.py) and is exported to initialcommit.com; edit it there.
(function(){
  const V = window.GitSimViewer;
  const inVscode = typeof acquireVsCodeApi === 'function';
  const host = inVscode ? acquireVsCodeApi() : null;
  const $ = id => document.getElementById(id);
  const dot = $('liveDot'), status = $('liveStatus'), chips = $('chips');
  const replayBtn = $('replay'), followBtn = $('follow'), clearBtn = $('clear');
  const info = (() => { try { return JSON.parse($('git-sim-meta').textContent); } catch (e) { return {}; } })();
  // Where the graphs come from: the fragment names the local git-sim server
  // when this page is hosted (#live=http://127.0.0.1:PORT&k=KEY); served by
  // that server itself the URLs are relative and the key is in the page.
  const frag = new URLSearchParams((location.hash || '').replace(/^#/, ''));
  const base = (frag.get('live') || '').replace(/\/+$/, '');
  const key = frag.get('k') || info.key || '';
  const hosted = !!base;
  const api = path => base + path + (path.includes('?') ? '&' : '?') + 'k=' + encodeURIComponent(key);
  const items = [];            // {index, label, detail, time, page?, svg?}
  const svgs = new Map();      // index -> svg text
  let current = -1, follow = true, replaying = false, connected = false;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const clock = t => { const d = new Date(t * 1000); return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'}); };
  // A failure while drawing is said in the strip rather than lost in a console.
  let lastError = '';
  const complain = text => { lastError = 'error: ' + String(text).slice(0, 160); status.textContent = lastError; dot.className = 'off'; };
  window.addEventListener('error', e => complain(e.message || e.type));
  window.addEventListener('unhandledrejection', e => complain((e.reason && e.reason.message) || e.reason || 'promise rejected'));

  function setStatus(){
    const repo = info.repo ? ' · ' + info.repo : '';
    dot.className = connected ? (follow && !replaying ? 'on' : '') : 'off';
    if (lastError) { status.textContent = lastError; dot.className = 'off'; }
    else if (!connected) status.textContent = 'disconnected' + repo;
    else if (replaying) status.textContent = `replaying ${current} / ${items.length - 1}`;
    else if (follow) status.textContent = 'live' + repo;
    else status.textContent = `paused at ${current} of ${items.length - 1}` + repo;
    followBtn.classList.toggle('on', follow);
    replayBtn.classList.toggle('on', replaying);
    replayBtn.disabled = items.length < 2;
    clearBtn.disabled = items.length < 2;
    document.title = (items[current] ? items[current].label + ' — ' : '') + 'git-sim live';
  }
  function chipFor(item){
    const b = document.createElement('button');
    b.className = 'chip'; b.dataset.i = item.index;
    b.title = (item.detail || item.label) + '\n' + clock(item.time) + '\nshift+click opens this change as a page of its own';
    b.innerHTML = item.index === 0
      ? `<b>start</b> ${esc(item.label)} <small>${clock(item.time)}</small>`
      : `<b>${item.index}</b> ${esc(item.label)} <small>${clock(item.time)}</small>`;
    b.addEventListener('click', e => {
      if (e.shiftKey) {
        if (inVscode) host.postMessage({type: 'openPage', page: item.page}); else window.open(api(`/page/${item.index}`), '_blank');
        return;
      }
      replaying = false;
      follow = item.index === items[items.length - 1].index;
      show(item.index, true);
    });
    return b;
  }
  async function svgOf(index){
    if (svgs.has(index)) return svgs.get(index);
    if (inVscode) return null;  // the extension sends every graph with its item
    const r = await fetch(api(`/svg/${index}`));
    if (!r.ok) throw new Error(`the graph for change ${index} could not be fetched (${r.status})`);
    const text = await r.text();
    svgs.set(index, text);
    return text;
  }
  // #debug=1 in the fragment narrates the page's steps in the strip.
  const trace = frag.has('debug') ? (m => { lastError = 'trace: ' + m; status.textContent = lastError; }) : () => {};
  async function show(index, play, then){
    const item = items.find(i => i.index === index);
    if (!item) return;
    trace(`fetching ${index}`);
    const svg = await svgOf(index);
    trace(`fetched ${index}: ${svg ? svg.length : 0} chars`);
    if (!svg) return;
    current = index;
    Array.from(chips.children).forEach(c => c.classList.toggle('cur', Number(c.dataset.i) === index));
    const chip = chips.querySelector(`.chip[data-i="${index}"]`);
    if (chip) chip.scrollIntoView({block: 'nearest', inline: 'nearest'});
    const empty = $('empty'); if (empty) empty.remove();
    // Opens on "after" (the repository as it is) and plays the change once,
    // rather than looping: a live page should settle on the current state.
    try {
      V.mount(svg, {title: item.label, state: 'after'});
    } catch (e) { complain(`could not draw change ${index}: ${e.message}`); return; }
    trace(`mounted ${index}: stage has ${$('stage').children.length} child(ren)`);
    setStatus();
    if (play) V.playOnce(then); else if (then) then();
  }
  function add(item, svg, fresh){
    if (items.some(i => i.index === item.index)) return;
    items.push(item);
    items.sort((a, b) => a.index - b.index);
    // The extension sends each graph's text with its item; the server's list
    // carries the path of the file instead, and the text is fetched on demand.
    if (svg && /^\s*</.test(svg)) svgs.set(item.index, svg);
    const chip = chipFor(item);
    if (fresh) chip.classList.add('fresh');
    chips.appendChild(chip);
    if (fresh && follow && !replaying) show(item.index, true);
    else if (current < 0) show(item.index, false);
    setStatus();
  }
  function replay(){
    if (items.length < 2) return;
    replaying = true; follow = false;
    const order = items.map(i => i.index).filter(i => i !== 0);
    let at = 0;
    const next = () => {
      if (!replaying) return;
      if (at >= order.length) { replaying = false; follow = true; setStatus(); return; }
      show(order[at++], true, () => setTimeout(next, 700));
    };
    next();
  }
  replayBtn.addEventListener('click', () => { if (replaying) { replaying = false; setStatus(); } else replay(); });
  followBtn.addEventListener('click', () => {
    follow = !follow; replaying = false;
    if (follow && items.length) show(items[items.length - 1].index, false);
    setStatus();
  });
  clearBtn.addEventListener('click', () => {
    // Forget everything but the latest state, which becomes the new start.
    const last = items[items.length - 1];
    if (!last) return;
    items.length = 0; chips.innerHTML = '';
    svgs.forEach((v, k) => { if (k !== last.index) svgs.delete(k); });
    add(Object.assign({}, last, {label: 'cleared · ' + last.label}), svgs.get(last.index), false);
    follow = true; replaying = false;
    show(last.index, false);
    if (host) host.postMessage({type: 'clear', keep: last.index});
  });
  document.addEventListener('keydown', e => {
    const t = e.target;
    if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
    if (e.key === '[' || e.key === ']') {
      const pos = items.findIndex(i => i.index === current);
      const to = items[pos + (e.key === ']' ? 1 : -1)];
      if (to) { replaying = false; follow = to.index === items[items.length - 1].index; show(to.index, true); }
    }
    if (e.key === 'l' || e.key === 'L') followBtn.click();
    if (e.key === 'r' || e.key === 'R') replayBtn.click();
  });

  // ---- when the local server cannot be reached ------------------------------
  // Hosted here but the browser would not let the page talk to localhost (a
  // blocked local-network permission, a strict shield), or git-sim live is no
  // longer running: say so and offer the local copy of the page, which needs
  // no permission at all.
  function unreachable(){
    connected = false; setStatus();
    if (items.length) return;  // it was working: the dot says it dropped
    let empty = $('empty');
    if (!empty) { empty = document.createElement('p'); empty.id = 'empty'; $('stage').after(empty); }
    if (hosted) {
      const local = base + '/#k=' + encodeURIComponent(key);
      empty.innerHTML = `<b>This page cannot reach git-sim live on your machine</b> (${esc(base)}). ` +
        'Either <code>git-sim live</code> has stopped, or your browser is not letting a website talk to your computer ' +
        '(Chrome and Edge ask for permission the first time; Brave blocks it unless the shield is lowered). ' +
        `The same page is served by git-sim itself, with no permission needed:<br><a class="go" href="${esc(local)}">Open the local page</a>`;
    } else {
      empty.innerHTML = '<b>git-sim live is not running</b> or has stopped. Start it again in your repository with <code>git-sim live</code>.';
    }
  }

  // ---- transport --------------------------------------------------------------
  function handle(msg){
    if (!msg || !msg.type) return;
    if (msg.type === 'history') { connected = true; (msg.items || []).forEach(i => add(i, i.svg, false)); setStatus(); }
    else if (msg.type === 'snapshot') { connected = true; add(msg.item, msg.svg, true); }
    else if (msg.type === 'status') { connected = !!msg.connected; if (msg.text) status.textContent = msg.text; dot.className = connected ? dot.className : 'off'; }
  }
  if (inVscode) {
    window.addEventListener('message', e => handle(e.data));
    host.postMessage({type: 'ready'});
  } else if (!hosted && !document.documentElement.dataset.liveLocal) {
    // The hosted page opened on its own, with no git-sim behind it: the page
    // below the stage explains what this is; nothing to connect to.
    connected = false; setStatus();
    dot.className = '';
    status.textContent = 'not connected: run git-sim live';
  } else {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 6000);
    fetch(api('/history'), {signal: controller.signal})
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(items => { clearTimeout(timer); handle({type: 'history', items}); connect(); })
      .catch(() => { clearTimeout(timer); unreachable(); });
    let source = null;
    function connect(){
      source = new EventSource(api('/events'));
      source.onopen = () => { connected = true; setStatus(); };
      source.onmessage = e => { try { handle(JSON.parse(e.data)); } catch (err) {} };
      source.onerror = () => { connected = false; setStatus(); };  // EventSource reconnects on its own
    }
  }
  setStatus();
})();
"""


def strip_markup(fragment_attr=""):
    """The strip of recorded changes and its controls. Shared verbatim by the
    standalone page and the hosted page (through export_viewer_assets, which
    passes a Thymeleaf fragment attribute)."""
    return (
        f'<nav id="live"{fragment_attr} aria-label="changes seen so far">'
        '<span id="liveDot"></span><span id="liveStatus">connecting</span>'
        '<div id="chips"></div>'
        '<div class="tools">'
        '<button id="replay" title="play every recorded change in order (R)"><span class="ico">&#8635;</span><span class="txt">Replay all</span></button>'
        '<button id="follow" class="on" title="jump to each change as it happens (L)"><span class="ico">&#9679;</span><span class="txt">Follow</span></button>'
        '<button id="clear" title="forget the recorded changes and start from the current state"><span class="ico">&#10005;</span><span class="txt">Clear</span></button>'
        "</div></nav>"
    )


EMPTY_NOTE = (
    '<p id="empty"><b>Watching the repository.</b> Commit, branch, stage a file, switch, reset, rebase: '
    "each change plays here as it happens, and stays in the strip above so you can step back through it "
    "([ and ] move between changes).</p>"
)


def build_live_html(*, theme=None, repo="", viewer_url=DEFAULT_VIEWER_URL, key=""):
    """The page ``git-sim live`` serves and the VS Code extension embeds.
    ``key`` is the session key the page presents to the local server."""
    theme = theme or DARK
    meta = json.dumps(
        {
            "title": "git-sim live",
            "theme": theme.name,
            "repo": repo,
            "viewer_url": viewer_url,
            "live": True,
            "key": key,
        }
    ).replace("</", "<\\/")
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en" data-theme="{theme.name}" data-live="1" data-live-local="1"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>git-sim live{' — ' + html.escape(repo) if repo else ''}</title>"
        '<meta name="generator" content="git-sim">'
        f"<style>{VIEWER_CSS}{LIVE_CSS}</style></head><body>"
        f"{header_markup()}"
        f"{strip_markup()}"
        '<div id="stage"></div>'
        f"{EMPTY_NOTE}"
        '<div id="tip"></div>'
        '<div id="toast"></div>'
        f'<script type="application/json" id="git-sim-meta">{meta}</script>'
        f"<script>{VIEWER_JS}</script>"
        f"<script>{LIVE_JS}</script>"
        "</body></html>"
    )


def hosted_live_url(viewer_url, base, key):
    """The address git-sim opens for live mode: the hosted page, with the
    local server's address and the session key in the fragment, which the
    browser never sends to the site."""
    import urllib.parse

    page = viewer_url.rstrip("/") + "/live"
    return page + "#" + urllib.parse.urlencode({"live": base, "k": key})
