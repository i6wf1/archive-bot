import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from pathlib import Path

# ─── Config ───────────────────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"

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

def get_item_title(item) -> str:
    return item["title"] if isinstance(item, dict) else item

def get_item_poster(item) -> str:
    if isinstance(item, dict):
        return item.get("poster", "")
    return ""

# ─── Category config ──────────────────────────────────────
CATEGORY_COLORS = {
    "movies": 0xE74C3C, "series": 0x3498DB, "anime": 0xE91E8C,
    "comics": 0xF39C12, "games": 0x2ECC71, "other": 0x9B59B6,
}
CATEGORY_EMOJIS = {
    "movies": "🎬", "series": "📺", "anime": "⛩️",
    "comics": "📖", "games": "🎮", "other": "📌",
}

# ─── Build single item embed (big poster) ─────────────────
def build_item_embed(list_name: str, lst: dict, index: int) -> discord.Embed:
    items    = lst.get("items", [])
    item     = items[index]
    category = lst.get("category", "other")
    color    = CATEGORY_COLORS.get(category, 0x7289DA)
    emoji    = CATEGORY_EMOJIS.get(category, "📌")
    title    = get_item_title(item)
    poster   = get_item_poster(item)
    total    = len(items)

    embed = discord.Embed(title=f"{emoji}  {title}", color=color)
    embed.set_footer(text=f"{list_name}  •  {index+1} / {total}")

    if poster:
        embed.set_image(url=poster)
    else:
        embed.description = "*No poster added for this entry.*"

    return embed

# ─── Browse View (prev/next per item) ─────────────────────
class BrowseView(discord.ui.View):
    def __init__(self, list_name: str, lst: dict, index: int = 0):
        super().__init__(timeout=180)
        self.list_name = list_name
        self.lst       = lst
        self.index     = index
        self.total     = len(lst.get("items", []))
        self._update()

    def _update(self):
        self.prev_btn.disabled = self.index == 0
        self.next_btn.disabled = self.index == self.total - 1
        self.counter.label     = f"{self.index+1} / {self.total}"

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.primary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self._update()
        await interaction.response.edit_message(
            embed=build_item_embed(self.list_name, self.lst, self.index), view=self
        )

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True)
    async def counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self._update()
        await interaction.response.edit_message(
            embed=build_item_embed(self.list_name, self.lst, self.index), view=self
        )

# ─── Panel View (buttons per list) ────────────────────────
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
            items = lst.get("items", [])
            if not items:
                await interaction.response.send_message(f"📭 **{name}** is empty.", ephemeral=True)
                return
            embed = build_item_embed(name, lst, 0)
            view  = BrowseView(name, lst, 0)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return callback

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
        description="Welcome to the **Archive**!\nClick any list below to browse it privately.\n\n" + lines,
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
#  /item_add
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
    data["lists"][list_name]["items"].append({"title": title, "poster": poster})
    save_data(data)
    count     = len(data["lists"][list_name]["items"])
    has_poster = "🖼️ with poster" if poster else "📝 no poster"
    await interaction.response.send_message(
        f"✅ Added **{title}** to **{list_name}** (#{count}) — {has_poster}.", ephemeral=True
    )

# ══════════════════════════════════════════════════════════
#  /item_poster
# ══════════════════════════════════════════════════════════
@tree.command(name="item_poster", description="Add or update the poster of an existing entry.")
@app_commands.describe(list_name="Target list", number="Entry number", poster="New poster image URL")
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
    title = get_item_title(items[number - 1])
    await interaction.response.send_message(f"🖼️ Poster updated for **{title}**!", ephemeral=True)

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
    save_data(data)
    await interaction.response.send_message(f"🗑️ Removed **{get_item_title(removed)}** from **{list_name}**.", ephemeral=True)

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
            title = get_item_title(item)
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
        value="`/search` — Search across all lists\n`/lists` — View all lists",
        inline=False
    )
    embed.add_field(
        name="🔧 For Managers",
        value=(
            "`/panel` — Post/refresh the archive panel\n"
            "`/list_create` — Create a new list\n"
            "`/list_delete` — Delete a list\n"
            "`/list_rename` — Rename a list\n"
            "`/item_add` — Add entry (+ optional poster URL)\n"
            "`/item_poster` — Update poster for existing entry\n"
            "`/item_remove` — Remove an entry by number"
        ),
        inline=False
    )
    embed.set_footer(text="Click a list button → browse entries with ◀ ▶")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─── Run ──────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN environment variable not set!")

bot.run(TOKEN)
