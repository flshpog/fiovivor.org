#!/usr/bin/env python3
"""
Scans the Fiovivor archive folders and generates index.html for the website.
"""

import os
import re
import urllib.parse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_FILE = os.path.join(BASE_DIR, "index.html")

# Define the folder structure for each season/section
SEASONS = {
    "s8": {
        "label": "Season 8",
        "categories": [
            ("In-Game Information", "fiovivor 8 archive/in-game information"),
            ("Tribal Councils", "fiovivor 8 archive/tribal councils"),
            ("Confessionals", "fiovivor 8 archive/confessionals"),
            ("Alliances", "fiovivor 8 archive/alliances"),
            ("Public Archives", "fiovivor 8 archive/other channels"),
        ],
    },
    "s9": {
        "label": "Season 9",
        "categories": [
            ("In-Game Information", "fiovivor 9 archive/in-game information"),
            ("Tribal Councils", "fiovivor 9 archive/tribal councils"),
            ("Confessionals", "fiovivor 9 archive/confessionals"),
            ("Alliances", "fiovivor 9 archive/alliances"),
            ("Public Archives", "fiovivor 9 archive/other channels"),
        ],
    },
    "s10": {
        "label": "Season 10",
        "categories": [
            ("In-Game Information", "fiovivor 10 archive/in-game information"),
            ("Audience Seating", "fiovivor 10 archive/audience seating"),
            ("Confessionals", "fiovivor 10 archive/confessionals"),
            ("Tribal Councils", "fiovivor 10 archive/tribal councils"),
            ("Alliances", "fiovivor 10 archive/alliances"),
            ("Public Archives", "fiovivor 10 archive/other channels"),
        ],
    },
    "stage": {
        "label": "The Stage",
        "categories": [
            (None, "the stage"),  # None = no category wrapper, just a flat list
        ],
    },
}

SEASON_ORDER = ["s8", "s9", "s10", "stage"]
DEFAULT_ACTIVE = "s10"


def scan_html_files(folder_rel):
    """Return list of .html filenames in the given folder (relative to BASE_DIR)."""
    folder_abs = os.path.join(BASE_DIR, folder_rel)
    if not os.path.isdir(folder_abs):
        return []
    files = [f for f in os.listdir(folder_abs) if f.endswith(".html")]
    return files


def derive_channel_name(filename):
    """Remove the '-archive.html' suffix to get the display name."""
    if filename.endswith("-archive.html"):
        return filename[: -len("-archive.html")]
    if filename.endswith(".html"):
        return filename[: -len(".html")]
    return filename


def confessional_sort_key(filename):
    """
    Sort confessionals by placement number.
    Files like '1st-...', '2nd-...', '3rd-...' etc. get sorted numerically.
    Special files like '___-archive.html', '__JURY__-archive.html' go at the end.
    Handles fractional placements like '3.5th-...' or '3\u2024 5th-...' (with dot leader).
    """
    name = derive_channel_name(filename)
    # Try to extract a leading number (possibly fractional)
    # Handle unicode dot leader (\u2024) as decimal point
    normalized = name.replace("\u2024", ".")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:st|nd|rd|th)", normalized)
    if m:
        return (0, float(m.group(1)), name)
    # Non-numbered confessionals go at the end, sorted alphabetically
    return (1, 0, name)


def sort_files(files, is_confessional=False):
    """Sort files - alphabetically normally, by placement for confessionals."""
    if is_confessional:
        return sorted(files, key=confessional_sort_key)
    else:
        return sorted(files, key=lambda f: derive_channel_name(f).lower())


def encode_href(folder_rel, filename):
    """Build a URL-encoded href path."""
    # Split path into parts and encode each part individually
    parts = folder_rel.replace("\\", "/").split("/")
    parts.append(filename)
    encoded_parts = [urllib.parse.quote(p, safe="") for p in parts]
    return "/".join(encoded_parts)


