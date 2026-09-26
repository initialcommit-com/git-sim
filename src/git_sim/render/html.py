"""Self-contained interactive page around the SVG a scene rendered, and the
viewer assets that initialcommit.com serves for shared links.

No external requests: the page is the SVG, a stylesheet and a small script.
Behaviour comes from the data attributes the SVG painter wrote:

- hover a commit for its full message, author, date and parents, with its
  ancestry highlighted; click to copy the sha;
- ctrl/cmd + wheel (or pinch) to zoom, double-click to reset; a help menu in
  the header lists the controls;
- a scrubber from Before to After: dragging it plays the operation
  continuously (simulated elements fade in, moved labels and files travel,
  recolored commits blend), with one stop per step for multi-step commands;
- Play loops the scrubber (the page opens playing); any manual input takes
  over;
- Share: copy a link, copy the graph as PNG, download PNG/SVG/page, or post it.

Sharing without a server: "Copy link" produces a URL to the hosted viewer
(``settings.viewer_url``) carrying the compressed SVG in the fragment, which
never leaves the browser, plus the command and a short text graph in the
query string so the viewer can serve a real preview card. The viewer page
uses exactly the CSS, JS and header markup below; ``export_viewer_assets``
writes them out for the website repository, so there is one source of truth.

The SVG opens framed on its content (its viewBox is the content's bounding
box), laid out like an ordinary page: full width, the command title at the
top, scrolling if the graph is tall.
"""

import base64
import html
import json
import os
import sys
import urllib.parse
import zlib

from git_sim.render.svg import DEFAULT_FONT_STACK as FONT_STACK
from git_sim.theme import DARK, LIGHT

DEFAULT_VIEWER_URL = "https://initialcommit.com/tools/git-sim"


def _theme_vars(theme):
    panel = "rgba(255,255,255,.06)" if theme.glow else "rgba(0,0,0,.05)"
    return (
        f"--bg:{theme.bg};--text:{theme.text};--muted:{theme.text_muted};"
        f"--rule:{theme.rule};--accent:{theme.accent};--panel:{panel};"
    )


def _palettes_json():
    """Both palettes for the viewer script, which recolors a graph generated
    in one theme when the page showing it uses the other (the hosted viewer
    follows the site's dark/light setting)."""

    def dump(theme):
        return {
            "bg": theme.bg,
            "text": theme.text,
            "text_muted": theme.text_muted,
            "rule": theme.rule,
            "arrow": theme.arrow,
            "accent": theme.accent,
            "commit": theme.commit,
            "commit_ring": theme.commit_ring,
            "merge": theme.merge,
            "merge_ring": theme.merge_ring,
            "head": theme.head,
            "branch": theme.branch,
            "remote": theme.remote,
            "tag": theme.tag,
            "purple": theme.purple,
            "gold": theme.gold,
            "ref_text": theme.ref_text,
            "lane_colors": list(theme.lane_colors),
            "lane_rings": [theme.ring_for(c) for c in theme.lane_colors],
        }

    return json.dumps({"dark": dump(DARK), "light": dump(LIGHT)})


# Theme colors live on :root so the page (and the hosted viewer) switch with
# a data-theme attribute; everything else in the stylesheet is static.
VIEWER_CSS = (
    ":root{" + _theme_vars(DARK) + f"--font:{FONT_STACK};" + "}\n"
    ':root[data-theme="light"]{'
    + _theme_vars(LIGHT)
    + "}\n"
    + """*{box-sizing:border-box}
html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);font-family:var(--font)}
#bar{position:sticky;top:var(--bar-top,0);z-index:2;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:12px;height:64px;padding:0 18px;background:var(--bg);border-bottom:1px solid var(--rule)}
#bar .right{display:flex;justify-content:flex-end;align-items:center;gap:6px;color:var(--muted);font:12px/1 var(--font);position:relative}
#bar .right a{color:var(--muted);text-decoration:none;font:600 12px/1 var(--font);padding:8px 10px;border-radius:999px;border:1px solid transparent}
#bar .right a:hover{color:var(--text);border-color:var(--rule);background:var(--panel)}
#help{width:34px;height:34px;border-radius:50%;border:1px solid var(--rule);background:var(--panel);color:var(--muted);font:700 14px/1 var(--font);cursor:pointer;margin-left:6px}
#help:hover,#help.on{color:var(--text);border-color:var(--text)}
#helpMenu,#shareMenu{position:absolute;top:46px;right:0;width:360px;background:var(--bg);border:1px solid var(--rule);border-radius:12px;padding:12px 14px;box-shadow:0 12px 36px rgba(0,0,0,.4);z-index:4;text-align:left}
#shareMenu{right:44px;width:340px}
#helpMenu[hidden],#shareMenu[hidden]{display:none}
#helpMenu h3,#shareMenu h3{margin:0 0 8px;font:700 12px/1 var(--font);color:var(--muted);letter-spacing:.06em;text-transform:uppercase}
#helpMenu ul{list-style:none;margin:0;padding:0}
#helpMenu li{display:flex;gap:10px;padding:5px 0;font:13px/1.4 var(--font);color:var(--text)}
#helpMenu kbd{flex:0 0 108px;color:var(--muted);font:600 12px/1.4 var(--font)}
#share{border:1px solid var(--accent);background:transparent;color:var(--accent);font:700 12px/1 var(--font);padding:8px 14px;border-radius:999px;cursor:pointer;margin-left:6px}
#share:hover,#share.on{background:var(--accent);color:var(--bg)}
#shareMenu .grid{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px}
#shareMenu .grid button,#shareMenu .grid a{display:block;text-align:center;border:1px solid var(--rule);background:var(--panel);color:var(--text);text-decoration:none;font:600 12px/1 var(--font);padding:9px 10px;border-radius:8px;cursor:pointer}
#shareMenu .grid button:hover,#shareMenu .grid a:hover{border-color:var(--accent);color:var(--accent)}
#localNote{display:none;margin:0;color:var(--muted);font:12px/1.45 var(--font)}
#toast{position:fixed;left:50%;bottom:26px;transform:translate(-50%,12px);opacity:0;transition:opacity .25s,transform .25s;background:var(--text);color:var(--bg);padding:9px 16px;border-radius:999px;font:600 13px/1 var(--font);z-index:5;pointer-events:none}
#toast.show{opacity:1;transform:translate(-50%,0)}
#brand{color:var(--muted);text-decoration:none;font:600 13px/1 var(--font);letter-spacing:.04em}
#brand:hover{color:var(--text)}
#controls{display:flex;align-items:center;gap:14px;padding:6px 10px 6px 6px;border:1px solid var(--rule);border-radius:999px;background:var(--panel)}
#controls.off{visibility:hidden}
#controls.locked{opacity:.45;cursor:not-allowed}
#controls.locked button,#controls.locked input{pointer-events:none}
#play{width:40px;height:40px;border-radius:50%;border:0;background:var(--accent);color:var(--bg);font:700 15px/1 var(--font);cursor:pointer;display:grid;place-items:center;box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 25%,transparent)}
#play:hover{filter:brightness(1.08)}
.end{border:0;background:transparent;color:var(--muted);font:700 15px/1 var(--font);padding:6px 4px;cursor:pointer;letter-spacing:.02em}
.end.on{color:var(--text)}
#scrub{-webkit-appearance:none;appearance:none;width:min(44vw,520px);height:6px;margin:0 4px;border-radius:999px;outline:none;cursor:pointer;
  background:linear-gradient(90deg,var(--accent) var(--pct,100%),var(--rule) var(--pct,100%))}
#scrub::-webkit-slider-thumb{-webkit-appearance:none;width:22px;height:22px;border-radius:50%;background:var(--accent);border:3px solid var(--bg);box-shadow:0 0 0 2px var(--accent);cursor:grab}
#scrub::-moz-range-thumb{width:16px;height:16px;border-radius:50%;background:var(--accent);border:3px solid var(--bg);box-shadow:0 0 0 2px var(--accent);cursor:grab}
#scrub:active::-webkit-slider-thumb{cursor:grabbing}
#stepLabel{color:var(--muted);font:600 12px/1 var(--font);min-width:84px;text-align:left}
#stepLabel[hidden]{display:none}
/* Narrow windows: the bar gives up its side links, then the brand and step label, rather than overflowing. */
@media (max-width:1180px){#bar .right a{display:none}#scrub{width:min(36vw,520px)}}
@media (max-width:820px){#bar{grid-template-columns:auto 1fr auto;padding:0 10px}#brand,#stepLabel{display:none}#scrub{width:min(40vw,520px)}}
#stage{padding:0 0 24px}
#scene{display:block;width:100%;height:auto;margin:0 auto;user-select:none}
#scene .dim{filter:opacity(.18)}
#scene .lit{opacity:1 !important}
#scene [data-role="commit"],#scene [data-role="commit-label"],#scene [data-role="commit-hit"],#scene [data-role="ref"]{cursor:pointer}
#tip{position:fixed;pointer-events:none;display:none;max-width:420px;background:var(--bg);color:var(--text);border:1px solid var(--rule);border-radius:10px;padding:10px 12px;font:13px/1.45 var(--font);box-shadow:0 8px 28px rgba(0,0,0,.35);z-index:3}
#tip .k{color:var(--muted)}
#tip .sha{color:var(--accent);font-weight:700}
#tip .msg{margin:4px 0 6px;white-space:pre-wrap}
#viewerNote{max-width:720px;margin:48px auto;padding:0 18px;color:var(--muted);font:14px/1.6 var(--font);text-align:center}
#viewerNote b{color:var(--text)}
#openedNote{max-width:960px;margin:14px auto 0;padding:10px 14px;display:flex;gap:12px;align-items:center;border:1px solid var(--rule);border-radius:10px;background:var(--panel);color:var(--muted);font:13px/1.5 var(--font)}
#openedNote b{color:var(--text)}
#openedNote code{font:12px/1.4 var(--font);color:var(--text);background:var(--bg);border:1px solid var(--rule);border-radius:5px;padding:1px 5px;word-break:break-all}
#openedNote button{margin-left:auto;flex:none;border:1px solid var(--rule);background:transparent;color:var(--muted);border-radius:6px;width:26px;height:26px;cursor:pointer;font:600 13px/1 var(--font)}
#openedNote button:hover{color:var(--accent);border-color:var(--accent)}
"""
)

