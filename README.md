# AV Movie Universe — Design & Build Guide

An interactive "galaxy map" of my films and series. Every title is a star; stars cluster and
glow by genre, forming a soft nebula you can pan, zoom, search, and pick tonight's watch from.
Inspired by the [Open Syllabus Galaxy](https://galaxy.opensyllabus.org), and built as the
movie sibling of *AV's Library* (the same engine, pointed at IMDb data instead of books).

This document explains **what it is**, **how it works**, and **how to change it** — so the
look can be refined later without disturbing the stable, working app.

> [!IMPORTANT]
> **Note for AI assistants:** When implementing requested features or tweaks, always prioritize making **minimal changes** to the existing code structure. Do not rewrite large portions of the layout or rendering logic unless explicitly instructed. Always update this README and other documentation files with every change made.

---

## 1. The idea in one paragraph

I have ~2,100 films, series, and games across two IMDb exports — a **watchlist** (not yet seen)
and a **ratings** export (seen, with my 1–10 score). Instead of two boring CSVs, I want a
**living star‑map**: titles grouped into genre "galaxies" I can drift around, hover to learn a
region's name, search, and ask for a random movie or series to watch tonight. Each dot's
**size reflects how long the thing is** — a three‑hour epic is a bigger star than a short, and a
twenty‑episode series is bigger than either. There are **two looks**: a **light** mode of glowing
neurons on white, and a **dark** mode like a colour galaxy photo. The chrome stays out of the
way — everything lives behind a ☰ menu.

**Design north star:** calm, spacious, a little cosmic. Light mode = neuron network;
dark mode = the universe.

---

## 2. What it does (features)

- **Galaxy map** — 2,100 titles as dots clustered into 21 genres. **Dot size = watch length.**
  **Light mode** = glowing genre‑coloured neurons with connecting filaments on white;
  **Dark mode** = glowing stars on deep space with a faint starfield and, when zoomed in, a
  slowly rotating ring of text (director • genre • length) around each star.
- **🎬 IMDb‑synced watched/unwatched** — everything in `My_rating_imdb.csv` is baked in as
  watched with your score; everything in `My_watchlist_imdb.csv` is unwatched. See §5b to refresh.
- **Light / dark toggle** — the ☀️/🌙 button in the top bar; the choice is remembered.
- **⭐ Ratings (IMDb 1–10)** — your score shows as a 10‑star row in the detail panel. Filter the
  map by **"My rating ≥ N"** in the menu. The top bar shows your average.
- **Minimal chrome** — a top bar with a ☰ hamburger (menu drawer), logo, watched counter,
  theme toggle, and a 🔍 search shortcut. Nothing else covers the map.
- **Labels on demand** — genre names are hidden by default; they appear when you **hover** a
  region or **zoom in**.
- **Search** — title or director, with a results dropdown (shows year, genre, your score);
  picking one flies to it.
- **✦ Watch Tonight** — picks a random *unwatched* title (respecting your filters), flies to it,
  opens it. **🎬 Random movie** and **📺 Random series** do the same restricted to one type.
- **Details panel** — genre, IMDb title type, year, runtime, IMDb score, watched status, your
  1–10 score, a link to the IMDb page, "more by this director," and "explore this genre."
- **Filters** — All / Unwatched / Rated · All / Movies / Series / Games · My rating ≥ N ·
  toggle any genre.
- **Connections** — faint filaments linking titles inside a genre (always on in light mode; a
  toggle in dark mode).
- **Keyboard** — `/` search · `w` watch‑tonight · `f` fit · `m` menu · `Esc` close.

State that matters — **what you've watched, your scores, and your theme** — is stored in the
browser's `localStorage`, so it persists between visits on the same browser. Everything else is
just the file — no server, no internet needed. Double‑click `AV Movie Universe.html` to open it.

---

## 3. How it works (the concept)

1. **Titles → genres.** IMDb tags each title with up to four genres; a Python priority list picks
   the single most *specific* one so the clusters mean something. See §5.
2. **Genres → galaxies.** Each genre gets a position on a big 2‑D plane (a spiral packing where
   clusters are allowed to overlap slightly, so they read as one connected landmass). Within a
   genre, titles are scattered organically — same‑director titles clump together, denser toward
   the centre — using a gaussian spread. The whole field is stretched horizontally so it fills a
   wide screen.
3. **Dots → look.** Each dot's radius comes from its watch length (`minsToRad`). In **dark** mode
   an additive glow sprite is stamped under each star over a deep‑space gradient + static
   starfield; in **light** mode the same glow is drawn on white with a deeply shaded core.
4. **Interaction.** A single HTML `<canvas>` is redrawn on demand. A simple camera (pan/zoom
   with easing) maps world coordinates to the screen. Hovering finds the nearest star and the
   region under the cursor; clicking selects a star.
5. **Watched & rated.** Both come from the IMDb exports and are seeded into `localStorage` once
   on first open. The UI is **read‑only** — to change what's watched or scored, update the CSVs
   on IMDb, re‑export, and rebuild.

Rendering order each frame (top of `draw()`): background (white, or space gradient + starfield)
→ genre clouds → glow pass → connections → **star dots** → selection/hover ring → zoomed‑in
title labels → **genre labels** (hover/zoom‑gated).

---

## 4. Project files

```
AVMovieUniverse/
├── My_watchlist_imdb.csv     ← source data: titles you have NOT watched
├── My_rating_imdb.csv        ← source data: titles you HAVE watched, with your 1-10 score
├── AV Movie Universe.html    ← THE APP. Self-contained. This is the "stable code."
├── index.html                ← redirects to the app
├── README.md                 ← this document
└── pipeline/
    └── pipeline.py           ← both CSVs → ../AV Movie Universe.html  (one script, no deps)
```

**Two mental models:**
- `AV Movie Universe.html` **is the product.** It embeds the title data and all the CSS/JS. For
  a quick *look‑and‑feel* experiment you can edit this file directly and just reopen it.
- `pipeline/pipeline.py` **regenerates the product**, and it holds the HTML/CSS/JS as a template
  string. **Any edit you want to survive a rebuild has to be made here.** The safest workflow is
  to edit `pipeline.py` only and re‑run it.

---

## 5. The build pipeline (how to execute it)

No third‑party dependencies — it is plain Python 3 with `csv` and `json`:

```bash
cd "/Users/abhinavverma/Downloads/Claude/AVMovieUniverse/pipeline"
python3 pipeline.py
```

It overwrites `AV Movie Universe.html` in the parent folder and prints the genre distribution,
the type breakdown, and how many runtimes had to be estimated. Reopen the file in a browser to
see the result.

### What the script does, in order

1. **Load** both CSVs and de‑duplicate by IMDb const (`tt…`). A title present in both files is
   treated as **watched** — the ratings export wins.
2. **Tidy** titles and directors (IMDb packs co‑directors into one cell; the first is used for
   clustering, the whole list is shown in the panel).
3. **Genre** — pick one genre per title from `GENRE_PRIORITY` (earlier = more specific = wins).
   Genres that end up with fewer than `MIN_CLUSTER` (8) titles are folded into the next best
   genre on that title, so the map has no one‑dot galaxies.
4. **Type + length** — bucket the IMDb title type into `Movie` / `Series` / `Game` via
   `TYPE_BUCKET`, then compute the watch length (see §5a). Missing runtimes are filled from the
   **median of this very library** (by title type, then by genre) rather than invented constants.
5. **Emit** the slim per‑title records plus `SEED_WATCHED` / `SEED_RATINGS`, and write the HTML.

### 5a. How "length" is computed — and the one assumption in it

IMDb's `Runtime (mins)` column is **per episode** for a series, so a five‑season show would
otherwise be a *smaller* dot than a single film. The pipeline multiplies the episode runtime by
a rough typical episode count:

```python
EPISODES = {'TV Series': 20, 'TV Mini Series': 6, 'Podcast Series': 20}
PER_EPISODE_CEILING = 200   # a "runtime" above this is treated as an already-total figure
MAX_MINUTES = 3000          # clamp, so one huge show doesn't flatten every other dot
```

**These multipliers are a deliberate approximation** — the export carries no episode count, so a
20‑episode default stands in for every series. Change the numbers and rebuild to resize every
series on the map at once; set them all to `1` to size series by episode length instead. The
detail panel is honest about it, showing e.g. `30m/ep · ≈10h total`.

### 5b. Refreshing from newer IMDb exports

On IMDb: **Your Watchlist → Export**, and **Your Ratings → Export**. Save them over
`My_watchlist_imdb.csv` and `My_rating_imdb.csv`, keeping the filenames, then re‑run the
pipeline. Because ids are assigned by sort order, a changed library shifts them — so also bump
`SEED_VERSION` (e.g. `"imdb-1"` → `"imdb-2"`) in `pipeline.py` so the app re‑applies the new
baseline instead of trusting the ids saved in your browser.

---

## 6. Refining the design — the knobs

Search for the quoted strings inside **`pipeline/pipeline.py`**. Values below are the current
defaults.

### 6.1 Colours & theme
**The two themes have two separate palettes.** `GENRE_COLORS` is the dark‑mode one (bright
stars on black); `LIGHT_COLORS` is the light‑mode one (deep blues, teals, greens and black on
white). A title carries both — `b.color` and `b.lcolor` — and `dotColor(b)` picks whichever the
current theme needs. **Change a genre's colour in both maps**, or it will only shift in one mode.

| What | Find | Now | Notes |
|---|---|---|---|
| Dark‑mode palette | `var GENRE_COLORS={` | 24 hexes | Bright star colour per genre. Hues are spread so the **biggest** genres are the most distinct. |
| Light‑mode palette | `var LIGHT_COLORS={` | 24 hexes | Deep but saturated. Only Horror, Western and Film‑Noir are neutral **black** — everything else keeps a blue or green cast, because large regions of neutral dark read as mud rather than as colour. |
| UI colours (both themes) | `:root{` and `body.theme-dark{` (CSS) | — | Every panel colour is a CSS var; the `body.theme-dark{…}` block holds all dark overrides. |
| Default theme | `localStorage.getItem(THEME_KEY)||"light"` | light | Change `"light"` → `"dark"` to open dark by default. |
| Dark space background | the `bg.addColorStop(...)` gradient in `draw()` | deep blue‑black | The gradient behind dark mode. |
| Background starfield | `BGSTARS` / `drawBgStars()` | 220 faint stars | Ambient stars in dark mode only. |

### 6.2 Galaxy layout (shape of the map)
| What | Find | Now | Effect |
|---|---|---|---|
| Horizontal stretch | `var STRETCHX=1.32;` | 1.32 | >1 = wider field (fills landscape). 1.0 = circular. |
| Cluster spacing | `SP=18` | 18 | Base spiral spacing between genre centers (lower = tighter). |
| Cluster overlap | `OVER=0.70` | 0.70 | <1 lets galaxies overlap into one mass. Lower = tighter/more blended. |
| Cluster size | `r=31*Math.sqrt(n)+10` | — | Bigger number = larger, sparser genres. |
| Clump tightness | `var spread=Math.min(R*0.17,` … | 0.17 | How tightly same‑director titles clump. |
| Center density | `Math.pow(u,0.55)` | 0.55 | Lower = more titles pulled toward each galaxy's core. |

### 6.3 Stars (the dots) — size = watch length
| What | Find | Now | Effect |
|---|---|---|---|
| Dot size vs length | `function minsToRad(m){` → `0.6+0.19*Math.sqrt(m)` | clamp 1.15–7.0 | Maps minutes to radius. Raise the `0.19` for a bigger spread between short and long; raise the `7.0` clamp to let the longest series grow further. |
| Series length | `EPISODES` (Python, §5a) | 20 / 6 | The per‑episode → total multiplier that makes series big. |
| Dark star‑glow strength | `ctx.globalAlpha=…?0.04:0.12;` | 0.12 | Brightness of each star's halo in dark mode. |
| Dark glow size | `var gz=Math.max(30, rr*22);` | 22 | Halo size relative to dot size. |
| Light glow shape | `glowSpriteTight()` | tight falloff | Light mode uses its **own** sprite. The wide dark‑mode tail, drawn in a deep colour on white, spreads into a pale film — this one keeps the saturation close to the node so the deep palette still reads as vibrant. |
| Light glow strength / size | `?0.16:0.62` · `rr*12` | 0.62 / 12 | Higher alpha over a smaller radius than dark mode. Lower the alpha or raise the radius and light mode washes out again. |
| Light genre‑cloud alpha | the `else` branch of the cloud gradient | 0.185 / 0.115 | Deliberately under the dark‑mode alphas so the near‑black genres don't blot. |
| Light filament alpha | `(pa&&pb)?0.17:0.05` | 0.17 | Fainter than it was for the pale palette — deep filaments read as scribble at higher values. |
| Watched dot opacity | `hexA(col,dark?.36:.28)` | — | How faded a watched star looks. |
| Filtered‑out dots | `"rgba(190,194,203,.4)"` / `"rgba(120,132,164,.26)"` | grey | Titles hidden by a filter (light / dark). |
| Selection ring | strokeStyle in `drawAccent()` | theme‑aware | Selected vs. hover ring colour. |

### 6.4 Genre labels (hover / zoom reveal)
| What | Find | Now | Effect |
|---|---|---|---|
| Zoom fade‑in range | `var zoomA = cam.s<=0.42?0 : cam.s>=0.78?1 :` | 0.42→0.78 | Labels fade in between these zoom levels. Lower both to show them sooner. |
| Label size | `Math.min(27,m.r*cam.s*0.085)` | 27 / 0.085 | Cap and scale of label font. |
| Dark‑label brightness | `var LABEL_LUM=208;` / `brightenLabel()` | 208 | The important one. Each heading is first saturated, then mixed toward white by *exactly* enough to reach this luminance — so it is a **floor**, not a nudge, and no genre can come out dull. The deep navies (Biography, Thriller, Mystery, Documentary) went from luminance 88–117 to a uniform 208. Raise for brighter, lower for moodier; the trade‑off is that a higher value pulls every hue toward pastel. |
| Light‑label colour | `m.lcolor` | — | Light mode uses the deep light palette as‑is; it is already dark enough to read on white without extra shading. |
| Label backdrop | `rgba(3,5,12,0.9*a)` (dark) | 0.9 | Drawn 1px behind the text so headings keep contrast over a bright nebula. |
| Collision padding | the box math around `drawnBoxes` | — | Governs how aggressively overlapping labels are dropped. |

### 6.5 Ratings & filters
| What | Find | Now | Effect |
|---|---|---|---|
| Rating scale | `var MAXR=10;` | 10 | IMDb's scale. Drives the star rows and the filter. |
| Star colour (filled) | `.stars .star.on{color:#f5b301}` (CSS) | gold | The filled‑star colour everywhere. |
| Rating filter | `#ratefilterStars` / `state.minRating` | — | The "My rating ≥ N" control; filter logic is in `passFilter`. |
| Status filter | `#statusSeg` (`all` / `unwatched` / `rated`) | all | `rated` means "has a score"; `unwatched` means "not in the ratings export". |
| Type filter | `TYPE_BTNS` / `state.type` | all | All / Movies / Series / Games, from the `ty` bucket. |
| Random pickers | `suggest(kind,label)` | — | Always picks something **unwatched**; respects genre / type / search but not the status and rating filters. |

### 6.6 Camera & motion
| What | Find | Now | Effect |
|---|---|---|---|
| Fit padding | `var pad=60,` | 60 | Margin around the galaxy when framed. |
| Zoom limits | `Math.max(0.03,Math.min(16,` | 0.03–16 | Min/max zoom. |
| Intro zoom‑in | `cam.s=ts*0.72; flyTo(tx,ty,ts,1200);` | 0.72 / 1200ms | Opening animation start scale and duration. |
| Orbit text zoom gate | `if(cam.s>1.8)` | 1.8 | When the rotating director/genre/length ring appears in dark mode. |

### 6.7 Data / persistence (localStorage keys)
| What | Find | Now | Effect |
|---|---|---|---|
| Watched key | `var LS_KEY="avmu-watched-v1";` | array of ids | Which titles are watched. Bump the version to reset. |
| Ratings key | `var RATE_KEY="avmu-ratings-v1";` | `{id: 1‑10}` | Your IMDb scores. |
| Theme key | `var THEME_KEY="avmu-theme-v1";` | `"light"`/`"dark"` | Remembered light/dark choice. |
| IMDb seed | `var SEED_KEY` + `SEED_VERSION="imdb-1";` | applied once | On first load, `SEED_WATCHED`/`SEED_RATINGS` (baked from the CSVs at build time) are merged into `localStorage`. Bump `SEED_VERSION` after a new export. |
| Embedded data | `const TITLES =` | — | Generated by the pipeline — don't hand‑edit; change the CSVs + rebuild. |

---

## 7. Common recipes

**Recolor a genre** — change its hex in **both** `GENRE_COLORS` (dark) and `LIGHT_COLORS`
(light), then rebuild. Editing one map only shifts that one theme.

**Make the dark genre headings brighter / moodier** — change `LABEL_LUM` (§6.4).

**Make series bigger / smaller relative to films** — change `EPISODES` in `pipeline.py` (§5a).

**Change how strongly length affects dot size** — edit `minsToRad()` (§6.3).

**Open in dark mode by default** — change `||"light"` to `||"dark"` on the `theme` line.

**Show genre labels sooner** — lower the two numbers in `var zoomA = cam.s<=0.42?0 : cam.s>=0.78?1`
(e.g. `0.25` and `0.5`).

**Separate the galaxies more (less blended)** — raise `OVER` toward `0.95`, or raise `SP`.

**Reshape the genre clusters** — reorder `GENRE_PRIORITY` in `pipeline.py`. Whatever sits near
the top becomes a bigger, more distinct galaxy; e.g. moving `Crime` above `Action` moves a few
hundred titles between those two clusters. Re‑run and read the printed distribution.

**Split a genre back out** — lower `MIN_CLUSTER` (currently 8) so smaller genres keep their own
galaxy instead of being folded away.

**Refresh from newer IMDb exports** — replace the two CSVs, re‑run, bump `SEED_VERSION`. See §5b.

**Reset watched progress to the IMDb baseline** — clear the site's `localStorage`; the seed
re‑applies on next load.

---

## 8. Data model

Each embedded title is a small object:

```js
{ id: 0, t: "Barry", d: "", g: "Action", ty: "Series", tt: "TV Series",
  yr: 2018, rt: 30, m: 600, ep: 20, ir: 8.3, c: "tt5348176" }
//  t=title  d=director(s)  g=genre  ty=Movie|Series|Game  tt=exact IMDb type
//  yr=year  rt=runtime per episode/film  m=total watch minutes (drives dot size)
//  ep=episode multiplier used  ir=IMDb score  c=IMDb const
// optional: ot=original title (only when it differs)  e=1 if the runtime was estimated
```

> **Careful with field names:** `buildLayout()` writes `b.x`, `b.y`, `b.color` and `b.rad` onto
> these objects as map coordinates. That is why the year is `yr` and not `y` — a `y` field would
> be silently overwritten by the layout.

Watched status, scores, and theme are **not** stored in the file — they live in `localStorage`:
a title is "watched" iff its `id` is in the array under `LS_KEY`; scores are `{id: 1‑10}` under
`RATE_KEY`; theme under `THEME_KEY`. At build time the pipeline bakes your IMDb history into
`SEED_WATCHED` (ids) and `SEED_RATINGS` (`{id: 1‑10}`); on first open the app merges those into
`localStorage` once, guarded by `SEED_VERSION`.

---

## 9. Notes, limits, and future ideas

- **Series lengths are approximations** (§5a) — the IMDb export has no episode count.
- **Genres are IMDb's**, reduced to one per title by a priority list, so a few picks are
  arguable. Reordering `GENRE_PRIORITY` is the one‑line fix.
- **76 runtimes were missing** from the exports and are filled from library medians. The detail
  panel marks those with `(est.)`.
- **Directors are missing for ~465 titles** — normal, since IMDb credits series to creators
  rather than directors. Those titles cluster as singletons and read "Director uncredited".
- The map is a **designed layout**, not a true similarity embedding (like UMAP). It looks
  organic but positions are decorative, not semantic.
- Possible future features: decade filter, poster thumbnails, "where to stream", per‑title notes,
  a shareable hosted link, stats view (hours watched per genre / per year).

---

*Built as a single self‑contained HTML file so it stays simple, private, and offline‑friendly.
Keep the "stable code" (`AV Movie Universe.html`) working; use the knobs in §6 to make it yours.*

---

## Recent Changes

- **Converted from AV's Library to AV Movie Universe**: the book pipeline was replaced with an
  IMDb pipeline reading `My_watchlist_imdb.csv` + `My_rating_imdb.csv`; the app was renamed to
  `AV Movie Universe.html` and `index.html` now redirects there.
- **Domain mapping**: books → titles, author → director, pages → watch length, read/unread →
  watched/unwatched, eBook/Bookshelf → Movie/Series/Game, Goodreads 1–5 → IMDb 1–10.
- **Node size = watch length**: `minsToRad()` replaces `pagesToRad()`, and series runtimes are
  scaled from per‑episode to approximate totals so a long show outshines a short film.
- **Menu bar**: "Watch Tonight" plus dedicated **Random movie** / **Random series** buttons;
  status filter is now All / Unwatched / Rated; a four‑way Movies / Series / Games type filter;
  the rating filter is a 10‑star row reading "My rating ≥ N".
- **Detail panel**: adds year, IMDb title type, runtime (with `/ep · ≈total` for series), the
  IMDb score, a link out to IMDb, and "more by this director".
- **Palette rebuilt for 21 movie genres**, with hues spread so the largest genres are the most
  distinct and near‑white reserved for the smallest.
- **Read-Only Mode** (carried over): the UI never edits watched status or scores — those come
  from the IMDb exports through the pipeline. Searching and filtering are fully functional.
- **Light mode is darker and more vibrant**: it now has its own palette (`LIGHT_COLORS`) of deep
  blues, teals, dark greens and black, instead of tinting the dark-mode one. To keep those deep
  colours from washing into a pale film, light mode also got a tighter glow sprite
  (`glowSpriteTight`) drawn smaller and at higher alpha, plus lower cloud and filament alphas.
- **Dark-mode genre headings are brighter**: `brightenLabel()` now mixes each heading toward
  white until it hits a luminance floor (`LABEL_LUM = 208`), so genres like Biography, Thriller
  and Mystery — previously near-invisible on black — read as clearly as the bright ones.
- **Orbit text skips a missing director**: an uncredited title now shows `Genre · Length` rather
  than a placeholder.
- **Chrome follows the theme**: legend swatches, the detail-panel genre tag, and search-result
  genre text all use the active theme's palette; the legend is rebuilt on theme toggle.
