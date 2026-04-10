import os
import shutil
import discord
from discord import app_commands
from dotenv import load_dotenv
from archiver import archive_channel, wipe_r2

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

    await interaction.response.defer(ephemeral=True)

    total_messages = 0
    files = []
    failed = []

    for i, channel in enumerate(text_channels):
        try:
            await interaction.edit_original_response(
                content=f"Archiving **{channel.name}** ({i + 1}/{len(text_channels)})..."
            )
            count, filepath = await archive_channel(channel)
            total_messages += count
            files.append((channel.name, filepath, count))
        except Exception as e:
            failed.append((channel.name, str(e)))

    # Send each file as a separate followup (Discord has a 25MB file limit per message)
    summary = f"Archived **{len(files)}/{len(text_channels)}** channels from **{category.name}** ({total_messages:,} total messages)."
    if failed:
        summary += "\n\nFailed channels:\n" + "\n".join(f"- #{name}: {err}" for name, err in failed)

    await interaction.edit_original_response(content=summary)

    for name, filepath, count in files:
        try:
            file = discord.File(filepath, filename=f"{name}-archive.html")
            await interaction.followup.send(
                f"**#{name}** — {count:,} messages",
                file=file,
                ephemeral=True,
            )
        except Exception:
            await interaction.followup.send(f"Failed to upload **#{name}** (file may be too large)", ephemeral=True)


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


bot.run(os.environ["DISCORD_BOT_TOKEN"])