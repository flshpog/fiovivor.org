"""
Generates index-preview.html for fiovivor.org — a two-"world" archive browser:

  * EVEREST world  (default): cinematic snowy hero -> intro -> Season 1 archives
  * FIOVIVOR world (slides in): the original S8 / S9 / S10 / The Stage browser

Channel lists are scanned straight from the archive folders on disk, so this can
be re-run any time new seasons/channels are added.

    python build_index.py
"""

import os
import re
import html
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "index.html")

# ---- pretty names + ordering -------------------------------------------------

PRETTY = {
    "in-game info": "In-Game Info",
    "in-game information": "In-Game Information",
    "tribal councils": "Tribal Councils",
    "confessionals": "Confessionals",
    "alliances": "Alliances",
    "1-1s": "1-on-1s",
    "tribe chat archives": "Tribe Chats",
    "lodge twist archives": "Lodge Twist",
    "other channels": "Other Channels",
    "audience seating": "Audience Seating",
    "submissions": "Submissions",
}

EVEREST_ORDER = [
    "in-game info", "tribal councils", "confessionals", "alliances",
    "1-1s", "tribe chat archives", "lodge twist archives", "other channels",
]
FIO_ORDER = [
    "in-game information", "tribal councils", "confessionals",
    "alliances", "audience seating", "other channels",
]


def pretty(folder):
    return PRETTY.get(folder.lower(), folder.title())


def natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def channel_display(fname):
    name = fname[:-5] if fname.lower().endswith(".html") else fname
    if name.endswith("-archive"):
        name = name[:-len("-archive")]
    return name


def list_html(folder_abs):
    files = [f for f in os.listdir(folder_abs) if f.lower().endswith(".html")]
    files.sort(key=natkey)
    return files


def category_block(rel_dir_parts, folder_abs):
    """One collapsible category from a folder of html files."""
    files = list_html(folder_abs)
    if not files:
        return None, 0
    folder = rel_dir_parts[-1]
    rows = []
    for f in files:
        href = quote("/".join(rel_dir_parts + [f]))
        disp = html.escape(channel_display(f))
        rows.append(
            f'        <a class="channel-link" href="{href}">'
            f'<span class="hash">#</span> {disp}</a>'
        )
    block = f"""      <div class="category">
        <div class="category-header">
          <div><h3>{html.escape(pretty(folder))}</h3></div>
          <svg class="arrow" viewBox="0 0 24 24"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>
        </div>
        <div class="channel-list">
{chr(10).join(rows)}
        </div>
      </div>"""
    return block, len(files)


def flat_list(rel_dir_parts, folder_abs):
    """A flat (no category) channel list — used for The Stage."""
    files = list_html(folder_abs)
    rows = []
    for f in files:
        href = quote("/".join(rel_dir_parts + [f]))
        disp = html.escape(channel_display(f))
        rows.append(
            f'      <a class="channel-link" href="{href}">'
            f'<span class="hash">#</span> {disp}</a>'
        )
    return "\n".join(rows), len(files)


def season_categories(base_folder, order):
    """Build ordered category blocks for a season folder. Any folders not in the
    explicit order are appended alphabetically so nothing is silently dropped."""
    base_abs = os.path.join(ROOT, base_folder)
    present = [d for d in os.listdir(base_abs) if os.path.isdir(os.path.join(base_abs, d))]
    ordered = [c for c in order if c in [p.lower() for p in present]]
    # map lower->actual
    lower_to_actual = {p.lower(): p for p in present}
    seen = set(ordered)
    extras = sorted(p.lower() for p in present if p.lower() not in seen)
    blocks, total = [], 0
    for cat in ordered + extras:
        actual = lower_to_actual[cat]
        b, n = category_block([base_folder, actual], os.path.join(base_abs, actual))
        if b:
            blocks.append(b)
            total += n
    return "\n\n".join(blocks), total


# ---- assemble the two worlds -------------------------------------------------

everest_cats, everest_total = season_categories("everest survivor 1 archive", EVEREST_ORDER)

fio_worlds = []
for sid, folder, label in [
    ("s8", "fiovivor 8 archive", "Season 8"),
    ("s9", "fiovivor 9 archive", "Season 9"),
    ("s10", "fiovivor 10 archive", "Season 10"),
]:
    cats, total = season_categories(folder, FIO_ORDER)
    fio_worlds.append((sid, label, total, cats))

