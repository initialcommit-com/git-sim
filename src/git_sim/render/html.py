"""Self-contained interactive page around the SVG a scene rendered.

No external requests: the page is the SVG, a stylesheet and a small script.
Behaviour comes from the data attributes the SVG painter wrote:

- hover a commit for its full message, author, date and parents, with its
  ancestry highlighted; click to copy the sha;
- drag to pan, wheel to zoom, double-click to reset;
- a Before / After switch that fades the simulated elements in and out and
  slides moved labels and files back to where they were; commands that act
  in several steps (rebase -i, cherry-pick A..B) get step controls too.
"""

import html
import json

from git_sim.render.svg import DEFAULT_FONT_STACK as FONT_STACK

_CSS = """
:root{--bg:%(bg)s;--text:%(text)s;--muted:%(muted)s;--rule:%(rule)s;--accent:%(accent)s;--panel:%(panel)s;}
*{box-sizing:border-box}
html,body{margin:0;height:100%%;background:var(--bg);color:var(--text);font-family:%(font)s;overflow:hidden}
#stage{position:fixed;inset:0;cursor:grab}
#stage.panning{cursor:grabbing}
#scene{width:100%%;height:100%%;display:block;user-select:none}
#scene [data-phase]{transition:opacity .45s ease,transform .6s cubic-bezier(.4,0,.2,1)}
#scene .hidden{opacity:0 !important;pointer-events:none}
#scene .dim{opacity:.18;transition:opacity .2s ease}
#scene [data-role="commit"],#scene [data-role="commit-label"],#scene [data-role="ref"]{cursor:pointer}
#bar{position:fixed;top:14px;right:14px;display:flex;gap:10px;align-items:center;z-index:2}
.seg{display:flex;background:var(--panel);border:1px solid var(--rule);border-radius:999px;padding:3px;backdrop-filter:blur(6px)}
.seg button{border:0;background:transparent;color:var(--muted);font:600 13px/1 %(font)s;padding:7px 14px;border-radius:999px;cursor:pointer}
.seg button.on{background:var(--accent);color:var(--bg)}
.seg button:disabled{opacity:.35;cursor:default}
#steps{display:none}
#steps.show{display:flex}
#steps span{color:var(--text);font:600 13px/1 %(font)s;padding:7px 10px;min-width:82px;text-align:center}
#hint{position:fixed;left:14px;bottom:12px;color:var(--muted);font:12px/1.4 %(font)s;opacity:.8;z-index:2}
#tip{position:fixed;pointer-events:none;display:none;max-width:420px;background:var(--bg);color:var(--text);border:1px solid var(--rule);border-radius:10px;padding:10px 12px;font:13px/1.45 %(font)s;box-shadow:0 8px 28px rgba(0,0,0,.35);z-index:3}
#tip .k{color:var(--muted)}
#tip .sha{color:var(--accent);font-weight:700}
#tip .msg{margin:4px 0 6px;white-space:pre-wrap}
"""

