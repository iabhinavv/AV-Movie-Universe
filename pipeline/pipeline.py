# -*- coding: utf-8 -*-
"""
AV Movie Universe — build pipeline.

Reads the two IMDb exports that live one folder up:

    My_watchlist_imdb.csv   -> titles you have NOT watched yet (the "to-watch" list)
    My_rating_imdb.csv      -> titles you HAVE watched, with your 1-10 rating

and writes the whole self-contained app to  ../AV Movie Universe.html

Run it with:   python3 pipeline.py      (no third-party dependencies)
"""
import csv, json, os, re, math, statistics, unicodedata
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WATCHLIST_CSV = os.path.join(ROOT, 'My_watchlist_imdb.csv')
RATINGS_CSV   = os.path.join(ROOT, 'My_rating_imdb.csv')
DEST          = os.path.join(ROOT, 'AV Movie Universe.html')

# ---------------------------------------------------------------------------
# 1. LOAD  —  two CSVs -> one de-duplicated record per IMDb const (tt……)
# ---------------------------------------------------------------------------
def read_csv(path):
    if not os.path.exists(path):
        print('!! missing', path)
        return []
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

def s(row, key):
    return (row.get(key) or '').strip()

def to_int(v):
    try: return int(float(str(v).strip()))
    except (TypeError, ValueError): return None

def to_float(v):
    try: return float(str(v).strip())
    except (TypeError, ValueError): return None

records = {}          # const -> record

def ingest(rows, watched):
    for row in rows:
        const = s(row, 'Const')
        title = s(row, 'Title') or s(row, 'Original Title')
        if not const or not title:
            continue
        my = to_int(s(row, 'Your Rating'))
        rec = {
            'const'   : const,
            'title'   : title,
            'orig'    : s(row, 'Original Title'),
            'url'     : s(row, 'URL') or 'https://www.imdb.com/title/%s/' % const,
            'ttype'   : s(row, 'Title Type') or 'Movie',
            'imdb'    : to_float(s(row, 'IMDb Rating')),
            'runtime' : to_int(s(row, 'Runtime (mins)')),
            'year'    : to_int(s(row, 'Year')),
            'genres'  : [g.strip() for g in s(row, 'Genres').split(',') if g.strip()],
            'votes'   : to_int(s(row, 'Num Votes')),
            'director': s(row, 'Directors'),
            'my'      : my,
            'watched' : bool(watched or my),
        }
        prev = records.get(const)
        # a rated row always wins over a watchlist row for the same title
        if prev is None or (rec['watched'] and not prev['watched']):
            records[const] = rec

ingest(read_csv(WATCHLIST_CSV), watched=False)
ingest(read_csv(RATINGS_CSV),   watched=True)

titles = list(records.values())
print('loaded %d unique titles (%d watched / %d unwatched)'
      % (len(titles), sum(1 for t in titles if t['watched']),
                      sum(1 for t in titles if not t['watched'])))

# ---------------------------------------------------------------------------
# 2. TIDY  —  titles + directors
# ---------------------------------------------------------------------------
def strip_diacritics(s_):
    return ''.join(c for c in unicodedata.normalize('NFKD', s_) if not unicodedata.combining(c))

def norm(s_):
    s_ = strip_diacritics(s_ or '').lower()
    s_ = re.sub(r'[^a-z0-9 ]', ' ', s_)
    return re.sub(r'\s+', ' ', s_).strip()

def first_director(raw):
    """IMDb packs co-directors into one comma-separated cell. The first one is
    used for clustering / 'more by this director'; the full list is shown in the
    detail panel."""
    if not raw: return ''
    d = raw.split(',')[0].strip()
    return d if len(d) < 60 else ''

for t in titles:
    t['title'] = re.sub(r'\s+', ' ', t['title']).strip()
    t['dir_all'] = t['director']
    t['dir'] = first_director(t['director'])
    if t['orig'] == t['title']:
        t['orig'] = ''

# ---------------------------------------------------------------------------
# 3. GENRE  —  IMDb tags a title with 1-4 genres; the map needs exactly one.
#    We pick the most *specific* one, using this priority list (earlier wins).
#    Reorder it to reshape the galaxies: whatever sits near the top becomes a
#    bigger, more distinct cluster.
# ---------------------------------------------------------------------------
GENRE_PRIORITY = [
    'Film-Noir', 'Documentary', 'Animation', 'Horror', 'Sci-Fi', 'Fantasy',
    'Western', 'War', 'Musical', 'Music', 'Sport', 'Biography', 'History',
    'Action', 'Adventure', 'Crime', 'Mystery', 'Thriller', 'Romance', 'Family',
    'Comedy', 'Drama', 'Reality-TV', 'Talk-Show', 'Game-Show', 'News',
    'Short', 'Adult',
]
GRANK = {g: i for i, g in enumerate(GENRE_PRIORITY)}
FALLBACK_GENRE = 'Drama'
MIN_CLUSTER = 8          # genres smaller than this are folded into the next best

def pick(gl, allowed=None):
    gl = [g for g in gl if allowed is None or g in allowed]
    if not gl: return None
    return min(gl, key=lambda g: GRANK.get(g, 99))

# pass 1: naive most-specific pick, to find out which genres are worth a galaxy
first_pass = Counter(pick(t['genres']) or FALLBACK_GENRE for t in titles)
ALLOWED = {g for g, n in first_pass.items() if n >= MIN_CLUSTER} or {FALLBACK_GENRE}
ALLOWED.add(FALLBACK_GENRE)
# pass 2: final assignment, restricted to genres that earned a galaxy
for t in titles:
    t['genre'] = pick(t['genres'], ALLOWED) or FALLBACK_GENRE

# ---------------------------------------------------------------------------
# 4. TYPE + LENGTH  —  length drives the node size on the map
# ---------------------------------------------------------------------------
# Coarse bucket used by the Movies / Series / Games filter.
TYPE_BUCKET = {
    'Movie': 'Movie', 'TV Movie': 'Movie', 'Video': 'Movie', 'Short': 'Movie',
    'TV Short': 'Movie', 'Music Video': 'Movie', 'TV Special': 'Movie',
    'TV Series': 'Series', 'TV Mini Series': 'Series', 'TV Episode': 'Series',
    'Podcast Series': 'Series', 'Podcast Episode': 'Series',
    'Video Game': 'Game',
}
# IMDb's "Runtime (mins)" for a series is the length of ONE episode, so a 5-season
# show would otherwise be a smaller dot than a single film. These multipliers turn
# the per-episode runtime into an approximate *total* watch length. They are rough
# by design — change them here and rebuild to resize every series on the map.
EPISODES = {'TV Series': 20, 'TV Mini Series': 6, 'Podcast Series': 20}
PER_EPISODE_CEILING = 200   # a "runtime" above this is already a total, not an episode
MAX_MINUTES = 3000          # clamp so one huge show doesn't flatten every other dot

for t in titles:
    t['bucket'] = TYPE_BUCKET.get(t['ttype'], 'Movie')

# fill in missing runtimes from the medians of this very library (type first,
# then genre) rather than from invented constants
_by_type  = defaultdict(list)
_by_genre = defaultdict(list)
for t in titles:
    if t['runtime']:
        _by_type[t['ttype']].append(t['runtime'])
        _by_genre[t['genre']].append(t['runtime'])
MED_TYPE  = {k: int(statistics.median(v)) for k, v in _by_type.items()  if v}
MED_GENRE = {k: int(statistics.median(v)) for k, v in _by_genre.items() if v}
MED_ALL   = int(statistics.median([t['runtime'] for t in titles if t['runtime']] or [100]))

n_est = 0
for t in titles:
    if not t['runtime']:
        t['runtime'] = MED_TYPE.get(t['ttype']) or MED_GENRE.get(t['genre']) or MED_ALL
        t['est'] = True
        n_est += 1
    else:
        t['est'] = False
    eps = EPISODES.get(t['ttype'], 1)
    if eps > 1 and t['runtime'] > PER_EPISODE_CEILING:
        eps = 1                      # already a total runtime — don't multiply again
    t['eps'] = eps
    t['mins'] = min(t['runtime'] * eps, MAX_MINUTES)

# ---------------------------------------------------------------------------
# 5. REPORT
# ---------------------------------------------------------------------------
gc = Counter(t['genre'] for t in titles)
print()
print('=== GENRE DISTRIBUTION ===')
for g, c in gc.most_common():
    print('%5d  %s' % (c, g))
print('genres', len(gc), '/ titles', len(titles))
print()
print('=== TYPE ===', dict(Counter(t['bucket'] for t in titles)))
print('=== IMDB TYPES ===', dict(Counter(t['ttype'] for t in titles).most_common()))
print('runtimes estimated from library medians:', n_est)
missing_dir = sum(1 for t in titles if not t['dir'])
print('titles without a director credit (normal for series):', missing_dir)

# ---------------------------------------------------------------------------
# 6. EMIT  —  slim records + the watched/rating seed
# ---------------------------------------------------------------------------
titles.sort(key=lambda t: (t['genre'], norm(t['dir']), norm(t['title'])))
for i, t in enumerate(titles):
    t['id'] = i

slim = [{
    'id': t['id'],
    't' : t['title'],
    'd' : t['dir_all'],
    'g' : t['genre'],
    'ty': t['bucket'],
    'tt': t['ttype'],
    'yr': t['year'] or 0,          # NB: not "y" — buildLayout() writes b.y (the map coordinate)
    'rt': t['runtime'],
    'm' : t['mins'],
    'ep': t['eps'],
    'ir': t['imdb'] or 0,
    'c' : t['const'],
} for t in titles]
for t, r in zip(titles, slim):
    if t['orig']: r['ot'] = t['orig']
    if t['est']:  r['e'] = 1

