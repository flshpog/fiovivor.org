import os
import re
import html
import hashlib
import asyncio
import tempfile
import subprocess
import discord
import aiohttp
import boto3
from io import BytesIO
from PIL import Image
from datetime import datetime

ARCHIVES_DIR = "archives"

# R2 config — loaded once at import time
_s3 = None
_bucket = None
_cdn_base = None


def _init_r2():
    global _s3, _bucket, _cdn_base
    if _s3 is not None:
        return
    _s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    _bucket = os.environ["R2_BUCKET"]
    _cdn_base = os.environ.get("CDN_BASE_URL", "").rstrip("/")


async def wipe_r2():
    """Delete all objects from the R2 bucket. Returns count of deleted objects."""
    _init_r2()
    def _do_wipe():
        s3 = _make_s3()
        count = 0
        pag = s3.get_paginator("list_objects_v2")
        for page in pag.paginate(Bucket=_bucket):
            objects = page.get("Contents", [])
            if not objects:
                continue
            delete_keys = [{"Key": obj["Key"]} for obj in objects]
            s3.delete_objects(Bucket=_bucket, Delete={"Objects": delete_keys})
            count += len(delete_keys)
        return count
    deleted = await asyncio.to_thread(_do_wipe)
    return deleted


def _content_hash(data: bytes) -> str:
    """Short hash for deduplication."""
    return hashlib.sha256(data).hexdigest()[:16]


async def _download(url: str) -> bytes:
    """Download a file from a URL."""
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()


def _convert_image_to_webp(data: bytes) -> bytes:
    """Convert image bytes to WebP."""
    img = Image.open(BytesIO(data))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGBA")
    else:
        img = img.convert("RGB")
    buf = BytesIO()
    img.save(buf, format="WEBP", quality=85)
    return buf.getvalue()


