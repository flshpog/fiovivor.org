"""
Re-process existing archive HTML files to fix markdown rendering.
Injects missing CSS and re-renders content divs with improved markdown.

Run from the repo root:
    python archiverbot/reprocess.py
"""

import os
import re
import glob

ARCHIVE_DIRS = [
    os.path.join(os.path.dirname(__file__), "..", "fiovivor 8 archive"),
    os.path.join(os.path.dirname(__file__), "..", "fiovivor 9 archive"),
]

# CSS to inject
EXTRA_CSS = """
.blockquote {
    border-left: 4px solid #4f545c;
    padding-left: 12px;
    margin: 2px 0;
}

.spoiler {
    background: #202225;
    color: transparent;
    border-radius: 3px;
    padding: 0 4px;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
}

.spoiler:hover {
    background: rgba(79, 84, 92, 0.48);
    color: #dcddde;
}

.mention {
    background: rgba(88, 101, 242, 0.15);
    color: #dee0fc;
    padding: 0 3px;
    border-radius: 3px;
    font-weight: 500;
    cursor: default;
}

.custom-emoji {
    width: 22px;
    height: 22px;
    vertical-align: -0.4em;
    object-fit: contain;
}
"""


def reprocess_content(text):
    """
    Takes the inner HTML of a <div class="content"> and re-renders markdown.
    The text is already HTML-escaped from the original archiver.
    We need to undo the old broken markdown, then re-apply correctly.
    """
    # Undo old markdown conversions so we can redo them properly
    # The old code applied: bold, italic (*), italic (_), strikethrough, inline code, code blocks, <br>
    # We need to reverse these then reapply

    # Undo <br> back to newlines
    text = text.replace("<br>", "\n")

    # Undo old italic from underscore (the broken one) — <em> from _ patterns
    # Can't easily distinguish which <em> came from * vs _ so we leave <em> alone

    # Undo old code blocks
    text = re.sub(r'<pre><code>([\s\S]*?)</code></pre>', lambda m: '```\n' + m.group(1) + '```', text)
    # Undo old inline code
    text = re.sub(r'<code>([^<]+?)</code>', lambda m: '`' + m.group(1) + '`', text)
    # Undo old bold
    text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text)
    # Undo old italic
    text = re.sub(r'<em>(.*?)</em>', r'*\1*', text)
    # Undo old strikethrough
    text = re.sub(r'<s>(.*?)</s>', r'~~\1~~', text)

    # Now re-apply the improved markdown processing
    # (Same logic as _escape in archiver.py, but without guild_data for mention resolution)

    placeholders = []

    # Code blocks
    def code_block(m):
        code = m.group(1)
        idx = len(placeholders)
        placeholders.append(f'<pre><code>{code}</code></pre>')
        return f"\x00PH{idx}\x00"
    text = re.sub(r"```(?:\w+)?\n?([\s\S]*?)```", code_block, text)

    # Inline code
    def inline_code(m):
        code = m.group(1)
        idx = len(placeholders)
        placeholders.append(f'<code>{code}</code>')
        return f"\x00PH{idx}\x00"
    text = re.sub(r"`([^`]+)`", inline_code, text)

    # Block quotes
    text = re.sub(r"^&gt;&gt;&gt; ?([\s\S]+)", r'<div class="blockquote">\1</div>', text)

    def merge_quotes(text):
        lines = text.split("\n")
        result = []
        quote_buf = []
        for line in lines:
            m = re.match(r"^&gt; ?(.*)$", line)
            if m:
                quote_buf.append(m.group(1))
            else:
                if quote_buf:
                    result.append('<div class="blockquote">' + "<br>".join(quote_buf) + "</div>")
                    quote_buf = []
                result.append(line)
        if quote_buf:
            result.append('<div class="blockquote">' + "<br>".join(quote_buf) + "</div>")
        return "\n".join(result)
    text = merge_quotes(text)

    # Headers
    text = re.sub(r"^### (.+)$", r'<strong style="font-size:1em">\1</strong>', text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r'<strong style="font-size:1.25em">\1</strong>', text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$", r'<strong style="font-size:1.5em">\1</strong>', text, flags=re.MULTILINE)

    # Spoilers
    text = re.sub(r"\|\|(.+?)\|\|", r'<span class="spoiler">\1</span>', text)

    # Bold italic
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    # Bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic *
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    # Underline __
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    # Italic _ (word boundary only)
    text = re.sub(r"(?<![a-zA-Z0-9_])_([^_\n]+?)_(?![a-zA-Z0-9_])", r"<em>\1</em>", text)
    # Strikethrough
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # Custom emojis that are still in raw form
    def replace_emoji(m):
        animated = m.group(1) == "a"
        emoji_name = m.group(2)
        emoji_id = m.group(3)
        ext = "gif" if animated else "webp"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=48"
        return f'<img class="custom-emoji" src="{url}" alt=":{emoji_name}:" title=":{emoji_name}:">'
    text = re.sub(r"&lt;(a?):(\w+):(\d+)&gt;", replace_emoji, text)

    # Newlines
    text = text.replace("\n", "<br>")

    # Restore placeholders
    for i, ph in enumerate(placeholders):
        text = text.replace(f"\x00PH{i}\x00", ph)

    return text


def process_file(filepath):
    """Re-process a single archive HTML file."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    modified = False

    # Inject extra CSS if not already present
    if ".blockquote" not in content and "</style>" in content:
        content = content.replace("</style>", EXTRA_CSS + "\n</style>")
        modified = True

    # Re-process content divs
    def replace_content(m):
        nonlocal modified
        inner = m.group(1)
        new_inner = reprocess_content(inner)
        if new_inner != inner:
            modified = True
        return f'<div class="content">{new_inner}</div>'

    content = re.sub(
        r'<div class="content">([\s\S]*?)</div>',
        replace_content,
        content,
    )

    if modified:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return modified


def main():
    total = 0
    updated = 0

    for archive_dir in ARCHIVE_DIRS:
        archive_dir = os.path.normpath(archive_dir)
        if not os.path.isdir(archive_dir):
            print(f"Skipping {archive_dir} (not found)")
            continue

        for root, dirs, files in os.walk(archive_dir):
            for fname in files:
                if not fname.endswith(".html"):
                    continue
                filepath = os.path.join(root, fname)
                total += 1
                try:
                    if process_file(filepath):
                        updated += 1
                        print(f"  Updated: {os.path.relpath(filepath, archive_dir)}")
                except Exception as e:
                    print(f"  FAILED: {filepath}: {e}")

    print(f"\nDone. {updated}/{total} files updated.")


if __name__ == "__main__":
    main()