data_json = json.dumps(slim, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
seed_watched = [t['id'] for t in titles if t['watched']]
seed_ratings = {t['id']: t['my'] for t in titles if t['my']}
seed_watched_json = json.dumps(seed_watched, separators=(',', ':'))
seed_ratings_json = json.dumps(seed_ratings, separators=(',', ':'))

HTML = r'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<title>AV Movie Universe</title>
<style>
:root{
  --bg:#ffffff; --map-bg:#ffffff;
  --ink:#1d2430; --muted:#6b7280; --muted2:#9aa1ad;
  --line:#e7e9ee; --line2:#dfe2e8;
  --panel:#ffffff; --chip:#f4f5f8; --card:#ffffff; --field:#f7f8fb; --hover:#f1f1fb;
  --seg-bg:#f2f3f7; --topbar-bg:rgba(255,255,255,.92); --zoom-bg:rgba(255,255,255,.95); --hint-bg:rgba(255,255,255,.8);
  --accent:#5b57e0; --accent2:#37b6cf; --good:#1aa06d;
  --shadow:0 10px 34px rgba(30,36,60,.14);
  --shadow-sm:0 2px 10px rgba(30,36,60,.10);
  --font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  --topbar-h:56px;
}
body.theme-dark{
  --bg:#05060c; --map-bg:#05060c;
  --ink:#e9edf6; --muted:#9aa2b6; --muted2:#6b7386;
  --line:#1c2236; --line2:#2a3350;
  --panel:#0d111e; --chip:#161c2e; --card:#0d111e; --field:#121728; --hover:#1a2136;
  --seg-bg:#141a2b; --topbar-bg:rgba(9,12,22,.86); --zoom-bg:rgba(16,20,34,.92); --hint-bg:rgba(12,16,28,.7);
  --accent:#8189ff; --accent2:#49c7e0; --good:#38d39b;
  --shadow:0 12px 40px rgba(0,0,0,.55);
  --shadow-sm:0 2px 12px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden;background:var(--bg);color:var(--ink);font-family:var(--font);-webkit-font-smoothing:antialiased}
#app{position:fixed;inset:0}
canvas{display:block;position:absolute;inset:0;top:var(--topbar-h);touch-action:none;cursor:grab;background:var(--map-bg)}
canvas.grabbing{cursor:grabbing}
button{font-family:var(--font)}

/* ---------------- top bar ---------------- */
#topbar{position:absolute;top:0;left:0;right:0;height:var(--topbar-h);z-index:30;display:flex;align-items:center;gap:12px;
  padding:0 14px;background:var(--topbar-bg);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  border-bottom:1px solid var(--line)}
#burger{width:38px;height:38px;border-radius:10px;border:1px solid var(--line2);background:var(--card);cursor:pointer;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;flex:none;transition:.15s}
#burger:hover{border-color:var(--accent);background:var(--hover)}
#burger span{width:16px;height:2px;background:var(--ink);border-radius:2px;display:block}
.brand{display:flex;align-items:center;gap:8px;user-select:none}
.brand .logo{width:22px;height:22px;flex:none}
.brand .name{font-weight:800;font-size:17px;letter-spacing:.2px;white-space:nowrap}
.brand .name b{color:var(--accent)}
#topbar .spacer{flex:1}
#topbar .prog{font-size:12.5px;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
#topbar .prog b{color:var(--ink)}
#searchIcon,#themeBtn{width:38px;height:38px;border-radius:10px;border:1px solid var(--line2);background:var(--card);color:var(--ink);cursor:pointer;flex:none;
  display:flex;align-items:center;justify-content:center;transition:.15s}
#searchIcon:hover,#themeBtn:hover{border-color:var(--accent);background:var(--hover);color:var(--accent)}
#themeBtn .ic-sun{display:none}
body.theme-dark #themeBtn .ic-moon{display:none}
body.theme-dark #themeBtn .ic-sun{display:block}

/* ---------------- drawer ---------------- */
#scrim{position:absolute;inset:0;z-index:38;background:rgba(20,24,40,.18);opacity:0;pointer-events:none;transition:.25s}
#scrim.on{opacity:1;pointer-events:auto}
#drawer{position:absolute;top:0;left:0;bottom:0;z-index:40;width:320px;max-width:86vw;background:var(--panel);
  border-right:1px solid var(--line);box-shadow:18px 0 50px rgba(30,36,60,.12);
  transform:translateX(-104%);transition:transform .3s cubic-bezier(.22,.9,.3,1);
  display:flex;flex-direction:column;overflow:hidden}
#drawer.on{transform:translateX(0)}
.dwrap{padding:16px 15px 22px;overflow-y:auto;display:flex;flex-direction:column;gap:13px;height:100%}
.dhead{display:flex;align-items:center;justify-content:space-between}
.dhead .t{font-size:15px;font-weight:800}
.dhead .x{width:30px;height:30px;border:1px solid var(--line2);border-radius:9px;background:var(--card);cursor:pointer;color:var(--muted);font-size:15px}
.dhead .x:hover{color:var(--ink)}

.searchwrap{position:relative}
#search{width:100%;padding:11px 12px 11px 36px;border-radius:11px;border:1px solid var(--line2);background:var(--field);color:var(--ink);
  font-size:14px;font-family:var(--font);outline:none}
#search:focus{border-color:var(--accent);background:var(--card)}
.searchwrap>svg{position:absolute;left:11px;top:50%;transform:translateY(-50%);opacity:.5}
#results{margin-top:7px;max-height:250px;overflow:auto;border-radius:11px;border:1px solid var(--line);background:var(--card);display:none}
#results.on{display:block}
.res{padding:9px 12px;cursor:pointer;border-bottom:1px solid var(--line)}
.res:last-child{border-bottom:none}
.res:hover,.res.sel{background:var(--hover)}
.res .rt{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.res .ra{font-size:11px;color:var(--muted);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.res .rg{font-weight:700}

#tonight{width:100%;padding:12px;border:none;border-radius:12px;cursor:pointer;font-size:14.5px;font-weight:800;color:#fff;letter-spacing:.2px;
  background:linear-gradient(135deg,#6b5cff 0%,#37b6cf 100%);box-shadow:0 6px 18px rgba(91,87,224,.28);
  display:flex;align-items:center;justify-content:center;gap:8px;transition:transform .12s}
#tonight:hover{transform:translateY(-1px)}

.seg{display:flex;background:var(--seg-bg);border:1px solid var(--line2);border-radius:11px;padding:3px;gap:3px}
.seg button{flex:1;padding:8px 6px;border:none;border-radius:8px;background:transparent;color:var(--muted);font-size:12px;font-weight:700;cursor:pointer;transition:.15s}
.seg button.on{background:var(--card);color:var(--accent);box-shadow:var(--shadow-sm)}

.row{display:flex;gap:8px}
.mini{flex:1;padding:9px 6px;border:1px solid var(--line2);border-radius:10px;background:var(--card);color:var(--muted);font-size:11.5px;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:5px;transition:.15s;white-space:nowrap}
.mini:hover{color:var(--ink);border-color:var(--accent)}
.mini.on{color:var(--accent);border-color:var(--accent);background:var(--hover)}

.ldiv{height:1px;background:var(--line);margin:3px 0}
.lh{display:flex;align-items:center;justify-content:space-between;padding:0 2px}
.lh span{font-size:11px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.7px}
.lh a{font-size:11px;color:var(--accent);cursor:pointer}
#genres{display:flex;flex-direction:column;gap:1px}
.gitem{display:flex;align-items:center;gap:9px;padding:6px 7px;border-radius:9px;cursor:pointer;transition:.12s}
.gitem:hover{background:var(--hover)}
.gitem.off{opacity:.4}
.dot{width:10px;height:10px;border-radius:50%;flex:none}
.gitem .gname{flex:1;font-size:12.5px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gitem .gcount{font-size:11px;color:var(--muted2);font-variant-numeric:tabular-nums}

/* ---------------- zoom ---------------- */
#zoom{position:absolute;bottom:20px;right:16px;z-index:22;display:flex;flex-direction:column;gap:8px}
#zoom button{width:40px;height:40px;border-radius:11px;border:1px solid var(--line2);background:var(--zoom-bg);color:var(--ink);
  font-size:19px;cursor:pointer;box-shadow:var(--shadow-sm);display:flex;align-items:center;justify-content:center;transition:.12s}
#zoom button:hover{border-color:var(--accent);color:var(--accent)}
#zoom .z-lbl{font-size:11px;font-weight:700}

#hint{position:absolute;bottom:22px;left:50%;transform:translateX(-50%);z-index:15;font-size:12px;color:var(--muted2);
  background:var(--hint-bg);padding:6px 14px;border-radius:20px;border:1px solid var(--line);pointer-events:none;transition:opacity .6s;white-space:nowrap}

/* ---------------- tooltip (dark pill) ---------------- */
#tip{position:absolute;z-index:44;pointer-events:none;display:none;max-width:250px;padding:8px 11px;background:#1e2330;color:#fff;
  border-radius:10px;box-shadow:0 8px 24px rgba(20,24,40,.28);transform:translate(-50%,calc(-100% - 14px))}
#tip .tt{font-size:12.5px;font-weight:700;line-height:1.25}
#tip .ta{font-size:11px;color:#c3c7d4;margin-top:2px}
#tip .tg{font-size:10px;margin-top:5px;display:inline-flex;align-items:center;gap:5px;font-weight:700}
#tip .ts{font-size:10px;color:#9aa1b2;margin-top:3px}

/* ---------------- detail ---------------- */
#detail{position:absolute;top:var(--topbar-h);right:0;bottom:0;z-index:36;width:350px;max-width:88vw;background:var(--card);
  border-left:1px solid var(--line);box-shadow:-16px 0 46px rgba(30,36,60,.14);
  transform:translateX(105%);transition:transform .32s cubic-bezier(.22,.9,.3,1);display:flex;flex-direction:column;padding:22px;overflow-y:auto}
