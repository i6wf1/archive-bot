import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from pathlib import Path

# ─── Config ───────────────────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"
ITEMS_PER_PAGE = 5  # Lower since each item now has a poster

# ─── Data helpers ─────────────────────────────────────────
def load_data() -> dict:
    Path("data").mkdir(exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {"lists": {}, "panel_message": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: dict):
    Path("data").mkdir(exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def can_manage(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.name == MANAGER_ROLE_NAME for r in member.roles)

# ─── Category colors & emojis ─────────────────────────────
CATEGORY_COLORS = {
    "movies": 0xE74C3C, "series": 0x3498DB, "anime": 0xE91E8C,
    "comics": 0xF39C12, "games": 0x2ECC71, "other": 0x9B59B6,
}
CATEGORY_EMOJIS = {
    "movies": "🎬", "series": "📺", "anime": "⛩️",
    "comics": "📖", "games": "🎮", "other": "📌",
}

# ─── Embed builder ────────────────────────────────────────
def build_list_embeds(name: str, lst: dict) -> list[discord.Embed]:
    items    = lst.get("items", [])
    category = lst.get("category", "other")
    color    = CATEGORY_COLORS.get(category, 0x7289DA)
    emoji    = CATEGORY_EMOJIS.get(category, "📌")
    desc     = lst.get("description", "")

    if not items:
        embed = discord.Embed(title=f"{emoji} {name}", description=desc or None, color=color)
        embed.add_field(name="📋 Entries", value="*This list is empty.*", inline=False)
        embed.set_footer(text=f"Category: {category.capitalize()} • Page 1/1")
        return [embed]

    # Group items into pages
    pages = [items[i:i+ITEMS_PER_PAGE] for i in range(0, len(items), ITEMS_PER_PAGE)]
    embeds = []

    for idx, page_items in enumerate(pages):
        embed = discord.Embed(title=f"{emoji} {name}", description=desc or None, color=color)

        for i, item in enumerate(page_items):
            num = i + 1 + idx * ITEMS_PER_PAGE
            # item is either a string (old format) or dict {title, poster}
            if isinstance(item, dict):
                title  = item.get("title", "Unknown")
                poster = item.get("poster", "")
            else:
                title  = item
                poster = ""

            field_val = f"🖼️ [Poster]({poster})" if poster else "*No poster*"
            embed.add_field(
                name=f"`{num:02d}.` {title}",
                value=field_val,
                inline=True
            )

        embed.set_footer(text=f"Category: {category.capitalize()} • Page {idx+1}/{len(pages)}")
        embeds.append(embed)

    return embeds

# ─── Single item embed (for /item_view) ───────────────────
def build_item_embed(list_name: str, lst: dict, number: int) -> discord.Embed | None:
    items    = lst.get("items", [])
    if number < 1 or number > len(items):
        return None
    item     = items[number - 1]
    category = lst.get("category", "other")
    color    = CATEGORY_COLORS.get(category, 0x7289DA)
    emoji    = CATEGORY_EMOJIS.get(category, "📌")

    if isinstance(item, dict):
        title  = item.get("title", "Unknown")
        poster = item.get("poster", "")
    else:
        title  = item
        poster = ""

    embed = discord.Embed(
        title=f"{emoji} {title}",
        description=f"From list: **{list_name}**",
        color=color
    )
    if poster:
        embed.set_image(url=poster)
    else:
        embed.add_field(name="Poster", value="*No poster added.*", inline=False)

    embed.set_footer(text=f"Entry #{number} • {category.capitalize()}")
    return embed

# ─── Panel View ───────────────────────────────────────────
class PanelView(discord.ui.View):
    def __init__(self, list_names: list[str]):
        super().__init__(timeout=None)
        for name in list_names:
            btn = discord.ui.Button(
                label=name,
                custom_id=f"archive_list_{name}",
                style=discord.ButtonStyle.secondary,
                emoji="📋"
            )
            btn.callback = self.make_callback(name)
            self.add_item(btn)

    def make_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data = load_data()
            lst  = data["lists"].get(name)
            if not lst:
                await interaction.response.send_message(f"❌ List **{name}** not found.", ephemeral=True)
                return
            embeds = build_list_embeds(name, lst)
            view   = PaginationView(embeds) if len(embeds) > 1 else None
            await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=True)
        return callback

# ─── Pagination View ──────────────────────────────────────
class PaginationView(discord.ui.View):
    def __init__(self, embeds: list[discord.Embed]):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.page   = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page == len(self.embeds) - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.primary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.embeds[self.page], view=self)