VIEWER_JS = r"""
// git-sim interactive viewer. One copy lives in the git-sim package
// (git_sim/render/html.py) and is exported to initialcommit.com; edit it there.
//
// makeViewer(root) builds one viewer whose #id lookups are scoped to root, so a
// page can host several graphs, each in its own frame with its own header,
// stage and git-sim-meta. window.GitSimViewer is the document-wide instance
// (the hosted viewer, the lessons); GitSimViewer.instance(frame) makes another.
function makeViewer(root){
  const $ = (s, scope) => Array.from((scope || document).querySelectorAll(s));
  const byId = id => root.querySelector('#' + id);
  // Keyboard shortcuts belong to the document-wide viewer. Among embedded
  // viewers (a page with several graphs) they go to the one the pointer or the
  // focus is in, and otherwise to the one showing most in the viewport, so the
  // reader's keys always drive the graph they are looking at.
  const embeds = (window.__gitSimEmbeds = window.__gitSimEmbeds || []);
  if (root !== document && !embeds.includes(root)) embeds.push(root);
  const shown = el => {
    const r = el.getBoundingClientRect();
    return Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
  };
  const mine = () => {
    if (root === document) return true;
    const live = embeds.filter(r => r.isConnected);
    const engaged = live.find(r => r.matches(':hover') || r.contains(document.activeElement));
    if (engaged) return engaged === root;
    let best = null, most = 0;
    live.forEach(r => { const a = shown(r); if (a > most) { best = r; most = a; } });
    return best === root;
  };
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const b64url = bytes => { let s = ''; bytes.forEach(b => { s += String.fromCharCode(b); }); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); };
  const unb64url = text => Uint8Array.from(atob(text.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  async function deflate(text){
    const stream = new Blob([text]).stream().pipeThrough(new CompressionStream('deflate'));
    return b64url(new Uint8Array(await new Response(stream).arrayBuffer()));
  }
  async function inflate(b64){
    const stream = new Blob([unb64url(b64)]).stream().pipeThrough(new DecompressionStream('deflate'));
    return await new Response(stream).text();
  }
  function hashParams(){
    const raw = (location.hash || '').replace(/^#/, '');
    // A bare state (#before, #after, #step=N) or key=value pairs (d=, s=, p=, t=).
    if (!raw.includes('=') || /^step=\d+$/.test(raw)) return {s: raw};
    const out = {}; new URLSearchParams(raw).forEach((v, k) => { out[k] = v; }); return out;
  }
  function meta(){
    try { return JSON.parse(byId('git-sim-meta').textContent); } catch (e) { return {}; }
  }

  // ---- themes ---------------------------------------------------------------
  // A shared graph was generated in one theme; the page showing it may use the
  // other (the hosted viewer follows the site's dark/light setting). Every
  // theme color has a counterpart, so the graph is recolored by mapping.
  const PALETTES = __PALETTES__;
  const SVG_NS = 'http://www.w3.org/2000/svg';
  function colorMap(from, to){
    const a = PALETTES[from], b = PALETTES[to], map = {};
    Object.keys(a).forEach(k => {
      if (k === 'ref_text') return;  // handled per element: it collides with the dark background color
      if (Array.isArray(a[k])) a[k].forEach((c, i) => { if (b[k][i]) map[c.toUpperCase()] = b[k][i]; });
      else if (/^#/.test(a[k])) map[a[k].toUpperCase()] = b[k];
    });
    // Translucent table bands: white on dark, black on light.
    if (!map['#FFFFFF']) map['#FFFFFF'] = to === 'light' ? '#000000' : '#FFFFFF';
    if (!map['#000000']) map['#000000'] = to === 'dark' ? '#FFFFFF' : '#000000';
    return map;
  }
  function reshade(svg, to){
    // Dark mode glows discs in their own color; light mode drops a soft
    // neutral shadow under discs and pills. Filters are rebuilt for the target.
    const light = to === 'light';
    let defs = svg.querySelector('defs');
    if (!defs) { defs = document.createElementNS(SVG_NS, 'defs'); svg.insertBefore(defs, svg.firstChild); }
    const sample = svg.querySelector('feDropShadow');
    let scale = 135;  // pixels per scene unit, inferred from an existing shadow
    if (sample) { const sd = parseFloat(sample.getAttribute('stdDeviation')); const wasLight = Math.abs(parseFloat(sample.getAttribute('dy') || '0')) > 0.01; scale = sd / (wasLight ? 0.05 : 0.11) || 135; }
    $('filter', defs).forEach(f => f.remove());
    const make = (id, dy, sigma, color, opacity) => {
      const f = document.createElementNS(SVG_NS, 'filter');
      f.setAttribute('id', id); f.setAttribute('x', '-60%'); f.setAttribute('y', '-60%'); f.setAttribute('width', '220%'); f.setAttribute('height', '220%'); f.setAttribute('color-interpolation-filters', 'sRGB');
      const d = document.createElementNS(SVG_NS, 'feDropShadow');
      d.setAttribute('dx', '0'); d.setAttribute('dy', String(dy)); d.setAttribute('stdDeviation', String(sigma)); d.setAttribute('flood-color', color); d.setAttribute('flood-opacity', String(opacity));
      f.appendChild(d); defs.appendChild(f);
    };
    const ensure = (id, ...spec) => { if (!defs.querySelector('#' + id)) make(id, ...spec); return `url(#${id})`; };
    $('[filter]', svg).forEach(el => {
      if (el.dataset.role === 'ref') { if (light) el.setAttribute('filter', ensure('shadow-pill', 0.02 * scale, 0.03 * scale, '#000000', .14)); else el.removeAttribute('filter'); return; }
      if (light) el.setAttribute('filter', ensure('shadow-drop', 0.035 * scale, 0.05 * scale, '#000000', .16));
      else { const c = (el.getAttribute('fill') || PALETTES.dark.commit).toUpperCase(); el.setAttribute('filter', ensure('glow-' + c.slice(1), 0, 0.11 * scale, c, .45)); }
    });
    if (light) $('rect[data-role="ref"]:not([filter])', svg).forEach(el => el.setAttribute('filter', ensure('shadow-pill', 0.02 * scale, 0.03 * scale, '#000000', .14)));
  }
  function retheme(svg, from, to){
    if (!svg || from === to || !PALETTES[from] || !PALETTES[to]) return;
    const map = colorMap(from, to);
    const attrs = ['fill', 'stroke', 'flood-color', 'data-before-fill', 'data-before-stroke', 'data-after-fill', 'data-after-stroke'];
    $('*', svg).forEach(el => attrs.forEach(a => { const v = el.getAttribute(a); if (v) { const m = map[v.toUpperCase()]; if (m) el.setAttribute(a, m); } }));
    $('text[data-role="ref"]', svg).forEach(t => t.setAttribute('fill', PALETTES[to].ref_text));
    $('[data-role="background"]', svg).forEach(r => r.setAttribute('fill', PALETTES[to].bg));
    // The dark accent is also the dark commit hue, so the title underline is set explicitly.
    $('line[data-role="title"]', svg).forEach(l => l.setAttribute('stroke', PALETTES[to].accent));
    reshade(svg, to);
    svg.dataset.theme = to;
  }
  function setTheme(to){
    const svg = byId('scene');
    const info = meta();
    const from = (svg && svg.dataset.theme) || info.svg_theme || info.theme || 'dark';
    retheme(svg, from, to);
    document.documentElement.dataset.theme = to;
  }

  // initialcommit.com's dark / light toggle is a cookie its header sets and
  // then reloads the page. Reading it here as well means the graph follows the
  // toggle even when the page itself was served without it (older or cached).
  function siteTheme(){
    const m = /(?:^|;\s*)dark-mode=(true|false)\b/.exec(document.cookie || '');
    return m ? (m[1] === 'true' ? 'dark' : 'light') : '';
  }

  // git-sim opened this page here on the user's behalf (#p= carries the path
  // of the copy it saved): say so, and say how to open that file instead.
  function openedNote(localPath){
    const stage = byId('stage');
    if (!stage || byId('openedNote')) return;
    const note = document.createElement('div');
    note.id = 'openedNote';
    note.setAttribute('role', 'note');
    const text = document.createElement('span');
    text.innerHTML = '<b>Opened here by git-sim.</b> No user, git or codebase data was sent to our server: the graph travels inside the link’s #fragment, which stays in your browser. The page is also saved on your machine as <code></code> in your git-sim media folder. To open that file instead, run with <code>--open-in local</code>, or set <code>git_sim_open_in=local</code> to make it the default.';
    text.querySelector('code').textContent = String(localPath).split(/[\\/]/).pop();
    const close = document.createElement('button');
    close.title = 'dismiss'; close.textContent = '✕';
    close.addEventListener('click', () => { note.remove(); window.dispatchEvent(new Event('git-sim:layout')); });
    note.append(text, close);
    stage.parentNode.insertBefore(note, stage);
  }

  // Hosted viewer: the graph arrives compressed in the URL fragment (#d=...),
  // so it never reaches the server; the query string only carried the
  // command and a short text graph for the preview card.
  // boot({demo, title}) shows a canned graph (an SVG at the demo URL) when
  // the link carries none, which is how the tool page doubles as the viewer.
  async function boot(options){
    options = options || {};
    const params = hashParams();
    const demo = !params.d && options.demo ? options.demo : null;
    document.documentElement.dataset.mode = params.d ? 'shared' : demo ? 'demo' : 'empty';
    const note = byId('viewerNote');
    // When the graph cannot be shown, fall back to the text graph the link
    // carried for its preview card (the only other thing we have).
    const fail = message => {
      if (!note) return;
      const summary = meta().summary || '';
      const plain = s => String(s).replace(/[&<>]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;'}[c]));
      note.innerHTML = message + (summary ? '<pre style="text-align:left;white-space:pre;overflow-x:auto;margin:24px 0 0;color:var(--muted)">' + plain(summary) + '</pre>' : '');
    };
    if (!params.d && !demo) { fail('<b>Nothing to show.</b> This page displays a git-sim simulation shared as a link; the link you followed has no graph in it.'); return; }
    if (!demo && typeof DecompressionStream === 'undefined') { fail('<b>This browser cannot open the link.</b> Shared git-sim graphs need a browser with DecompressionStream (Chrome 80+, Edge 80+, Firefox 113+, Safari 16.4+).'); return; }
    try {
      const svgText = demo ? await (await fetch(demo)).text() : await inflate(params.d);
      if (note) note.remove();
      if (params.d && params.p) openedNote(params.p);  // before init, so the fit accounts for it
      mount(svgText, {title: demo ? options.title : ''});
    } catch (e) {
      fail('<b>Could not open this link.</b> The graph data in it is damaged or truncated (some apps cut long links). Ask for the link again, or for the image.');
    }
  }

  // ---- mounting a graph -------------------------------------------------------
  // One graph is shown at a time. mount() puts an SVG (as text) on the stage
  // and starts the viewer on it; a graph already there is disposed of first,
  // listeners and playback included, so a page can show one graph after
  // another (a lesson stepping through a scenario) without leaks.
  // options: title (the command, for the share text), svgTheme (the theme the
  // graph was drawn in), state ('before', 'after', 'step=N'; else it plays).
  let dispose = null;      // tears down the viewer currently on the stage
  let pendingState = null; // the state the next init() opens on, when mount() sets one
  let pendingLocked = false; // whether the next init() starts with its playback controls locked
  let control = null;      // the playback of the graph on the stage, for a host page (a lesson's terminal)
  function mount(svgText, options){
    options = options || {};
    if (dispose) { try { dispose(); } catch (e) {} dispose = null; }
    const doc = new DOMParser().parseFromString(svgText, 'image/svg+xml');
    const svgEl = doc.documentElement;
    if (svgEl.nodeName !== 'svg') throw new Error('not an svg');
    $('script', svgEl).forEach(el => el.remove());
    svgEl.querySelectorAll('*').forEach(el => { Array.from(el.attributes).forEach(a => { if (/^on/i.test(a.name) || (a.name === 'href' && !a.value.startsWith('data:image/'))) el.removeAttribute(a.name); }); });
    svgEl.id = 'scene';
    const stage = byId('stage');
    stage.innerHTML = ''; stage.appendChild(document.importNode(svgEl, true));
    if (options.title) {  // this graph's command stands in for the page's
      const el = byId('git-sim-meta');
      if (el) { try { const j = JSON.parse(el.textContent); j.title = options.title; el.textContent = JSON.stringify(j); } catch (e) {} }
    }
    // The graph says which theme drew it (its own data-theme, since git-sim
    // draws light by default; older graphs carry none and were drawn dark);
    // the page says which it shows.
    const info = meta();
    const shown = byId('scene');
    shown.dataset.theme = shown.dataset.theme || options.svgTheme || info.svg_theme || info.theme || 'dark';
    const want = siteTheme() || info.theme;
    if (want && shown.dataset.theme !== want) retheme(shown, shown.dataset.theme, want);
    if (want) document.documentElement.dataset.theme = want;
    pendingState = options.state || null;
    pendingLocked = !!options.locked;
    try { init(); } finally { pendingState = null; pendingLocked = false; }
  }
  // load(url | svgText, options): fetch when given a URL, then mount.
  async function load(source, options){
    const text = /^\s*</.test(source) ? source : await (await fetch(source)).text();
    mount(text, options);
  }
  // unmount(): take the graph down and leave the stage empty (a lesson shows a
  // message there when git would refuse the command instead of drawing it).
  function unmount(){
    if (dispose) { try { dispose(); } catch (e) {} dispose = null; }
    const stage = byId('stage');
    if (stage) stage.innerHTML = '';
  }

  function init(){
  const svg = byId('scene');
  if (!svg) return;
  const stage = byId('stage');
  const tip = byId('tip');
  const info = meta();
  // Every listener on something that outlives the graph (the document, the
  // window, the bar's controls) is recorded so mount() can remove it.
  const offs = [];
  const on = (target, type, fn, opts) => { target.addEventListener(type, fn, opts); offs.push(() => target.removeEventListener(type, fn, opts)); };
  const pristine = svg.outerHTML;  // the graph as generated, before the scrubber touches it
  const pristineTheme = svg.dataset.theme || meta().theme || 'dark';  // the theme pristine is drawn in

  // ---- the operation as a continuous progress value ------------------------
  // progress runs from 0 (before) to maxStep (after). An element that belongs
  // to step k goes from its before state to its after state while progress
  // travels from k-1 to k, so dragging the scrubber plays the command.
  const after = $('[data-phase="after"]', svg);
  const removed = $('[data-phase="removed"]', svg);
  const moved = $('[data-dx]', svg);
  const recolored = $('[data-before-fill]', svg);
  let maxStep = 1;
  [...after, ...removed, ...moved, ...recolored].forEach(el => { const s = parseInt(el.dataset.step || '0', 10); if (s > maxStep) maxStep = s; });
  const stepOf = el => parseInt(el.dataset.step || '0', 10) || maxStep;
  const amount = (el, p) => clamp(p - (stepOf(el) - 1), 0, 1);
  const hex = c => { const m = /^#?([0-9a-f]{6})$/i.exec((c || '').trim()); return m ? [0, 2, 4].map(i => parseInt(m[1].slice(i, i + 2), 16)) : null; };
  const mix = (a, b, t) => { const A = hex(a), B = hex(b); if (!A || !B) return t < .5 ? a : b; return '#' + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, '0')).join(''); };
  recolored.forEach(el => { el.dataset.afterFill = el.getAttribute('fill') || ''; el.dataset.afterStroke = el.getAttribute('stroke') || ''; });

  // ---- hit areas ------------------------------------------------------------
  // A commit is drawn as a disc, an id and a message with gaps between them.
  // One transparent rectangle per commit, spanning all three, sits behind
  // them so the pointer, tooltip and highlight treat the gaps as part of the
  // commit instead of as empty space.
  const commitOf = new Map();
  $('[data-role="commit"]', svg).forEach(el => { if (el.dataset.sha) commitOf.set(el.dataset.sha, el); });
  const hits = new Map();
  {
    const boxes = new Map();
    $('[data-role="commit"],[data-role="commit-label"]', svg).forEach(el => {
      const sha = el.dataset.sha;
      if (!sha) return;
      let b;
      try { b = el.getBBox(); } catch (e) { return; }
      if (!b || (!b.width && !b.height)) return;
      const cur = boxes.get(sha) || {x: Infinity, y: Infinity, r: -Infinity, b: -Infinity};
      cur.x = Math.min(cur.x, b.x); cur.y = Math.min(cur.y, b.y);
      cur.r = Math.max(cur.r, b.x + b.width); cur.b = Math.max(cur.b, b.y + b.height);
      boxes.set(sha, cur);
    });
    const anchor = svg.querySelector('[data-role="background"]') || svg.querySelector('defs');
    boxes.forEach((b, sha) => {
      const pad = 6, hit = document.createElementNS(SVG_NS, 'rect');
      hit.setAttribute('x', b.x - pad); hit.setAttribute('y', b.y - pad);
      hit.setAttribute('width', b.r - b.x + 2 * pad); hit.setAttribute('height', b.b - b.y + 2 * pad);
      hit.setAttribute('fill', 'transparent');
      hit.dataset.role = 'commit-hit'; hit.dataset.sha = sha;
      if (anchor) anchor.after(hit); else svg.prepend(hit);
      hits.set(sha, hit);
    });
  }
  // A commit hidden by the scrubber takes its hit area with it.
  const syncHits = () => hits.forEach((hit, sha) => { const c = commitOf.get(sha); hit.style.pointerEvents = c && parseFloat(c.style.opacity || '1') < .5 ? 'none' : ''; });

  const scrub = byId('scrub');
  const stepLabel = byId('stepLabel');
  const showSteps = !!document.documentElement.dataset.live;
  stepLabel.hidden = !showSteps;
  if (!showSteps) stepLabel.textContent = '';
  const btnBefore = byId('toBefore'), btnAfter = byId('toAfter');
  const play = byId('play');
  const RES = 1000;
  scrub.max = String(maxStep * RES);
  let progress = 0;  // the page opens on "before" and plays forward from there

  // "Copied from" links (rebase, cherry-pick) matter while their commit
  // appears; afterwards they fade out completely, so the finished graph and
  // every whole step of it show nothing half-transparent. Hovering a commit
  // brings its links back (see highlight).
  // A trail belonging to the last step fades in that step's final stretch,
  // since progress never goes past it; any other trail fades during the step
  // after its own and is gone by the end of it.
  const trailFade = el => {
    const s = stepOf(el);
    return s >= maxStep ? [s - 0.15, 0.15] : [s + 0.35, 0.65];
  };
  const isOrigin = el => el.dataset.role === 'edge' && el.dataset.kind === 'origin';
  const isLane = el => el.dataset.role === 'edge' && el.dataset.kind !== 'origin';
  // An arrow draws itself tail to tip: its line grows and the head rides the
  // growing end. The exporter emits the head polygon right after its line
  // with the same tags, which is how the two are paired here.
  const heads = new Map();  // head polygon -> the line or path it belongs to
  const isCurve = el => el.tagName === 'path' || el.tagName === 'polyline';  // a curved arrow's body
  after.filter(el => isLane(el) && (el.tagName === 'line' || isCurve(el))).forEach(el => {
    let len = 0;
    try { len = isCurve(el) ? el.getTotalLength() : Math.hypot(el.x2.baseVal.value - el.x1.baseVal.value, el.y2.baseVal.value - el.y1.baseVal.value); } catch (e) {}
    if (len > 0) el.dataset.len = len;
    const head = el.nextElementSibling;
    if (len > 0 && head && head.tagName === 'polygon' && isLane(head) && head.dataset.step === el.dataset.step) heads.set(head, el);
  });
  // Where a line's drawn end is when a fraction t of it has been drawn.
  const pointAt = (line, t) => {
    if (isCurve(line)) { const p = line.getPointAtLength(parseFloat(line.dataset.len) * t); return [p.x, p.y]; }
    const x1 = line.x1.baseVal.value, y1 = line.y1.baseVal.value;
    return [x1 + (line.x2.baseVal.value - x1) * t, y1 + (line.y2.baseVal.value - y1) * t];
  };
  // A file entry an arrow in the zone table points at is pushed along by the
  // head: it appears beside the file it came from and travels just ahead of
  // the head, keeping their final spacing all the way. (Only table arrows,
  // which carry no data-src; a graph arrow may end on a commit that slides
  // for its own reasons.)
  const pushed = new Map();  // file text -> the line pushing it
  {
    const files = moved.filter(el => el.dataset.role === 'file' && el.dataset.phase === 'after');
    heads.forEach((line, head) => {
      if (line.dataset.src || line.tagName !== 'line') return;
      const [ex, ey] = pointAt(line, 1), dir = Math.sign(line.x2.baseVal.value - line.x1.baseVal.value) || 1;
      let reach = 40; try { reach = head.getBBox().width * 2.5 + 10; } catch (e) {}
      let best = null, bestGap = Infinity;
      files.forEach(f => {
        let b; try { b = f.getBBox(); } catch (e) { return; }
        if (!b.width || Math.abs(b.y + b.height / 2 - ey) > b.height * 0.6) return;
        const gap = dir > 0 ? b.x - ex : ex - (b.x + b.width);
        if (gap >= 0 && gap < reach && gap < bestGap) { best = f; bestGap = gap; }
      });
      if (best) pushed.set(best, line);
    });
  }
  // The head, drawn at the line's final end, moved back to the drawn end
  // (and, on a curve, turned to follow the tangent there).
  function placeHead(head, line, t){
    if (t >= 1) { head.removeAttribute('transform'); return; }
    const [ex, ey] = pointAt(line, 1), [px, py] = pointAt(line, t);
    let turn = '';
    if (isCurve(line)) {
      const [qx, qy] = pointAt(line, Math.max(t - 0.02, 0)), [rx, ry] = pointAt(line, 0.98);
      const deg = (Math.atan2(py - qy, px - qx) - Math.atan2(ey - ry, ex - rx)) * 180 / Math.PI;
      turn = ` rotate(${deg} ${ex} ${ey})`;
    }
    head.setAttribute('transform', `translate(${px - ex} ${py - ey})${turn}`);
  }
  // A copy made by rebase or cherry-pick appears at the commit it came from
  // and slides to its place (its data-dx/dy point back at the source).
  const slides = new Set(moved.filter(el => el.dataset.phase === 'after'));
  function render(){
    after.forEach(el => {
      const a = amount(el, progress);
      let o = a;
      if (isOrigin(el)) {
        // The dotted trail lights up dot by dot as the copy passes; the head last.
        const t = el.dataset.t !== undefined ? parseFloat(el.dataset.t) : 1;
        o = a > 0 && a >= t - 1e-6 ? 1 : 0;
        const [from, span] = trailFade(el);
        o *= 1 - clamp((progress - from) / span, 0, 1);
      } else if (heads.has(el)) {
        placeHead(el, heads.get(el), a);  // the head rides the growing line
        o = a > 0 ? 1 : 0;
      } else if (isLane(el)) {
        const len = parseFloat(el.dataset.len || '0');
        if (len > 0) { el.style.strokeDasharray = `${len}`; el.style.strokeDashoffset = `${len * (1 - a)}`; o = a > 0 ? 1 : 0; }
        else o = a > .85 ? 1 : 0;  // a head whose line could not be measured
      } else if (slides.has(el)) {
        // visible almost at once, then on its way; a pushed file fades in
        // while it is still beside the entry it came from
        o = clamp(a / (pushed.has(el) ? 0.3 : 0.15), 0, 1);
      }
      el.style.opacity = o; el.style.pointerEvents = o < .5 ? 'none' : '';
    });
    removed.forEach(el => { const a = 1 - amount(el, progress); el.style.opacity = a; el.style.pointerEvents = a < .5 ? 'none' : ''; });
    syncHits();
    moved.forEach(el => {
      const a = amount(el, progress), back = 1 - a;
      const line = pushed.get(el);
      if (line) {  // rides with the arrowhead
        const [ex, ey] = pointAt(line, 1), [px, py] = pointAt(line, a);
        el.style.transform = back > 0 ? `translate(${px - ex}px, ${py - ey}px)` : '';
        return;
      }
      el.style.transform = back > 0 ? `translate(${el.dataset.dx * back}px, ${el.dataset.dy * back}px)` : '';
    });
    recolored.forEach(el => {
      const a = amount(el, progress);
      if (el.dataset.afterFill) el.setAttribute('fill', mix(el.dataset.beforeFill, el.dataset.afterFill, a));
      if (el.dataset.afterStroke) el.setAttribute('stroke', mix(el.dataset.beforeStroke || el.dataset.beforeFill, el.dataset.afterStroke, a));
    });
    scrub.value = String(Math.round(progress * RES));
    scrub.style.setProperty('--pct', (100 * progress / maxStep) + '%');
    btnBefore.classList.toggle('on', progress <= 0.001);
    btnAfter.classList.toggle('on', progress >= maxStep - 0.001);
    // The step counter only earns its place on the live page, where a change
    // is several steps (removals, moves, arrivals); a simulation's Before and
    // After buttons already say where the slider is.
    if (showSteps && maxStep > 1) {
      stepLabel.textContent = progress <= 0.001 ? 'before' : progress >= maxStep - 0.001 ? 'after' : `step ${Math.ceil(progress - 0.001)} / ${maxStep}`;
    }
  }
  function setProgress(p){ progress = clamp(p, 0, maxStep); render(); }

  // ---- play: loop before -> after -> before; any manual input takes over ---
  let playing = false, raf = null, hold = null;
  const ease = t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  function tween(to, ms, then){
    const from = progress, t0 = performance.now();
    const frame = now => {
      if (!playing) return;
      const t = clamp((now - t0) / ms, 0, 1);
      setProgress(from + (to - from) * ease(t));
      if (t < 1) raf = requestAnimationFrame(frame); else if (then) hold = setTimeout(then, then === backward ? 1400 : 1000);
    };
    raf = requestAnimationFrame(frame);
  }
  // Long sequences (commits, then arrows, then labels) get quicker beats so
  // a whole pass stays around five seconds.
  const perStep = clamp(4500 / maxStep, 380, 900);
  function forward(){ tween(maxStep, perStep * Math.max(1, maxStep - progress) + 200, backward); }
  function backward(){ tween(0, 700 + 120 * maxStep, forward); }
  function startPlay(){
    if (playing) return;
    playing = true; play.innerHTML = '&#10074;&#10074;'; play.title = 'pause (A)';
    if (progress >= maxStep - 0.001) { setProgress(0); }
    forward();
  }
  function stopPlay(){
    playing = false; cancelAnimationFrame(raf); clearTimeout(hold);
    play.innerHTML = '&#9654;'; play.title = 'play the command from before to after, on a loop (A)';
  }
  // A host page can play the command once, before to after, and leave it there
  // (a lesson does this when the learner types the command), or pin a state.
  function playOnce(then){
    stopPlay();
    if (!animatable) { if (then) then(); return; }
    setProgress(0);
    playing = true; play.innerHTML = '&#10074;&#10074;'; play.title = 'pause (A)';
    tween(maxStep, perStep * maxStep + 200, () => { stopPlay(); if (then) then(); });
  }
  // A host page can lock the playback controls (a lesson does until the
  // learner has typed the command, so "After" cannot stand in for typing it):
  // the bar's buttons, the slider and the shortcuts do nothing; playOnce and
  // setState, which the page itself calls, still work.
  let locked = false;
  const controls = byId('controls');
  function setLocked(v){
    locked = !!v;
    if (locked) stopPlay();
    controls.classList.toggle('locked', locked);
    controls.title = locked ? 'Type the command in the terminal to play it' : '';
    [play, btnBefore, btnAfter, scrub].forEach(el => { el.disabled = locked; });
  }
  control = {
    playOnce, setLocked,
    setState: s => { stopPlay(); setProgress(s === 'after' ? maxStep : s === 'before' ? 0 : clamp(parseInt(String(s).replace(/^step=/, ''), 10) || 0, 0, maxStep)); },
    // A host that drives the animation itself (the live page recording a video) sets a fractional progress.
    setProgress: p => { stopPlay(); setProgress(p); },
    steps: () => maxStep,
    animatable: () => animatable,
  };
  // Manual controls never wait for the loop: they stop it and apply at once.
  const manual = fn => (...args) => { if (locked) return; stopPlay(); fn(...args); };
  play.onclick = () => { if (locked) return; playing ? stopPlay() : startPlay(); };
  btnBefore.onclick = manual(() => setProgress(0));
  btnAfter.onclick = manual(() => setProgress(maxStep));
  on(scrub, 'input', manual(() => setProgress(parseInt(scrub.value, 10) / RES)));
  on(scrub, 'pointerdown', () => stopPlay());

  const animatable = after.length + removed.length + moved.length + recolored.length > 0;
  controls.classList.toggle('off', !animatable);
  if (pendingLocked) setLocked(true);
  const params = hashParams();
  const state = pendingState !== null ? pendingState : (params.s || '');
  const pinned = /^(before|after|step=\d+)$/.test(state);
  // Opens on "before" and plays, unless the link pins a state (#before,
  // #after, #step=N). A graph nothing changes in just shows its one state.
  if (state === 'after' || !animatable) progress = maxStep;
  else if (/^step=\d+$/.test(state)) progress = clamp(parseInt(state.slice(5), 10), 0, maxStep);
  else progress = 0;
  render();
  if (animatable && !pinned) startPlay();

  on(document, 'keydown', e => {
    if (!mine()) return;
    // Typing in a field on the host page is never a shortcut here.
    const t = e.target;
    if (t && t !== scrub && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable)) return;
    if (e.target === scrub && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); }
    if (e.key === 'Escape') { stopPlay(); resetView(); return; }
    if (!animatable || locked) return;
    if (e.key === 'a' || e.key === 'A') { playing ? stopPlay() : startPlay(); return; }
    if (e.key === 'ArrowLeft') manual(() => setProgress(Math.ceil(progress - 0.001) - 1))();
    else if (e.key === 'ArrowRight') manual(() => setProgress(Math.floor(progress + 0.001) + 1))();
    // The page-wide viewer shown as one exhibit among a page's content (the tools
    // page, a lesson) leaves the space bar to the page; a graph embedded in an
    // article takes it, since the reader's eye is on the graph they are over.
    else if (e.key === ' ' && (root !== document || document.documentElement.dataset.mode !== 'demo')) { e.preventDefault(); manual(() => setProgress(progress >= maxStep - 0.001 ? 0 : maxStep))(); }
  });

  // ---- ancestry highlight + tooltip ---------------------------------------
  // Ancestry follows the drawn graph (the arrows between discs), so a "..."
  // placeholder still links the commits on either side of it; a commit's real
  // parents count too when they are drawn.
  const drawn = new Set($('[data-role="commit"]', svg).map(el => el.dataset.sha));
  const parents = {};
  const link = (a, b) => { if (!a || !b || a === b || !drawn.has(b)) return; const list = parents[a] = parents[a] || []; if (!list.includes(b)) list.push(b); };
  $('[data-role="edge"]', svg).forEach(el => link(el.dataset.src, el.dataset.dst));
  $('[data-role="commit"]', svg).forEach(el => (el.dataset.parents || '').split(/\s+/).filter(Boolean).forEach(q => link(el.dataset.sha, q)));
  function ancestry(sha){
    const seen = new Set(); const stack = [sha];
    while (stack.length) { const s = stack.pop(); if (seen.has(s)) continue; seen.add(s); (parents[s] || []).forEach(p => stack.push(p)); }
    return seen;
  }
  function highlight(sha){
    const keep = ancestry(sha);
    $('[data-role="commit"],[data-role="commit-label"]', svg).forEach(el => el.classList.toggle('dim', !keep.has(el.dataset.sha)));
    $('[data-role="edge"]', svg).forEach(el => {
      const linked = keep.has(el.dataset.src) && keep.has(el.dataset.dst);
      el.classList.toggle('dim', !linked);
      // A settled "copied from" link touching the hovered commit lights back up.
      el.classList.toggle('lit', isOrigin(el) && amount(el, progress) > .5 && (el.dataset.src === sha || el.dataset.dst === sha));
    });
  }
  function clearHighlight(){ $('.dim,.lit', svg).forEach(el => el.classList.remove('dim', 'lit')); }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  function describe(el){
    const d = el.dataset;
    if (d.role === 'commit' || d.role === 'commit-label' || d.role === 'commit-hit') {
      const c = $('[data-role="commit"][data-sha="' + d.sha + '"]', svg)[0];
      const data = c ? c.dataset : d;
      if (data.kind === 'elided') return `<div class="msg">${esc(data.message || '')}</div><div class="k">stands for the commits between its neighbours</div>`;
      return `<div class="sha">${esc(data.sha)}</div><div class="msg">${esc(data.message || '')}</div>` +
        `<div><span class="k">author</span> ${esc(data.author || '')}</div>` +
        (data.date ? `<div><span class="k">date</span> ${esc(data.date)}</div>` : '') +
        `<div><span class="k">parents</span> ${esc((data.parents || '').split(/\s+/).filter(Boolean).map(p => p.slice(0, 7)).join(', ') || 'none')}</div>` +
        (data.kind === 'merge' ? '<div><span class="k">merge commit</span></div>' : '') +
        (data.phase === 'after' ? '<div><span class="k">simulated by this command</span></div>' : '') +
        '<div class="k">click to copy sha</div>';
    }
    if (d.role === 'ref') return `<div class="sha">${esc(d.name)}</div><div><span class="k">${esc(d.kind || 'ref')}</span>${d.phase === 'after' ? ' · simulated' : d.phase === 'removed' ? ' · removed by this command' : ''}</div>`;
    if (d.role === 'file') return `<div class="sha">${esc(d.name)}</div><div><span class="k">${esc(d.column || '')}</span>${d.phase === 'after' ? ' · after the command' : ''}</div>`;
    return '';
  }
  // A commit is a disc, an id and a message with gaps between them. Crossing a
  // gap must not flash the highlight off and on, so leaving an element only
  // schedules the clear, and reaching another part of the same commit (or any
  // commit) within the grace period cancels it.
  let hoverSha = null, clearTimer = null;
  function clearNow(){ clearTimeout(clearTimer); clearTimer = null; hoverSha = null; tip.style.display = 'none'; clearHighlight(); }
  function scheduleClear(){ if (clearTimer === null) clearTimer = setTimeout(clearNow, 320); }
  svg.addEventListener('mousemove', e => {
    const el = e.target.closest('[data-role="commit"],[data-role="commit-label"],[data-role="commit-hit"],[data-role="ref"],[data-role="file"]');
    const shown = el && (el.dataset.role === 'commit-hit' ? commitOf.get(el.dataset.sha) || el : el);
    // Truly empty space: the tooltip goes at once (so it never trails the
    // pointer), the highlight only after the grace period.
    if (!el || parseFloat(shown.style.opacity || '1') < .5) { tip.style.display = 'none'; scheduleClear(); return; }
    const content = describe(el);
    if (!content) { tip.style.display = 'none'; scheduleClear(); return; }
    clearTimeout(clearTimer); clearTimer = null;
    tip.innerHTML = content; tip.style.display = 'block';
    const x = Math.min(e.clientX + 16, window.innerWidth - tip.offsetWidth - 12);
    const y = Math.min(e.clientY + 16, window.innerHeight - tip.offsetHeight - 12);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
    const sha = el.dataset.sha || null;
    if (sha !== hoverSha) { hoverSha = sha; if (sha) highlight(sha); else clearHighlight(); }
  });
  svg.addEventListener('mouseleave', clearNow);
  svg.addEventListener('click', e => {
    const el = e.target.closest('[data-sha]');
    if (!el || !navigator.clipboard) return;
    navigator.clipboard.writeText(el.dataset.sha).then(() => {
      tip.innerHTML = `<div class="sha">${esc(el.dataset.sha)}</div><div class="k">copied</div>`;
      clearTimeout(tipTimer); tipTimer = setTimeout(() => { tip.style.display = 'none'; }, 900);
    }).catch(() => {});
  });

  // ---- zoom -------------------------------------------------------------------
  // The initial viewBox frames the content; zooming changes it. Plain wheel
  // scrolls the page like any web page; ctrl/cmd + wheel (which is also what
  // a trackpad pinch sends) zooms around the cursor; double-click resets.
  const base = svg.viewBox.baseVal;
  const vb0 = {x: base.x, y: base.y, w: base.width, h: base.height};
  let vb = {...vb0};
  function setView(){ svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`); }
  function resetView(){ vb = {...vb0}; setView(); }
  function toScene(cx, cy){
    const r = svg.getBoundingClientRect();
    const k = Math.max(vb.w / r.width, vb.h / r.height);
    const ox = (r.width - vb.w / k) / 2, oy = (r.height - vb.h / k) / 2;
    return {x: vb.x + (cx - r.left - ox) * k, y: vb.y + (cy - r.top - oy) * k, k};
  }
  on(stage, 'wheel', e => {
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const f = Math.exp(e.deltaY * 0.0015);
    const p = toScene(e.clientX, e.clientY);
    const nw = Math.min(vb0.w * 4, Math.max(vb0.w / 12, vb.w * f));
    const s = nw / vb.w;
    vb = {x: p.x - (p.x - vb.x) * s, y: p.y - (p.y - vb.y) * s, w: nw, h: vb.h * s};
    setView();
  }, {passive: false});
  on(stage, 'dblclick', resetView);

  // ---- fit ------------------------------------------------------------------
  // The graph fills the width, which suits the usual five commits plus a zone
  // table. A taller graph (several lanes, no table) would then run past the
  // bottom of the window, so it is scaled down until it fits the space the
  // stage actually has, below whatever sits above it (the bar, a note, the
  // site's own header), but never below about half size: past that,
  // scrolling beats squinting.
  function fit(){
    // A demo graph sits below an introduction on purpose; it is read by
    // scrolling, so it keeps its natural size.
    if (document.documentElement.dataset.mode === 'demo') { svg.style.height = ''; return; }
    const natural = stage.clientWidth * vb0.h / vb0.w;
    const top = stage.getBoundingClientRect().top + window.scrollY;  // as if scrolled to the top
    const available = window.innerHeight - top - 24;
    svg.style.height = (available > 240 && natural > available) ? Math.max(available, natural * 0.55) + 'px' : '';
  }
  fit();
  on(window, 'resize', fit);
  on(window, 'git-sim:layout', fit);

  // ---- help menu --------------------------------------------------------------
  const help = byId('help'), helpMenu = byId('helpMenu');
  const showHelp = on => { helpMenu.hidden = !on; help.classList.toggle('on', on); };
  help.onclick = e => { e.stopPropagation(); showHelp(helpMenu.hidden); };
  on(document, 'click', e => { if (!helpMenu.hidden && !helpMenu.contains(e.target)) showHelp(false); });
  on(document, 'keydown', e => { if (!mine()) return; if (e.key === 'Escape') showHelp(false); if (e.key === '?') showHelp(helpMenu.hidden); });

  // ---- share ---------------------------------------------------------------------
  const shareBtn = byId('share'), shareMenu = byId('shareMenu');
  const toast = byId('toast');
  let toastTimer = null;
  const say = msg => { toast.textContent = msg; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 1900); };
  const showShare = on => { shareMenu.hidden = !on; shareBtn.classList.toggle('on', on); if (on) showHelp(false); };
  shareBtn.onclick = e => { e.stopPropagation(); showShare(shareMenu.hidden); };
  on(document, 'click', e => { if (!shareMenu.hidden && !shareMenu.contains(e.target)) showShare(false); });
  on(document, 'keydown', e => { if (e.key === 'Escape') showShare(false); });
  // The command: from the page's meta, else from the link's fragment (git-sim
  // opening the hosted viewer keeps it out of the query string).
  const title = (info.title && info.title !== 'git-sim' ? info.title : '') || params.t || document.title;
  if (params.t && (!info.title || info.title === 'git-sim')) document.title = params.t + ' — simulated with git-sim';
  // The state a copied link pins. While the loop is playing nothing is pinned,
  // so whoever opens the link sees it play from "before" too.
  const stateHash = () => playing ? '' : progress <= 0.001 ? 'before' : progress >= maxStep - 0.001 ? 'after' : 'step=' + Math.round(progress);
  const shareText = () => `${title} — simulated with git-sim`;
  const fileName = () => (title.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'git-sim');
  const canPack = typeof CompressionStream !== 'undefined';
  // A link to the hosted viewer: command + short text graph in the query
  // (for the preview card), the whole graph compressed in the fragment.
  async function shareUrl(){
    const s = stateHash();
    if (params.d) {  // already on the hosted viewer: keep the graph, update the state
      const p = new URLSearchParams(location.hash.replace(/^#/, ''));
      if (s) p.set('s', s); else p.delete('s');
      p.delete('p');  // the local path only means something on this machine
      return location.href.split('#')[0] + '#' + p.toString();
    }
    if (!info.viewer_url || !canPack) return location.href.split('#')[0] + (s ? '#' + s : '');
    const q = new URLSearchParams({t: title, m: pristineTheme});
    if (info.summary) q.set('g', await deflate(info.summary));
    const frag = new URLSearchParams({d: await deflate(pristine)});
    if (s) frag.set('s', s);
    return `${info.viewer_url}?${q}#${frag}`;
  }
  async function toPng(scale){
    // Rasterize the SVG as it is right now (current slider position included).
    const clone = svg.cloneNode(true);
    clone.setAttribute('viewBox', `${vb0.x} ${vb0.y} ${vb0.w} ${vb0.h}`);
    clone.setAttribute('width', Math.round(vb0.w * scale)); clone.setAttribute('height', Math.round(vb0.h * scale));
    const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], {type: 'image/svg+xml;charset=utf-8'}));
    try {
      const img = await new Promise((ok, fail) => { const i = new Image(); i.onload = () => ok(i); i.onerror = fail; i.src = url; });
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(vb0.w * scale); canvas.height = Math.round(vb0.h * scale);
      canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
      return await new Promise(ok => canvas.toBlob(ok, 'image/png'));
    } finally { URL.revokeObjectURL(url); }
  }
  const download = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 3000); };
  const actions = {
    link: async () => {
      const url = await shareUrl();
      await navigator.clipboard.writeText(url);
      say(url.length > 60000 ? 'link copied — it is long; chat and email carry it, some social sites will not' : 'link copied');
    },
    image: async () => {
      const png = await toPng(2);
      try { await navigator.clipboard.write([new ClipboardItem({'image/png': png})]); say('image copied — paste it anywhere'); }
      catch (e) { download(png, fileName() + '.png'); say('image downloaded'); }
    },
    png: async () => { download(await toPng(2), fileName() + '.png'); say('PNG downloaded'); },
    svg: async () => { download(new Blob([pristine], {type: 'image/svg+xml'}), fileName() + '.svg'); say('SVG downloaded'); },
    html: async () => { download(new Blob(['<!DOCTYPE html>\n' + document.documentElement.outerHTML], {type: 'text/html'}), fileName() + '.html'); say('page downloaded'); },
    native: async () => { await navigator.share({title, text: shareText(), url: await shareUrl()}); },
  };
  const enc = encodeURIComponent;
  const intents = {
    x: u => `https://twitter.com/intent/tweet?text=${enc(shareText())}&url=${enc(u)}`,
    bluesky: u => `https://bsky.app/intent/compose?text=${enc(shareText() + ' ' + u)}`,
    linkedin: u => `https://www.linkedin.com/sharing/share-offsite/?url=${enc(u)}`,
    reddit: u => `https://www.reddit.com/submit?url=${enc(u)}&title=${enc(shareText())}`,
    hn: u => `https://news.ycombinator.com/submitlink?u=${enc(u)}&t=${enc(shareText())}`,
    email: u => `mailto:?subject=${enc(shareText())}&body=${enc(u)}`,
  };
  const shortOnly = {x: 4096, bluesky: 280};  // platforms that refuse long URLs
  on(shareMenu, 'click', e => {
    const b = e.target.closest('[data-action],[data-intent]');
    if (!b) return;
    e.preventDefault();
    if (b.dataset.action) { Promise.resolve().then(() => actions[b.dataset.action]()).catch(() => say('could not share')); return; }
    const w = window.open('', '_blank');  // open synchronously so the popup is not blocked
    shareUrl().then(u => {
      const limit = shortOnly[b.dataset.intent];
      if (limit && u.length > limit) { if (w) w.close(); say(`this graph makes a link too long for ${b.textContent}; copy the image and post that instead`); return; }
      if (w) { w.opener = null; w.location = intents[b.dataset.intent](u); }
      showShare(false);
    }).catch(() => { if (w) w.close(); say('could not share'); });
  });
  if (!navigator.share) $('[data-action="native"]', shareMenu).forEach(el => el.remove());
  const localNote = byId('localNote');
  if (localNote && location.protocol === 'file:' && !(info.viewer_url && canPack)) localNote.style.display = 'block';

  // What mount() calls before putting the next graph on the stage.
  dispose = () => { stopPlay(); clearNow(); showHelp(false); showShare(false); offs.forEach(off => off()); offs.length = 0; control = null; };
  }

  // playOnce(then): play the graph on the stage from before to after, once,
  // then call then(). setState('before' | 'after' | 'step=N'): jump there.
  function playOnce(then){ if (control) control.playOnce(then); else if (then) then(); }
  function setState(s){ if (control) control.setState(s); }
  // setLocked(true | false): lock or free the playback controls of the graph on the stage.
  function setLocked(v){ if (control) control.setLocked(v); }
  // setProgress(p): put the graph at a fractional point of its animation (0 = before, steps() = after).
  function setProgress(p){ if (control) control.setProgress(p); }
  function steps(){ return control ? control.steps() : 0; }
  function animatable(){ return !!(control && control.animatable()); }

  return {init, boot, mount, load, unmount, deflate, inflate, setTheme, retheme, playOnce, setState, setLocked, setProgress, steps, animatable, root};
}
window.GitSimViewer = Object.assign(makeViewer(document), {instance: makeViewer});
"""
VIEWER_JS = VIEWER_JS.replace("__PALETTES__", _palettes_json())