#detail.on{transform:translateX(0)}
#detail .close{position:absolute;top:15px;right:15px;width:31px;height:31px;border-radius:9px;border:1px solid var(--line2);background:var(--card);color:var(--muted);cursor:pointer;font-size:15px}
#detail .close:hover{color:var(--ink)}
#detail .dtag{align-self:flex-start;margin-top:6px;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.6px;padding:5px 11px;border-radius:20px;display:inline-flex;align-items:center;gap:6px}
#detail h2{margin:15px 0 5px;font-size:22px;line-height:1.2;font-weight:800}
#detail .dauth{font-size:14px;color:var(--muted);margin-bottom:2px}
#detail .dorig{font-size:12px;color:var(--muted2);font-style:italic;margin-top:3px}
#detail .dmeta{margin-top:16px;display:flex;flex-direction:column;gap:9px}
#detail .drow{display:flex;justify-content:space-between;gap:10px;font-size:13px;padding:9px 12px;background:var(--field);border-radius:10px;border:1px solid var(--line)}
#detail .drow b{color:var(--muted);font-weight:600;flex:none}
#detail .drow span{text-align:right}
#imdbLink{margin-top:16px;width:100%;padding:12px;border-radius:12px;border:1px solid var(--line2);background:var(--field);color:var(--ink);
  text-decoration:none;font-size:13.5px;font-weight:700;display:flex;align-items:center;justify-content:center;gap:8px;transition:.15s}
#imdbLink:hover{border-color:var(--accent);color:var(--accent)}
#detail .dsub{margin-top:20px;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.6px;color:var(--muted2)}
#detail .chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:10px}
#detail .chip{font-size:12px;padding:7px 11px;border-radius:9px;background:var(--chip);border:1px solid var(--line);cursor:pointer;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;transition:.12s}
#detail .chip:hover{color:var(--ink);border-color:var(--accent)}