def _convert_video_to_webm(data: bytes, original_ext: str) -> bytes:
    """Convert video bytes to WebM using ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=f".{original_ext}", delete=False) as inp:
        inp.write(data)
        inp_path = inp.name
    out_path = inp_path.rsplit(".", 1)[0] + ".webm"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", inp_path,
                "-c:v", "libvpx", "-crf", "20", "-b:v", "1M",
                "-vf", "scale='min(720,iw)':-2",
                "-c:a", "libvorbis", "-b:a", "96k",
                "-f", "webm", out_path,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        for p in (inp_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


def _make_s3():
    """Create a fresh S3 client (thread-safe, one per call)."""
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def _upload_to_r2(data: bytes, key: str, content_type: str) -> str:
    """Upload bytes to R2 and return CDN URL. Retries on failure."""
    _init_r2()
    import time
    for attempt in range(3):
        try:
            s3 = _make_s3()
            try:
                s3.head_object(Bucket=_bucket, Key=key)
                return f"{_cdn_base}/{key}"  # Already uploaded
            except s3.exceptions.ClientError:
                pass
            s3.put_object(
                Bucket=_bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            return f"{_cdn_base}/{key}"
        except Exception as e:
            if attempt < 2:
                print(f"    [R2] Upload failed for {key}, retrying ({attempt + 1}/3): {e}")
                time.sleep(2 ** attempt)
            else:
                raise


async def _process_image(url: str, filename: str) -> str:
    """Download image, convert to webp, upload to R2, return CDN URL."""
    data = await _download(url)
    h = _content_hash(data)
    name = os.path.splitext(filename)[0]
    key = f"images/{h}-{name}.webp"

    webp_data = await asyncio.to_thread(_convert_image_to_webp, data)
    cdn_url = await asyncio.to_thread(_upload_to_r2, webp_data, key, "image/webp")
    return cdn_url


async def _process_video(url: str, filename: str) -> str:
    """Download video, convert to webm, upload to R2, return CDN URL."""
    data = await _download(url)
    h = _content_hash(data)
    name = os.path.splitext(filename)[0]
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "mp4"
    key = f"videos/{h}-{name}.webm"

    webm_data = await asyncio.to_thread(_convert_video_to_webm, data, ext)
    cdn_url = await asyncio.to_thread(_upload_to_r2, webm_data, key, "video/webm")
    return cdn_url


async def _process_avatar(url: str, user_id: int) -> str:
    """Download avatar, convert to webp, upload to R2."""
    data = await _download(url)
    h = _content_hash(data)
    key = f"avatars/{user_id}-{h}.webp"

    webp_data = await asyncio.to_thread(_convert_image_to_webp, data)
    cdn_url = await asyncio.to_thread(_upload_to_r2, webp_data, key, "image/webp")
    return cdn_url


def _role_color(member):
    """Get the top role color hex for a member, or default grey."""
    if member and hasattr(member, "top_role") and member.top_role and member.top_role.color.value != 0:
        return f"#{member.top_role.color.value:06x}"
    return "#dcddde"


def _format_timestamp(dt):
    return dt.strftime("%m/%d/%Y %I:%M %p")


def _escape(text, guild_data=None):
    """HTML-escape text, resolve Discord mentions/emojis, and convert markdown to HTML."""
    text = html.escape(text)

    # Resolve Discord mentions/emojis before markdown processing
    if guild_data:
        members, roles, channels, emojis = guild_data

        # User mentions: <@123> or <@!123>
        def replace_user(m):
            uid = int(m.group(1))
            name = members.get(uid, f"Unknown User")
            return f'<span class="mention">@{html.escape(name)}</span>'
        text = re.sub(r"&lt;@!?(\d+)&gt;", replace_user, text)

        # Role mentions: <@&123>
        def replace_role(m):
            rid = int(m.group(1))
            role_name, role_color = roles.get(rid, ("Unknown Role", "#99aab5"))
            return f'<span class="mention" style="color:{role_color};background:rgba({int(role_color[1:3],16)},{int(role_color[3:5],16)},{int(role_color[5:7],16)},0.1)">@{html.escape(role_name)}</span>'
        text = re.sub(r"&lt;@&amp;(\d+)&gt;", replace_role, text)

        # Channel mentions: <#123>
        def replace_channel(m):
            cid = int(m.group(1))
            name = channels.get(cid, "deleted-channel")
            return f'<span class="mention">#{html.escape(name)}</span>'
        text = re.sub(r"&lt;#(\d+)&gt;", replace_channel, text)

        # Custom emojis: <:name:123> or <a:name:123>
        def replace_emoji(m):
            animated = m.group(1) == "a"
            emoji_name = m.group(2)
            emoji_id = m.group(3)
            ext = "gif" if animated else "webp"
            url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=48"
            return f'<img class="custom-emoji" src="{url}" alt=":{emoji_name}:" title=":{emoji_name}:">'
        text = re.sub(r"&lt;(a?):(\w+):(\d+)&gt;", replace_emoji, text)

    # Discord timestamps: <t:1234567890:R>, <t:1234567890:F>, <t:1234567890>, etc.
    def replace_timestamp(m):
        try:
            ts = int(m.group(1))
            style = m.group(2) or "f"
            dt = datetime.utcfromtimestamp(ts)
            if style == "t":
                formatted = dt.strftime("%I:%M %p").lstrip("0")
            elif style == "T":
                formatted = dt.strftime("%I:%M:%S %p").lstrip("0")
            elif style == "d":
                formatted = dt.strftime("%m/%d/%Y")
            elif style == "D":
                formatted = dt.strftime("%B %d, %Y")
            elif style == "F":
                formatted = dt.strftime("%A, %B %d, %Y %I:%M %p").replace("  ", " ")
            elif style == "R":
                formatted = dt.strftime("%B %d, %Y %I:%M %p")
            else:  # "f" (default)
                formatted = dt.strftime("%B %d, %Y %I:%M %p")
            return f'<span class="timestamp-inline">{formatted}</span>'
        except (ValueError, OSError):
            return m.group(0)
    text = re.sub(r"&lt;t:(\d+)(?::([tTdDfFR]))?&gt;", replace_timestamp, text)

    # Markdown — extract code first so markup inside it isn't processed
    # Placeholder system to protect code blocks from further processing
    placeholders = []

    def placeholder(m):
        idx = len(placeholders)
        placeholders.append(m.group(0))
        return f"\x00PH{idx}\x00"

    # Code blocks (``` ```)
    def code_block(m):
        code = m.group(1)
        idx = len(placeholders)
        placeholders.append(f'<pre><code>{code}</code></pre>')
        return f"\x00PH{idx}\x00"
    text = re.sub(r"```(?:\w+)?\n?([\s\S]*?)```", code_block, text)

    # Inline code (` `)
    def inline_code(m):
        code = m.group(1)
        idx = len(placeholders)
        placeholders.append(f'<code>{code}</code>')
        return f"\x00PH{idx}\x00"
    text = re.sub(r"`([^`]+)`", inline_code, text)

    # Block quotes (>>> and >)
    # >>> makes everything after it a single blockquote
    text = re.sub(r"^&gt;&gt;&gt; ?([\s\S]+)", r'<div class="blockquote">\1</div>', text)
    # > at start of line — merge consecutive > lines into one blockquote
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

    # Headers (# ## ###)
    text = re.sub(r"^### (.+)$", r'<strong style="font-size:1em">\1</strong>', text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r'<strong style="font-size:1.25em">\1</strong>', text, flags=re.MULTILINE)
    text = re.sub(r"^# (.+)$", r'<strong style="font-size:1.5em">\1</strong>', text, flags=re.MULTILINE)

    # Spoilers ||text||
    text = re.sub(r"\|\|(.+?)\|\|", r'<span class="spoiler">\1</span>', text)

    # Bold italic ***text***
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    # Bold **text**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # Italic *text*
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    # Underline __text__
    text = re.sub(r"__(.+?)__", r"<u>\1</u>", text)
    # Italic _text_ — only at word boundaries (Discord-style)
    text = re.sub(r"(?<![a-zA-Z0-9_])_([^_\n]+?)_(?![a-zA-Z0-9_])", r"<em>\1</em>", text)
    # Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # Newlines
    text = text.replace("\n", "<br>")

    # Restore placeholders
    for i, ph in enumerate(placeholders):
        text = text.replace(f"\x00PH{i}\x00", ph)

    return text


async def build_guild_data(guild):
    """Build lookup dicts for mention resolution. Call once and reuse across channels."""
    print(f"  [guild-data] Fetching members...")
    members = {}
    async for member in guild.fetch_members(limit=None):
        members[member.id] = member.display_name
    print(f"  [guild-data] {len(members)} members loaded")
    roles = {}
    for role in guild.roles:
        color = f"#{role.color.value:06x}" if role.color.value != 0 else "#99aab5"
        roles[role.id] = (role.name, color)
    print(f"  [guild-data] {len(roles)} roles loaded")
    channels_map = {}
    for ch in guild.channels:
        channels_map[ch.id] = ch.name
    print(f"  [guild-data] {len(channels_map)} channels loaded")
    return (members, roles, channels_map, None)


async def archive_channel(channel, progress_callback=None, output_path=None, guild_data=None):
    """Fetch all messages from a channel and write an HTML archive. Returns (count, filepath)."""
    _init_r2()
    os.makedirs(ARCHIVES_DIR, exist_ok=True)

    print(f"  [#{channel.name}] Fetching messages...")
    messages = []
    count = 0
    async for msg in channel.history(limit=None, oldest_first=True):
        messages.append(msg)
        count += 1
        if count % 500 == 0:
            print(f"  [#{channel.name}] {count:,} messages fetched...")
    print(f"  [#{channel.name}] {len(messages):,} messages total")

    # --- Pre-process all media in parallel ---
    # Maps: original_url -> cdn_url
    media_map = {}

    # Collect all media tasks
    tasks = {}

    # Avatars (deduplicate by user ID)
    seen_avatars = {}
    for msg in messages:
        uid = msg.author.id
        if uid not in seen_avatars and msg.author.display_avatar:
            avatar_url = msg.author.display_avatar.url
            seen_avatars[uid] = avatar_url
            tasks[avatar_url] = _process_avatar(avatar_url, uid)

    # Attachments
    for msg in messages:
        for att in msg.attachments:
            ct = att.content_type or ""
            if att.url not in tasks:
                if ct.startswith("image/"):
                    tasks[att.url] = _process_image(att.url, att.filename)
                elif ct.startswith("video/"):
                    tasks[att.url] = _process_video(att.url, att.filename)
            # audio and other files: keep original Discord URL (no conversion needed)

    # Embed images/videos (tenor gifs, image embeds, etc.)
    for msg in messages:
        for embed in msg.embeds:
            if embed.type == "gifv" and embed.video and embed.video.url:
                url = embed.video.url
                if url not in tasks:
                    tasks[url] = _process_video(url, "gifv.mp4")
            elif embed.type == "image" and embed.thumbnail and embed.thumbnail.url:
                url = embed.thumbnail.url
                if url not in tasks:
                    tasks[url] = _process_image(url, "embed-image.png")
            else:
                if embed.image and embed.image.url and embed.image.url not in tasks:
                    tasks[embed.image.url] = _process_image(embed.image.url, "embed-img.png")
                if embed.thumbnail and embed.thumbnail.url and embed.thumbnail.url not in tasks:
                    tasks[embed.thumbnail.url] = _process_image(embed.thumbnail.url, "embed-thumb.png")

    # Forwarded message attachments
    for msg in messages:
        if hasattr(msg, "message_snapshots") and msg.message_snapshots:
            for snap in msg.message_snapshots:
                for att in snap.attachments:
                    ct = att.content_type or ""
                    if att.url not in tasks:
                        if ct.startswith("image/"):
                            tasks[att.url] = _process_image(att.url, att.filename)
                        elif ct.startswith("video/"):
                            tasks[att.url] = _process_video(att.url, att.filename)

    # Run all downloads/conversions/uploads concurrently
    if tasks:
        urls = list(tasks.keys())
        coros = list(tasks.values())
        total = len(coros)
        print(f"  [#{channel.name}] Processing {total} media items...")
        results = []
        # Process in batches to avoid overwhelming connections
        batch_size = 10
        for i in range(0, total, batch_size):
            batch = [asyncio.wait_for(c, timeout=150) for c in coros[i:i + batch_size]]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            results.extend(batch_results)
            done = min(i + batch_size, total)
            print(f"  [#{channel.name}] Media: {done}/{total}")
            if progress_callback:
                await progress_callback(f"Processing media: {done}/{total}")

        failures = 0
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                media_map[url] = url  # fallback to original URL on failure
                failures += 1
            else:
                media_map[url] = result
        if failures:
            print(f"  [#{channel.name}] {failures} media items failed (using fallback URLs)")
    else:
        print(f"  [#{channel.name}] No media to process")

    guild = channel.guild

    if guild_data is None:
        guild_data = await build_guild_data(guild)

    # Also add message authors not in the member list (left the server)
    members = guild_data[0]
    for msg in messages:
        if msg.author.id not in members:
            display = msg.author.display_name if hasattr(msg.author, "display_name") else str(msg.author)
            members[msg.author.id] = display

    if output_path:
        filepath = output_path
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
    else:
        filepath = os.path.join(ARCHIVES_DIR, f"{guild.id}-{channel.id}.html")

    print(f"  [#{channel.name}] Writing HTML to {filepath}")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(_render_html(channel, messages, media_map, guild_data))

    print(f"  [#{channel.name}] Done — {len(messages):,} messages archived")
    return len(messages), filepath


def _render_html(channel, messages, media_map, guild_data=None):
    guild = channel.guild
    parts = []

    def cdn(url):
        """Look up CDN URL from media map, fallback to original."""
        return media_map.get(url, url)

    parts.append(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>#{channel.name} — {html.escape(guild.name)}</title>
<style>
{_css()}
</style>
</head>
<body>
<div class="container">
<header>
    <h1><span class="hash">#</span>{html.escape(channel.name)}</h1>
    <p class="meta">{html.escape(guild.name)} &middot; {len(messages):,} messages archived</p>
    {f'<p class="topic">{html.escape(channel.topic)}</p>' if channel.topic else ''}
</header>
<div class="messages">
""")

    prev_author = None
    prev_time = None

    for msg in messages:
        same_group = (
            prev_author == msg.author.id
            and prev_time
            and (msg.created_at - prev_time).total_seconds() < 420
        )

        if not same_group:
            if prev_author is not None:
                parts.append("</div>")

            avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else ""
            avatar_cdn = cdn(avatar_url) if avatar_url else ""
            color = _role_color(msg.author if not isinstance(msg.author, dict) else None)
            display_name = html.escape(msg.author.display_name if hasattr(msg.author, "display_name") else str(msg.author))
            username = html.escape(str(msg.author))
            timestamp = _format_timestamp(msg.created_at)

            bot_tag = ' <span class="bot-tag">BOT</span>' if msg.author.bot else ""

            parts.append(f"""<div class="msg-group">
    <div class="msg-header">
        <img class="avatar" src="{avatar_cdn}" alt="" loading="lazy">
        <span class="author" style="color:{color}">{display_name}{bot_tag}</span>
        <span class="username">@{username}</span>
        <span class="timestamp">{timestamp}</span>
    </div>""")

        parts.append('    <div class="msg">')

        # Forwarded messages
        is_forward = (
            msg.reference
            and hasattr(msg.reference, "type")
            and msg.reference.type == discord.MessageReferenceType.forward
            and hasattr(msg, "message_snapshots")
            and msg.message_snapshots
        )

        if is_forward:
            parts.append('        <div class="forwarded">')
            parts.append('            <div class="forwarded-header">Forwarded Message</div>')
            for snap in msg.message_snapshots:
                if snap.content:
                    parts.append(f'            <div class="content">{_escape(snap.content, guild_data)}</div>')
                for att in snap.attachments:
                    ct = att.content_type or ""
                    if ct.startswith("image/"):
                        parts.append(f'            <div class="attachment"><img src="{cdn(att.url)}" alt="{html.escape(att.filename)}" loading="lazy"></div>')
                    elif ct.startswith("video/"):
                        parts.append(f'            <div class="attachment"><video controls preload="metadata" src="{cdn(att.url)}" style="max-width:400px;max-height:300px;border-radius:4px;margin:4px 0;"></video></div>')
                    else:
                        parts.append(f'            <div class="attachment"><a href="{att.url}" target="_blank">{html.escape(att.filename)}</a></div>')
                for embed in snap.embeds:
                    if embed.image:
                        parts.append(f'            <img class="embed-img" src="{cdn(embed.image.url)}" loading="lazy">')
                    if embed.description:
                        parts.append(f'            <div class="embed-desc">{_escape(embed.description, guild_data)}</div>')
            parts.append('        </div>')
        else:
            # Reply reference
            if msg.reference and msg.reference.resolved:
                ref = msg.reference.resolved
                if isinstance(ref, discord.Message):
                    ref_content = ref.content[:80] + ("..." if len(ref.content) > 80 else "")
                    parts.append(f'        <div class="reply"><span class="reply-author">{html.escape(str(ref.author))}</span> {_escape(ref_content, guild_data)}</div>')

            if msg.content:
                parts.append(f"        <div class=\"content\">{_escape(msg.content, guild_data)}</div>")

        # Attachments
        for att in msg.attachments:
            ct = att.content_type or ""
            if ct.startswith("image/"):
                parts.append(f'        <div class="attachment"><img src="{cdn(att.url)}" alt="{html.escape(att.filename)}" loading="lazy"></div>')
            elif ct.startswith("video/"):
                parts.append(f'        <div class="attachment"><video controls preload="metadata" src="{cdn(att.url)}" style="max-width:400px;max-height:300px;border-radius:4px;margin:4px 0;"></video></div>')
            elif ct.startswith("audio/"):
                parts.append(f'        <div class="attachment"><audio controls src="{att.url}" style="margin:4px 0;"></audio></div>')
            else:
                parts.append(f'        <div class="attachment"><a href="{att.url}" target="_blank">{html.escape(att.filename)}</a></div>')

        # Stickers
        for sticker in msg.stickers:
            sticker_url = f"https://media.discordapp.net/stickers/{sticker.id}.webp?size=160"
            parts.append(f'        <div class="attachment"><img src="{sticker_url}" alt="{html.escape(sticker.name)}" title="{html.escape(sticker.name)}" loading="lazy" style="max-width:160px;max-height:160px;"></div>')

        # Embeds
        for embed in msg.embeds:
            if embed.type == "gifv" and embed.video and embed.video.url:
                parts.append(f'        <div class="attachment"><video autoplay loop muted playsinline src="{cdn(embed.video.url)}" style="max-width:400px;max-height:300px;border-radius:4px;margin:4px 0;"></video></div>')
                continue
            if embed.type == "image" and embed.thumbnail and embed.thumbnail.url:
                parts.append(f'        <div class="attachment"><img src="{cdn(embed.thumbnail.url)}" loading="lazy" style="max-width:400px;max-height:300px;border-radius:4px;margin:4px 0;"></div>')
                continue

            embed_color = f"#{embed.color.value:06x}" if embed.color and embed.color.value else "#4f545c"
            parts.append(f'        <div class="embed" style="border-left-color:{embed_color}">')
            if embed.author:
                author_name = html.escape(embed.author.name) if embed.author.name else ""
                if embed.author.icon_url:
                    parts.append(f'            <div class="embed-author"><img class="embed-author-icon" src="{embed.author.icon_url}" alt="">{author_name}</div>')
                elif author_name:
                    parts.append(f'            <div class="embed-author">{author_name}</div>')
            if embed.title:
                title_text = html.escape(embed.title)
                if embed.url:
                    parts.append(f'            <div class="embed-title"><a href="{embed.url}">{title_text}</a></div>')
                else:
                    parts.append(f'            <div class="embed-title">{title_text}</div>')
            if embed.description:
                parts.append(f'            <div class="embed-desc">{_escape(embed.description, guild_data)}</div>')
            if embed.fields:
                parts.append('            <div class="embed-fields">')
                for field in embed.fields:
                    inline = " inline" if field.inline else ""
                    parts.append(f'                <div class="embed-field{inline}"><div class="embed-field-name">{html.escape(field.name)}</div><div class="embed-field-value">{_escape(field.value, guild_data)}</div></div>')
                parts.append("            </div>")
            if embed.image:
                parts.append(f'            <img class="embed-img" src="{cdn(embed.image.url)}" loading="lazy">')
            if embed.thumbnail:
                parts.append(f'            <img class="embed-thumb" src="{cdn(embed.thumbnail.url)}" loading="lazy">')
            if embed.video and embed.video.url:
                parts.append(f'            <video class="embed-img" controls preload="metadata" src="{cdn(embed.video.url)}"></video>')
            if embed.footer:
                footer_text = html.escape(embed.footer.text) if embed.footer.text else ""
                parts.append(f'            <div class="embed-footer">{footer_text}</div>')
            parts.append("        </div>")

        # Reactions
        if msg.reactions:
            parts.append('        <div class="reactions">')
            for reaction in msg.reactions:
                parts.append(f'            <span class="reaction">{reaction.emoji} <span class="reaction-count">{reaction.count}</span></span>')
            parts.append("        </div>")

        parts.append("    </div>")

        prev_author = msg.author.id
        prev_time = msg.created_at

    if prev_author is not None:
        parts.append("</div>")

    parts.append("""</div>
</div>
</body>
</html>""")

    return "\n".join(parts)


