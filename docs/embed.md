# Embedding a git-sim graph in a page

Any blog post, tutorial or documentation page can show a git-sim graph with
the full interactive viewer: the Before / After slider and play button, hover
details, zoom, sharing. Two lines:

```html
<div class="git-sim" data-src="/img/rebase-main.svg" data-title="git rebase main"></div>
<script src="https://initialcommit.com/js/tools/git-sim-embed.js" defer></script>
```

The script replaces every `.git-sim` element with the viewer showing its graph.
Include it once; it finds all of them.

## Making the graph

```
git-sim --img-format svg rebase main
```

writes the graph alone (the interactive page's SVG, with the before / after
data the viewer plays) under `git-sim media-dir`. Copy it next to your page.
"Download SVG" in any git-sim page's Share menu gives the same file. A saved
page (`.html`) works too and is framed as it is.

## Attributes

| Attribute | Meaning |
| --- | --- |
| `data-src` | The SVG (or saved page) to show. Same origin as your page, or a host that allows cross-origin reads. |
| `data-title` | The command, for the share text and the frame's title. |
| `data-state` | `before`, `after` or `step=N` pins the graph there; without it the graph plays on a loop. |
| `data-theme` | `dark` or `light`. Default: your reader's colour-scheme preference. |
| `data-controls` | `compact` drops the brand and partner links, keeping the slider and Share. |
| `data-height` | A fixed height (`480px`). Default: the embed takes the height the graph needs. |

## How it works

Each embed is an iframe with a self-contained document (the script carries the
viewer's stylesheet and script), so several graphs on one page never share ids
or keyboard shortcuts, and your page's styles never reach the graph. Your page
fetches the SVG itself and hands the text to the frame, so there is nothing to
configure on a server; the frame reports its height back so the embed fits the
graph exactly. `GitSimEmbed.scan(root)` mounts elements added later, for pages
that render content dynamically.

The script is exported from the git-sim package (`python -m git_sim.render.html`)
alongside the viewer assets, so it is the same viewer as the pages git-sim
writes and the one at initialcommit.com.