_HELP_ITEMS = (
    (
        "slider / ▶",
        "Drag the slider, or press play, to watch the command happen. Before and After jump to either end.",
    ),
    (
        "← → · space",
        "Step through a multi-step command; space toggles Before / After.",
    ),
    (
        "A",
        "Play or pause the loop (the page opens playing). Any manual input takes over.",
    ),
    (
        "hover",
        "A commit shows its message, author, date and parents, with its history highlighted.",
    ),
    ("click", "Copies the commit sha."),
    (
        "ctrl + wheel",
        "Zoom around the cursor (pinch on a trackpad). Double-click resets the view.",
    ),
    ("Esc", "Stop playback, reset the view, close this menu."),
    (
        "share",
        "The Share button copies a link to this graph, copies it as an image, downloads PNG/SVG/page, or posts it. #before, #after or #step=N in the link pins the state.",
    ),
)


def header_markup(fragment_attr=""):
    """The viewer's header: brand, scrubber cluster, partner links, share and
    help menus. Shared verbatim by the standalone page and the hosted viewer
    template (via export_viewer_assets, which passes a Thymeleaf fragment
    attribute)."""
    help_items = "".join(
        f"<li><kbd>{html.escape(k)}</kbd><span>{html.escape(v)}</span></li>"
        for k, v in _HELP_ITEMS
    )
    return (
        f'<header id="bar"{fragment_attr}>'
        '<a id="brand" href="https://github.com/initialcommit-com/git-sim" target="_blank" rel="noopener" title="git-sim on GitHub: the tool that rendered this page">git-sim</a>'
        '<div id="controls">'
        '<button id="play" title="play the command from before to after, on a loop (A)">&#9654;</button>'
        '<button id="toBefore" class="end" title="the repository as it is">Before</button>'
        '<input id="scrub" type="range" min="0" max="1000" value="1000" step="1" aria-label="before / after">'
        '<button id="toAfter" class="end on" title="after the command">After</button>'
        '<span id="stepLabel"></span>'
        "</div>"
        '<div class="right">'
        '<a href="https://initialcommit.com" target="_blank" rel="noopener" '
        'title="Initial Commit — the team behind git-sim. Quality resources and tools for developers: Git guides, courses and tools that make version control click.">Initial Commit</a>'
        '<a href="https://devlands.com" target="_blank" rel="noopener" '
        'title="Devlands — learn Git comfortably, use Git confidently. Explore your own repository as an immersive 3D world where every Git operation is something you can see and walk through.">Devlands</a>'
        '<button id="share" title="copy a link or an image of this simulation, save it, or post it">Share</button>'
        '<div id="shareMenu" hidden>'
        '<h3>Copy</h3><div class="grid">'
        '<button data-action="link" title="a link that opens this graph in the git-sim viewer at the current slider position. The graph itself stays in the link\'s #fragment; the command and a short text graph (git log --oneline, up to 12 lines) go in the query string so the link gets a preview card when posted">Copy link</button>'
        '<button data-action="image" title="a PNG of the graph as shown right now, on your clipboard">Copy image</button>'
        "</div>"
        '<h3>Save</h3><div class="grid">'
        '<button data-action="png" title="a PNG of the graph as shown right now">Download PNG</button>'
        '<button data-action="svg" title="the graph as vector art, as generated">Download SVG</button>'
        '<button data-action="html" title="this whole interactive page as one file">Download page</button>'
        "</div>"
        '<h3>Post</h3><div class="grid">'
        '<a data-intent="x" href="#">X</a><a data-intent="bluesky" href="#">Bluesky</a>'
        '<a data-intent="linkedin" href="#">LinkedIn</a><a data-intent="reddit" href="#">Reddit</a>'
        '<a data-intent="hn" href="#">Hacker News</a><a data-intent="email" href="#">Email</a>'
        '<button data-action="native" title="your device\'s share sheet">Share…</button>'
        "</div>"
        '<p id="localNote">This page is a local file, so a posted link only works once the .html is hosted somewhere. '
        "Copy the image to post right away, or download the page and attach it.</p>"
        "</div>"
        '<button id="help" title="how to use this page (?)">?</button>'
        f'<div id="helpMenu" hidden><h3>How to use this page</h3><ul>{help_items}</ul></div>'
        "</div>"
        "</header>"
    )