stage_rows, stage_total = flat_list(["the stage"], os.path.join(ROOT, "the stage"))

# fiovivor tabs
fio_tabs = []
for sid, label, total, _ in fio_worlds:
    active = " active" if sid == "s10" else ""
    fio_tabs.append(f'<button class="tab{active}" data-season="{sid}">{label}</button>')
fio_tabs.append('<button class="tab" data-season="stage">The Stage</button>')
fio_tabs_html = "\n      ".join(fio_tabs)

# fiovivor season panels
fio_panels = []
for sid, label, total, cats in fio_worlds:
    active = " active" if sid == "s10" else ""
    fio_panels.append(f"""    <div class="season{active}" id="{sid}">
{cats}
    </div>""")
fio_panels.append(f"""    <div class="season" id="stage">
      <div class="channel-list flat">
{stage_rows}
      </div>
    </div>""")
fio_panels_html = "\n".join(fio_panels)

fio_grand_total = sum(t for _, _, t, _ in fio_worlds) + stage_total

# ---- template (raw string; tokens replaced below) ----------------------------

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Everest</title>
<meta property="og:title" content="Everest">
<meta property="og:description" content="A collaborative multiformat Discord ORG community, home to competitive Survivor, Traitors, Big Brother and more.">
<meta property="og:type" content="website">
<meta property="og:image" content="https://fiovivor.org/everestembedlogo.png">
<meta name="theme-color" content="#637798">
<link rel="icon" type="image/png" href="everestlogo.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400..800&family=Hanken+Grotesk:ital,wght@0,400;0,500;0,600;0,700;0,800;1,500&display=swap" rel="stylesheet">
<style>
:root{
  --night:#070b16; --night-2:#0b1220; --panel:#0e1626; --panel-2:#121d31;
  --line:#20304d; --snow:#eaf1ff; --ice:#9fc2e8; --muted:#8394b3;
  --accent:#637798; --accent-soft:rgba(99,119,152,.16);
}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth}
body{
  font-family:'Hanken Grotesk',system-ui,sans-serif;
  background:var(--night); color:var(--snow);
  -webkit-font-smoothing:antialiased; overflow:hidden;
}
a{color:inherit;text-decoration:none}

