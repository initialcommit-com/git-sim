"""The live page: the interactive viewer plus a strip of the changes seen so
far, fed by ``git-sim live``.

One page, four hosts. Served by the command's own local server it talks to
that server with relative URLs (``/history`` for the list so far, ``/svg/<n>``
for a graph, ``/events`` for pushes). Hosted on initialcommit.com it is the
same page with the local server's address in the fragment (``#live=http://
127.0.0.1:PORT&k=KEY``): the graphs still come from the user's machine and the
site only serves the page, as with shared simulations. Inside the VS Code
extension's webview it receives the same data through postMessage instead,
and knows it is there because ``acquireVsCodeApi`` exists. And saved as a
recorded session (``build_live_html(session=...)``) it carries every graph
inline and needs no server at all: one file that opens anywhere, steps
through the session and can still record it as a video.

Every request to the local server carries the session key git-sim printed
and put in the page, so a stranger's web page cannot read the repository
graph off localhost. ``export_viewer_assets`` (render/html.py) writes the
strip's markup, stylesheet and script for the website repository, so the
hosted copy is the same code.
"""

import html
import json
import time

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
#liveDot.rec{background:#ef4444;animation:pulse-red 1s ease-out infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(34,197,94,.55)}100%{box-shadow:0 0 0 9px rgba(34,197,94,0)}}
@keyframes pulse-red{0%{box-shadow:0 0 0 0 rgba(239,68,68,.6)}100%{box-shadow:0 0 0 9px rgba(239,68,68,0)}}
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
#live .tools button.rec{color:#ef4444;border-color:#ef4444}
#live .tools button:disabled{opacity:.45;cursor:default}
#live .tools button[hidden]{display:none}
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
  // the editor's handle can be taken only once per page; the viewer's Share menu uses it too
  const host = inVscode ? (window.__gitSimHost = window.__gitSimHost || acquireVsCodeApi()) : null;
  const $ = id => document.getElementById(id);
  const dot = $('liveDot'), status = $('liveStatus'), chips = $('chips');
  const replayBtn = $('replay'), followBtn = $('follow'), clearBtn = $('clear'), saveBtn = $('save'), recordBtn = $('record');
  const info = (() => { try { return JSON.parse($('git-sim-meta').textContent); } catch (e) { return {}; } })();
  // A recorded session: every graph is in the page, nothing to connect to.
  const recorded = (() => { const el = $('git-sim-session'); if (!el) return null; try { return JSON.parse(el.textContent); } catch (e) { return null; } })();
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
  let current = -1, follow = true, replaying = false, connected = false, recording = false;
  let downNote = '';  // what the status says while disconnected, after Watch tried to reconnect
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  const clock = t => { const d = new Date(t * 1000); return d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit', second: '2-digit'}); };
  const repoName = () => (recorded && recorded.repo) || info.repo || '';
  // the repository's path, home folder and account names already left out by git-sim
  const whereOf = () => (recorded && recorded.where) || info.where || '';
  const fileStem = () => ((repoName() || 'git-sim') + '-live-' + new Date((recorded && recorded.started ? recorded.started * 1000 : Date.now())).toISOString().slice(0, 19).replace(/[:T]/g, '-')).replace(/[^a-z0-9-]+/gi, '-');
  // A failure while drawing is said in the strip rather than lost in a console.
  let lastError = '';
  const complain = text => { lastError = 'error: ' + String(text).slice(0, 160); status.textContent = lastError; dot.className = 'off'; };
  window.addEventListener('error', e => complain(e.message || e.type));
  window.addEventListener('unhandledrejection', e => complain((e.reason && e.reason.message) || e.reason || 'promise rejected'));

  function setStatus(){
    const repo = repoName() ? ' · ' + repoName() : '';
    const changes = items.filter(i => i.index !== 0).length;
    dot.className = recording ? 'rec' : recorded ? '' : connected ? (follow && !replaying ? 'on' : '') : 'off';
    if (lastError) { status.textContent = lastError; dot.className = 'off'; }
    else if (recording) status.textContent = recording;
    else if (recorded && recorded.title) status.textContent = `${recorded.title} · ${changes} step${changes === 1 ? '' : 's'}`;
    else if (recorded) status.textContent = `recorded${repo} · ${changes} change${changes === 1 ? '' : 's'}` + (recorded.started ? ' · ' + new Date(recorded.started * 1000).toLocaleString([], {dateStyle: 'medium', timeStyle: 'short'}) : '');
    else if (!connected) status.textContent = (downNote || 'disconnected') + repo;
    else if (replaying) status.textContent = `replaying ${current} / ${changes}`;
    else if (follow) status.textContent = 'live' + repo;
    else status.textContent = `paused at ${current} of ${changes}` + repo;
    // the state in one word, and where, for the player's header
    status.dataset.state = recorded ? '' : !connected ? 'disconnected' : replaying ? 'replaying' : follow ? 'watching' : 'paused';
    status.dataset.where = whereOf();
    // lit only while it really is watching: not when git-sim live is gone
    followBtn.classList.toggle('on', follow && !recorded && connected);
    followBtn.title = !recorded && !connected ? 'reconnect to git-sim live and jump to each change as it happens (L)' : 'jump to each change as it happens (L)';
    replayBtn.classList.toggle('on', replaying);
    const busy = !!recording;
    replayBtn.disabled = busy || items.filter(i => i.index !== 0).length < (recorded ? 1 : 2);
    clearBtn.disabled = busy || items.length < 2;
    followBtn.disabled = busy;
    if (saveBtn) saveBtn.disabled = busy || items.length < 1;
    if (recordBtn) { recordBtn.disabled = items.length < 1 || !window.MediaRecorder; recordBtn.classList.toggle('rec', busy); }
    document.title = recorded && recorded.title
      ? (items[current] ? items[current].label + ' — ' : '') + recorded.title + ' — git-sim'
      : (items[current] ? items[current].label + ' — ' : '') + 'git-sim live' + (repoName() ? ': ' + repoName() : '');
  }
  function chipFor(item){
    const b = document.createElement('button');
    b.className = 'chip'; b.dataset.i = item.index;
    const when = item.time ? clock(item.time) : '';
    b.title = (item.detail || item.label) + (when ? '\n' + when : '') + (recorded ? '' : '\nshift+click opens this change as a page of its own');
    b.innerHTML = (item.index === 0 ? '<b>start</b> ' : `<b>${item.index}</b> `) + esc(item.label) + (when ? ` <small>${when}</small>` : '');
    b.addEventListener('click', e => {
      if (recording) return;
      if (e.shiftKey && !recorded) {
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
    if (inVscode || recorded) return null;  // every graph arrived with its item
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
    // scroll only the strip: scrollIntoView would also scroll a page this one is framed in
    if (chip) { const cr = chip.getBoundingClientRect(), sr = chips.getBoundingClientRect();
      if (cr.left < sr.left) chips.scrollLeft += cr.left - sr.left; else if (cr.right > sr.right) chips.scrollLeft += cr.right - sr.right; }
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
    // The extension and a recorded session carry each graph's text with its
    // item; the server's list carries the path of the file instead, and the
    // text is fetched on demand.
    if (svg && /^\s*</.test(svg)) svgs.set(item.index, svg);
    const chip = chipFor(item);
    if (fresh) chip.classList.add('fresh');
    chips.appendChild(chip);
    if (fresh && follow && !replaying && !recording) show(item.index, true);
    else if (current < 0 && !recording) show(item.index, false);
    setStatus();
  }
  function replay(from){
    const order = items.map(i => i.index).filter(i => i !== 0);
    if (!order.length || (items.length < 2 && !recorded)) return;
    replaying = true; follow = false;
    let at = from == null ? 0 : Math.max(0, order.indexOf(from));
    const next = () => {
      if (!replaying) return;
      if (at >= order.length) { replaying = false; follow = !recorded; setStatus(); return; }
      show(order[at++], true, () => {
        // A page hosting the strip may hold the run after each step (to let it be
        // read, or read aloud): window.GitSimLiveHooks.hold(isLast) returns a promise.
        const hooks = window.GitSimLiveHooks || {};
        if (!hooks.hold) { setTimeout(next, 700); return; }
        Promise.resolve().then(() => hooks.hold(at >= order.length)).catch(() => {}).then(() => setTimeout(next, 150));
      });
    };
    next();
  }
  // ending a replay early tells the hosting page, which may be reading a step aloud
  function stopReplay(){ replaying = false; setStatus(); const hooks = window.GitSimLiveHooks || {}; if (hooks.stopped) hooks.stopped(); }
  replayBtn.addEventListener('click', () => { if (replaying) stopReplay(); else replay(); });
  // For a page that hosts the strip (the site's viewer): play the session on from
  // the change on screen (from the first when on the last), or stop it.
  window.GitSimLive = {
    play(from){ if (recording) return; const order = items.map(i => i.index).filter(i => i !== 0);
      if (from != null && order.includes(from)) { replay(from); return; }
      replay(current === order[order.length - 1] ? order[0] : current); },
    stop(){ stopReplay(); },
    get playing(){ return replaying; },
  };
  followBtn.addEventListener('click', () => {
    // disconnected: try git-sim live again now, rather than waiting for the next retry
    if (!connected && !recorded && window.GitSimLiveReconnect) { follow = true; window.GitSimLiveReconnect(); setStatus(); return; }
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

  // ---- saving: the session as one file, the replay as a video -----------------
  // Bytes leave the page one of two ways: a download in a browser, or, inside
  // the extension's webview (which cannot download), a message the extension
  // turns into a save dialog.
  function deliver(blob, name){
    if (inVscode) {
      const reader = new FileReader();
      reader.onload = () => host.postMessage({type: 'saveFile', name, mime: blob.type, data: String(reader.result).split(',')[1]});
      reader.readAsDataURL(blob);
      return;
    }
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }
  async function saveSession(){
    if (inVscode) { host.postMessage({type: 'saveSession'}); return; }
    // The server builds the file: every graph inline, this same page around them.
    const r = await fetch(api('/session.html'));
    if (!r.ok) throw new Error(`the session could not be saved (${r.status})`);
    deliver(await r.blob(), fileStem() + '.html');
  }
  if (saveBtn) saveBtn.addEventListener('click', () => saveSession().catch(e => complain(e.message)));

  // Recording draws the replay frame by frame onto a canvas and encodes it
  // with MediaRecorder: each frame the graph is put at a point of its
  // animation, serialized as it stands (the viewer's changes are inline
  // styles and attributes) and painted through an <img>. Frames are paced to
  // real time, so the video plays at the speed the page plays.
  const ease = t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  const sleep = ms => new Promise(ok => setTimeout(ok, ms));
  async function record(){
    if (recording || !window.MediaRecorder || !items.length) return;
    const order = items.length > 1 ? items.map(i => i.index).filter(i => i !== 0) : [items[0].index];
    const mime = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'].find(t => MediaRecorder.isTypeSupported(t));
    if (!mime) { complain('this browser cannot encode video'); return; }
    const wasFollowing = follow;
    recording = 'preparing recording'; follow = false; replaying = false; setStatus();
    const canvas = document.createElement('canvas');
    const W = 1600;
    let H = 900;
    const ctx = canvas.getContext('2d');
    const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim() || '#0d1117';
    const stream = canvas.captureStream(0);
    const track = stream.getVideoTracks()[0];
    const chunks = [];
    const rec = new MediaRecorder(stream, {mimeType: mime, videoBitsPerSecond: 6000000});
    rec.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    const done = new Promise(ok => { rec.onstop = ok; });
    const FPS = 30;
    let frameNo = 0, t0 = 0;
    async function paint(){
      const svg = document.getElementById('scene');
      if (!svg) return;
      const clone = svg.cloneNode(true);
      const vb = svg.viewBox.baseVal;
      clone.setAttribute('width', vb.width); clone.setAttribute('height', vb.height);
      clone.querySelectorAll('.dim,.lit').forEach(el => el.classList.remove('dim', 'lit'));
      const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], {type: 'image/svg+xml;charset=utf-8'}));
      try {
        const img = new Image(); img.src = url; await img.decode();
        ctx.fillStyle = bg; ctx.fillRect(0, 0, canvas.width, canvas.height);
        const k = Math.min((canvas.width - 40) / vb.width, (canvas.height - 40) / vb.height);
        const w = vb.width * k, h = vb.height * k;
        ctx.drawImage(img, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
      } finally { URL.revokeObjectURL(url); }
      // keep to real time: wait for this frame's slot, or catch up if late
      const due = t0 + frameNo * 1000 / FPS;
      const now = performance.now();
      if (now < due) await sleep(due - now);
      track.requestFrame();
      frameNo++;
    }
    try {
      // the canvas takes the first graph's shape
      await show(order[0], false);
      const first = document.getElementById('scene');
      if (first) { const vb = first.viewBox.baseVal; H = Math.max(360, Math.round(W * vb.height / vb.width)); }
      canvas.width = W; canvas.height = H;
      rec.start();
      t0 = performance.now();
      for (let n = 0; n < order.length && recording; n++) {
        recording = `recording ${n + 1} / ${order.length} (Esc stops)`; setStatus();
        await show(order[n], false);
        const steps = V.steps();
        if (V.animatable() && steps > 0) {
          const perStep = Math.max(380, Math.min(900, 4500 / steps));
          const frames = Math.round((perStep * steps + 200) / 1000 * FPS);
          V.setProgress(0);
          for (let f = 0; f < 10; f++) await paint();  // a beat on "before"
          for (let f = 1; f <= frames && recording; f++) { V.setProgress(steps * ease(f / frames)); await paint(); }
        } else {
          for (let f = 0; f < 10; f++) await paint();
        }
        for (let f = 0; f < Math.round(0.7 * FPS); f++) await paint();  // hold on "after"
      }
    } catch (e) {
      complain('recording failed: ' + e.message);
    } finally {
      const stopped = !!recording;
      recording = false;
      rec.stop(); await done;
      const blob = new Blob(chunks, {type: mime.split(';')[0]});
      trace(`video: ${blob.size} bytes, ${mime}, ${frameNo} frames`);
      if (stopped && blob.size) deliver(blob, fileStem() + (mime.startsWith('video/mp4') ? '.mp4' : '.webm'));
      follow = wasFollowing && !recorded;
      if (follow && items.length) show(items[items.length - 1].index, false);
      setStatus();
    }
  }
  if (recordBtn) recordBtn.addEventListener('click', () => { if (recording) { recording = false; } else record(); });

  document.addEventListener('keydown', e => {
    const t = e.target;
    if (t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
    if (e.key === 'Escape' && recording) { recording = false; return; }
    if (recording) return;
    if (e.key === '[' || e.key === ']') {
      const pos = items.findIndex(i => i.index === current);
      const to = items[pos + (e.key === ']' ? 1 : -1)];
      if (to) { replaying = false; follow = to.index === items[items.length - 1].index; show(to.index, true); }
    }
    if (e.key === 'l' || e.key === 'L') followBtn.click();
    if (e.key === 'r' || e.key === 'R') replayBtn.click();
    if ((e.key === 's' || e.key === 'S') && saveBtn && !saveBtn.hidden) saveBtn.click();
    if ((e.key === 'v' || e.key === 'V') && recordBtn) recordBtn.click();
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
  if (recorded) {
    // A saved session: the strip is the whole story, nothing is live.
    followBtn.hidden = true; clearBtn.hidden = true; if (saveBtn) saveBtn.hidden = true;
    follow = false;
    (recorded.items || []).forEach(i => add(i, i.svg, false));
    const last = items[items.length - 1];
    // a demo (start "first") waits on its first step, before its command, for Play
    if (recorded.start === 'first' && items.length) show(items[0].index, false, () => V.setProgress(0));
    else if (last) show(last.index, false);
  } else if (inVscode) {
    window.addEventListener('message', e => handle(e.data));
    host.postMessage({type: 'ready'});
  } else if (!hosted && !document.documentElement.dataset.liveLocal) {
    // The hosted page opened on its own, with no git-sim behind it: the page
    // below the stage explains what this is; nothing to connect to.
    connected = false; setStatus();
    dot.className = '';
    status.textContent = 'not connected: run git-sim live';
    if (saveBtn) saveBtn.hidden = true;
  } else {
    let source = null, dropped = false;
    // The history, and then the stream of changes. After git-sim live was
    // stopped and started again (on the same port and key: it keeps them per
    // repository), the history is a new session's: the page starts over from it.
    function load(fresh){
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 6000);
      return fetch(api('/history'), {signal: controller.signal})
        .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
        .then(list => {
          clearTimeout(timer);
          if (fresh) {
            items.length = 0; chips.innerHTML = ''; svgs.clear(); current = -1;
            replaying = false; follow = true; lastError = '';
            const empty = $('empty'); if (empty) empty.remove();
          }
          handle({type: 'history', items: list});
          const last = items[items.length - 1];
          if (fresh && last) show(last.index, false);
          // the repository's name and path (the hosted page has neither in it)
          fetch(api('/info')).then(r => r.ok ? r.json() : null).then(i => {
            if (i) { info.repo = i.repo || info.repo; info.where = i.where || info.where; setStatus(); }
          }).catch(() => {});
          return true;
        })
        .catch(() => { clearTimeout(timer); return false; });
    }
    function connect(){
      if (source) source.close();
      source = new EventSource(api('/events'));
      source.onopen = () => {
        connected = true; downNote = ''; setStatus();
        // back after a drop: catch up on the session (a new one if git-sim live restarted)
        if (dropped) { dropped = false; load(true); }
      };
      source.onmessage = e => { try { handle(JSON.parse(e.data)); } catch (err) {} };
      // EventSource retries on its own (every 1.5s, the server's "retry")
      source.onerror = () => { if (connected) dropped = true; connected = false; setStatus(); };
    }
    // Watch, clicked while disconnected: try now
    window.GitSimLiveReconnect = () => {
      status.textContent = 'reconnecting';
      load(true).then(ok => {
        if (ok) { dropped = false; downNote = ''; connect(); return; }
        // the page keeps trying on its own, and catches up once it's back
        downNote = 'not running: start git-sim live again';
        unreachable();
        if (!source) { dropped = true; connect(); }
      });
    };
    // not running yet: keep trying in the background, and load the history once it is
    load(false).then(ok => { if (ok) connect(); else { unreachable(); dropped = true; connect(); } });
  }
  setStatus();
})();
"""


# ---- the player: the hosted viewer's layout for a live session, on git-sim's own page ----
# The strip above (#live) keeps recording and drives the graph, unseen. The page
# shows which change is on screen in the header (Live, the repository, Change n / N),
# a bar of the changes above the graph (with each one's number, time and command
# unless the reader hid them), and a player under it: back, Play / Pause from the
# change on screen, Record, forward, and Follow, Save session and Clear. The same
# design as initialcommit.com's viewer page (templates/pages/tools/git-sim-viewer-page.html
# in the site repository). The VS Code views keep the compact strip.
PLAYER_CSS = """
html[data-player] #live{display:none!important}
html[data-player] #controls{display:none!important}
.vp-head{display:flex;align-items:center;justify-content:center;gap:12px;min-width:0}
.vp-kicker{display:flex;align-items:center;gap:8px;min-width:0;margin:0;font:700 12px/1 var(--font);letter-spacing:.12em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
.vp-kicker b{min-width:0;overflow:hidden;text-overflow:ellipsis;color:var(--text);font-size:14px;letter-spacing:.02em;text-transform:none}
.vp-kicker i{flex:none;width:9px;height:9px;border-radius:50%;background:var(--muted)}
.vp-kicker i.on{background:#22c55e;box-shadow:0 0 0 4px rgba(34,197,94,.18)}
.vp-kicker i.off,.vp-kicker i.rec{background:#ef4444}
.vp-step-n{flex:none;padding:7px 13px;border-radius:999px;background:var(--accent);color:var(--bg);font:800 12px/1 var(--font);letter-spacing:.08em;text-transform:uppercase;white-space:nowrap}
.vp-step-n[data-state="paused"]{background:transparent;color:var(--accent);box-shadow:inset 0 0 0 1.5px var(--accent)}
.vp-step-n[data-state="disconnected"]{background:var(--muted);color:var(--bg)}
.vp-step{max-width:1240px;margin:0 auto;padding:20px 18px 0}
.vp-step[hidden]{display:none}
.vp-step-top{display:flex;justify-content:flex-end;margin:0 0 12px}
.vp-labels{padding:6px 12px;border:1px solid var(--rule);border-radius:999px;background:transparent;color:var(--muted);font:600 12px/1 var(--font);cursor:pointer}
.vp-labels:hover{color:var(--text);border-color:var(--text)}
.vp-step-bar{display:flex;gap:6px;margin-bottom:26px}
.vp-step-bar button{flex:1;height:8px;padding:0;border:0;border-radius:999px;background:var(--rule);cursor:pointer;transition:background .2s,transform .2s}
.vp-step-bar button.done{background:color-mix(in srgb,var(--accent) 55%,var(--rule))}
.vp-step-bar button.cur{background:var(--accent);transform:scaleY(1.4)}
.vp-step-bar button:hover{background:var(--accent)}
.vp-step-bar:not(.labeled) button>span{display:none}
.vp-step-bar.labeled{gap:8px;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin;padding:2px 2px 6px}
.vp-step-bar.labeled button{flex:1 0 auto;display:flex;flex-direction:column;align-items:flex-start;gap:5px;min-width:112px;max-width:260px;height:auto;padding:7px 11px 9px;border-radius:10px;border-top:4px solid var(--rule);background:var(--panel);text-align:left;transform:none;transition:background .2s}
.vp-step-wait{flex:1;display:flex;align-items:center;height:52px;padding:0 14px;border:1.5px dashed var(--rule);border-radius:10px;color:var(--muted);font:600 12px/1 var(--font)}
.vp-step-bar:not(.labeled) .vp-step-wait{height:8px;padding:0;border:0;border-radius:999px;background:var(--rule);font-size:0}
.vp-step-bar.labeled button.done{background:var(--panel);border-top-color:color-mix(in srgb,var(--accent) 55%,var(--rule))}
.vp-step-bar.labeled button.cur{background:color-mix(in srgb,var(--accent) 12%,var(--panel));border-top-color:var(--accent);box-shadow:0 0 0 1.5px var(--accent) inset;transform:none}
.vp-step-bar.labeled button:hover{background:color-mix(in srgb,var(--accent) 12%,var(--panel))}
.vp-step-bar .seg-meta{font:600 11px/1 var(--font);letter-spacing:.02em;color:var(--muted);white-space:nowrap}
.vp-step-bar .seg-cmd{max-width:100%;font:600 12.5px/1.25 var(--font);color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.vp-controls{display:flex;justify-content:center;padding:4px 18px 28px}
.vp-player{display:flex;flex-direction:column;align-items:center;gap:12px}
.vp-player-main{display:flex;align-items:center;gap:14px}
.vp-player button{font-family:var(--font);cursor:pointer}
.vp-player .vp-skip{display:inline-flex;align-items:center;justify-content:center;width:44px;height:44px;border-radius:50%;border:1.5px solid var(--rule);background:var(--panel);color:var(--text);font-size:17px;line-height:1;transition:border-color .15s,color .15s}
.vp-player .vp-skip:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.vp-player .vp-skip:disabled{opacity:.35;cursor:default}
.vp-player .vp-play{display:inline-flex;align-items:center;gap:10px;height:56px;padding:0 26px 0 22px;border-radius:999px;border:0;background:var(--accent);color:var(--bg);font-weight:700;font-size:16px;box-shadow:0 12px 24px -12px var(--accent);transition:transform .15s,filter .15s}
.vp-player .vp-play:hover{transform:translateY(-2px);filter:brightness(1.06)}
.vp-player .vp-play span{display:inline-flex}
.vp-player .vp-rec{display:inline-flex;align-items:center;gap:10px;height:56px;padding:0 24px 0 20px;border-radius:999px;border:2px solid #ef4444;background:transparent;color:#ef4444;font-size:16px;font-weight:700;transition:transform .15s,background .15s,color .15s}
.vp-player .vp-rec i{width:16px;height:16px;border-radius:50%;background:#ef4444;transition:border-radius .2s}
.vp-player .vp-rec:hover:not(:disabled){transform:translateY(-2px);background:rgba(239,68,68,.12)}
.vp-player .vp-rec.on{background:#ef4444;color:#fff}
.vp-player .vp-rec.on i{background:#fff;border-radius:3px;animation:vp-rec 1s ease-in-out infinite}
.vp-player .vp-rec:disabled{opacity:.35;cursor:default}
@keyframes vp-rec{50%{opacity:.45}}
@media (prefers-reduced-motion:reduce){.vp-player .vp-rec.on i{animation:none}}
.vp-player-main{flex-wrap:wrap;justify-content:center}
.vp-player .vp-tool{display:inline-flex;align-items:center;gap:8px;height:44px;padding:0 16px 0 14px;border-radius:999px;border:1.5px solid var(--rule);background:var(--panel);color:var(--text);font-size:14px;font-weight:600;white-space:nowrap;transition:border-color .15s,color .15s,background .15s}
.vp-player .vp-tool svg{flex:none}
.vp-player .vp-tool:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}
.vp-player .vp-tool.on{border-color:var(--accent);background:color-mix(in srgb,var(--accent) 12%,var(--panel));color:var(--accent)}
.vp-player .vp-tool:disabled{opacity:.35;cursor:default}
.vp-player .vp-tool[hidden]{display:none}
.vp-player .vp-sep{width:1.5px;height:28px;background:var(--rule)}
.vp-player-main:not(:has(.vp-tool:not([hidden]))) .vp-sep{display:none}
@media (max-width:820px){.vp-kicker{display:none}}
@media (max-width:1100px){.vp-player .vp-tool b{display:none}.vp-player .vp-tool{width:44px;padding:0;justify-content:center}}
@media (max-width:560px){.vp-player-main{gap:8px}.vp-player .vp-sep{display:none}.vp-player .vp-tool{width:38px;height:38px}.vp-player .vp-play,.vp-player .vp-rec{height:46px;padding:0 16px;font-size:15px}.vp-player .vp-rec b{display:none}.vp-player .vp-skip{width:38px;height:38px}}
@media (max-width:440px){.vp-player-main{gap:5px}.vp-player .vp-skip,.vp-player .vp-tool{width:34px;height:34px}.vp-player .vp-play{padding:0 14px 0 12px;gap:6px}.vp-player .vp-rec{padding:0 14px}}
"""


def player_markup():
    """The step bar (above the graph) and the player (under it)."""
    return (
        '<div class="vp-step" id="vpStep" aria-live="polite">'
        '<div class="vp-step-top"><button type="button" class="vp-labels" id="vpLabels" aria-pressed="true" '
        'title="show or hide each change\'s command and time">Hide details</button></div>'
        '<div class="vp-step-bar" id="vpStepBar"></div>'
        "</div>",
        '<div class="vp-controls" id="vpControls"><div class="vp-player" id="vpPlayer">'
        '<div class="vp-player-main">'
        '<button type="button" class="vp-skip" id="vpPrev" title="previous change ([)" aria-label="Previous change">'
        '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 5h2v14H6zM20 5v14L9 12z" fill="currentColor"/></svg></button>'
        '<button type="button" class="vp-play" id="vpPlay"><span id="vpPlayIcon"></span><b id="vpPlayText">Play</b></button>'
        '<button type="button" class="vp-rec" data-proxy="record" title="record the whole run as a video (V; Esc stops)"><i></i><b>Record</b></button>'
        '<button type="button" class="vp-skip" id="vpNext" title="next change (])" aria-label="Next change">'
        '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M16 5h2v14h-2zM4 5v14l11-7z" fill="currentColor"/></svg></button>'
        '<span class="vp-sep" aria-hidden="true"></span>'
        '<button type="button" class="vp-tool" data-proxy="follow" aria-label="Watch the repo">'
        '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 5C6.5 5 2.7 9.4 1.5 12c1.2 2.6 5 7 10.5 7s9.3-4.4 10.5-7C21.3 9.4 17.5 5 12 5zm0 11.5a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9zm0-2.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4z" fill="currentColor"/></svg>'
        "<b>Watch the repo</b></button>"
        '<button type="button" class="vp-tool" data-proxy="save" aria-label="Save session">'
        '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M11 3h2v9.2l3.3-3.3 1.4 1.4L12 16l-5.7-5.7 1.4-1.4 3.3 3.3zM4 18h16v2H4z" fill="currentColor"/></svg>'
        "<b>Save session</b></button>"
        '<button type="button" class="vp-tool" data-proxy="clear" aria-label="Clear">'
        '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M9 3h6l1 2h4v2H4V5h4zM6 9h12l-1 12H7zm4 2v8h1.5v-8zm2.5 0v8H14v-8z" fill="currentColor"/></svg>'
        "<b>Clear</b></button>"
        "</div></div></div>",
    )


PLAYER_JS = r"""
// git-sim live, the player: the hosted viewer's layout for a session (see PLAYER_CSS).
(function(){
  const root = document.documentElement;
  if (!root.dataset.player) return;
  const $ = id => document.getElementById(id);
  const chips = $('chips'), box = $('vpStep');
  if (!chips || !box) return;
  const session = (() => { try { return JSON.parse(($('git-sim-session') || {}).textContent || 'null'); } catch (e) { return null; } })();
  const demo = !!(session && session.title);   // a recorded demo has steps; a live session has changes
  const noun = demo ? 'Step' : 'Change';
  const icon = {
    play: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M7 4v16l13-8z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path d="M6 4h4v16H6zM14 4h4v16h-4z" fill="currentColor"/></svg>',
  };
  // The header says what is on screen: the session's state, and which change.
  const head = document.createElement('div');
  head.className = 'vp-head';
  head.innerHTML = '<p class="vp-kicker"><i id="vpDot"></i><span id="vpKicker"></span><b id="vpName"></b></p><span class="vp-step-n" id="vpStepN"></span>';
  const controls = $('controls');
  if (controls) controls.after(head); else $('bar').appendChild(head);
  $('vpPlayIcon').innerHTML = icon.play;

  const labelOf = chip => { const c = chip.cloneNode(true); c.querySelectorAll('b, small').forEach(n => n.remove()); return c.textContent.trim(); };
  const timeOf = chip => { const t = chip.querySelector('small'); return t ? t.textContent.trim() : ''; };
  // the changes, without a live session's starting snapshot
  const steps = () => Array.from(chips.querySelectorAll('.chip')).filter(c => c.dataset.i !== '0');
  let paused = false;
  const running = () => !!(window.GitSimLive && GitSimLive.playing);
  const playing = () => running() && !paused;
  // to a change: a run that was playing carries on from there
  function go(k){
    const s = steps()[k];
    if (!s) return;
    const wasPlaying = playing();
    paused = false;
    GitSimLive.stop();
    if (wasPlaying) GitSimLive.play(+s.dataset.i); else s.click();
    syncPlay();
  }
  // The pill: a live session's state (watching, paused, disconnected), or a
  // recorded one's change on screen
  const STATES = {watching: 'Watching', paused: 'Paused', disconnected: 'Disconnected', replaying: 'Replaying'};
  function pill(){
    const n = $('vpStepN');
    if (!session) {
      const st = $('liveStatus');
      let s = (st && st.dataset.state) || '';
      if (s === 'replaying' && paused) s = 'paused';
      n.textContent = STATES[s] || ''; n.dataset.state = s; n.hidden = !STATES[s];
      return;
    }
    const all = steps(), cur = chips.querySelector('.chip.cur'), at = all.indexOf(cur);
    n.textContent = !cur ? '' : at < 0 ? 'Watching' : noun + ' ' + (at + 1) + ' / ' + all.length;
    n.hidden = !cur;
  }
  function show(){
    const all = steps(), cur = chips.querySelector('.chip.cur');
    const at = all.indexOf(cur);  // -1: a live session's starting snapshot
    // the bar keeps its room from the start, so the first change doesn't push the graph down
    box.hidden = false;
    pill();
    const bar = $('vpStepBar');
    if (bar.dataset.n !== String(all.length)) {
      bar.dataset.n = all.length;
      bar.innerHTML = all.length ? '' : '<span class="vp-step-wait">Waiting for the first change</span>';
      all.forEach((chip, k) => {
        const seg = document.createElement('button'), label = labelOf(chip), time = timeOf(chip);
        seg.type = 'button'; seg.title = label + (time ? '\n' + time : '');
        seg.setAttribute('aria-label', noun + ' ' + (k + 1) + ': ' + label + (time ? ', ' + time : ''));
        const meta = document.createElement('span'), cmd = document.createElement('span');
        meta.className = 'seg-meta'; meta.textContent = noun + ' ' + (k + 1) + (time ? ' · ' + time : '');
        cmd.className = 'seg-cmd'; cmd.textContent = label;
        seg.append(meta, cmd);
        seg.addEventListener('click', () => go(k));
        bar.appendChild(seg);
      });
    }
    Array.from(bar.children).forEach((seg, k) => { seg.classList.toggle('done', k < at); seg.classList.toggle('cur', k === at); });
    // with details on, keep the change on screen in view (scrolling the row only, not the page)
    const curSeg = bar.children[at];
    if (curSeg && bar.classList.contains('labeled')) {
      const sr = curSeg.getBoundingClientRect(), br = bar.getBoundingClientRect();
      if (sr.left < br.left) bar.scrollLeft += sr.left - br.left - 8;
      else if (sr.right > br.right) bar.scrollLeft += sr.right - br.right + 8;
    }
    $('vpPrev').disabled = at <= 0;
    $('vpNext').disabled = at >= all.length - 1;
  }
  new MutationObserver(show).observe(chips, {childList: true, subtree: true, attributes: true, attributeFilter: ['class']});

  // Details: each change's command and time in the bar, on unless the reader turned them off
  const DETAILS = 'git-sim:step-details';
  let details = (() => { try { return localStorage.getItem(DETAILS) !== '0'; } catch (e) { return true; } })();
  function applyDetails(){
    $('vpStepBar').classList.toggle('labeled', details);
    $('vpLabels').setAttribute('aria-pressed', details ? 'true' : 'false');
    $('vpLabels').textContent = details ? 'Hide details' : 'Show details';
  }
  $('vpLabels').addEventListener('click', () => {
    details = !details;
    try { localStorage.setItem(DETAILS, details ? '1' : '0'); } catch (e) {}
    applyDetails(); show();
  });
  applyDetails();

  // Play / Pause: the run from the change on screen; Pause holds it where it is.
  function syncPlay(){
    const on = playing();
    $('vpPlayIcon').innerHTML = on ? icon.pause : icon.play;
    $('vpPlayText').textContent = on ? 'Pause' : 'Play';
    pill();
  }
  function togglePlay(){
    if (paused && running()) { paused = false; GitSimViewer.resumeOnce(); }
    else if (running()) { paused = true; GitSimViewer.pauseOnce(); }
    else { paused = false; GitSimLive.play(); }
    syncPlay();
  }
  $('vpPlay').addEventListener('click', togglePlay);
  // a click doesn't leave the focus on a player button, so space stays the viewer's
  document.querySelectorAll('.vp-player button').forEach(b => b.addEventListener('mousedown', e => e.preventDefault()));
  $('vpPrev').addEventListener('click', () => { const all = steps(); go(all.indexOf(chips.querySelector('.chip.cur')) - 1); });
  $('vpNext').addEventListener('click', () => { const all = steps(); go(all.indexOf(chips.querySelector('.chip.cur')) + 1); });
  // the strip's own tools, as the player's buttons
  document.querySelectorAll('.vp-player [data-proxy]').forEach(b => {
    const real = $(b.dataset.proxy);
    if (!real) { b.hidden = true; return; }
    b.addEventListener('click', () => real.click());
    const sync = () => {
      b.classList.toggle('on', real.classList.contains('on') || real.classList.contains('rec'));
      b.disabled = real.disabled; b.hidden = !!real.hidden;
      if (b.classList.contains('vp-tool') && real.title) b.title = real.title;
      if (b.classList.contains('vp-rec')) b.querySelector('b').textContent = real.classList.contains('rec') ? 'Stop' : 'Record';
    };
    new MutationObserver(sync).observe(real, {attributes: true}); sync();
  });
  // the dot and the words in the header: the session's state, as the strip says it
  const status = $('liveStatus'), dot = $('liveDot');
  // a long path keeps its start and its last two folders
  const shorten = p => { const parts = p.split('/'); return p.length > 56 && parts.length > 4 ? parts[0] + '/…/' + parts.slice(-2).join('/') : p; };
  function syncStatus(){
    syncPlay(); pill();
    $('vpKicker').textContent = demo ? 'Workflow' : session ? 'Recorded' : 'Live';
    const where = (!session && status && status.dataset.where) || '';
    $('vpName').textContent = demo ? session.title : where ? shorten(where) : status ? status.textContent.replace(/^(live|recorded)\s*·\s*/, '') : '';
    $('vpName').title = where;
    $('vpDot').className = dot ? dot.className : '';
  }
  if (status) new MutationObserver(syncStatus).observe(status, {childList: true, characterData: true, subtree: true, attributes: true});
  if (dot) new MutationObserver(syncStatus).observe(dot, {attributes: true});
  const replayBtn = $('replay');
  if (replayBtn) new MutationObserver(syncPlay).observe(replayBtn, {attributes: true});
  syncStatus();
  show();

  // A graph never draws its commits bigger than about 60px across: stretched to
  // the full width, a short chain of commits reads as zoomed in. (Graphs are drawn
  // at different scales, so the cap comes from a commit's own size.) It is also
  // kept short enough that the player under it stays on screen, though a commit
  // never gets under about 34px across. As on initialcommit.com's viewer page.
  const stage = $('stage');
  function cap(){
    const svg = stage.querySelector('svg');
    const vb = svg && svg.viewBox && svg.viewBox.baseVal;
    const commit = svg && svg.querySelector('[data-role="commit"]');
    if (!vb || !vb.width || !commit) { if (svg) svg.style.maxWidth = ''; return; }
    const size = commit.getBBox().width;
    if (!size) return;
    let width = vb.width * 60 / size;
    const room = window.innerHeight - (stage.getBoundingClientRect().top + window.scrollY) - 150;
    if (room > 120) width = Math.max(Math.min(width, room * vb.width / vb.height), vb.width * 34 / size);
    svg.style.maxWidth = Math.round(width) + 'px';
    // the viewer's own fit may give the graph a height for the full width: hold it to this width's
    svg.style.maxHeight = Math.round(width * vb.height / vb.width) + 'px';
    svg.style.marginLeft = svg.style.marginRight = 'auto';
  }
  new MutationObserver(cap).observe(stage, {childList: true});
  window.addEventListener('resize', cap);
  if (window.ResizeObserver) new ResizeObserver(() => cap()).observe(stage);
  cap();
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
        '<button id="follow" class="on" title="jump to each change as it happens (L)"><span class="ico">&#9679;</span><span class="txt">Watch</span></button>'
        '<button id="save" title="save the whole session as one page: every change, this strip, nothing to install (S)"><span class="ico">&#8681;</span><span class="txt">Save session</span></button>'
        '<button id="record" title="record the replay as a video to post (V; Esc stops)"><span class="ico">&#9210;</span><span class="txt">Record video</span></button>'
        '<button id="clear" title="forget the recorded changes and start from the current state"><span class="ico">&#10005;</span><span class="txt">Clear</span></button>'
        "</div></nav>"
    )


EMPTY_NOTE = (
    '<p id="empty"><b>Watching the repository.</b> Commit, branch, stage a file, switch, reset, rebase: '
    "each change plays here as it happens, and stays in the strip above so you can step back through it "
    "([ and ] move between changes).</p>"
)

PLAYER_EMPTY_NOTE = (
    '<p id="empty"><b>Watching the repository.</b> Commit, branch, stage a file, switch, reset, rebase: '
    "each change plays here as it happens, and stays in the bar above so you can step back through it "
    "([ and ] move between changes).</p>"
)


def build_live_html(
    *,
    theme=None,
    repo="",
    where="",
    viewer_url=DEFAULT_VIEWER_URL,
    key="",
    session=None,
    player=True,
):
    """The page ``git-sim live`` serves and the VS Code extension embeds.
    ``key`` is the session key the page presents to the local server, and
    ``where`` the repository's path as the header shows it (live.display_path).

    With ``player`` (the default) the page has the hosted viewer's layout: the
    session's state and the change on screen in the header, a bar of the
    changes above the graph, and a player under it, with the strip hidden but
    still driving it. Without it (the VS Code views, which are narrow) the
    strip shows instead.

    With ``session`` ({"repo", "started", "items": [{index, label, detail,
    time, svg}]}) the page is a recorded session instead: every graph inline,
    no server, the strip stepping through them. A session with a ``title`` (a
    demo) is named by it in the strip, and one with ``start: "first"`` opens on
    its first step, before the command, and waits to be played; steps without a
    ``time`` show no clock."""
    theme = theme or DARK
    meta = json.dumps(
        {
            "title": "git-sim live",
            "theme": theme.name,
            "repo": repo,
            "where": where,
            "viewer_url": viewer_url,
            "live": True,
            "key": key,
        }
    ).replace("</", "<\\/")
    recorded = ""
    recorded_attr = ""
    title = "git-sim live" + (" — " + html.escape(repo) if repo else "")
    if session is not None:
        recorded = (
            '<script type="application/json" id="git-sim-session">'
            + json.dumps(session).replace("</", "<\\/")
            + "</script>"
        )
        recorded_attr = ' data-live-recorded="1"'
        when = time.strftime(
            "%Y-%m-%d %H:%M", time.localtime(session.get("started") or time.time())
        )
        title = f"git-sim live session — {html.escape(repo or session.get('repo', ''))} — {when}"
    above, below = player_markup() if player else ("", "")
    player_attr = ' data-player="1"' if player else ""
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en" data-theme="{theme.name}" data-live="1" data-live-local="1"'
        f'{recorded_attr}{player_attr}><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title}</title>"
        '<meta name="generator" content="git-sim">'
        f"<style>{VIEWER_CSS}{LIVE_CSS}{PLAYER_CSS if player else ''}</style></head><body>"
        f"{header_markup()}"
        f"{strip_markup()}"
        f"{above}"
        '<div id="stage"></div>'
        f"{below}"
        f"{(PLAYER_EMPTY_NOTE if player else EMPTY_NOTE) if session is None else ''}"
        '<div id="tip"></div>'
        '<div id="toast"></div>'
        f'<script type="application/json" id="git-sim-meta">{meta}</script>'
        f"{recorded}"
        f"<script>{VIEWER_JS}</script>"
        f"<script>{LIVE_JS}</script>"
        f"{'<script>' + PLAYER_JS + '</script>' if player else ''}"
        "</body></html>"
    )


def hosted_live_url(viewer_url, base, key):
    """The address git-sim opens for live mode: the hosted viewer, with the
    local server's address and the session key in the fragment, which the
    browser never sends to the site."""
    import urllib.parse

    return viewer_url.rstrip("/") + "#" + urllib.parse.urlencode({"live": base, "k": key})