# ─── Panel refresh ────────────────────────────────────────
async def refresh_panel(guild: discord.Guild, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())

    lines = "\n".join(
        f"{CATEGORY_EMOJIS.get(v.get('category','other'), '📌')} **{k}** — "
        f"*{v.get('category','other').capitalize()}* · {len(v.get('items',[]))} entries"
        for k, v in data["lists"].items()
    ) if list_names else "*No lists yet. Admins can create one with `/list_create`.*"

    embed = discord.Embed(
        title="🗂️ Archive — Browse Lists",
        description="Welcome to the **Archive**!\nClick any button below to view a list privately.\n\n" + lines,
        color=0x2F3136
    )
    embed.set_footer(text="Only you can see the list when you click a button.")

    panel_info = data.get("panel_message", {})
    guild_key  = str(guild.id)
    old_msg_id = panel_info.get(guild_key)
    view       = PanelView(list_names)

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(old_msg_id)
            await old_msg.edit(embed=embed, view=view)
            return
        except discord.NotFound:
            pass

    msg = await channel.send(embed=embed, view=view)
    data.setdefault("panel_message", {})[guild_key] = msg.id
    save_data(data)

# ─── Bot setup ────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot  = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    await tree.sync()
    print("✅ Slash commands synced.")

# ══════════════════════════════════════════════════════════
#  /panel
# ══════════════════════════════════════════════════════════
@tree.command(name="panel", description="Post/refresh the archive panel in this channel.")
async def cmd_panel(interaction: discord.Interaction):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ You need the **Archive Manager** role or admin perms.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await refresh_panel(interaction.guild, interaction.channel)
    await interaction.followup.send("✅ Panel posted/refreshed!", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /list_create
# ══════════════════════════════════════════════════════════
@tree.command(name="list_create", description="Create a new archive list.")
@app_commands.describe(name="List name", category="Type of content", description="Short description (optional)")
@app_commands.choices(category=[
    app_commands.Choice(name="🎬 Movies", value="movies"),
    app_commands.Choice(name="📺 Series", value="series"),
    app_commands.Choice(name="⛩️ Anime",  value="anime"),
    app_commands.Choice(name="📖 Comics", value="comics"),
    app_commands.Choice(name="🎮 Games",  value="games"),
    app_commands.Choice(name="📌 Other",  value="other"),
])
async def cmd_list_create(interaction: discord.Interaction, name: str, category: str, description: str = ""):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    data = load_data()
    if name in data["lists"]:
        await interaction.response.send_message(f"❌ A list named **{name}** already exists.", ephemeral=True)
        return
    data["lists"][name] = {"category": category, "description": description, "items": []}
    save_data(data)
    await interaction.response.send_message(f"✅ List **{name}** created!", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /list_delete
# ══════════════════════════════════════════════════════════
@tree.command(name="list_delete", description="Delete an archive list.")
@app_commands.describe(name="Name of the list to delete")
async def cmd_list_delete(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    data = load_data()
    if name not in data["lists"]:
        await interaction.response.send_message(f"❌ List **{name}** not found.", ephemeral=True)
        return
    del data["lists"][name]
    save_data(data)
    await interaction.response.send_message(f"🗑️ List **{name}** deleted.", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /list_rename
# ══════════════════════════════════════════════════════════
@tree.command(name="list_rename", description="Rename an archive list.")
@app_commands.describe(old_name="Current list name", new_name="New name")
async def cmd_list_rename(interaction: discord.Interaction, old_name: str, new_name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    data = load_data()
    if old_name not in data["lists"]:
        await interaction.response.send_message(f"❌ List **{old_name}** not found.", ephemeral=True)
        return
    if new_name in data["lists"]:
        await interaction.response.send_message(f"❌ **{new_name}** already exists.", ephemeral=True)
        return
    data["lists"][new_name] = data["lists"].pop(old_name)
    save_data(data)
    await interaction.response.send_message(f"✅ Renamed **{old_name}** → **{new_name}**.", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /item_add  ← Updated: now accepts optional poster URL
# ══════════════════════════════════════════════════════════
@tree.command(name="item_add", description="Add an entry to a list.")
@app_commands.describe(
    list_name="Target list",
    title="Title (e.g. Iron Man (2008))",
    poster="Poster image URL (optional)"
)
async def cmd_item_add(interaction: discord.Interaction, list_name: str, title: str, poster: str = ""):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    data = load_data()
    if list_name not in data["lists"]:
        await interaction.response.send_message(f"❌ List **{list_name}** not found.", ephemeral=True)
        return

    item = {"title": title, "poster": poster} if poster else {"title": title, "poster": ""}
    data["lists"][list_name]["items"].append(item)
    save_data(data)
    count = len(data["lists"][list_name]["items"])
    has_poster = "🖼️ with poster" if poster else "📝 no poster"
    await interaction.response.send_message(
        f"✅ Added **{title}** to **{list_name}** (#{count}) — {has_poster}.", ephemeral=True
    )

# ══════════════════════════════════════════════════════════
#  /item_poster  ← New: add/update poster for existing entry
# ══════════════════════════════════════════════════════════
@tree.command(name="item_poster", description="Add or update the poster of an existing entry.")
@app_commands.describe(
    list_name="Target list",
    number="Entry number",
    poster="New poster image URL"
)
async def cmd_item_poster(interaction: discord.Interaction, list_name: str, number: int, poster: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    data = load_data()
    if list_name not in data["lists"]:
        await interaction.response.send_message(f"❌ List **{list_name}** not found.", ephemeral=True)
        return

    items = data["lists"][list_name]["items"]
    if number < 1 or number > len(items):
        await interaction.response.send_message(f"❌ Invalid number. List has {len(items)} entries.", ephemeral=True)
        return

    item = items[number - 1]
    if isinstance(item, str):
        items[number - 1] = {"title": item, "poster": poster}
    else:
        items[number - 1]["poster"] = poster

    save_data(data)
    title = items[number - 1]["title"] if isinstance(items[number - 1], dict) else item
    await interaction.response.send_message(f"🖼️ Poster updated for **{title}**!", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /item_view  ← New: view single item with full poster
# ══════════════════════════════════════════════════════════
@tree.command(name="item_view", description="View a single entry with its full poster.")
@app_commands.describe(list_name="Target list", number="Entry number")
async def cmd_item_view(interaction: discord.Interaction, list_name: str, number: int):
    data = load_data()
    if list_name not in data["lists"]:
        await interaction.response.send_message(f"❌ List **{list_name}** not found.", ephemeral=True)
        return
    embed = build_item_embed(list_name, data["lists"][list_name], number)
    if not embed:
        await interaction.response.send_message("❌ Invalid entry number.", ephemeral=True)
        return
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /item_remove
# ══════════════════════════════════════════════════════════
@tree.command(name="item_remove", description="Remove an entry from a list by its number.")
@app_commands.describe(list_name="Target list", number="Entry number to remove")
async def cmd_item_remove(interaction: discord.Interaction, list_name: str, number: int):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ No permission.", ephemeral=True)
        return
    data = load_data()
    if list_name not in data["lists"]:
        await interaction.response.send_message(f"❌ List **{list_name}** not found.", ephemeral=True)
        return
    items = data["lists"][list_name]["items"]
    if number < 1 or number > len(items):
        await interaction.response.send_message(f"❌ Invalid number. List has {len(items)} entries.", ephemeral=True)
        return
    removed = items.pop(number - 1)
    title   = removed["title"] if isinstance(removed, dict) else removed
    save_data(data)
    await interaction.response.send_message(f"🗑️ Removed **{title}** from **{list_name}**.", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /lists
# ══════════════════════════════════════════════════════════
@tree.command(name="lists", description="Show all archive lists.")
async def cmd_lists(interaction: discord.Interaction):
    data = load_data()
    if not data["lists"]:
        await interaction.response.send_message("📭 No lists yet.", ephemeral=True)
        return
    embed = discord.Embed(title="🗂️ All Archive Lists", color=0x5865F2)
    for name, lst in data["lists"].items():
        emoji = CATEGORY_EMOJIS.get(lst.get("category", "other"), "📌")
        embed.add_field(
            name=f"{emoji} {name}",
            value=f"Category: `{lst.get('category','other')}` · **{len(lst.get('items',[]))}** entries",
            inline=False
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /search
# ══════════════════════════════════════════════════════════
@tree.command(name="search", description="Search across all lists.")
@app_commands.describe(query="Search term")
async def cmd_search(interaction: discord.Interaction, query: str):
    data    = load_data()
    results = []
    for list_name, lst in data["lists"].items():
        for item in lst.get("items", []):
            title = item["title"] if isinstance(item, dict) else item
            if query.lower() in title.lower():
                results.append((list_name, title))
    if not results:
        await interaction.response.send_message(f"🔍 No results for **{query}**.", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"🔍 Search: {query}",
        description=f"Found **{len(results)}** result(s):",
        color=0xF39C12
    )
    for list_name, title in results[:20]:
        embed.add_field(name=title, value=f"📂 {list_name}", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /help
# ══════════════════════════════════════════════════════════
@tree.command(name="help", description="Show all bot commands.")
async def cmd_help(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Archive Bot — Commands", color=0x57F287)
    embed.add_field(
        name="👀 For Everyone",
        value=(
            "`/search` — Search across all lists\n"
            "`/lists` — View all lists\n"
            "`/item_view` — View a single entry with full poster"
        ),
        inline=False
    )
    embed.add_field(
        name="🔧 For Managers",
        value=(
            "`/panel` — Post/refresh the archive panel\n"
            "`/list_create` — Create a new list\n"
            "`/list_delete` — Delete a list\n"
            "`/list_rename` — Rename a list\n"
            "`/item_add` — Add an entry (+ optional poster URL)\n"
            "`/item_poster` — Add/update poster for existing entry\n"
            "`/item_remove` — Remove an entry by number"
        ),
        inline=False
    )
    embed.set_footer(text="Clicking a button in the panel shows the list only to you.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─── Run ──────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN environment variable not set!")

bot.run(TOKEN)
