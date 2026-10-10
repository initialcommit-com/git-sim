"""The embeddable viewer: one script that turns a git-sim graph into the
interactive before / after viewer on any web page.

A blog post or a documentation page writes

    <div class="git-sim" data-src="/img/rebase.svg" data-title="git rebase main"></div>
    <script src="https://initialcommit.com/js/tools/git-sim-embed.js" defer></script>

and the script replaces each ``.git-sim`` element with the viewer showing that
graph: the header with the Before / After slider and play button, the graph
with its tooltips and zoom, sharing. The SVG is what ``git-sim --img-format
svg <command>`` writes (or "Download SVG" on any page).

Each embed is an iframe with a self-contained document (this file carries the
viewer's stylesheet and script), so several graphs on one page never share
ids or key bindings, and the host page's styles never leak in. The host page
fetches the SVG itself (same origin as the post, so no cross-origin setup) and
hands the text to the frame; the frame reports its height back so the embed
takes exactly the room the graph needs.

Attributes: ``data-graph`` (the graph itself, compressed as in a git-sim
link's ``#d=``, which the Share menu's "Copy embed" writes, so the page hosts
no file) or ``data-src`` (the SVG, or a saved .html page, which is fetched
into the frame), ``data-title`` (the command, for the share text), ``data-state``
(``before`` / ``after`` / ``step=N``; else it plays), ``data-theme`` (``dark``
or ``light``; default follows the host page's ``prefers-color-scheme``),
``data-controls`` (``full`` or ``compact``, which drops the brand and share
links), ``data-height`` (a fixed height instead of fitting the graph).

Under the frame goes a one-line credit, "<command>, created with git-sim",
linking to git-sim's page at initialcommit.com. It is part of the host page,
not the frame, so readers (and search engines) see where the graph comes
from. The README's embed snippet writes the link inside the ``.git-sim``
element, where it is also the fallback when the script can't run; the script
keeps that link rather than adding a second one. On initialcommit.com itself
the credit is left out.
"""

import json

from git_sim.render.html import VIEWER_CSS, VIEWER_JS, header_markup