def build_html(
    svg,
    *,
    title="",
    theme=None,
    width=1920,
    height=1080,
    summary="",
    viewer_url=DEFAULT_VIEWER_URL,
):
    """The standalone page written by ``git-sim --interactive``."""
    theme = theme or DARK
    title = " ".join((title or "").split())  # scenes build titles with stray spaces
    page_title = html.escape(title or "git-sim")
    meta = json.dumps(
        {
            "title": title,
            "theme": theme.name,
            "width": int(width),
            "height": int(height),
            "summary": summary,
            "viewer_url": viewer_url,
        }
    ).replace("</", "<\\/")
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en" data-theme="{theme.name}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{page_title}</title>"
        '<meta name="generator" content="git-sim">'
        f"<style>{VIEWER_CSS}</style></head><body>"
        f"{header_markup()}"
        f'<div id="stage">{svg}</div>'
        '<div id="tip"></div>'
        '<div id="toast"></div>'
        f'<script type="application/json" id="git-sim-meta">{meta}</script>'
        f"<script>{VIEWER_JS}</script>"
        "<script>GitSimViewer.init();</script>"
        "</body></html>"
    )


def _pack(text):
    """zlib-compress and base64url-encode ``text`` the way the page's script
    does (DecompressionStream('deflate') on the other end)."""
    raw = zlib.compress(text.encode("utf-8"), 9)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def viewer_link(
    svg,
    title="",
    theme_name="dark",
    summary="",
    viewer_url=DEFAULT_VIEWER_URL,
    state=None,
    local_path=None,
    share=True,
):
    """A link that opens ``svg`` in the hosted viewer. The whole graph travels
    compressed in the #fragment, which browsers never send to the server.

    With ``share=True`` (what the page's own "Copy link" produces) the
    command, theme and a short text graph go in the query string so the
    server can draw a preview card for the link when it is posted. With
    ``share=False`` (git-sim opening the page for its own user) the query
    string carries only the theme; the command rides in the fragment and no
    text graph is sent, so nothing about the repository reaches the server.

    ``local_path`` (the saved page's name) rides in the fragment too, so the
    viewer can say where the local copy is. Without ``state`` the page opens
    on "before" and plays the command."""
    title = " ".join((title or "").split())
    query = {"m": theme_name}
    fragment = {"d": _pack(svg)}
    if share:
        query = {"t": title, "m": theme_name}
        if summary:
            query["g"] = _pack(summary)
    elif title:
        fragment["t"] = title
    if state:  # "before", "after" or "step=N" pins the view; unpinned, it plays
        fragment["s"] = state
    if local_path:
        fragment["p"] = os.path.basename(str(local_path))
    return (
        f"{viewer_url}?{urllib.parse.urlencode(query)}"
        f"#{urllib.parse.urlencode(fragment)}"
    )


