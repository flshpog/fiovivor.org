import os
import shutil
from typing import Optional
import discord
from discord import app_commands
from dotenv import load_dotenv
from archiver import archive_channel, wipe_r2, build_guild_data

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class ArchiverBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        pass


bot = ArchiverBot()


@bot.event
async def on_ready():
    # Sync commands to every guild the bot is in (instant, no 1hr wait)
    for guild in bot.guilds:
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user} (ID: {bot.user.id}) — commands synced")


@bot.tree.command(name="archive", description="Archive all messages in a channel to an HTML file")
@app_commands.describe(channel="The channel to archive")
async def archive(interaction: discord.Interaction, channel: discord.TextChannel):
    # Only allow users with manage_guild to archive
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need **Manage Server** permission to use this.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        async def progress(status):
            await interaction.edit_original_response(content=status)

        await interaction.edit_original_response(content=f"Fetching messages from {channel.mention}...")
        count, filepath = await archive_channel(channel, progress_callback=progress)
        file = discord.File(filepath, filename=f"{channel.name}-archive.html")
        await interaction.followup.send(
            f"Archived **{count:,}** messages from {channel.mention}.",
            file=file,
            ephemeral=True,
        )
    except Exception as e:
        await interaction.followup.send(f"Archive failed: {e}", ephemeral=True)


@bot.tree.command(name="massarchive", description="Archive every channel in a category to separate HTML files")
@app_commands.describe(category="The category to archive all channels from")
async def massarchive(interaction: discord.Interaction, category: discord.CategoryChannel):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need **Manage Server** permission to use this.", ephemeral=True)
        return

    text_channels = [ch for ch in category.channels if isinstance(ch, discord.TextChannel)]
    if not text_channels:
        await interaction.response.send_message("No text channels found in that category.", ephemeral=True)
        return

    # Sort by position (top to bottom in Discord)
    text_channels.sort(key=lambda ch: ch.position)

    await interaction.response.send_message(
        f"Starting mass archive of **{category.name}** ({len(text_channels)} channels)...",
        ephemeral=True,
    )

    # Use a regular message in the channel for progress (interaction tokens expire after 15 min)
    dest = interaction.channel
    progress_msg = await dest.send(
        f"Archiving **{category.name}** — 0/{len(text_channels)} channels..."
    )

    total_messages = 0
    files = []
    failed = []

    for i, channel in enumerate(text_channels):
        try:
            try:
                await progress_msg.edit(
                    content=f"Archiving **{channel.name}** ({i + 1}/{len(text_channels)})..."
                )
            except Exception:
                pass  # don't fail the archive if progress update fails
            count, filepath = await archive_channel(channel)
            total_messages += count
            files.append((channel.name, filepath, count))
        except Exception as e:
            failed.append((channel.name, str(e)))

    summary = f"Archived **{len(files)}/{len(text_channels)}** channels from **{category.name}** ({total_messages:,} total messages)."
    if failed:
        summary += "\n\nFailed channels:\n" + "\n".join(f"- #{name}: {err}" for name, err in failed)

    try:
        await progress_msg.edit(content=summary)
    except Exception:
        await dest.send(summary)

    for name, filepath, count in files:
        try:
            file = discord.File(filepath, filename=f"{name}-archive.html")
            await dest.send(f"**#{name}** — {count:,} messages", file=file)
        except Exception:
            await dest.send(f"Failed to upload **#{name}** (file may be too large)")