def generate_channel_link(folder_rel, filename):
    """Generate an <a> tag for a channel."""
    href = encode_href(folder_rel, filename)
    display_name = derive_channel_name(filename)
    return f'        <a class="channel-link" href="{href}"><span class="hash">#</span> {display_name}</a>'


def generate_category_html(cat_name, folder_rel, is_confessional=False):
    """Generate a category accordion section."""
    files = scan_html_files(folder_rel)
    files = [f for f in files if f.endswith("-archive.html") or f.endswith(".html")]
    files = sort_files(files, is_confessional=is_confessional)
    count = len(files)

    lines = []
    lines.append('    <div class="category">')
    lines.append('      <div class="category-header">')
    lines.append(
        f'        <div><h3>{cat_name} <span class="count">{count}</span></h3></div>'
    )
    lines.append(
        '        <svg class="arrow" viewBox="0 0 24 24"><path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"/></svg>'
    )
    lines.append("      </div>")
    lines.append('      <div class="channel-list">')
    for f in files:
        lines.append(generate_channel_link(folder_rel, f))
    lines.append("      </div>")
    lines.append("    </div>")
    return "\n".join(lines)


def generate_flat_list_html(folder_rel):
    """Generate a flat channel list (no category wrapper) for The Stage."""
    files = scan_html_files(folder_rel)
    files = sort_files(files, is_confessional=False)

    lines = []
    lines.append('    <div class="channel-list" style="display:block">')
    for f in files:
        lines.append(generate_channel_link(folder_rel, f))
    lines.append("    </div>")
    return "\n".join(lines)


def generate_season_html(season_id, season_config):
    """Generate a full season section."""
    is_active = season_id == DEFAULT_ACTIVE
    active_class = " active" if is_active else ""

    lines = []
    lines.append(f'  <div class="season{active_class}" id="{season_id}">')
    lines.append("")

    for cat_name, folder_rel in season_config["categories"]:
        is_confessional = cat_name is not None and "confessional" in cat_name.lower()
        if cat_name is None:
            # Flat list (The Stage)
            lines.append(generate_flat_list_html(folder_rel))
        else:
            lines.append(
                generate_category_html(cat_name, folder_rel, is_confessional)
            )
        lines.append("")

    lines.append("  </div>")
    return "\n".join(lines)


def generate_tabs_html():
    """Generate the tab buttons."""
    tabs = []
    for sid in SEASON_ORDER:
        active = " active" if sid == DEFAULT_ACTIVE else ""
        label = SEASONS[sid]["label"]
        tabs.append(
            f'    <button class="tab{active}" data-season="{sid}">{label}</button>'
        )
    return "\n".join(tabs)