_JS = r"""
(function(){
  const svg = document.getElementById('scene');
  const stage = document.getElementById('stage');
  const tip = document.getElementById('tip');
  const W = %(width)d, H = %(height)d;
  const $ = (s, root) => Array.from((root || svg).querySelectorAll(s));

  // ---- before / after -----------------------------------------------------
  const after = $('[data-phase="after"]');
  const removed = $('[data-phase="removed"]');
  const moved = $('[data-dx]');
  const recolored = $('[data-before-fill]');
  let maxStep = 1;
  after.forEach(el => { const s = parseInt(el.dataset.step || '0', 10); if (s > maxStep) maxStep = s; });
  const stepOf = el => parseInt(el.dataset.step || '0', 10) || maxStep;
  recolored.forEach(el => { el.dataset.afterFill = el.getAttribute('fill') || ''; el.dataset.afterStroke = el.getAttribute('stroke') || ''; });
  // A shared link can open on the "before" view or a given step: #before, #step=2
  let step = maxStep;
  const hash = (location.hash || '').replace('#', '');
  if (hash === 'before') step = 0;
  else if (/^step=\d+$/.test(hash)) step = Math.min(maxStep, parseInt(hash.slice(5), 10));
  const stepLabel = document.getElementById('stepLabel');
  const btnBefore = document.getElementById('before'), btnAfter = document.getElementById('afterBtn');
  const prev = document.getElementById('prev'), next = document.getElementById('next');

  function apply(){
    after.forEach(el => el.classList.toggle('hidden', step < stepOf(el)));
    removed.forEach(el => el.classList.toggle('hidden', step >= stepOf(el)));
    moved.forEach(el => {
      const back = step < stepOf(el);
      el.style.transform = back ? `translate(${el.dataset.dx}px, ${el.dataset.dy}px)` : '';
    });
    recolored.forEach(el => {
      const back = step < stepOf(el);
      if (el.dataset.afterFill) el.setAttribute('fill', back ? el.dataset.beforeFill : el.dataset.afterFill);
      if (el.dataset.afterStroke) el.setAttribute('stroke', back ? (el.dataset.beforeStroke || el.dataset.beforeFill) : el.dataset.afterStroke);
    });
    btnBefore.classList.toggle('on', step === 0);
    btnAfter.classList.toggle('on', step === maxStep);
    if (stepLabel) stepLabel.textContent = step === 0 ? 'before' : `step ${step} / ${maxStep}`;
    prev.disabled = step === 0; next.disabled = step === maxStep;
  }
  function setStep(s){ step = Math.max(0, Math.min(maxStep, s)); apply(); }
  btnBefore.onclick = () => setStep(0);
  btnAfter.onclick = () => setStep(maxStep);
  prev.onclick = () => setStep(step - 1);
  next.onclick = () => setStep(step + 1);
  if (maxStep > 1) document.getElementById('steps').classList.add('show');
  if (after.length + removed.length + moved.length + recolored.length === 0) document.getElementById('bar').style.display = 'none';
  document.addEventListener('keydown', e => {
    if (e.key === 'ArrowLeft') setStep(step - 1);
    else if (e.key === 'ArrowRight') setStep(step + 1);
    else if (e.key === ' ') { e.preventDefault(); setStep(step === maxStep ? 0 : maxStep); }
    else if (e.key === 'Escape') resetView();
  });
  apply();

  // ---- ancestry highlight + tooltip ---------------------------------------
  const parents = {};
  $('[data-role="commit"]').forEach(el => { parents[el.dataset.sha] = (el.dataset.parents || '').split(/\s+/).filter(Boolean); });
  function ancestry(sha){
    const seen = new Set(); const stack = [sha];
    while (stack.length) { const s = stack.pop(); if (seen.has(s)) continue; seen.add(s); (parents[s] || []).forEach(p => stack.push(p)); }
    return seen;
  }
  function highlight(sha){
    const keep = ancestry(sha);
    $('[data-role="commit"],[data-role="commit-label"]').forEach(el => el.classList.toggle('dim', !keep.has(el.dataset.sha)));
    $('[data-role="edge"]').forEach(el => el.classList.toggle('dim', !(keep.has(el.dataset.src) && keep.has(el.dataset.dst))));
  }
  function clearHighlight(){ $('.dim').forEach(el => el.classList.remove('dim')); }
  const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  function describe(el){
    const d = el.dataset;
    if (d.role === 'commit' || d.role === 'commit-label') {
      const info = $('[data-role="commit"][data-sha="' + d.sha + '"]')[0]?.dataset || d;
      return `<div class="sha">${esc(info.sha)}</div><div class="msg">${esc(info.message || '')}</div>` +
        `<div><span class="k">author</span> ${esc(info.author || '')}</div>` +
        (info.date ? `<div><span class="k">date</span> ${esc(info.date)}</div>` : '') +
        `<div><span class="k">parents</span> ${esc((info.parents || '').split(/\s+/).filter(Boolean).map(p => p.slice(0, 7)).join(', ') || 'none')}</div>` +
        (info.kind === 'merge' ? '<div><span class="k">merge commit</span></div>' : '') +
        (info.phase === 'after' ? '<div><span class="k">simulated by this command</span></div>' : '') +
        '<div class="k">click to copy sha</div>';
    }
    if (d.role === 'ref') return `<div class="sha">${esc(d.name)}</div><div><span class="k">${esc(d.kind || 'ref')}</span>${d.phase === 'after' ? ' · simulated' : d.phase === 'removed' ? ' · removed by this command' : ''}</div>`;
    if (d.role === 'file') return `<div class="sha">${esc(d.name)}</div><div><span class="k">${esc(d.column || '')}</span>${d.phase === 'after' ? ' · after the command' : ''}</div>`;
    return '';
  }
  let tipTimer = null;
  svg.addEventListener('mousemove', e => {
    const el = e.target.closest('[data-role="commit"],[data-role="commit-label"],[data-role="ref"],[data-role="file"]');
    if (!el || el.classList.contains('hidden')) { tip.style.display = 'none'; clearHighlight(); return; }
    const content = describe(el);
    if (!content) { tip.style.display = 'none'; return; }
    tip.innerHTML = content; tip.style.display = 'block';
    const x = Math.min(e.clientX + 16, window.innerWidth - tip.offsetWidth - 12);
    const y = Math.min(e.clientY + 16, window.innerHeight - tip.offsetHeight - 12);
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
    if (el.dataset.sha) highlight(el.dataset.sha); else clearHighlight();
  });
  svg.addEventListener('mouseleave', () => { tip.style.display = 'none'; clearHighlight(); });
  svg.addEventListener('click', e => {
    const el = e.target.closest('[data-sha]');
    if (!el || !navigator.clipboard) return;
    navigator.clipboard.writeText(el.dataset.sha).then(() => {
      tip.innerHTML = `<div class="sha">${esc(el.dataset.sha)}</div><div class="k">copied</div>`;
      clearTimeout(tipTimer); tipTimer = setTimeout(() => { tip.style.display = 'none'; }, 900);
    }).catch(() => {});
  });

  // ---- pan / zoom -----------------------------------------------------------
  let vb = {x: 0, y: 0, w: W, h: H};
  function setView(){ svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`); }
  function resetView(){ vb = {x: 0, y: 0, w: W, h: H}; setView(); }
  function toScene(cx, cy){
    const r = svg.getBoundingClientRect();
    const k = Math.max(vb.w / r.width, vb.h / r.height);
    const ox = (r.width - vb.w / k) / 2, oy = (r.height - vb.h / k) / 2;
    return {x: vb.x + (cx - r.left - ox) * k, y: vb.y + (cy - r.top - oy) * k, k};
  }
  stage.addEventListener('wheel', e => {
    e.preventDefault();
    const f = Math.exp(e.deltaY * 0.0015);
    const p = toScene(e.clientX, e.clientY);
    const nw = Math.min(W * 4, Math.max(W / 12, vb.w * f));
    const s = nw / vb.w;
    vb = {x: p.x - (p.x - vb.x) * s, y: p.y - (p.y - vb.y) * s, w: nw, h: vb.h * s};
    setView();
  }, {passive: false});
  let drag = null;
  stage.addEventListener('mousedown', e => { if (e.button !== 0) return; drag = {x: e.clientX, y: e.clientY, vb: {...vb}}; stage.classList.add('panning'); });
  window.addEventListener('mousemove', e => {
    if (!drag) return;
    const k = toScene(0, 0).k;
    vb.x = drag.vb.x - (e.clientX - drag.x) * k; vb.y = drag.vb.y - (e.clientY - drag.y) * k; setView();
  });
  window.addEventListener('mouseup', () => { drag = null; stage.classList.remove('panning'); });
  stage.addEventListener('dblclick', resetView);
})();
"""