THYMELEAF_HEADER_TEMPLATE = (
    "<!-- Generated by git-sim (python -m git_sim.render.html); do not edit by hand. -->\n"
    '<html xmlns:th="http://www.thymeleaf.org"><body>\n'
    "{header}\n"
    "</body></html>\n"
)


def export_viewer_assets(directory):
    """Write the viewer's stylesheet, script and header markup (as a Thymeleaf
    fragment) for the hosted viewer on initialcommit.com. Returns the paths
    written."""
    from git_sim.render.embed import build_embed_js
    from git_sim.render.live_html import LIVE_CSS, LIVE_JS, strip_markup

    os.makedirs(directory, exist_ok=True)
    files = {
        # One script for blogs and docs: the viewer around a graph on any page
        "git-sim-embed.js": build_embed_js(),
        "git-sim-viewer.css": VIEWER_CSS,
        "git-sim-viewer.js": VIEWER_JS,
        "git-sim-viewer-header.html": THYMELEAF_HEADER_TEMPLATE.format(
            header=header_markup(' th:fragment="header"')
        ),
        # The live page's strip, stylesheet and script, for /tools/git-sim/live
        "git-sim-live.css": LIVE_CSS,
        "git-sim-live.js": LIVE_JS,
        "git-sim-live-strip.html": THYMELEAF_HEADER_TEMPLATE.format(
            header=strip_markup(' th:fragment="strip"')
        ),
    }
    written = []
    for name, content in files.items():
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content.strip("\n") + "\n")
        written.append(path)
    return written


if __name__ == "__main__":  # python -m git_sim.render.html <dir>
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    for written_path in export_viewer_assets(target):
        print(written_path)