@bot.tree.command(name="wipe", description="Delete all media from R2 and local archives")
async def wipe(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need **Manage Server** permission to use this.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    try:
        # Wipe R2 bucket
        deleted = await wipe_r2()

        # Wipe local archives
        if os.path.exists("archives"):
            shutil.rmtree("archives")

        await interaction.followup.send(
            f"Wiped **{deleted}** objects from R2 and cleared local archives.",
            ephemeral=True,
        )
    except Exception as e:
        await interaction.followup.send(f"Wipe failed: {e}", ephemeral=True)


# Base path for the website repo
SITE_ROOT = r"C:\Users\cash\Documents\GitHub\fiovivor.org"

# Category ID → subfolder under SITE_ROOT
CATEGORY_MAP = {
    # The Stage (cross-season)
    1414013872528031967: "the stage",

    # Season 10
    1479952641319764198: "fiovivor 10 archive/in-game information",
    1414016817923362888: "fiovivor 10 archive/audience seating",
    1479953040730751147: "fiovivor 10 archive/confessionals",
    1479979983337422868: "fiovivor 10 archive/submissions",
    1479952849726210179: "fiovivor 10 archive/tribal councils",
    1479986085995086025: "fiovivor 10 archive/alliances",
    1487540482203713639: "fiovivor 10 archive/alliances",
    1487647582208528585: "fiovivor 10 archive/alliances",
    1482026521689329695: "fiovivor 10 archive/alliances",
    1491945072726376458: "fiovivor 10 archive/alliances",
    1483245615143190591: "fiovivor 10 archive/other channels",

    # Season 9
    1458583928737632555: "fiovivor 9 archive/in-game information",
    1459671571881787432: "fiovivor 9 archive/tribal councils",
    1459094038815703121: "fiovivor 9 archive/confessionals",

    # Season 8
    1414007541041729586: "fiovivor 8 archive/in-game information",
    1430351956005753015: "fiovivor 8 archive/tribal councils",
    1414014197049724928: "fiovivor 8 archive/confessionals",
}


@bot.tree.command(name="rearchiveall", description="Re-archive ALL mapped categories and save to the website folders")
async def rearchiveall(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need **Manage Server** permission to use this.", ephemeral=True)
        return

    await interaction.response.send_message("Starting full re-archive...", ephemeral=True)

    dest = interaction.channel
    guild = interaction.guild

    # Build guild data once for all channels
    progress_msg = await dest.send("Building member/role/channel data...")
    gd = await build_guild_data(guild)

    # Find all matching categories
    matched = []
    for cat in guild.categories:
        if cat.id in CATEGORY_MAP:
            folder = CATEGORY_MAP[cat.id]
            text_channels = [ch for ch in cat.channels if isinstance(ch, discord.TextChannel)]
            text_channels.sort(key=lambda ch: ch.position)
            matched.append((cat.name, folder, text_channels))

    if not matched:
        await progress_msg.edit(content="No matching categories found.")
        return

    total_channels = sum(len(chs) for _, _, chs in matched)
    total_done = 0
    total_messages = 0
    failed = []

    for cat_name, folder, channels in matched:
        for i, channel in enumerate(channels):
            total_done += 1
            try:
                await progress_msg.edit(
                    content=f"**[{total_done}/{total_channels}]** Archiving **#{channel.name}** from **{cat_name}**..."
                )
            except Exception:
                pass

            output_path = os.path.join(SITE_ROOT, folder, f"{channel.name}-archive.html")

            try:
                count, filepath = await archive_channel(
                    channel,
                    output_path=output_path,
                    guild_data=gd,
                )
                total_messages += count
            except Exception as e:
                failed.append((cat_name, channel.name, str(e)))

    summary = f"Re-archived **{total_done - len(failed)}/{total_channels}** channels ({total_messages:,} total messages).\nFiles saved to `{SITE_ROOT}`."
    if failed:
        summary += "\n\n**Failed:**\n" + "\n".join(f"- {cat}/#{ch}: {err}" for cat, ch, err in failed)

    try:
        await progress_msg.edit(content=summary)
    except Exception:
        await dest.send(summary)


@bot.tree.command(
    name="gigaarchive",
    description="Archive many categories at once — sends every channel back as an HTML file",
)
@app_commands.describe(
    category1="A category to archive",
    category2="A category to archive",
    category3="A category to archive",
    category4="A category to archive",
    category5="A category to archive",
    category6="A category to archive",
    category7="A category to archive",
    category8="A category to archive",
    category9="A category to archive",
    category10="A category to archive",
    category11="A category to archive",
    category12="A category to archive",
    category13="A category to archive",
    category14="A category to archive",
    category15="A category to archive",
)
async def gigaarchive(
    interaction: discord.Interaction,
    category1: discord.CategoryChannel,
    category2: Optional[discord.CategoryChannel] = None,
    category3: Optional[discord.CategoryChannel] = None,
    category4: Optional[discord.CategoryChannel] = None,
    category5: Optional[discord.CategoryChannel] = None,
    category6: Optional[discord.CategoryChannel] = None,
    category7: Optional[discord.CategoryChannel] = None,
    category8: Optional[discord.CategoryChannel] = None,
    category9: Optional[discord.CategoryChannel] = None,
    category10: Optional[discord.CategoryChannel] = None,
    category11: Optional[discord.CategoryChannel] = None,
    category12: Optional[discord.CategoryChannel] = None,
    category13: Optional[discord.CategoryChannel] = None,
    category14: Optional[discord.CategoryChannel] = None,
    category15: Optional[discord.CategoryChannel] = None,
):
    if not interaction.user.guild_permissions.manage_guild:
        await interaction.response.send_message("You need **Manage Server** permission to use this.", ephemeral=True)
        return

    # Collect provided categories, de-duplicated, preserving order
    provided = [
        category1, category2, category3, category4, category5,
        category6, category7, category8, category9, category10,
        category11, category12, category13, category14, category15,
    ]
    categories = []
    seen_cats = set()
    for cat in provided:
        if cat is not None and cat.id not in seen_cats:
            seen_cats.add(cat.id)
            categories.append(cat)

    # Build the full channel plan (category, channel), top-to-bottom within each category
    plan = []
    for cat in categories:
        text_channels = [ch for ch in cat.channels if isinstance(ch, discord.TextChannel)]
        text_channels.sort(key=lambda ch: ch.position)
        for ch in text_channels:
            plan.append((cat, ch))

    if not plan:
        await interaction.response.send_message("No text channels found in the provided categories.", ephemeral=True)
        return

    await interaction.response.send_message(
        f"Starting **giga archive** — {len(categories)} categories, {len(plan)} channels. "
        f"This can take a while; you can leave it running.",
        ephemeral=True,
    )

    # Progress + uploads go to a regular message (interaction tokens expire after 15 min)
    dest = interaction.channel
    guild = interaction.guild

    # Build member/role/channel data once and reuse for every channel (big speedup)
    progress_msg = await dest.send("Building member/role/channel data...")
    gd = await build_guild_data(guild)

    total = len(plan)
    done = 0
    total_messages = 0
    failed = []

    for cat, channel in plan:
        done += 1
        try:
            await progress_msg.edit(
                content=f"**[{done}/{total}]** Archiving **#{channel.name}** from **{cat.name}**..."
            )
        except Exception:
            pass

        try:
            count, filepath = await archive_channel(channel, guild_data=gd)
            total_messages += count
            try:
                file = discord.File(filepath, filename=f"{channel.name}-archive.html")
                await dest.send(f"**{cat.name} / #{channel.name}** — {count:,} messages", file=file)
            except Exception:
                await dest.send(
                    f"Archived **#{channel.name}** ({count:,} messages) but upload failed (file too large)."
                )
        except Exception as e:
            failed.append((cat.name, channel.name, str(e)))

    summary = (
        f"**Giga archive complete** — {total - len(failed)}/{total} channels "
        f"({total_messages:,} messages) across {len(categories)} categories."
    )
    if failed:
        summary += "\n\n**Failed:**\n" + "\n".join(f"- {cat}/#{ch}: {err}" for cat, ch, err in failed)

    try:
        await progress_msg.edit(content=summary)
    except Exception:
        await dest.send(summary)


bot.run(os.environ["DISCORD_BOT_TOKEN"])