/* ---------- world slider ---------- */
.viewport{width:100vw;height:100vh;overflow:hidden;position:relative}
/* track holds [fiovivor | everest]; Everest (2nd panel) is the default view */
.track{display:flex;width:200vw;height:100vh;transform:translateX(-100vw);transition:transform .8s cubic-bezier(.76,0,.24,1)}
.track.show-fio{transform:translateX(0)}
.world{width:100vw;min-width:0;height:100vh;overflow-y:auto;overflow-x:hidden;position:relative;scroll-behavior:smooth}
.world::-webkit-scrollbar{width:10px}
.world::-webkit-scrollbar-thumb{background:#1c2b45;border-radius:6px}

/* ---------- EVEREST ---------- */
#everest{background:
  radial-gradient(120% 80% at 50% -10%, #16233f 0%, #0a1120 45%, var(--night) 100%);}
#snow{position:fixed;inset:0;pointer-events:none;z-index:1}
.everest-inner{position:relative;z-index:2}

.hero{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
  text-align:center;padding:5rem 1.5rem 3rem;position:relative}
.emblem{width:auto;height:180px;max-width:80vw;object-fit:contain;margin-bottom:1.4rem;
  filter:drop-shadow(0 0 36px rgba(150,190,235,.30)) drop-shadow(0 14px 30px rgba(0,0,0,.55));
  animation:emblem-in 1.3s cubic-bezier(.2,.8,.2,1) both}
.wordmark{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;letter-spacing:-.015em;
  font-size:clamp(4rem,17vw,13rem);line-height:.85;text-transform:uppercase;
  background:linear-gradient(180deg,#ffffff 0%,#bcd4f2 55%,#7ea2cc 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
  animation:rise 1.1s cubic-bezier(.2,.8,.2,1) .15s both}
.wordmark .dot{color:var(--accent);-webkit-text-fill-color:var(--accent)}
.kicker{font-weight:800;letter-spacing:.2em;text-transform:uppercase;
  font-size:1.15rem;color:var(--ice);margin-bottom:1.4rem;padding-left:.2em;
  animation:fade 1s .1s both}
.tagline{max-width:min(640px,calc(100vw - 3rem));color:#cdd9ee;font-size:1.12rem;line-height:1.6;margin-top:1.7rem;
  animation:fade 1s .5s both}
.season-tag{margin-top:1.5rem;display:inline-flex;align-items:center;gap:.6rem;
  font-weight:700;font-size:.74rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--snow);border:1px solid var(--line);border-radius:100px;padding:.5rem 1.1rem;
  background:rgba(10,17,32,.5);animation:fade 1s .7s both}
.season-tag b{color:var(--accent);font-weight:700}
.discord-btn{margin-top:1.8rem;display:inline-flex;align-items:center;gap:.55rem;
  background:var(--accent);color:#f4f8ff;font-weight:800;font-size:.98rem;letter-spacing:.01em;
  padding:.8rem 1.5rem;border-radius:100px;transition:transform .18s,filter .18s,box-shadow .18s;
  box-shadow:0 10px 30px rgba(99,119,152,.34);animation:fade 1s .85s both}
.discord-btn:hover{transform:translateY(-2px);filter:brightness(1.1);box-shadow:0 14px 38px rgba(99,119,152,.48)}
.discord-btn svg{width:20px;height:20px;fill:currentColor}
.scroll-cue{margin-top:auto;padding-top:2.4rem;display:flex;flex-direction:column;align-items:center;gap:.6rem;
  color:var(--muted);font-weight:700;font-size:.72rem;letter-spacing:.16em;text-transform:uppercase;
  animation:fade 1s 1s both}
.scroll-cue svg{width:22px;height:22px;fill:var(--accent);animation:bob 1.8s ease-in-out infinite}

/* about / intro */
.about{max-width:940px;margin:0 auto;padding:4rem 1.6rem 2rem}
.about-block{margin-bottom:3rem}
.about h2{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;letter-spacing:-.01em;text-transform:uppercase;
  font-size:clamp(1.8rem,4.5vw,2.9rem);display:flex;align-items:center;gap:.5rem;margin-bottom:.3rem}
.about h2 .q{color:var(--accent)}
.about h2::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--line),transparent);margin-left:.8rem}
.about p{color:#c2cfe6;font-size:1.06rem;line-height:1.75;margin-top:1rem;max-width:820px}
.about b{color:#fff;font-weight:700}
.about .name{color:var(--accent);font-weight:700}
.rule{height:1px;background:linear-gradient(90deg,transparent,var(--line),transparent);margin:1rem 0}

/* archives cta */
.arch-cta{display:block;text-align:center;padding:3rem 1.5rem 1rem}
.arch-cta .lead{font-family:'Bricolage Grotesque',sans-serif;font-weight:800;font-size:clamp(1.6rem,5vw,3rem);text-transform:uppercase;
  letter-spacing:-.01em;background:linear-gradient(180deg,#fff,#9fc2e8);-webkit-background-clip:text;background-clip:text;color:transparent}
.arch-cta svg{width:26px;height:26px;fill:var(--accent);margin-top:.8rem;animation:bob 1.8s ease-in-out infinite}

/* ---------- archive browser (shared look) ---------- */
.browser{max-width:820px;margin:1.5rem auto;padding:0 1.2rem 6rem}
.season-head{font-weight:700;text-transform:uppercase;letter-spacing:.14em;
  font-size:.74rem;color:var(--ice);text-align:center;margin:1.5rem 0 1.2rem}
.season-head b{color:var(--accent)}
.search-bar{position:relative;max-width:520px;margin:0 auto 1.4rem}
.search-bar input{width:100%;padding:.7rem 1rem .7rem 2.5rem;border:1px solid var(--line);border-radius:10px;
  background:#0a1120;color:var(--snow);font-size:.95rem;font-family:inherit;outline:none;transition:border-color .2s}
.search-bar input:focus{border-color:var(--accent)}
.search-bar svg{position:absolute;left:.85rem;top:50%;transform:translateY(-50%);width:16px;height:16px;fill:#4a5c7e}
.tabs{display:flex;justify-content:center;flex-wrap:wrap;gap:.4rem;margin:0 auto 1.4rem}
.tab{padding:.55rem 1.4rem;background:transparent;border:1px solid var(--line);color:var(--muted);
  cursor:pointer;font-size:.9rem;font-weight:600;font-family:inherit;border-radius:8px;transition:all .18s}
.tab:hover:not(.active){background:var(--panel-2);color:var(--snow)}
.tab.active{background:var(--accent);border-color:var(--accent);color:#fff}

.season{display:none}
.season.active{display:block}
.category{margin-bottom:.5rem;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--panel)}
.category-header{display:flex;align-items:center;justify-content:space-between;padding:.85rem 1rem;cursor:pointer;user-select:none;transition:background .15s}
.category-header:hover{background:var(--panel-2)}
.category-header h3{font-size:.9rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#d4deef}
.category-header .count{font-size:.7rem;color:var(--ice);background:#0a1120;padding:.15rem .55rem;border-radius:10px;margin-left:.5rem}
.category-header .arrow{transition:transform .2s;fill:#4a5c7e;width:18px;height:18px;flex-shrink:0}
.category.open .arrow{transform:rotate(180deg)}
.channel-list{display:none;padding:.25rem .5rem .5rem}
.category.open .channel-list{display:block}
.channel-list.flat{display:block;padding:.5rem;border:1px solid var(--line);border-radius:10px;background:var(--panel)}
.channel-link{display:flex;align-items:center;gap:.5rem;padding:.5rem .65rem;color:#aebbd2;border-radius:6px;font-size:.9rem;transition:background .12s,color .12s}
.channel-link:hover{background:var(--panel-2);color:#fff}
.channel-link .hash{color:var(--accent);font-weight:700;font-size:1.05rem;flex-shrink:0}
.no-results{display:none;text-align:center;color:var(--muted);padding:3rem 1rem}

/* ---------- FIOVIVOR (restored original blurple design) ---------- */
#fiovivor{background:#1a1a2e;color:#e0e0e0}
#fiovivor .fio-header{text-align:center;padding:2rem 1rem 1.5rem;background:linear-gradient(180deg,#16213e 0%,#1a1a2e 100%);border-bottom:1px solid #2a2a4a}
#fiovivor .fio-logo{max-width:150px;height:auto;margin-bottom:.5rem}
#fiovivor .fio-title{font-size:1.8rem;font-weight:700;color:#e0e0e0;letter-spacing:.02em}
#fiovivor .fio-header p{color:#888;font-size:.9rem;margin-top:.25rem}
#fiovivor .season-head{color:#8a8aa8}
#fiovivor .search-bar input{background:#0f0f23;border-color:#2a2a4a;border-radius:8px}
#fiovivor .search-bar input:focus{border-color:#5865f2}
#fiovivor .search-bar svg{fill:#666}
#fiovivor .tabs{gap:0}
#fiovivor .tab{padding:.7rem 2rem;border:1px solid #2a2a4a;color:#888;border-radius:0}
#fiovivor .tab:first-child{border-radius:8px 0 0 8px}
#fiovivor .tab:last-child{border-radius:0 8px 8px 0}
#fiovivor .tab:not(:first-child){border-left:none}
#fiovivor .tab.active{background:#5865f2;border-color:#5865f2;color:#fff}
#fiovivor .tab:hover:not(.active){background:#2a2a4a;color:#e0e0e0}
#fiovivor .category{background:#16213e;border-color:#2a2a4a}
#fiovivor .category-header:hover{background:#1e2d4d}
#fiovivor .category-header h3{color:#ccc}
#fiovivor .category-header .count{color:#888;background:#0f0f23}
#fiovivor .category-header .arrow{fill:#666}
#fiovivor .channel-link{color:#b0b0c0}
#fiovivor .channel-link:hover{background:#2a2a4a;color:#fff}
#fiovivor .channel-link .hash{color:#5865f2}
#fiovivor .channel-list.flat{background:#16213e;border-color:#2a2a4a}
#fiovivor .no-results{color:#666}

/* ---------- world nav flags ---------- */
.flag{position:fixed;top:50%;transform:translateY(-50%);z-index:30;cursor:pointer;
  display:flex;align-items:center;gap:.6rem;padding:1rem .9rem;border:1px solid var(--line);
  background:rgba(9,14,26,.82);backdrop-filter:blur(6px);color:var(--snow);
  font-weight:700;font-size:.66rem;letter-spacing:.14em;text-transform:uppercase;
  transition:background .2s,border-color .2s,transform .35s cubic-bezier(.76,0,.24,1),opacity .35s}
.flag:hover{background:var(--accent);border-color:var(--accent);color:#fff}
.flag svg{width:16px;height:16px;fill:currentColor;flex-shrink:0}
.flag-left{left:0;border-left:none;border-radius:0 12px 12px 0;writing-mode:vertical-rl;text-orientation:mixed}
.flag-left:hover{transform:translateY(-50%) translateX(3px)}
.flag-right{right:0;border-right:none;border-radius:12px 0 0 12px;writing-mode:vertical-rl;text-orientation:mixed}
.flag-right:hover{transform:translateY(-50%) translateX(-3px)}
.flag-left .lbl,.flag-right .lbl{writing-mode:vertical-rl}
.flag-icon{display:none}
.flag-left.hidden{transform:translateY(-50%) translateX(-120%);opacity:0;pointer-events:none}
.flag-right.hidden{transform:translateY(-50%) translateX(120%);opacity:0;pointer-events:none}

/* ---------- viewer overlay ---------- */
.viewer{display:none;position:fixed;inset:0;z-index:100;background:var(--night);flex-direction:column}
.viewer.active{display:flex}
.viewer-bar{display:flex;align-items:center;gap:.75rem;padding:.6rem 1rem;background:var(--panel);border-bottom:1px solid var(--line);flex-shrink:0}
.viewer-back{display:flex;align-items:center;gap:.4rem;padding:.45rem .95rem;background:var(--accent);color:#fff;border:none;border-radius:7px;cursor:pointer;font-size:.85rem;font-weight:700;font-family:inherit}
.viewer-back:hover{filter:brightness(1.08)}
.viewer-back svg{width:15px;height:15px;fill:currentColor}
.viewer-title{color:#cdd9ee;font-size:.9rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.viewer-title .hash{color:var(--accent);font-weight:700;margin-right:.25rem}
.viewer iframe{flex:1;border:none;width:100%}
body.viewing{overflow:hidden}

#snow{transition:opacity .6s ease}
.toast{position:fixed;left:50%;bottom:2.4rem;transform:translateX(-50%) translateY(20px);z-index:200;
  background:rgba(14,22,38,.97);border:1px solid var(--line);color:var(--snow);
  padding:.85rem 1.5rem;border-radius:14px;font-weight:600;font-size:.95rem;
  box-shadow:0 14px 44px rgba(0,0,0,.55);opacity:0;pointer-events:none;transition:opacity .3s,transform .3s}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}

@keyframes rise{from{opacity:0;transform:translateY(40px)}to{opacity:1;transform:translateY(0)}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes emblem-in{from{opacity:0;transform:translateY(-20px) scale(.9)}to{opacity:1;transform:none}}
@keyframes bob{0%,100%{transform:translateY(0)}50%{transform:translateY(7px)}}

@media(max-width:600px){
  .flag-left,.flag-right{writing-mode:horizontal-tb;padding:.4rem;gap:0}
  .flag-left{border-radius:0 14px 14px 0}
  .flag-right{border-radius:14px 0 0 14px}
  .flag-left .lbl,.flag-right .lbl,.flag-left>svg,.flag-right>svg{display:none}
  .flag .flag-icon{display:block;width:30px;height:30px;object-fit:contain;border-radius:6px}
  .kicker{font-size:.76rem;letter-spacing:.1em;padding-left:.1em}
  .tagline{font-size:1rem}
  .wordmark{font-size:clamp(2.4rem,14vw,8rem)}
}
@media(prefers-reduced-motion:reduce){
  *{animation:none!important;transition:none!important}
  html{scroll-behavior:auto}
}
</style>
</head>
<body>

<canvas id="snow"></canvas>

<div class="viewport">
  <div class="track" id="track">

    <!-- ============ FIOVIVOR WORLD ============ -->
    <section class="world" id="fiovivor">
      <div class="fio-header">
        <img class="fio-logo" src="fiovivorlogo.png" alt="Fiovivor logo">
        <h1 class="fio-title">Fiovivor Archive</h1>
        <p>Fiovivor channel archives from Seasons 8, 9 &amp; 10</p>
      </div>
      <div class="browser">
        <div class="search-bar">
          <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
          <input type="text" class="search" placeholder="Search Fiovivor channels..." autocomplete="off">
        </div>
        <div class="tabs">
      __FIO_TABS__
        </div>
__FIO_PANELS__
        <div class="no-results">No channels found.</div>
      </div>
    </section>

    <!-- ============ EVEREST WORLD ============ -->
    <section class="world" id="everest">
      <div class="everest-inner">

        <div class="hero">
          <img class="emblem" src="everestlogo.png" alt="Everest logo">
          <div class="kicker">Multiformat Discord ORG</div>
          <h1 class="wordmark">Everest<span class="dot">.</span></h1>
          <p class="tagline">An official spinoff and evolution of the Fiovivor series, built for high quality, competitive, and thoroughly enjoyable ORG experiences.</p>
          <div class="season-tag">Now casting: <b>Season 2 &middot; New Horizons</b></div>
          <a class="discord-btn" href="https://discord.gg/everest-org" target="_blank" rel="noopener">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19.3 5.3A17.5 17.5 0 0 0 15 4l-.2.4a16 16 0 0 1 3.8 1.2 15 15 0 0 0-12.9 0A16 16 0 0 1 9.5 4.4L9.3 4A17.5 17.5 0 0 0 5 5.3C2.3 9.3 1.6 13.2 2 17a17.7 17.7 0 0 0 5.3 2.7l.4-.6a11.5 11.5 0 0 1-1.8-.9l.4-.3a12.6 12.6 0 0 0 10.8 0l.4.3a11.5 11.5 0 0 1-1.8.9l.4.6A17.7 17.7 0 0 0 22 17c.5-4.5-.7-8.4-2.7-11.7zM8.9 14.8c-.9 0-1.6-.8-1.6-1.8s.7-1.8 1.6-1.8 1.6.8 1.6 1.8-.7 1.8-1.6 1.8zm6.2 0c-.9 0-1.6-.8-1.6-1.8s.7-1.8 1.6-1.8 1.6.8 1.6 1.8-.7 1.8-1.6 1.8z"/></svg>
            Join the Everest server
          </a>
          <a class="scroll-cue" href="#everest-archives">
            <span>Scroll</span>
            <svg viewBox="0 0 24 24"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>
          </a>
        </div>

        <div class="about">
          <div class="about-block">
            <h2>What is Everest <span class="q">&#8265;</span></h2>
            <p><b>Everest</b> is a collaborative ORG server founded by <span class="name">Fio</span>, alongside executive producers <span class="name">fishpog</span> and <span class="name">Mike</span>.</p>
            <p>At its core, Everest exists to create <b>high quality, competitive, and genuinely fun ORG experiences</b> that preserve what makes these games exciting in the first place. It also serves as an official spinoff and evolution of the Fiovivor series, building on that foundation while expanding what we are able to do as a team!</p>
          </div>
          <div class="rule"></div>
          <div class="about-block">
            <h2>What happens here <span class="q">&#8265;</span></h2>
            <p>The <b>main focus</b> of Everest is our <b>Survivor ORG series!</b> These are long term, fully developed seasons where players compete socially, strategically and physically for the title of Sole Survivor, with a strong emphasis on structure and engaging gameplay.</p>
            <p>Each season is led by a designated <b>Season Lead</b>, who takes on the primary host role for that installment. While one person leads, <b>all hosts collaborate</b> behind the scenes to ensure each season is as polished and enjoyable as possible!</p>
            <p>Outside of Survivor, Everest also features <b>side projects</b> (ie: Sequesters, Minecraft Survivors, The Traitors) hosted by our team. These are designed to be more flexible and accessible for people who may not be able to commit to a full length ORG, while still keeping the same level of creativity and effort!</p>
            <p>Hosts are encouraged to <b>bring their own ideas to life,</b> meaning the server will continue to grow with new formats, experiments, and experiences over time!</p>
          </div>
        </div>

        <a class="arch-cta" id="everest-archives" href="#everest-browser">
          <div class="lead">View our season archives</div>
          <svg viewBox="0 0 24 24"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>
        </a>

        <div class="browser" id="everest-browser">
          <div class="tabs everest-tabs">
            <button class="tab active" data-eseason="everest-s1">Season 1 &middot; Twin Peaks</button>
            <button class="tab" data-eseason="soon">Season 2 &middot; New Horizons</button>
          </div>
          <div class="search-bar">
            <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
            <input type="text" class="search" placeholder="Search Season 1 channels..." autocomplete="off">
          </div>
          <div class="season active" id="everest-s1">
__EVEREST_CATS__
          </div>
          <div class="no-results">No channels found.</div>
        </div>

      </div>
    </section>

  </div>
</div>

<!-- world nav flags -->
<button class="flag flag-left" id="to-fio" title="See Fiovivor archives">
  <svg viewBox="0 0 24 24"><path d="M14 7l-5 5 5 5V7z"/></svg>
  <span class="lbl">Also see our Fiovivor archives</span>
  <img class="flag-icon" src="fiovivorlogo.png" alt="Fiovivor">
</button>
<button class="flag flag-right" id="to-everest" title="Back to Everest" style="display:none">
  <span class="lbl">Back to Everest</span>
  <svg viewBox="0 0 24 24"><path d="M10 17l5-5-5-5v10z"/></svg>
  <img class="flag-icon" src="everestlogo.png" alt="Everest">
</button>

<div class="toast" id="toast"></div>

<!-- shared viewer -->
<div class="viewer" id="viewer">
  <div class="viewer-bar">
    <button class="viewer-back" id="viewer-back">
      <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
      Back
    </button>
    <div class="viewer-title" id="viewer-title"></div>
  </div>
  <iframe id="viewer-frame" src="" title="Archive viewer"></iframe>
</div>

<script>
// ---------- world sliding ----------
var track = document.getElementById('track');
var toFio = document.getElementById('to-fio');
var toEverest = document.getElementById('to-everest');
var snowEl = document.getElementById('snow');
function showFio(){ track.classList.add('show-fio'); toFio.style.display='none'; toEverest.style.display='flex'; toEverest.classList.remove('hidden'); snowEl.style.opacity='0'; }
function showEverest(){ track.classList.remove('show-fio'); toEverest.style.display='none'; toFio.style.display='flex'; toFio.classList.remove('hidden'); snowEl.style.opacity='1'; }
toFio.addEventListener('click', showFio);
toEverest.addEventListener('click', showEverest);

// hide the side flag while scrolling down within a world, reveal on scroll up
function attachFlagAutohide(world, flag){
  var last = 0;
  world.addEventListener('scroll', function(){
    var y = world.scrollTop;
    if (y < 120) flag.classList.remove('hidden');
    else if (y > last + 6) flag.classList.add('hidden');
    else if (y < last - 6) flag.classList.remove('hidden');
    last = y;
  }, {passive:true});
}
attachFlagAutohide(document.getElementById('everest'), toFio);
attachFlagAutohide(document.getElementById('fiovivor'), toEverest);

// toast + everest season tabs
function showToast(msg){
  var t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._timer); t._timer = setTimeout(function(){ t.classList.remove('show'); }, 2600);
}
document.querySelectorAll('.everest-tabs .tab').forEach(function(tab){
  tab.addEventListener('click', function(){
    if(tab.dataset.eseason === 'soon'){ showToast('Season 2 · New Horizons is coming soon'); return; }
    document.querySelectorAll('.everest-tabs .tab').forEach(function(t){ t.classList.remove('active'); });
    tab.classList.add('active');
    document.getElementById('everest-s1').classList.add('active');
  });
});

// ---------- accordions ----------
document.querySelectorAll('.category-header').forEach(function(h){
  h.addEventListener('click', function(){ h.parentElement.classList.toggle('open'); });
});

// ---------- fiovivor tabs ----------
document.querySelectorAll('#fiovivor .tab').forEach(function(tab){
  tab.addEventListener('click', function(){
    document.querySelectorAll('#fiovivor .tab').forEach(function(t){t.classList.remove('active');});
    document.querySelectorAll('#fiovivor .season').forEach(function(s){s.classList.remove('active');});
    tab.classList.add('active');
    document.getElementById(tab.dataset.season).classList.add('active');
  });
});

// ---------- viewer ----------
var viewer = document.getElementById('viewer');
var viewerFrame = document.getElementById('viewer-frame');
var viewerTitle = document.getElementById('viewer-title');
var viewerBack = document.getElementById('viewer-back');
document.querySelectorAll('.channel-link').forEach(function(link){
  link.addEventListener('click', function(e){
    e.preventDefault();
    var name = link.textContent.trim().replace(/^#\s*/, '');
    viewerTitle.innerHTML = '<span class="hash">#</span> ' + name;
    viewerFrame.src = link.getAttribute('href');
    viewer.classList.add('active');
    document.body.classList.add('viewing');
  });
});
viewerBack.addEventListener('click', function(){
  viewer.classList.remove('active'); document.body.classList.remove('viewing'); viewerFrame.src='';
});
document.addEventListener('keydown', function(e){
  if(e.key==='Escape' && viewer.classList.contains('active')) viewerBack.click();
});

// ---------- per-world search ----------
document.querySelectorAll('.world').forEach(function(world){
  var input = world.querySelector('.search');
  if(!input) return;
  var noResults = world.querySelector('.no-results');
  var tabsEl = world.querySelector('.tabs');
  input.addEventListener('input', function(){
    var q = input.value.toLowerCase().trim();
    var anyVisible = false;
    world.querySelectorAll('.season').forEach(function(season){
      var seasonHas = false;
      season.querySelectorAll('.category').forEach(function(cat){
        var catHas = false;
        cat.querySelectorAll('.channel-link').forEach(function(link){
          var m = !q || link.textContent.toLowerCase().indexOf(q) !== -1;
          link.style.display = m ? '' : 'none';
          if(m) catHas = true;
        });
        cat.style.display = catHas ? '' : 'none';
        if(q && catHas) cat.classList.add('open');
        if(catHas) seasonHas = true;
      });
      season.querySelectorAll(':scope > .channel-list .channel-link').forEach(function(link){
        var m = !q || link.textContent.toLowerCase().indexOf(q) !== -1;
        link.style.display = m ? '' : 'none';
        if(m) seasonHas = true;
      });
      if(q){ season.style.display = seasonHas ? 'block' : 'none'; if(seasonHas) anyVisible = true; }
      else { season.style.display=''; anyVisible = true; }
    });
    if(tabsEl) tabsEl.style.display = q ? 'none' : '';
    if(q){
      world.querySelectorAll('.season').forEach(function(s){ if(s.style.display!=='none') s.classList.add('active'); });
    } else {
      var activeTab = world.querySelector('.tab.active');
      if(activeTab){
        world.querySelectorAll('.season').forEach(function(s){s.classList.remove('active');});
        document.getElementById(activeTab.dataset.season).classList.add('active');
      }
    }
    if(noResults) noResults.style.display = (!anyVisible && q) ? 'block' : 'none';
  });
});

// ---------- snow ----------
(function(){
  var c = document.getElementById('snow'), x = c.getContext('2d');
  var flakes = [], W, H;
  function resize(){ W=c.width=innerWidth; H=c.height=innerHeight; }
  resize(); addEventListener('resize', resize);
  var N = Math.min(140, Math.floor(W/12));
  for(var i=0;i<N;i++) flakes.push({x:Math.random()*W,y:Math.random()*H,r:Math.random()*2.2+0.6,d:Math.random()*1+0.4,o:Math.random()*0.5+0.3});
  function draw(){
    x.clearRect(0,0,W,H);
    for(var i=0;i<flakes.length;i++){
      var f=flakes[i];
      x.beginPath(); x.arc(f.x,f.y,f.r,0,6.283);
      x.fillStyle='rgba(234,241,255,'+f.o+')'; x.fill();
      f.y+=f.d; f.x+=Math.sin(f.y/40)*0.4;
      if(f.y>H){ f.y=-5; f.x=Math.random()*W; }
    }
    requestAnimationFrame(draw);
  }
  if(!matchMedia('(prefers-reduced-motion: reduce)').matches) draw();
})();
</script>
</body>
</html>
"""

out = (TEMPLATE
       .replace("__EVEREST_CATS__", everest_cats)
       .replace("__EVEREST_TOTAL__", f"{everest_total:,}")
       .replace("__FIO_TABS__", fio_tabs_html)
       .replace("__FIO_PANELS__", fio_panels_html)
       .replace("__FIO_TOTAL__", f"{fio_grand_total:,}"))

with open(OUT, "w", encoding="utf-8") as f:
    f.write(out)

print(f"Wrote {OUT}")
print(f"  Everest S1: {everest_total} channels")
print(f"  Fiovivor:   {fio_grand_total} channels (S8/S9/S10 + Stage)")