def generate_index():
    """Generate the full index.html."""
    tabs_html = generate_tabs_html()

    season_sections = []
    for sid in SEASON_ORDER:
        section = generate_season_html(sid, SEASONS[sid])
        season_sections.append(f"  <!-- {SEASONS[sid]['label']} -->")
        season_sections.append(section)

    seasons_html = "\n\n".join(season_sections)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Fiovivor Archive</title>
  <meta property="og:title" content="Fiovivor Archive">
  <meta property="og:description" content="Discord channel archives from Fiovivor Seasons 8, 9, &amp; 10">
  <meta property="og:image" content="https://fiovivor.org/embedlogo.png">
  <meta property="og:type" content="website">
  <meta name="theme-color" content="#5865f2">
  <link rel="icon" type="image/png" href="logo.png">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      background: #1a1a2e;
      color: #e0e0e0;
      min-height: 100vh;
    }}

    header {{
      text-align: center;
      padding: 2rem 1rem 1rem;
      background: linear-gradient(180deg, #16213e 0%, #1a1a2e 100%);
      border-bottom: 1px solid #2a2a4a;
    }}

    header img {{
      max-width: 320px;
      height: auto;
      margin-bottom: 0.5rem;
    }}

    header h1 {{
      font-size: 1.8rem;
      color: #e0e0e0;
      font-weight: 600;
      letter-spacing: 1px;
    }}

    header p {{
      color: #888;
      font-size: 0.9rem;
      margin-top: 0.25rem;
    }}

    .search-bar {{
      max-width: 500px;
      margin: 1.25rem auto 0;
      position: relative;
    }}

    .search-bar input {{
      width: 100%;
      padding: 0.6rem 1rem 0.6rem 2.4rem;
      border: 1px solid #2a2a4a;
      border-radius: 8px;
      background: #0f0f23;
      color: #e0e0e0;
      font-size: 0.95rem;
      outline: none;
      transition: border-color 0.2s;
    }}

    .search-bar input:focus {{
      border-color: #5865f2;
    }}

    .search-bar svg {{
      position: absolute;
      left: 0.75rem;
      top: 50%;
      transform: translateY(-50%);
      width: 16px;
      height: 16px;
      fill: #666;
    }}

    .tabs {{
      display: flex;
      justify-content: center;
      gap: 0;
      max-width: 800px;
      margin: 1.5rem auto 0;
    }}

    .tab {{
      padding: 0.7rem 2rem;
      background: transparent;
      border: 1px solid #2a2a4a;
      color: #888;
      cursor: pointer;
      font-size: 1rem;
      font-weight: 500;
      transition: all 0.2s;
    }}

    .tab:first-child {{ border-radius: 8px 0 0 8px; border-right: none; }}
    .tab:last-child {{ border-radius: 0 8px 8px 0; border-left: none; }}
    .tab:not(:first-child):not(:last-child) {{ border-radius: 0; border-right: none; }}

    .tab.active {{
      background: #5865f2;
      border-color: #5865f2;
      color: #fff;
    }}

    .tab:hover:not(.active) {{
      background: #2a2a4a;
      color: #e0e0e0;
    }}

    main {{
      max-width: 800px;
      margin: 1.5rem auto;
      padding: 0 1rem 3rem;
    }}

    .season {{ display: none; }}
    .season.active {{ display: block; }}

    .category {{
      margin-bottom: 0.5rem;
      border: 1px solid #2a2a4a;
      border-radius: 8px;
      overflow: hidden;
      background: #16213e;
    }}

    .category-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.85rem 1rem;
      cursor: pointer;
      user-select: none;
      transition: background 0.15s;
    }}

    .category-header:hover {{
      background: #1e2d4d;
    }}

    .category-header h3 {{
      font-size: 0.95rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #ccc;
    }}

    .category-header .count {{
      font-size: 0.75rem;
      color: #666;
      background: #0f0f23;
      padding: 0.15rem 0.5rem;
      border-radius: 10px;
      margin-left: 0.5rem;
    }}

    .category-header .arrow {{
      transition: transform 0.2s;
      fill: #666;
      width: 18px;
      height: 18px;
      flex-shrink: 0;
    }}

    .category.open .category-header .arrow {{
      transform: rotate(180deg);
    }}

    .channel-list {{
      display: none;
      padding: 0 0.5rem 0.5rem;
    }}

    .category.open .channel-list {{
      display: block;
    }}

    .channel-link {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.5rem 0.65rem;
      color: #b0b0c0;
      text-decoration: none;
      border-radius: 4px;
      font-size: 0.9rem;
      transition: background 0.12s, color 0.12s;
    }}

    .channel-link:hover {{
      background: #2a2a4a;
      color: #fff;
    }}

    .channel-link .hash {{
      color: #5865f2;
      font-weight: 700;
      font-size: 1.05rem;
      flex-shrink: 0;
    }}

    .no-results {{
      text-align: center;
      color: #666;
      padding: 3rem 1rem;
      font-size: 0.95rem;
      display: none;
    }}

    /* Viewer overlay */
    .viewer {{
      display: none;
      position: fixed;
      inset: 0;
      z-index: 100;
      background: #1a1a2e;
      flex-direction: column;
    }}

    .viewer.active {{
      display: flex;
    }}

    .viewer-bar {{
      display: flex;
      align-items: center;
      gap: 0.75rem;
      padding: 0.6rem 1rem;
      background: #16213e;
      border-bottom: 1px solid #2a2a4a;
      flex-shrink: 0;
    }}

    .viewer-back {{
      display: flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.4rem 0.9rem;
      background: #5865f2;
      color: #fff;
      border: none;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.85rem;
      font-weight: 500;
      transition: background 0.15s;
    }}

    .viewer-back:hover {{
      background: #4752c4;
    }}

    .viewer-back svg {{
      width: 16px;
      height: 16px;
      fill: currentColor;
    }}

    .viewer-title {{
      color: #ccc;
      font-size: 0.9rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    .viewer-title .hash {{
      color: #5865f2;
      font-weight: 700;
      margin-right: 0.25rem;
    }}

    .viewer iframe {{
      flex: 1;
      border: none;
      width: 100%;
    }}

    body.viewing {{ overflow: hidden; }}

    .marquee-wrap {{
      position: relative;
      transition: margin-top 0.3s ease;
    }}

    .marquee-wrap.hidden {{
      margin-top: -2rem;
      pointer-events: none;
    }}

    .marquee {{
      background: #0f0f23;
      border-bottom: 1px solid #2a2a4a;
      overflow: hidden;
      white-space: nowrap;
      padding: 0.3rem 0;
      font-size: 0.7rem;
      color: #fff;
    }}

    .marquee span {{
      display: inline-block;
      animation: scroll-left 30s linear infinite;
      padding-left: 100%;
    }}

    .marquee-close {{
      position: absolute;
      right: 0.5rem;
      top: calc(100% + 4px);
      background: none;
      border: none;
      color: #fff;
      cursor: pointer;
      font-size: 1.1rem;
      line-height: 1;
      padding: 0.15rem 0.3rem;
      z-index: 1;
    }}

    .marquee-close {{
      transition: opacity 0.3s ease;
    }}

    .marquee-close.fade {{
      opacity: 0;
    }}

    .marquee-close:hover {{
      color: #aaa;
    }}

    @keyframes scroll-left {{
      0%   {{ transform: translateX(0); }}
      100% {{ transform: translateX(-100%); }}
    }}

    @media (max-width: 600px) {{
      header img {{ max-width: 120px; }}
      header h1 {{ font-size: 1.3rem; }}
      .tab {{ padding: 0.6rem 1.2rem; font-size: 0.9rem; }}
    }}
  </style>
</head>
<body>

<div class="marquee-wrap" id="marquee-wrap">
  <div class="marquee"><span>now with season 10, AND better user viewing experience!</span></div>
  <button class="marquee-close" id="marquee-close">&times;</button>
</div>

<header>
  <img src="logo.png" alt="Fiovivor Logo">
  <h1>Fiovivor Archive</h1>
  <p>Discord channel archives from Seasons 8, 9, &amp; 10</p>
  <div class="search-bar">
    <svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.47 6.47 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
    <input type="text" id="search" placeholder="Search channels..." autocomplete="off">
  </div>
  <div class="tabs">
{tabs_html}
  </div>
</header>

<main>
{seasons_html}

  <div class="no-results" id="no-results">No channels found matching your search.</div>
</main>

<div class="viewer" id="viewer">
  <div class="viewer-bar">
    <button class="viewer-back" id="viewer-back">
      <svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>
      Back to channels
    </button>
    <span class="viewer-title" id="viewer-title"></span>
  </div>
  <iframe id="viewer-frame" sandbox="allow-same-origin"></iframe>
</div>

<script>
  // Marquee dismiss
  document.getElementById('marquee-close').addEventListener('click', (e) => {{
    e.target.classList.add('fade');
    setTimeout(() => {{
      document.getElementById('marquee-wrap').classList.add('hidden');
    }}, 200);
  }});

  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {{
    tab.addEventListener('click', () => {{
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.season').forEach(s => s.classList.remove('active'));
      tab.classList.add('active');
      document.getElementById(tab.dataset.season).classList.add('active');
    }});
  }});

  // Category accordion
  document.querySelectorAll('.category-header').forEach(header => {{
    header.addEventListener('click', () => {{
      header.parentElement.classList.toggle('open');
    }});
  }});

  // Viewer
  const viewer = document.getElementById('viewer');
  const viewerFrame = document.getElementById('viewer-frame');
  const viewerTitle = document.getElementById('viewer-title');
  const viewerBack = document.getElementById('viewer-back');

  document.querySelectorAll('.channel-link').forEach(link => {{
    link.addEventListener('click', (e) => {{
      e.preventDefault();
      const name = link.textContent.trim();
      viewerTitle.innerHTML = '<span class="hash">#</span> ' + name.replace(/^#\\s*/, '');
      viewerFrame.src = link.getAttribute('href');
      viewer.classList.add('active');
      document.body.classList.add('viewing');
    }});
  }});

  viewerBack.addEventListener('click', () => {{
    viewer.classList.remove('active');
    document.body.classList.remove('viewing');
    viewerFrame.src = '';
  }});

  // Also close viewer with Escape key
  document.addEventListener('keydown', (e) => {{
    if (e.key === 'Escape' && viewer.classList.contains('active')) {{
      viewerBack.click();
    }}
  }});

  // Search
  const searchInput = document.getElementById('search');
  const noResults = document.getElementById('no-results');

  searchInput.addEventListener('input', () => {{
    const query = searchInput.value.toLowerCase().trim();
    let anyVisible = false;

    document.querySelectorAll('.season').forEach(season => {{
      let seasonHasResults = false;

      season.querySelectorAll('.category').forEach(cat => {{
        let catHasResults = false;

        cat.querySelectorAll('.channel-link').forEach(link => {{
          const text = link.textContent.toLowerCase();
          const match = !query || text.includes(query);
          link.style.display = match ? '' : 'none';
          if (match) catHasResults = true;
        }});

        cat.style.display = catHasResults ? '' : 'none';
        if (query && catHasResults) cat.classList.add('open');
        if (catHasResults) seasonHasResults = true;
      }});

      // Also search flat channel lists (The Stage)
      season.querySelectorAll(':scope > .channel-list .channel-link').forEach(link => {{
        const text = link.textContent.toLowerCase();
        const match = !query || text.includes(query);
        link.style.display = match ? '' : 'none';
        if (match) seasonHasResults = true;
      }});

      if (query) {{
        season.style.display = seasonHasResults ? 'block' : 'none';
        if (seasonHasResults) anyVisible = true;
      }} else {{
        season.style.display = '';
        anyVisible = true;
      }}
    }});

    // Show/hide tabs during search
    const tabsEl = document.querySelector('.tabs');
    if (query) {{
      tabsEl.style.display = 'none';
      document.querySelectorAll('.season').forEach(s => {{
        if (s.style.display !== 'none') s.classList.add('active');
      }});
    }} else {{
      tabsEl.style.display = '';
      // Restore active tab
      const activeTab = document.querySelector('.tab.active');
      document.querySelectorAll('.season').forEach(s => s.classList.remove('active'));
      document.getElementById(activeTab.dataset.season).classList.add('active');
    }}

    noResults.style.display = (!anyVisible && query) ? 'block' : 'none';
  }});
</script>

</body>
</html>"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated {OUTPUT_FILE}")

    # Print summary
    for sid in SEASON_ORDER:
        cfg = SEASONS[sid]
        total = 0
        for cat_name, folder_rel in cfg["categories"]:
            files = scan_html_files(folder_rel)
            count = len(files)
            total += count
            label = cat_name if cat_name else "Flat list"
            print(f"  {cfg['label']} / {label}: {count} files")
        print(f"  {cfg['label']} total: {total}")
        print()


if __name__ == "__main__":
    generate_index()