EMBED_JS = r"""
// git-sim embed. One copy lives in the git-sim package (git_sim/render/embed.py)
// and is exported to initialcommit.com; edit it there.
(function(){
  if (window.GitSimEmbed) return;
  const CSS = __CSS__;
  const HEADER = __HEADER__;
  const VIEWER = __VIEWER__;
  // min-height:0 so the height the frame reports is its content's, not the frame's own
  // (which would hold a short graph at the frame's starting 320px)
  // no learn link in an embed: the host page is the lesson
  const FRAME_CSS = 'html,body{overflow:hidden;min-height:0}#bar{position:static}#learn{display:none!important}' +
    '[data-controls="compact"] #brand,[data-controls="compact"] #bar .right a{display:none}' +
    '[data-controls="compact"] #bar{grid-template-columns:auto 1fr auto;padding:0 10px}';
  const FRAME_JS = `
    // the body's height: the document's own scrollHeight is never less than the frame, so a frame could grow but never shrink
    const send = () => parent.postMessage({gitSimEmbed: document.documentElement.dataset.embedId, height: document.body.scrollHeight}, '*');
    window.addEventListener('message', e => {
      const m = e.data || {};
      if (m.gitSimEmbedGraph !== document.documentElement.dataset.embedId) return;
      try {
        GitSimViewer.mount(m.svg, {title: m.title || '', state: m.state || null});
        if (m.theme) GitSimViewer.setTheme(m.theme);
      } catch (err) {
        document.getElementById('stage').innerHTML = '<p style="padding:24px;font:14px/1.5 var(--font);color:var(--muted)">This graph could not be shown: ' + String(err.message).replace(/[<&]/g, '') + '</p>';
      }
      send();
      new ResizeObserver(send).observe(document.getElementById('stage'));
    });
    window.addEventListener('git-sim:layout', send);
    window.addEventListener('load', () => { send(); parent.postMessage({gitSimEmbedReady: document.documentElement.dataset.embedId}, '*'); });
  `;
  let counter = 0;
  const frames = new Map();  // id -> {iframe, element, svg, ...}

  function documentFor(id, theme, controls, title){
    const meta = JSON.stringify({title: title || 'git-sim', theme: theme, viewer_url: 'https://initialcommit.com/tools/git-sim/viewer'}).replace(/<\//g, '<\\/');
    return '<!DOCTYPE html><html lang="en" data-theme="' + theme + '" data-embed-id="' + id + '" data-controls="' + controls + '"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width, initial-scale=1"><style>' + CSS + FRAME_CSS + '</style></head><body>' +
      HEADER + '<div id="stage"></div><div id="tip"></div><div id="toast"></div>' +
      '<script type="application/json" id="git-sim-meta">' + meta + '</script>' +
      '<script>' + VIEWER + '</script><script>' + FRAME_JS + '</script></body></html>';
  }

  function themeFor(el){
    const asked = (el.dataset.theme || '').toLowerCase();
    if (asked === 'dark' || asked === 'light') return asked;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }

  // The credit under each graph: what the snippet wrote inside the element
  // when it links initialcommit.com ("Copy embed" links the command's page and
  // git-sim's; older snippets link git-sim alone), else a new line. Not shown
  // on initialcommit.com itself.
  const HOME = 'https://initialcommit.com/tools/git-sim';
  function credit(el){
    if (/(^|\.)initialcommit\.com$/i.test(location.hostname)) return null;
    const line = document.createElement('p');
    line.className = 'git-sim-credit';
    line.style.cssText = 'margin:6px 2px 0;font:12px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif;text-align:right;opacity:.75';
    if (el.querySelector('a[href*="initialcommit.com"]')) {
      line.append(...Array.from(el.childNodes));
      line.normalize();
      if (line.firstChild && line.firstChild.nodeType === 3) line.firstChild.textContent = line.firstChild.textContent.replace(/^\s+/, '');
      if (line.lastChild && line.lastChild.nodeType === 3) line.lastChild.textContent = line.lastChild.textContent.replace(/\s+$/, '');
    } else {
      const link = document.createElement('a');
      link.href = HOME;
      link.textContent = (el.dataset.title ? el.dataset.title + ', created' : 'Created') + ' with git-sim';
      line.appendChild(link);
    }
    line.querySelectorAll('a').forEach(a => { a.style.color = 'inherit'; });
    return line;
  }
  function place(el, iframe){
    const line = credit(el);
    if (line) el.replaceChildren(iframe, line); else el.replaceChildren(iframe);
  }

  // data-graph: the graph compressed the way a git-sim link's #d= carries it
  // (what the Share menu's "Copy embed" writes), so the page hosts no file
  async function inflate(b64){
    const bytes = Uint8Array.from(atob(b64.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
    return await new Response(stream).text();
  }

  function mount(el){
    if (el.dataset.gitSimMounted) return;
    el.dataset.gitSimMounted = '1';
    const src = el.dataset.src, graph = el.dataset.graph;
    if (!src && !graph) { el.textContent = 'git-sim embed: data-graph or data-src is missing'; return; }
    if (graph && typeof DecompressionStream === 'undefined') { el.textContent = 'git-sim embed: this browser cannot unpack the graph (it needs DecompressionStream)'; return; }
    const id = 'gs' + (++counter);
    const iframe = document.createElement('iframe');
    iframe.setAttribute('title', el.dataset.title ? 'git-sim: ' + el.dataset.title : 'git-sim graph');
    iframe.style.cssText = 'display:block;width:100%;border:0;border-radius:12px;background:transparent;' + (el.dataset.height ? 'height:' + el.dataset.height : 'height:320px');
    iframe.setAttribute('loading', 'lazy');
    const theme = themeFor(el);
    const controls = (el.dataset.controls || 'full').toLowerCase() === 'compact' ? 'compact' : 'full';
    if (!graph && /\.html?(\?|#|$)/i.test(src)) {
      // A saved git-sim page (a simulation or a recorded live session): fetched
      // and given to the frame as its document, so a host that refuses to be
      // framed by URL (X-Frame-Options) still shows it; its own script runs it.
      if (!el.dataset.height) iframe.style.height = '560px';
      place(el, iframe);
      fetch(src, {credentials: 'same-origin'}).then(r => { if (!r.ok) throw new Error(r.status + ' fetching ' + src); return r.text(); })
        .then(html => { iframe.srcdoc = html; })
        .catch(err => { el.textContent = 'git-sim embed: ' + err.message; });
      return;
    }
    iframe.srcdoc = documentFor(id, theme, controls, el.dataset.title || '');
    frames.set(id, {iframe, element: el, theme, svg: null, ready: false});
    place(el, iframe);
    const svgText = graph ? inflate(graph)
      : fetch(src, {credentials: 'same-origin'}).then(r => { if (!r.ok) throw new Error(r.status + ' fetching ' + src); return r.text(); });
    svgText.then(svg => { const f = frames.get(id); f.svg = svg; if (f.ready) deliver(id); })
      .catch(err => { el.textContent = 'git-sim embed: ' + (graph ? 'the graph could not be unpacked' : err.message); });
  }

  function deliver(id){
    const f = frames.get(id);
    if (!f || !f.svg || !f.ready) return;
    f.iframe.contentWindow.postMessage({gitSimEmbedGraph: id, svg: f.svg, title: f.element.dataset.title || '', state: f.element.dataset.state || null, theme: f.theme}, '*');
  }

  window.addEventListener('message', e => {
    const m = e.data || {};
    if (m.gitSimEmbedReady) { const f = frames.get(m.gitSimEmbedReady); if (f) { f.ready = true; deliver(m.gitSimEmbedReady); } }
    if (m.gitSimEmbed && m.height) {
      const f = frames.get(m.gitSimEmbed);
      if (f && !f.element.dataset.height) f.iframe.style.height = Math.ceil(m.height) + 'px';
    }
  });

  function scan(root){ Array.from((root || document).querySelectorAll('.git-sim[data-src], .git-sim[data-graph]')).forEach(mount); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => scan()); else scan();
  window.GitSimEmbed = {mount, scan, version: 1};
})();
"""


def build_embed_js() -> str:
    """The single script a page includes."""
    return (
        EMBED_JS.replace("__CSS__", json.dumps(VIEWER_CSS))
        .replace("__HEADER__", json.dumps(header_markup()))
        .replace("__VIEWER__", json.dumps(VIEWER_JS).replace("</", "<\\/"))
    )