def build_html(svg, *, title="", theme=None, width=1920, height=1080):
    bg = theme.bg if theme else "#0D1117"
    text = theme.text if theme else "#E6EDF3"
    muted = theme.text_muted if theme else "#8B949E"
    rule = theme.rule if theme else "#3D444D"
    accent = theme.accent if theme else "#F47067"
    panel = (
        "rgba(255,255,255,.06)" if (theme is None or theme.glow) else "rgba(0,0,0,.05)"
    )
    css = _CSS % {
        "bg": bg,
        "text": text,
        "muted": muted,
        "rule": rule,
        "accent": accent,
        "panel": panel,
        "font": FONT_STACK,
    }
    js = _JS % {"width": int(width), "height": int(height)}
    page_title = html.escape(title or "git-sim")
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{page_title}</title>"
        f'<meta name="generator" content="git-sim">'
        f"<style>{css}</style></head><body>"
        f'<div id="stage">{svg}</div>'
        '<div id="bar">'
        '<div class="seg" id="steps"><button id="prev" title="previous step (←)">&#9664;</button>'
        '<span id="stepLabel"></span><button id="next" title="next step (→)">&#9654;</button></div>'
        '<div class="seg"><button id="before" title="the repository as it is (space)">Before</button>'
        '<button id="afterBtn" class="on" title="after the command (space)">After</button></div>'
        "</div>"
        '<div id="hint">hover a commit · click to copy its sha · drag to pan · wheel to zoom · double-click to reset</div>'
        '<div id="tip"></div>'
        f"<script>{js}</script>"
        f"<script type=\"application/json\" id=\"git-sim-meta\">{json.dumps({'title': title, 'theme': theme.name if theme else None})}</script>"
        "</body></html>"
    )