def _css():
    return """
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    background: #36393f;
    color: #dcddde;
    font-family: 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 15px;
    line-height: 1.375;
}

.container {
    max-width: 900px;
    margin: 0 auto;
}

header {
    padding: 24px 16px;
    border-bottom: 1px solid #42454a;
    background: #2f3136;
    position: sticky;
    top: 0;
    z-index: 10;
}

header h1 {
    font-size: 20px;
    font-weight: 600;
    color: #fff;
}

header .hash {
    color: #72767d;
    margin-right: 2px;
}

header .meta {
    color: #72767d;
    font-size: 13px;
    margin-top: 4px;
}

header .topic {
    color: #96989d;
    font-size: 13px;
    margin-top: 4px;
}

.messages {
    padding: 16px 0;
}

.msg-group {
    padding: 4px 16px 4px 72px;
    position: relative;
    margin-top: 12px;
}

.msg-group:hover {
    background: #32353b;
}

.msg-header {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 2px;
}

.avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    position: absolute;
    left: 16px;
    top: 4px;
    object-fit: cover;
}

.author {
    font-weight: 600;
    font-size: 15px;
    cursor: default;
}

.username {
    color: #72767d;
    font-size: 12px;
}

.bot-tag {
    background: #5865f2;
    color: #fff;
    font-size: 10px;
    padding: 1px 5px;
    border-radius: 3px;
    font-weight: 600;
    vertical-align: middle;
    margin-left: 4px;
}

.timestamp {
    color: #72767d;
    font-size: 12px;
    margin-left: auto;
}

.msg {
    padding: 2px 0;
}

.content {
    word-wrap: break-word;
    white-space: pre-wrap;
}

.content code {
    background: #2f3136;
    padding: 2px 4px;
    border-radius: 3px;
    font-size: 13px;
    font-family: 'Consolas', 'Courier New', monospace;
}

.content pre {
    background: #2f3136;
    padding: 8px;
    border-radius: 4px;
    margin: 4px 0;
    overflow-x: auto;
}

.content pre code {
    padding: 0;
    background: none;
}

.content strong { color: #fff; }

.reply {
    font-size: 13px;
    color: #72767d;
    padding: 2px 0 4px 0;
    border-left: 2px solid #4f545c;
    padding-left: 8px;
    margin-bottom: 4px;
}

.reply-author {
    font-weight: 600;
    color: #b9bbbe;
}

.attachment img {
    max-width: 400px;
    max-height: 300px;
    border-radius: 4px;
    margin: 4px 0;
}

.attachment a {
    color: #00aff4;
    text-decoration: none;
}

.attachment a:hover { text-decoration: underline; }

.embed {
    border-left: 4px solid #4f545c;
    background: #2f3136;
    padding: 8px 12px;
    border-radius: 4px;
    margin: 4px 0;
    max-width: 520px;
}

.embed-title {
    font-weight: 600;
    color: #fff;
    margin-bottom: 4px;
}

.embed-title a { color: #00aff4; text-decoration: none; }
.embed-title a:hover { text-decoration: underline; }

.embed-desc {
    font-size: 14px;
    color: #dcddde;
}

.embed-author {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 4px;
}

.embed-author-icon {
    width: 20px;
    height: 20px;
    border-radius: 50%;
}

.embed-fields {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 6px;
}

.embed-field {
    width: 100%;
}

.embed-field.inline {
    width: calc(33% - 8px);
    min-width: 120px;
}

.embed-field-name {
    font-size: 13px;
    font-weight: 600;
    color: #b9bbbe;
    margin-bottom: 2px;
}

.embed-field-value {
    font-size: 14px;
    color: #dcddde;
}

.embed-img {
    max-width: 100%;
    max-height: 300px;
    border-radius: 4px;
    margin-top: 8px;
}

.embed-thumb {
    max-width: 80px;
    max-height: 80px;
    border-radius: 4px;
    margin-top: 8px;
    float: right;
}

.embed-footer {
    font-size: 12px;
    color: #72767d;
    margin-top: 6px;
}

.reactions {
    display: flex;
    gap: 4px;
    margin-top: 4px;
    flex-wrap: wrap;
}

.reaction {
    background: #2f3136;
    border: 1px solid #4f545c;
    border-radius: 8px;
    padding: 2px 8px;
    font-size: 14px;
    display: flex;
    align-items: center;
    gap: 4px;
}

.reaction-count {
    font-size: 12px;
    color: #b9bbbe;
}

.timestamp-inline {
    background: rgba(79, 84, 92, 0.48);
    padding: 0 3px;
    border-radius: 3px;
    color: #fff;
    font-size: 14px;
}

.forwarded {
    border: 1px solid #4f545c;
    border-radius: 8px;
    padding: 8px 12px;
    margin: 4px 0;
    background: #2f3136;
    max-width: 520px;
}

.forwarded-header {
    font-size: 12px;
    color: #72767d;
    font-weight: 600;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

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

@media (max-width: 600px) {
    .msg-group { padding-left: 56px; }
    .avatar { width: 32px; height: 32px; }
    .attachment img { max-width: 100%; }
}
"""