/* ---------------- star ratings (IMDb 1-10 scale) ---------------- */
.stars{display:inline-flex;gap:2px;align-items:center}
.stars .star{font-size:22px;line-height:1;color:var(--line2);transition:color .1s,transform .1s;user-select:none}
.stars .star.on{color:#f5b301}
.stars.ten .star{font-size:15px}
.ratefilter{display:flex;flex-direction:column;gap:5px;background:var(--seg-bg);border:1px solid var(--line2);border-radius:11px;padding:8px 10px}
.ratefilter .rf-top{display:flex;align-items:center;gap:8px}
.ratefilter .rf-label{font-size:11px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
.ratefilter .rf-val{margin-left:auto;font-size:11.5px;color:var(--muted2);font-variant-numeric:tabular-nums}
.ratefilter .rf-clear{border:none;background:transparent;color:var(--muted2);cursor:pointer;font-size:14px;padding:0 3px;border-radius:6px;visibility:hidden}
.ratefilter .rf-clear.on{visibility:visible}
.ratefilter .rf-clear:hover{color:var(--ink)}
.ratefilter .stars{justify-content:space-between;gap:0}
.ratefilter .stars .star{cursor:pointer}
.ratefilter .stars .star:hover{transform:scale(1.18)}
#detail .drate{margin-top:16px;display:flex;flex-direction:column;gap:5px;padding:11px 12px;background:var(--field);border:1px solid var(--line);border-radius:11px}
#detail .drate .dtop{display:flex;align-items:center;gap:8px}
#detail .drate .dlabel{font-size:11px;font-weight:800;color:var(--muted);text-transform:uppercase;letter-spacing:.6px}
#detail .drate .dratev{margin-left:auto;font-size:12px;color:var(--muted2);white-space:nowrap}
#detail .drate .stars{justify-content:space-between;gap:0}
#topbar .prog .ravg{color:#e0a300;font-weight:700}
.res .rr{color:#f5b301}
#tip .trate{color:#ffcf4d;font-size:11px;margin-top:4px;font-weight:700}

#toast{position:absolute;bottom:74px;left:50%;transform:translateX(-50%) translateY(16px);z-index:70;background:#1e2330;color:#fff;
  border-radius:11px;padding:11px 18px;font-size:13.5px;font-weight:600;box-shadow:0 10px 30px rgba(20,24,40,.3);opacity:0;transition:.3s;pointer-events:none;max-width:80vw;text-align:center}
#toast.on{opacity:1;transform:translateX(-50%) translateY(0)}

.dwrap::-webkit-scrollbar,#detail::-webkit-scrollbar,#results::-webkit-scrollbar{width:8px}
.dwrap::-webkit-scrollbar-thumb,#detail::-webkit-scrollbar-thumb,#results::-webkit-scrollbar-thumb{background:#d7dae1;border-radius:8px}
@media (max-width:560px){ #topbar .prog{display:none} }
</style>
</head>
<body>
<div id="app">
  <canvas id="cv"></canvas>

  <header id="topbar">
    <button id="burger" aria-label="Menu"><span></span><span></span><span></span></button>
    <div class="brand">
      <svg class="logo" viewBox="0 0 24 24"><path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4L12 2z" fill="url(#lg)"/><defs><linearGradient id="lg" x1="3" y1="2" x2="21" y2="20"><stop stop-color="#6b5cff"/><stop offset="1" stop-color="#37b6cf"/></linearGradient></defs></svg>
      <div><div class="name">AV Movie <b>Universe</b></div></div>
    </div>
    <div class="spacer"></div>
    <div class="prog"><b id="pcount">0</b> / <span id="tcount">0</span> watched<span id="ravgWrap"></span></div>
    <button id="themeBtn" aria-label="Toggle light or dark" title="Toggle light / dark">
      <svg class="ic-moon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/></svg>
      <svg class="ic-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
    </button>
    <button id="searchIcon" aria-label="Search"><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg></button>
  </header>

  <div id="scrim"></div>
  <aside id="drawer">
    <div class="dwrap">
      <div class="dhead"><div class="t">Explore</div><button class="x" id="drawerClose">✕</button></div>
      <div class="searchwrap">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#9aa1ad" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>
        <input id="search" placeholder="Search title or director…" autocomplete="off" spellcheck="false">
        <div id="results"></div>
      </div>
      <button id="tonight">✦ Watch Tonight</button>
      <div class="row">
        <button class="mini" id="randMovie">🎬 Random movie</button>
        <button class="mini" id="randSeries">📺 Random series</button>
      </div>
      <div class="seg" id="statusSeg">
        <button data-s="all" class="on">All</button>
        <button data-s="unwatched">Unwatched</button>
        <button data-s="rated">Rated</button>
      </div>
      <div class="ratefilter">
        <div class="rf-top">
          <span class="rf-label">My rating ≥</span>
          <span class="rf-val" id="rateVal">any</span>
          <button class="rf-clear" id="rateClear" title="Clear rating filter">✕</button>
        </div>
        <span class="stars ten" id="ratefilterStars"></span>
      </div>
      <div class="row">
        <button class="mini on" id="tyAll" data-ty="all">All</button>
        <button class="mini" id="tyMovie" data-ty="Movie">Movies</button>
        <button class="mini" id="tySeries" data-ty="Series">Series</button>
        <button class="mini" id="tyGame" data-ty="Game">Games</button>
      </div>
      <div class="row">
        <button class="mini" id="connBtn">✧ Connections</button>
      </div>
      <div class="ldiv"></div>
      <div class="lh"><span>Genres</span><a id="genAll">reset</a></div>
      <div id="genres"></div>
    </div>
  </aside>

  <div id="zoom">
    <button id="zin">+</button>
    <button id="zout">−</button>
    <button id="zfit" title="Fit to view"><span class="z-lbl">fit</span></button>
  </div>

  <div id="hint">Drag to pan · scroll to zoom · hover a region for its name · click a dot for details · ☰ menu</div>
  <div id="tip"></div>

  <div id="detail">
    <button class="close" id="dclose">✕</button>
    <div class="dtag" id="dtag"></div>
    <h2 id="dtitle"></h2>
    <div class="dauth" id="dauth"></div>
    <div class="dorig" id="dorig" style="display:none"></div>
    <div class="dmeta">
      <div class="drow"><b>Genre</b><span id="dgenre"></span></div>
      <div class="drow"><b>Type</b><span id="dtype"></span></div>
      <div class="drow"><b>Year</b><span id="dyear"></span></div>
      <div class="drow"><b>Runtime</b><span id="druntime"></span></div>
      <div class="drow"><b>IMDb</b><span id="dimdb"></span></div>
      <div class="drow"><b>Status</b><span id="dstatus"></span></div>
    </div>
    <div class="drate">
      <div class="dtop">
        <span class="dlabel">My rating</span>
        <span class="dratev" id="dratev">Not rated</span>
      </div>
      <span class="stars ten" id="dstars"></span>
    </div>
    <a id="imdbLink" href="#" target="_blank" rel="noopener noreferrer">↗ Open on IMDb</a>
    <div class="dsub" id="dbysub" style="display:none">More by this director</div>
    <div class="chips" id="dbyauthor"></div>
    <div class="dsub">Explore this genre</div>
    <div class="chips" id="dgenrechips"></div>
  </div>

  <div id="toast"></div>
</div>

<script>const TITLES = __TITLES_JSON__;
const SEED_WATCHED = __SEED_WATCHED__;    /* IMDb: ids that are watched */
const SEED_RATINGS = __SEED_RATINGS__;    /* IMDb: {id: 1-10} */</script>
<script>
(function(){
"use strict";
var LS_KEY="avmu-watched-v1";
var GOLDEN=Math.PI*(3-Math.sqrt(5));
var MAXR=10;   // IMDb rating scale
// DARK-MODE "cosmic" palette (vivid stars on black); also used for the legend swatches
// Hues are spread so that the *biggest* genres are the most distinct; near-white is
// reserved for tiny genres, because light mode swaps very pale colours for grey.
var GENRE_COLORS={
 "Animation":"#21c7d6", "Action":"#8f6dff", "Horror":"#3d3fa8", "Romance":"#b06bff",
 "Sci-Fi":"#00ffff", "Crime":"#2e6f8e", "Comedy":"#7cc0ff", "Drama":"#2b93ff",
 "Biography":"#0a63cf", "Fantasy":"#7ef7ff", "Sport":"#4fe0a8", "Thriller":"#5b53c9",
 "War":"#12447f", "Mystery":"#7b5fd6", "Musical":"#cdb4ff", "Adventure":"#6f7dff",
 "Music":"#4fa9ff", "Family":"#d6ecff", "Documentary":"#12908c", "History":"#0b52ab",
 "Western":"#ffffff", "Film-Noir":"#5f6b8c", "Reality-TV":"#8aa0c0", "Short":"#9fb2cc"
};
function colorFor(g){ return GENRE_COLORS[g]||"#a8b6d6"; }

// LIGHT-MODE palette — its own map, not a tint of the dark one. Deep but saturated
// shades of blue, teal, dark green and black, so the neurons read strongly on white.
// Only the genres that should truly read as *black* are neutral (Horror, Western,
// Film-Noir); everything else keeps a blue or green cast, or large regions turn to mud.
var LIGHT_COLORS={
 "Animation":"#0b8579", "Action":"#1e40af", "Horror":"#0a0d12", "Romance":"#0e7490",
 "Sci-Fi":"#1668d6", "Crime":"#12263f", "Comedy":"#0f8a4a", "Drama":"#0b4f8a",
 "Biography":"#14532d", "Fantasy":"#0684a6", "Sport":"#3d8b1c", "Thriller":"#2e1f8f",
 "War":"#1b4d33", "Mystery":"#123a4d", "Musical":"#12856a", "Adventure":"#2b5cd9",
 "Music":"#076e8b", "Family":"#3f7fd0", "Documentary":"#2f5d3a", "History":"#0a3d62",
 "Western":"#1c1917", "Film-Noir":"#111827", "Reality-TV":"#1e3a4f", "Short":"#1f3d4d"
};
function lightColorFor(g){ return LIGHT_COLORS[g]||"#1e293b"; }
// the colour a title is actually drawn in, for the theme that is showing
function dotColor(b){ return theme==="light" ? b.lcolor : b.color; }
// genre-tinted text (chips, search rows) that has to sit on the panel background
function inkFor(b){ return theme==="light" ? b.lcolor : darken(b.color); }
// watch length (minutes) -> dot radius (world units); sqrt so area tracks length, clamped
function minsToRad(m){ m=m||100; return Math.max(1.15, Math.min(7.0, 0.6+0.19*Math.sqrt(m))); }
function fmtMins(m){ if(!m) return "—"; var h=Math.floor(m/60), mm=m%60; return h?(h+"h"+(mm?" "+mm+"m":"")):(mm+"m"); }

var watchedSet=loadWatched();
var RATE_KEY="avmu-ratings-v1";
var ratings=(function(){ try{ return JSON.parse(localStorage.getItem(RATE_KEY)||"{}")||{}; }catch(e){ return {}; } })();
var THEME_KEY="avmu-theme-v1";
var theme=(function(){ try{ return localStorage.getItem(THEME_KEY)||"light"; }catch(e){ return "light"; } })();
var STRETCHX=1.32;
var state={status:"all",type:"all",search:"",hidden:{},showConn:false,selected:null,hover:null,hoverGenre:null,minRating:0};
var cam={x:0,y:0,s:1,tx:0,ty:0,ts:1,fx:0,fy:0,fs:1,animating:false,animStart:0,animDur:0};

function loadWatched(){ try{var r=JSON.parse(localStorage.getItem(LS_KEY)||"[]");var s={};r.forEach(function(id){s[id]=1;});return s;}catch(e){return {};} }
function saveWatched(){ try{localStorage.setItem(LS_KEY,JSON.stringify(Object.keys(watchedSet).map(Number)));}catch(e){} }
function isWatched(id){ return !!watchedSet[id]; }
// ---- ratings (IMDb-style 1-10; a rating implies the title is watched) ----
function saveRatings(){ try{localStorage.setItem(RATE_KEY,JSON.stringify(ratings));}catch(e){} }
function getRating(id){ return ratings[id]||0; }
function mul32(a){ return function(){ a|=0;a=a+0x6D2B79F5|0;var t=Math.imul(a^a>>>15,1|a);t=t+Math.imul(t^t>>>7,61|t)^t;return ((t^t>>>14)>>>0)/4294967296; }; }
function hashStr(s){ var h=2166136261;for(var i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}return h>>>0; }
function norm(s){ return (s||"").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"").replace(/[^a-z0-9 ]/g," ").replace(/\s+/g," ").trim(); }
function gauss(rng){ var u=Math.max(1e-6,rng()),v=rng(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }
function firstDir(d){ return (d||"").split(",")[0].trim(); }

// ---------------- layout ----------------
var genres=[], genreMeta={}, edges=[], byId={};
TITLES.forEach(function(b){ byId[b.id]=b; });
function buildLayout(){
  var counts={}; TITLES.forEach(function(b){ counts[b.g]=(counts[b.g]||0)+1; });
  genres=Object.keys(counts).sort(function(a,b){ return counts[b]-counts[a]; });
  var placed=[], SP=18, OVER=0.70;   // OVER<1 lets clusters overlap -> connected landmass (lower = tighter)
  genres.forEach(function(g){
    var n=counts[g], r=31*Math.sqrt(n)+10, k=0, pt;
    while(true){
      var rad=SP*Math.sqrt(k+1), ang=k*GOLDEN; pt={x:rad*Math.cos(ang),y:rad*Math.sin(ang)};
      var ok=true;
      for(var i=0;i<placed.length;i++){ var p=placed[i],dx=pt.x-p.x,dy=pt.y-p.y; if(Math.sqrt(dx*dx+dy*dy)<(r+p.r)*OVER){ok=false;break;} }
      if(ok) break; k++; if(k>300000) break;
    }
    placed.push({x:pt.x,y:pt.y,r:r});
    genreMeta[g]={cx:pt.x,cy:pt.y,r:r,n:n,color:colorFor(g),lcolor:lightColorFor(g)};
  });
  var byGenre={}; TITLES.forEach(function(b){ (byGenre[b.g]=byGenre[b.g]||[]).push(b); });
  genres.forEach(function(g){
    var arr=byGenre[g], m=genreMeta[g], R=m.r, rng=mul32(hashStr(g));
    arr.sort(function(a,b){ var aa=(firstDir(a.d)||"~").toLowerCase(),ba=(firstDir(b.d)||"~").toLowerCase(); if(aa!==ba)return aa<ba?-1:1; return a.t.toLowerCase()<b.t.toLowerCase()?-1:1; });
    // group consecutive same-director (non-empty) into clumps; uncredited titles are singletons
    var i=0;
    while(i<arr.length){
      var a=norm(firstDir(arr[i].d)), grp=[arr[i]], j=i+1;
      if(a.length>=4){ while(j<arr.length && norm(firstDir(arr[j].d))===a){ grp.push(arr[j]); j++; } }
      // seed position within disc, denser toward centre
      var u=rng(), rr=R*Math.pow(u,0.55)*0.92, sang=rng()*Math.PI*2;
      var sx=m.cx+rr*Math.cos(sang), sy=m.cy+rr*Math.sin(sang);
      var spread=Math.min(R*0.17, R*0.04+Math.sqrt(grp.length)*R*0.022);
      for(var q=0;q<grp.length;q++){
        var b=grp[q];
        var x=sx+gauss(rng)*spread, y=sy+gauss(rng)*spread;
        var dx=x-m.cx, dy=y-m.cy, d=Math.sqrt(dx*dx+dy*dy), lim=R*1.05;
        if(d>lim){ x=m.cx+dx/d*lim; y=m.cy+dy/d*lim; }
        b.x=x; b.y=y; b.color=m.color; b.lcolor=m.lcolor;
        b.rad=minsToRad(b.m);   // dot size reflects how long the movie / series is
      }
      i=j;
    }
  });
  // horizontal stretch so the field fills landscape screens (like the reference map)
  TITLES.forEach(function(b){ b.x*=STRETCHX; });
  genres.forEach(function(g){ genreMeta[g].cx*=STRETCHX; });
  // constellation edges based on genres (neural network look)
  var byGenre2={};
  TITLES.forEach(function(b){ (byGenre2[b.g]=byGenre2[b.g]||[]).push(b); });
  Object.keys(byGenre2).forEach(function(g){
    var arr=byGenre2[g];
    if(arr.length<2) return;
    arr.sort(function(a,b){ return a.x - b.x; });
    for(var i=0; i<arr.length-1; i++){
      edges.push([arr[i], arr[i+1]]);
      if(i+2 < arr.length && Math.random() < 0.6) edges.push([arr[i], arr[i+2]]);
      if(i+3 < arr.length && Math.random() < 0.3) edges.push([arr[i], arr[i+3]]);
    }
  });
}

// ---------------- canvas ----------------
var cv=document.getElementById("cv"), ctx=cv.getContext("2d");
var DPR=Math.min(window.devicePixelRatio||1,2), W=0,H=0, TOP=56;
function resize(){
  W=window.innerWidth; H=window.innerHeight-TOP;
  cv.width=W*DPR; cv.height=H*DPR; cv.style.width=W+"px"; cv.style.height=H+"px";
  ctx.setTransform(DPR,0,0,DPR,0,0);
  if(!userMoved) fitView(0);
  requestDraw();
}
window.addEventListener("resize",resize);

function w2s(x,y){ return [ (x-cam.x)*cam.s + W/2, (y-cam.y)*cam.s + H/2 ]; }
function s2w(px,py){ return [ (px-W/2)/cam.s + cam.x, (py-H/2)/cam.s + cam.y ]; }
function hexA(hex,a){ var h=hex.replace("#","");return "rgba("+parseInt(h.substr(0,2),16)+","+parseInt(h.substr(2,2),16)+","+parseInt(h.substr(4,2),16)+","+a+")"; }

// DARK-mode additive glow sprite per colour (stars shine on black)
var glowCache={};
function glowSprite(color){
  if(glowCache[color]) return glowCache[color];
  var s=128, c=document.createElement("canvas"); c.width=s; c.height=s; var g=c.getContext("2d");
  var grd=g.createRadialGradient(s/2,s/2,0,s/2,s/2,s/2);
  grd.addColorStop(0,color);
  grd.addColorStop(0.15,color);
  grd.addColorStop(0.4,hexA(color,0.6));
  grd.addColorStop(1,hexA(color,0));
  g.fillStyle=grd; g.fillRect(0,0,s,s); glowCache[color]=c; return c;
}
// LIGHT-mode glow: a much tighter falloff. The wide dark-mode tail, drawn in a deep
// colour on white, spreads into a pale film — this keeps the saturation near the node.
var glowCacheTight={};
function glowSpriteTight(color){
  if(glowCacheTight[color]) return glowCacheTight[color];
  var s=128, c=document.createElement("canvas"); c.width=s; c.height=s; var g=c.getContext("2d");
  var grd=g.createRadialGradient(s/2,s/2,0,s/2,s/2,s/2);
  grd.addColorStop(0,color);
  grd.addColorStop(0.22,hexA(color,0.85));
  grd.addColorStop(0.48,hexA(color,0.30));
  grd.addColorStop(0.75,hexA(color,0.07));
  grd.addColorStop(1,hexA(color,0));
  g.fillStyle=grd; g.fillRect(0,0,s,s); glowCacheTight[color]=c; return c;
}
// faint static background starfield for dark mode (screen-space, deterministic)
var BGSTARS=(function(){ var a=[], rng=mul32(20240808); for(var i=0;i<220;i++){ a.push([rng(),rng(),0.4+rng()*1.2,0.15+rng()*0.5]); } return a; })();
function drawBgStars(){ ctx.fillStyle="#cfe0ff"; for(var i=0;i<BGSTARS.length;i++){ var s=BGSTARS[i]; ctx.globalAlpha=s[3]*0.5; ctx.beginPath(); ctx.arc(s[0]*W,s[1]*H,s[2],0,7); ctx.fill(); } ctx.globalAlpha=1; }

function passFilter(b){
  if(state.hidden[b.g]) return false;
  if(state.type!=="all" && b.ty!==state.type) return false;
  if(state.status==="rated" && !getRating(b.id)) return false;
  if(state.status==="unwatched" && isWatched(b.id)) return false;
  if(state.minRating>0 && getRating(b.id)<state.minRating) return false;   // rating filter
  if(state.search && (b.t+" "+(b.d||"")).toLowerCase().indexOf(state.search)<0) return false;
  return true;
}

var drawPending=false;
function requestDraw(){ if(!drawPending){ drawPending=true; requestAnimationFrame(draw); } }
function draw(ts){
  drawPending=false;
  if(!isFinite(cam.s)||cam.s<=0) cam.s=0.1; if(!isFinite(cam.x)) cam.x=0; if(!isFinite(cam.y)) cam.y=0;
  if(W<=0||H<=0) return;
  if(cam.animating){
    var t=Math.min(1,(ts-cam.animStart)/cam.animDur);
    var e=t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2;
    cam.x=cam.fx+(cam.tx-cam.fx)*e; cam.y=cam.fy+(cam.ty-cam.fy)*e; cam.s=cam.fs+(cam.ts-cam.fs)*e;
    if(t>=1) cam.animating=false; requestDraw();
  }
  var dark = theme==="dark";
  ctx.clearRect(0,0,W,H);
  if(dark){
    var bg=ctx.createRadialGradient(W*0.5,H*0.42,0,W*0.5,H*0.42,Math.max(W,H)*0.82);
    bg.addColorStop(0,"#0b1124"); bg.addColorStop(0.55,"#070912"); bg.addColorStop(1,"#04050b");
    ctx.fillStyle=bg; ctx.fillRect(0,0,W,H);
    drawBgStars();
  } else {
    ctx.fillStyle="#ffffff"; ctx.fillRect(0,0,W,H);
  }

  // galaxy background clouds per genre
  ctx.globalCompositeOperation=dark?"lighter":"source-over";
  genres.forEach(function(g){
    if(state.hidden[g]) return;
    var m=genreMeta[g], sp=w2s(m.cx,m.cy), cr=m.r*cam.s*1.8;
    if(sp[0]<-cr||sp[0]>W+cr||sp[1]<-cr||sp[1]>H+cr) return;
    var grd=ctx.createRadialGradient(sp[0],sp[1],0,sp[0],sp[1],cr);
    var col=dark?m.color:m.lcolor;
    var isHover = (state.hoverGenre === g);
    if(dark){
      grd.addColorStop(0,hexA(col,isHover?0.40:0.20));
      grd.addColorStop(0.4,hexA(col,isHover?0.12:0.06));
      grd.addColorStop(1,hexA(col,0));
    } else {
      // the light palette is deep, so these run a little under the dark-mode alphas —
      // high enough to saturate, low enough that the near-blacks don't blot
      grd.addColorStop(0,hexA(col,isHover?0.30:0.185));
      grd.addColorStop(0.4,hexA(col,isHover?0.17:0.115));
      grd.addColorStop(1,hexA(col,0));
    }
    ctx.fillStyle=grd; ctx.beginPath(); ctx.arc(sp[0],sp[1],cr,0,7); ctx.fill();
  });
  ctx.globalCompositeOperation="source-over";

  // luminous pass: additive star glow (dark) OR neuron glow (light)
  if(dark){
    ctx.globalCompositeOperation="lighter";
    for(var k=0;k<TITLES.length;k++){
      var b=TITLES[k]; if(!passFilter(b)) continue;
      var sp2=w2s(b.x,b.y); var rr=Math.max(1.2,b.rad*cam.s); var gz=Math.max(30, rr*22);
      if(sp2[0]<-gz||sp2[0]>W+gz||sp2[1]<-gz||sp2[1]>H+gz) continue;
      ctx.globalAlpha=isWatched(b.id)&&state.status!=="rated"?0.04:0.12;
      ctx.drawImage(glowSprite(b.color), sp2[0]-gz/2, sp2[1]-gz/2, gz, gz);
    }
    ctx.globalAlpha=1; ctx.globalCompositeOperation="source-over";
  } else {
    for(var k=0;k<TITLES.length;k++){
      var b=TITLES[k]; if(!passFilter(b)) continue;
      var rr=Math.max(1.2,b.rad*cam.s);
      var sp2=w2s(b.x,b.y); var bz=Math.max(17, rr*12);
      if(sp2[0]<-bz||sp2[0]>W+bz||sp2[1]<-bz||sp2[1]>H+bz) continue;
      ctx.globalAlpha=isWatched(b.id)&&state.status!=="rated"?0.16:0.62;
      ctx.drawImage(glowSpriteTight(dotColor(b)), sp2[0]-bz/2, sp2[1]-bz/2, bz, bz);
    }
    ctx.globalAlpha=1;
  }

  // optional faint connections
  if((!dark || state.showConn) && cam.s>0.05){
    ctx.lineWidth=dark ? Math.min(2.5,0.8*cam.s+0.4) : Math.min(1.8,0.6*cam.s+0.2);
    for(var i=0;i<edges.length;i++){
      var a=edges[i][0], b=edges[i][1], pa=passFilter(a), pb=passFilter(b);
      if(!pa&&!pb) continue;
      var s1=w2s(a.x,a.y), s2=w2s(b.x,b.y);
      if((s1[0]<0&&s2[0]<0)||(s1[0]>W&&s2[0]>W)||(s1[1]<0&&s2[1]<0)||(s1[1]>H&&s2[1]>H)) continue;
      var sel=state.selected&&(a.id===state.selected||b.id===state.selected);
      // light-mode filaments are drawn in a deep colour now, so they need to be fainter
      var alpha = dark ? ((pa&&pb)?0.25:0.05) : ((pa&&pb)?0.17:0.05);
      ctx.strokeStyle=sel?hexA(dotColor(a),.8):hexA(dotColor(a),alpha);
      ctx.beginPath(); ctx.moveTo(s1[0],s1[1]);
      if(!dark) {
         var dx = s2[0] - s1[0], dy = s2[1] - s1[1];
         var dist = Math.sqrt(dx*dx + dy*dy);
         var offset = ((a.id + b.id) % 10 - 4.5) * 0.2 * dist;
         var cx = (s1[0]+s2[0])/2 - (dy/dist) * offset;
         var cy = (s1[1]+s2[1])/2 + (dx/dist) * offset;
         ctx.quadraticCurveTo(cx, cy, s2[0], s2[1]);
      } else {
         ctx.lineTo(s2[0],s2[1]);
      }
      ctx.stroke();
    }
  }

  // dots — size = watch length; colour = genre
  var showLabels=cam.s>1.7, labelCand=[];
  for(var k=0;k<TITLES.length;k++){
    var b=TITLES[k], sp=w2s(b.x,b.y);
    if(sp[0]<-8||sp[0]>W+8||sp[1]<-8||sp[1]>H+8) continue;
    var active=passFilter(b), seen=isWatched(b.id), col=dotColor(b);
    var rad=Math.max(1.2, b.rad*cam.s);
    if(!active){ ctx.fillStyle=dark?"rgba(120,132,164,.26)":"rgba(190,194,203,.4)"; ctx.beginPath(); ctx.arc(sp[0],sp[1],Math.max(1,rad*0.7),0,7); ctx.fill(); continue; }
    if(seen && state.status!=="rated"){ ctx.fillStyle=hexA(col,dark?.36:.28); ctx.beginPath(); ctx.arc(sp[0],sp[1],rad*0.9,0,7); ctx.fill(); }
    else {
      ctx.fillStyle=col; ctx.beginPath(); ctx.arc(sp[0],sp[1],rad,0,7); ctx.fill();
      if(dark){
          ctx.fillStyle="rgba(255,250,220,1)"; ctx.beginPath(); ctx.arc(sp[0],sp[1],Math.max(1.0,rad*0.5),0,7); ctx.fill();
          var orbitR = Math.max(8, rad*4.2);
          ctx.strokeStyle="rgba(255,255,255,0.02)";
          ctx.lineWidth=1.0;
          ctx.beginPath(); ctx.arc(sp[0],sp[1],orbitR,0,7); ctx.stroke();

          if(cam.s>1.8){
              // no director credit (normal for series) -> drop that segment entirely
              var od = firstDir(b.d);
              var txt = (od ? od + " • " : "") + b.g + " • " + fmtMins(b.m);
              ctx.font="9px "+FS; ctx.fillStyle="rgba(255,255,255,0.75)";
              ctx.textAlign="center"; ctx.textBaseline="middle";

              var tw = ctx.measureText(txt).width;
              if(tw < orbitR * 2 * Math.PI * 0.75) {
                  var totalAngle = tw / orbitR;
                  ctx.save();
                  ctx.translate(sp[0], sp[1]);
                  var timeRot = (ts / 2000) % (Math.PI * 2);
                  ctx.rotate(-Math.PI/2 - totalAngle/2 + timeRot);
                  for (var c = 0; c < txt.length; c++) {
                      var char = txt[c];
                      var cw = ctx.measureText(char).width;
                      ctx.rotate((cw/2) / orbitR);
                      ctx.fillText(char, 0, -orbitR);
                      ctx.rotate((cw/2) / orbitR);
                  }
                  ctx.restore();
                  requestDraw();
              }
          }
      } else {
          // light mode core: the genre colour is already deep, so one step of shading is enough
          ctx.fillStyle=darken(col,0.55); ctx.beginPath(); ctx.arc(sp[0],sp[1],Math.max(1.2,rad*0.53),0,7); ctx.fill();
      }
    }
    if(showLabels && labelCand.length<60) labelCand.push([b,sp,seen]);
  }

  // selected + hover accents
  drawAccent(state.selected,true,ts);
  if(state.hover && state.hover!==state.selected) drawAccent(state.hover,false,ts);

  // zoomed-in title labels
  if(showLabels){
    ctx.font="600 12px "+FS; ctx.textAlign="left"; ctx.textBaseline="middle";
    var lblBg=dark?"rgba(8,10,20,.6)":"rgba(255,255,255,.85)";
    var lblInk=dark?"#dfe4f2":"#3a4150", lblSeen=dark?"#7f8aa6":"#9aa1ad";
    for(var i=0;i<labelCand.length;i++){
      var b=labelCand[i][0], sp=labelCand[i][1];
      var tx=sp[0]+Math.max(3,b.rad*cam.s)+4, ty=sp[1], txt=trunc(b.t,26);
      ctx.fillStyle=lblBg;
      var w=ctx.measureText(txt).width;
      ctx.fillRect(tx-2,ty-8,w+4,16);
      ctx.fillStyle=labelCand[i][2]?lblSeen:lblInk; ctx.fillText(txt,tx,ty);
    }
  }

  // genre region labels — hidden at overview; fade in as you zoom, or on hover
  var zoomA = cam.s<=0.42?0 : cam.s>=0.78?1 : (cam.s-0.42)/0.36;
  ctx.textAlign="center"; ctx.textBaseline="middle";
  var drawnBoxes=[];
  // ordered: hovered genre first (never skipped), then large clusters
  var order=genres.slice();
  if(state.hoverGenre){ order=order.filter(function(x){return x!==state.hoverGenre;}); order.unshift(state.hoverGenre); }
  for(var oi=0;oi<order.length;oi++){
    var g=order[oi]; if(state.hidden[g]) continue;
    var isHover=(g===state.hoverGenre);
    var a=isHover?1:zoomA;
    if(a<=0.02) continue;
    var m=genreMeta[g], sp=w2s(m.cx,m.cy);
    var fs=Math.max(11,Math.min(27,m.r*cam.s*0.085));
    if(isHover) fs=Math.max(fs,13);
    if(sp[0]<-220||sp[0]>W+220||sp[1]<-120||sp[1]>H+120) continue;
    ctx.font="700 "+fs+"px "+FS;
    var tw=ctx.measureText(g).width, th=fs;
    var bx=sp[0]-tw/2-3, by=sp[1]-th/2-2, bw=tw+6, bh=th+4, clash=false;
    for(var d=0;d<drawnBoxes.length;d++){ var o=drawnBoxes[d]; if(bx<o[0]+o[2]&&bx+bw>o[0]&&by<o[1]+o[3]&&by+bh>o[1]){ clash=true; break; } }
    if(clash && !isHover) continue;
    drawnBoxes.push([bx,by,bw,bh]);
    // backdrop first, so the label keeps its contrast over a bright nebula
    ctx.fillStyle=(dark?"rgba(3,5,12,":"rgba(255,255,255,")+((dark?0.9:0.72)*a)+")";
    ctx.fillText(g,sp[0]+(dark?1:0.6),sp[1]+(dark?1:0.6));
    // dark mode: every genre label is pushed to near-full brightness so none stay dull.
    // light mode: the light palette is already deep enough to read on white as-is.
    ctx.fillStyle=hexA(dark?brightenLabel(m.color):m.lcolor,(isHover?1:0.98)*a);
    ctx.fillText(g,sp[0],sp[1]);
  }
}

// Dark-mode genre headings. Two steps: saturate the hue (scale until its brightest
// channel is near white), then mix toward white by exactly enough to hit LABEL_LUM.
// Because the target is a *luminance floor*, every heading ends up equally readable on
// black — the deep navies (War, Horror, Crime, Biography) no longer come out dull, and
// each genre still keeps its own hue. Raise LABEL_LUM for brighter, lower for moodier.
var LABEL_LUM=208;
function brightenLabel(hex){
  if(!hex) return "#ffffff";
  var h=hex.replace("#",""); var r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16);
  var k=235/Math.max(r,g,b,1);
  r=Math.min(255,r*k); g=Math.min(255,g*k); b=Math.min(255,b*k);
  var L=0.2126*r+0.7152*g+0.0722*b;
  if(L<LABEL_LUM){
    var t=Math.min(1,(LABEL_LUM-L)/(255-L));       // white-mix that lands exactly on the target
    r=r+(255-r)*t; g=g+(255-g)*t; b=b+(255-b)*t;
  }
  return "#"+[r,g,b].map(function(v){return ("0"+Math.round(v).toString(16)).slice(-2);}).join("");
}
function darken(hex,f){ f=f||0.62; if(!hex) return "#000000"; var h=hex.replace("#","");var r=parseInt(h.substr(0,2),16),g=parseInt(h.substr(2,2),16),b=parseInt(h.substr(4,2),16); r=Math.round(r*f);g=Math.round(g*f);b=Math.round(b*f); return "#"+[r,g,b].map(function(v){return ("0"+v.toString(16)).slice(-2);}).join(""); }
function drawAccent(id,isSel,ts){
  if(id==null) return; var b=byId[id]; if(!b) return;
  var sp=w2s(b.x,b.y), rad=Math.max(3.5,b.rad*cam.s);
  ctx.fillStyle=dotColor(b); ctx.beginPath(); ctx.arc(sp[0],sp[1],rad,0,7); ctx.fill();
  ctx.strokeStyle=isSel?(theme==="dark"?"#ffffff":"#1e2330"):(theme==="dark"?"#aab4ff":"#5b57e0"); ctx.lineWidth=isSel?2.4:1.8;
  var pulse=isSel?(rad+5+2*Math.sin((ts||0)/300)):(rad+4);
  ctx.beginPath(); ctx.arc(sp[0],sp[1],pulse,0,7); ctx.stroke();
  if(isSel){
    // dark pill label
    ctx.font="700 12px "+FS; var txt=trunc(b.t,30), w=ctx.measureText(txt).width;
    var px=sp[0]-w/2-9, py=sp[1]-pulse-26, pw=w+18, ph=20;
    roundRect(px,py,pw,ph,7); ctx.fillStyle="#1e2330"; ctx.fill();
    ctx.fillStyle="#fff"; ctx.textAlign="left"; ctx.textBaseline="middle"; ctx.fillText(txt,px+9,py+ph/2);
    // pointer
    ctx.beginPath(); ctx.moveTo(sp[0]-5,py+ph); ctx.lineTo(sp[0]+5,py+ph); ctx.lineTo(sp[0],py+ph+6); ctx.closePath(); ctx.fillStyle="#1e2330"; ctx.fill();
    requestDraw();
  }
}
function roundRect(x,y,w,h,r){ ctx.beginPath(); ctx.moveTo(x+r,y); ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r); ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath(); }
var FS='-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif';
function trunc(s,n){ return s.length>n?s.slice(0,n-1)+"…":s; }

// ---------------- picking ----------------
function pickAt(px,py){
  var best=null,bestD=15*15;
  for(var k=0;k<TITLES.length;k++){ var b=TITLES[k]; if(!passFilter(b)) continue; var sp=w2s(b.x,b.y); var dx=sp[0]-px,dy=sp[1]-py,d=dx*dx+dy*dy; var rr=Math.max(6,b.rad*cam.s+4),thr=rr*rr; if(d<thr&&d<bestD){bestD=d;best=b;} }
  return best;
}

// ---------------- camera ----------------
var userMoved=false;
function flyTo(x,y,s,dur){ cam.fx=cam.x;cam.fy=cam.y;cam.fs=cam.s;cam.tx=x;cam.ty=y;cam.ts=s;cam.animStart=performance.now();cam.animDur=dur||700;cam.animating=true;requestDraw(); }
function fitView(dur){
  var minx=1e9,miny=1e9,maxx=-1e9,maxy=-1e9;
  TITLES.forEach(function(b){ if(b.x<minx)minx=b.x; if(b.y<miny)miny=b.y; if(b.x>maxx)maxx=b.x; if(b.y>maxy)maxy=b.y; });
  var gx=(minx+maxx)/2, gy=(miny+maxy)/2; if(!(W>0&&H>0)) return;
  var pad=60, s=Math.min((W-pad*2)/((maxx-minx)+80),(H-pad*2)/((maxy-miny)+80))*0.98;
  if(!isFinite(s)||s<=0) s=0.15;
  if(dur){ flyTo(gx,gy,s,dur); } else { cam.x=gx; cam.y=gy; cam.s=s; requestDraw(); }
}
function focusTitle(b){ state.selected=b.id; openDetail(b); userMoved=true; flyTo(b.x,b.y,Math.max(2.6,cam.s),720); }

// ---------------- input ----------------
var down=false,moved=false,lastX=0,lastY=0,downX=0,downY=0,pointers={},pinchDist=0;
function localXY(e){ return [e.clientX, e.clientY-TOP]; }
cv.addEventListener("pointerdown",function(e){ down=true;moved=false;lastX=e.clientX;lastY=e.clientY;downX=e.clientX;downY=e.clientY;cam.animating=false;cv.classList.add("grabbing");cv.setPointerCapture(e.pointerId);pointers[e.pointerId]={x:e.clientX,y:e.clientY}; });
cv.addEventListener("pointermove",function(e){
  if(pointers[e.pointerId]) pointers[e.pointerId]={x:e.clientX,y:e.clientY};
  if(Object.keys(pointers).length>=2){ pinchMove(); return; }
  var lc=localXY(e);
  if(down){ var dx=e.clientX-lastX,dy=e.clientY-lastY; if(Math.abs(e.clientX-downX)+Math.abs(e.clientY-downY)>4){moved=true;userMoved=true;} cam.x-=dx/cam.s;cam.y-=dy/cam.s;lastX=e.clientX;lastY=e.clientY;requestDraw();hideTip(); }
  else {
    var b=pickAt(lc[0],lc[1]); if((b?b.id:null)!==state.hover){ state.hover=b?b.id:null; requestDraw(); } if(b) showTip(b,e.clientX,e.clientY); else hideTip();
    // reveal the region label under the cursor: the hovered dot's genre, else the nearest cluster
    var hg = b ? b.g : null;
    if(!hg){ var wp=s2w(lc[0],lc[1]), bd=1e18; for(var gi=0;gi<genres.length;gi++){ var g=genres[gi]; if(state.hidden[g]) continue; var m=genreMeta[g]; var dx=(wp[0]-m.cx)/STRETCHX, dy=wp[1]-m.cy, d=dx*dx+dy*dy, rr=m.r*1.05; if(d<rr*rr && d<bd){ bd=d; hg=g; } } }
    if(hg!==state.hoverGenre){ state.hoverGenre=hg; requestDraw(); }
  }
});
cv.addEventListener("pointerleave",function(){ if(state.hoverGenre){ state.hoverGenre=null; requestDraw(); } hideTip(); });
function endPointer(e){ down=false;cv.classList.remove("grabbing");delete pointers[e.pointerId];pinchDist=0; if(!moved){ var lc=localXY(e); var b=pickAt(lc[0],lc[1]); if(b){state.selected=b.id;openDetail(b);requestDraw();} else closeDetail(); } }
cv.addEventListener("pointerup",endPointer);
cv.addEventListener("pointercancel",function(e){ down=false;delete pointers[e.pointerId];pinchDist=0;cv.classList.remove("grabbing"); });
function pinchMove(){ var ks=Object.keys(pointers); if(ks.length<2) return; var a=pointers[ks[0]],b=pointers[ks[1]]; var dx=a.x-b.x,dy=a.y-b.y,dist=Math.sqrt(dx*dx+dy*dy); var cx=(a.x+b.x)/2,cy=(a.y+b.y)/2-TOP; if(pinchDist) zoomAt(cx,cy,dist/pinchDist); pinchDist=dist; hideTip(); }
cv.addEventListener("wheel",function(e){ e.preventDefault(); zoomAt(e.clientX,e.clientY-TOP,Math.pow(1.0016,-e.deltaY)); hideTip(); },{passive:false});
function zoomAt(px,py,factor){ userMoved=true; var wpt=s2w(px,py); cam.s=Math.max(0.03,Math.min(16,cam.s*factor)); var np=w2s(wpt[0],wpt[1]); cam.x+=(np[0]-px)/cam.s; cam.y+=(np[1]-py)/cam.s; requestDraw(); }

// ---------------- tooltip ----------------
var tip=document.getElementById("tip");
function showTip(b,x,y){
  var rt=getRating(b.id);
  tip.innerHTML='<div class="tt">'+esc(b.t)+(b.yr?' <span style="opacity:.6">('+b.yr+')</span>':'')+'</div>'+
    (b.d?'<div class="ta">'+esc(b.d)+'</div>':'')+
    '<div class="tg" style="color:'+b.color+'"><span class="dot" style="width:8px;height:8px;background:'+b.color+'"></span>'+esc(b.g)+'</div>'+
    (rt?'<div class="trate">★ '+rt+'/10</div>':'')+
    '<div class="ts">'+(isWatched(b.id)?"✓ Watched":"○ Unwatched")+' · '+esc(b.tt)+' · '+fmtMins(b.m)+'</div>';
  tip.style.left=x+"px"; tip.style.top=(y)+"px"; tip.style.display="block";
}
function hideTip(){ tip.style.display="none"; }
function esc(s){ return (s||"").replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];}); }

// ---------------- detail ----------------
var detail=document.getElementById("detail");
function openDetail(b){
  document.getElementById("dtitle").textContent=b.t;
  document.getElementById("dauth").textContent=b.d||"Director uncredited";
  var orig=document.getElementById("dorig");
  if(b.ot){ orig.textContent="Original title: "+b.ot; orig.style.display="block"; } else orig.style.display="none";
  var tag=document.getElementById("dtag"); tag.style.background=hexA(dotColor(b),.13); tag.style.color=inkFor(b);
  tag.innerHTML='<span class="dot" style="width:8px;height:8px;background:'+dotColor(b)+'"></span>'+esc(b.g);
  document.getElementById("dgenre").textContent=b.g;
  document.getElementById("dtype").textContent=b.tt;
  document.getElementById("dyear").textContent=b.yr||"—";
  document.getElementById("druntime").textContent = b.ep>1
      ? (fmtMins(b.rt)+"/ep · ≈"+fmtMins(b.m)+" total")
      : (fmtMins(b.rt)+(b.e?" (est.)":""));
  document.getElementById("dimdb").textContent = b.ir? ("★ "+b.ir.toFixed(1)+"/10") : "—";
  document.getElementById("imdbLink").href = "https://www.imdb.com/title/"+b.c+"/";
  updStatus(b); renderDetailStars(b);
  var sub=document.getElementById("dbysub"), byD=document.getElementById("dbyauthor"); byD.innerHTML=""; var nd=norm(firstDir(b.d));
  if(nd.length>=4){ var same=TITLES.filter(function(x){return x.id!==b.id&&norm(firstDir(x.d))===nd;}).slice(0,6); if(same.length){ sub.style.display="block"; same.forEach(function(x){ byD.appendChild(chip(x.t,function(){focusTitle(x);})); }); } else sub.style.display="none"; } else sub.style.display="none";
  var gc=document.getElementById("dgenrechips"); gc.innerHTML=""; gc.appendChild(chip("◎ Show only "+b.g,function(){soloGenre(b.g);}));
  shuffle(TITLES.filter(function(x){return x.id!==b.id&&x.g===b.g&&!isWatched(x.id);})).slice(0,5).forEach(function(x){ gc.appendChild(chip(x.t,function(){focusTitle(x);})); });
  detail.classList.add("on");
}
function updStatus(b){
  var st=document.getElementById("dstatus"), seen=isWatched(b.id);
  st.textContent=seen?"✓ Watched":"○ Unwatched"; st.style.color=seen?"var(--good)":"var(--muted)";
}
document.getElementById("dclose").onclick=closeDetail;
function closeDetail(){ detail.classList.remove("on"); state.selected=null; requestDraw(); }
function chip(text,fn){ var c=document.createElement("div"); c.className="chip"; c.textContent=text; c.title=text; c.onclick=fn; return c; }
// read-only 1-10 star display in the detail panel (ratings come from the IMDb export)
function renderDetailStars(b){
  var host=document.getElementById("dstars"); host.innerHTML=""; var cur=getRating(b.id);
  for(var i=1;i<=MAXR;i++){
    var sp=document.createElement("span"); sp.className="star"+(i<=cur?" on":""); sp.textContent="★"; sp.title=i+"/10";
    host.appendChild(sp);
  }
  document.getElementById("dratev").textContent=cur?(cur+"/10"):"Not rated";
}
function paintStars(host,n){ var ch=host.children; for(var i=0;i<ch.length;i++) ch[i].classList.toggle("on", i<n); }
function shuffle(a){ a=a.slice(); for(var i=a.length-1;i>0;i--){var j=Math.floor(Math.random()*(i+1)),t=a[i];a[i]=a[j];a[j]=t;} return a; }

// ---------------- drawer ----------------
var drawer=document.getElementById("drawer"), scrim=document.getElementById("scrim");
function openDrawer(){ drawer.classList.add("on"); scrim.classList.add("on"); }
function closeDrawer(){ drawer.classList.remove("on"); scrim.classList.remove("on"); document.getElementById("results").classList.remove("on"); }
document.getElementById("burger").onclick=function(){ drawer.classList.contains("on")?closeDrawer():openDrawer(); };
document.getElementById("drawerClose").onclick=closeDrawer;
scrim.onclick=closeDrawer;
document.getElementById("searchIcon").onclick=function(){ openDrawer(); setTimeout(function(){document.getElementById("search").focus();},260); };
// ---------------- theme (light / dark) ----------------
function applyTheme(){ document.body.classList.toggle("theme-dark", theme==="dark"); try{localStorage.setItem(THEME_KEY,theme);}catch(e){} if(genres.length) buildGenreList(); requestDraw(); }
document.getElementById("themeBtn").onclick=function(){ theme=(theme==="dark")?"light":"dark"; applyTheme(); toast(theme==="dark"?"Dark mode — universe":"Light mode — neurons"); };

// ---------------- random suggestion ----------------
// base filters (genre / type / search) apply, but the status + rating filters don't:
// a suggestion is always something you have NOT watched yet.
function passFilterBase(b){ if(state.hidden[b.g]) return false; if(state.type!=="all"&&b.ty!==state.type) return false; if(state.search&&(b.t+" "+(b.d||"")).toLowerCase().indexOf(state.search)<0) return false; return true; }
function suggest(kind,label){
  var pool=TITLES.filter(function(b){ return passFilterBase(b)&&!isWatched(b.id)&&(kind==="any"||b.ty===kind); });
  if(!pool.length){ toast("Nothing unwatched matches your filters."); return; }
  var p=pool[Math.floor(Math.random()*pool.length)];
  closeDrawer(); focusTitle(p);
  toast(label+" — "+trunc(p.t,38)+(p.yr?" ("+p.yr+")":"")+" · "+fmtMins(p.m));
}
document.getElementById("tonight").onclick   =function(){ suggest("any",   "✦ Tonight's pick"); };
document.getElementById("randMovie").onclick =function(){ suggest("Movie", "🎬 Random movie"); };
document.getElementById("randSeries").onclick=function(){ suggest("Series","📺 Random series"); };

// ---------------- search ----------------
var search=document.getElementById("search"), results=document.getElementById("results"), resSel=-1, resList=[];
search.addEventListener("input",function(){ state.search=search.value.trim().toLowerCase(); requestDraw(); renderResults(); });
search.addEventListener("keydown",function(e){
  if(e.key==="ArrowDown"){ resSel=Math.min(resList.length-1,resSel+1); markRes(); e.preventDefault(); }
  else if(e.key==="ArrowUp"){ resSel=Math.max(0,resSel-1); markRes(); e.preventDefault(); }
  else if(e.key==="Enter"){ var t=resList[resSel]||resList[0]; if(t){ focusTitle(t); results.classList.remove("on"); closeDrawer(); } }
  else if(e.key==="Escape"){ search.value="";state.search="";results.classList.remove("on");requestDraw(); }
});
function renderResults(){
  var q=state.search; if(!q){ results.classList.remove("on"); resList=[]; return; }
  var arr=TITLES.filter(function(b){ return (b.t+" "+(b.d||"")).toLowerCase().indexOf(q)>=0; });
  arr.sort(function(a,b){ var at=a.t.toLowerCase().indexOf(q),bt=b.t.toLowerCase().indexOf(q); return (at<0?99:at)-(bt<0?99:bt); });
  resList=arr.slice(0,8); resSel=-1;
  if(!resList.length){ results.innerHTML='<div class="res"><div class="rt">No matches</div></div>'; results.classList.add("on"); return; }
  results.innerHTML="";
  resList.forEach(function(b,i){ var d=document.createElement("div"); d.className="res"; var rt=getRating(b.id);
    d.innerHTML='<div class="rt">'+esc(b.t)+(b.yr?' <span style="opacity:.55">('+b.yr+')</span>':'')+'</div><div class="ra">'+esc(b.d||"—")+' · <span class="rg" style="color:'+inkFor(b)+'">'+esc(b.g)+'</span> · '+(isWatched(b.id)?"✓":"○")+(rt?' <span class="rr">★'+rt+'</span>':'')+'</div>';
    d.onmouseenter=function(){resSel=i;markRes();}; d.onclick=function(){ focusTitle(b); results.classList.remove("on"); closeDrawer(); }; results.appendChild(d); });
  results.classList.add("on");
}
function markRes(){ [].forEach.call(results.children,function(c,i){ c.classList.toggle("sel",i===resSel); }); }

// ---------------- filters ----------------
var statusSeg=document.getElementById("statusSeg");
statusSeg.addEventListener("click",function(e){ var btn=e.target.closest("button"); if(!btn) return; state.status=btn.dataset.s; [].forEach.call(statusSeg.children,function(c){c.classList.toggle("on",c===btn);}); requestDraw(); });
var TYPE_BTNS=[["tyAll","all"],["tyMovie","Movie"],["tySeries","Series"],["tyGame","Game"]];
TYPE_BTNS.forEach(function(p){ document.getElementById(p[0]).onclick=function(){ state.type=p[1]; TYPE_BTNS.forEach(function(q){document.getElementById(q[0]).classList.toggle("on",q[0]===p[0]);}); requestDraw(); }; });
document.getElementById("connBtn").onclick=function(){ state.showConn=!state.showConn; this.classList.toggle("on",state.showConn); requestDraw(); };

// ---------------- rating filter (min stars, 1-10) ----------------
var rfStars=document.getElementById("ratefilterStars"), rfClear=document.getElementById("rateClear"), rfVal=document.getElementById("rateVal");
function buildRateFilter(){
  rfStars.innerHTML="";
  for(var i=1;i<=MAXR;i++){ (function(i){
    var sp=document.createElement("span"); sp.className="star"; sp.textContent="★"; sp.title=i+"+ / 10";
    sp.onmouseenter=function(){ paintStars(rfStars,i); rfVal.textContent=i+"+"; };
    sp.onmouseleave=function(){ syncRateFilter(); };
    sp.onclick=function(){ state.minRating=(state.minRating===i)?0:i; syncRateFilter(); requestDraw(); };
    rfStars.appendChild(sp);
  })(i); }
  syncRateFilter();
}
function syncRateFilter(){ paintStars(rfStars,state.minRating); rfClear.classList.toggle("on",state.minRating>0); rfVal.textContent=state.minRating?(state.minRating+"+ / 10"):"any"; }
rfClear.onclick=function(){ state.minRating=0; syncRateFilter(); requestDraw(); toast("Rating filter cleared"); };

// ---------------- legend ----------------
var genresEl=document.getElementById("genres");
function buildGenreList(){
  genresEl.innerHTML="";
  genres.forEach(function(g){ var m=genreMeta[g]; var seenN=TITLES.reduce(function(acc,b){return acc+((b.g===g&&isWatched(b.id))?1:0);},0);
    var it=document.createElement("div"); it.className="gitem"+(state.hidden[g]?" off":"");
    it.innerHTML='<span class="dot" style="background:'+(theme==="light"?m.lcolor:m.color)+'"></span><span class="gname">'+esc(g)+'</span><span class="gcount">'+seenN+'/'+m.n+'</span>';
    it.onclick=function(){ state.hidden[g]=!state.hidden[g]; it.classList.toggle("off",state.hidden[g]); requestDraw(); };
    genresEl.appendChild(it);
  });
}
document.getElementById("genAll").onclick=function(){ state.hidden={}; buildGenreList(); requestDraw(); };
function soloGenre(g){ state.hidden={}; genres.forEach(function(x){ if(x!==g) state.hidden[x]=true; }); buildGenreList(); requestDraw(); toast("Showing only "+g); }

// ---------------- zoom buttons ----------------
document.getElementById("zin").onclick=function(){ zoomAt(W/2,H/2,1.4); };
document.getElementById("zout").onclick=function(){ zoomAt(W/2,H/2,1/1.4); };
document.getElementById("zfit").onclick=function(){ userMoved=false; fitView(700); };

// ---------------- progress / toast ----------------
function updProgress(){
  document.getElementById("pcount").textContent=Object.keys(watchedSet).length;
  document.getElementById("tcount").textContent=TITLES.length;
  var ids=Object.keys(ratings), n=ids.length, sum=0; for(var i=0;i<n;i++) sum+=ratings[ids[i]]||0;
  document.getElementById("ravgWrap").innerHTML = n ? (' · <span class="ravg">★'+(sum/n).toFixed(1)+'</span> avg ('+n+')') : '';
}
var toastEl=document.getElementById("toast"), toastT=0;
function toast(msg){ toastEl.textContent=msg; toastEl.classList.add("on"); clearTimeout(toastT); toastT=setTimeout(function(){toastEl.classList.remove("on");},2600); }
setTimeout(function(){ var h=document.getElementById("hint"); if(h) h.style.opacity="0"; },7000);

// ---------------- keyboard ----------------
window.addEventListener("keydown",function(e){
  if(e.target.tagName==="INPUT"||e.target.tagName==="TEXTAREA") return;
  if(e.key==="/"){ openDrawer(); setTimeout(function(){search.focus();},260); e.preventDefault(); }
  else if(e.key==="w"||e.key==="W"){ document.getElementById("tonight").click(); }
  else if(e.key==="f"||e.key==="F"){ userMoved=false; fitView(600); }
  else if(e.key==="m"||e.key==="M"){ drawer.classList.contains("on")?closeDrawer():openDrawer(); }
  else if(e.key==="Escape"){ closeDrawer(); closeDetail(); }
});

// apply the IMDb seed once (merges watched + ratings into your saved state)
var SEED_KEY="avmu-seed-v1", SEED_VERSION="imdb-1";
(function applySeed(){
  try{ if(localStorage.getItem(SEED_KEY)===SEED_VERSION) return; }catch(e){}
  try{
    if(typeof SEED_WATCHED!=="undefined") SEED_WATCHED.forEach(function(id){ watchedSet[id]=1; });
    if(typeof SEED_RATINGS!=="undefined") Object.keys(SEED_RATINGS).forEach(function(id){ ratings[id]=+SEED_RATINGS[id]; watchedSet[id]=1; });
    saveWatched(); saveRatings(); localStorage.setItem(SEED_KEY,SEED_VERSION);
  }catch(e){}
})();

// ---------------- init ----------------
TOP=document.getElementById("topbar").offsetHeight||56;
applyTheme();
buildLayout(); buildGenreList(); buildRateFilter(); updProgress(); resize();
(function(){ var tx=cam.x,ty=cam.y,ts=cam.s; cam.s=ts*0.72; flyTo(tx,ty,ts,1200); })();
requestDraw();
})();
</script>
</body>
</html>'''

out = (HTML.replace('__TITLES_JSON__', data_json)
           .replace('__SEED_WATCHED__', seed_watched_json)
           .replace('__SEED_RATINGS__', seed_ratings_json))
with open(DEST, 'w', encoding='utf-8') as f:
    f.write(out)
print()
print('wrote', DEST, len(out), 'bytes; titles:', len(slim),
      '; seeded watched:', len(seed_watched), '; seeded ratings:', len(seed_ratings))
