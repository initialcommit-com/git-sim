# Embedding a git-sim graph in a page

You can put a git-sim graph in any blog post, tutorial, or docs page, with the full interactive viewer: the Before / After slider, the play button, hover details, zoom, and sharing. It takes two pieces of HTML:

```html
<div class="git-sim" data-src="/img/rebase-main.svg" data-title="git rebase main">
  <a href="https://initialcommit.com/tools/git-sim">git rebase main, created with git-sim</a>
</div>
<script src="https://initialcommit.com/js/tools/git-sim-embed.js" defer></script>
```

The script turns every element with the `git-sim` class into the viewer showing its graph. Include the script once per page, and it finds all of them.

The link inside the element becomes a one-line credit under the graph. It's also what readers see if the script can't run. If you leave it out, the script adds the same credit itself. git-sim is free and open source, and the credit is how other people find it.

## Making the graph

```console
$ git-sim --img-format svg rebase main
```

This saves just the graph as an SVG, with the before and after data the viewer plays, in git-sim's media folder (`git-sim media-dir` shows where). Copy it next to your page. **Download SVG** in any git-sim page's Share menu gives you the same file. A saved git-sim page (`.html`) works too, and is shown as it is.

## Attributes

| Attribute | What it does |
| --- | --- |
| `data-src` | The SVG (or saved page) to show. It has to be on the same site as your page, or on a host that allows cross-origin requests. |
| `data-title` | The command, used in the share text and the frame's title. |
| `data-state` | `before`, `after`, or `step=N` holds the graph at that point. Without it, the graph plays on a loop. |
| `data-theme` | `dark` or `light`. By default it follows your reader's light or dark mode setting. |
| `data-controls` | `full` (the default) or `compact`. Compact hides the git-sim, Initial Commit, and Devlands links, and keeps the slider and Share. |
| `data-height` | A fixed height, like `480px`. By default the embed sizes itself to fit the graph. |

The credit is a `<p class="git-sim-credit">` under the frame, in small muted text that takes its color from your page. Style that class if you want it to match your page more closely.

## How it works

Each embed is an iframe with its own self-contained document (the script carries the viewer's styles and code). So several graphs on one page never clash, and your page's styles never reach the graph. Your page fetches the SVG and hands it to the frame, so there's nothing to set up on your server. The frame reports its height back, so the embed fits the graph exactly.

If your page adds content after it loads, call `GitSimEmbed.scan(element)` to set up any new graphs inside that element.

The script comes from the git-sim package (`python -m git_sim.render.html <folder>` exports it along with the rest of the viewer's files), so it's the same viewer as the pages git-sim saves and the one at initialcommit.com.
