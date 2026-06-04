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

def get_title(item) -> str:
    return item.get("title", "—") if isinstance(item, dict) else item

def get_poster(item) -> str:
    return item.get("poster", "") if isinstance(item, dict) else ""

def get_desc(item) -> str:
    return item.get("desc", "") if isinstance(item, dict) else ""

# ─── Single item embed ────────────────────────────────────
def build_item_embed(list_name: str, items: list, index: int) -> discord.Embed:
    item   = items[index]
    title  = get_title(item)
    poster = get_poster(item)
    desc   = get_desc(item)
    total  = len(items)

    embed = discord.Embed(title=f"🎬  {title}", color=0xE74C3C)
    embed.set_footer(text=f"📂 {list_name}  •  {index+1} من {total}")

    if desc:
        embed.description = f"> {desc}"

    if poster:
        embed.set_image(url=poster)
    else:
        embed.description = (embed.description or "") + "\n\n*لا توجد صورة لهذا العنصر.*"

    return embed

# ─── All items embed ──────────────────────────────────────
def build_all_embed(list_name: str, items: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋  قائمة كاملة — {list_name}",
        color=0x5865F2
    )
    if not items:
        embed.description = "*القائمة فارغة.*"
    else:
        lines = "\n".join(
            f"`{i+1:02d}.`  {get_title(item)}" for i, item in enumerate(items)
        )
        embed.description = lines
    embed.set_footer(text=f"إجمالي العناصر: {len(items)}")
    return embed

# ─── Browse View ──────────────────────────────────────────
class BrowseView(discord.ui.View):
    def __init__(self, list_name: str, items: list, index: int = 0):
        super().__init__(timeout=180)
        self.list_name = list_name
        self.items     = items
        self.index     = index
        self.total     = len(items)
        self._update()

    def _update(self):
        self.prev_btn.disabled = self.index == 0
        self.next_btn.disabled = self.index == self.total - 1
        self.counter.label     = f"{self.index+1} / {self.total}"

    @discord.ui.button(emoji="◀", style=discord.ButtonStyle.primary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index -= 1
        self._update()
        await interaction.response.edit_message(
            embed=build_item_embed(self.list_name, self.items, self.index), view=self
        )

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(emoji="▶", style=discord.ButtonStyle.primary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index += 1
        self._update()
        await interaction.response.edit_message(
            embed=build_item_embed(self.list_name, self.items, self.index), view=self
        )

    @discord.ui.button(label="📋 عرض الكل", style=discord.ButtonStyle.secondary, row=1)
    async def show_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_all_embed(self.list_name, self.items)
        # Back button to return to browse
        back_view = BackView(self.list_name, self.items, self.index)
        await interaction.response.edit_message(embed=embed, view=back_view)

# ─── Back View (shown in "all items" screen) ──────────────
class BackView(discord.ui.View):
    def __init__(self, list_name: str, items: list, index: int):
        super().__init__(timeout=180)
        self.list_name = list_name
        self.items     = items
        self.index     = index

    @discord.ui.button(label="← رجوع للتصفح", style=discord.ButtonStyle.primary)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view  = BrowseView(self.list_name, self.items, self.index)
        embed = build_item_embed(self.list_name, self.items, self.index)
        await interaction.response.edit_message(embed=embed, view=view)

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
            data  = load_data()
            lst   = data["lists"].get(name)
            if not lst:
                await interaction.response.send_message(f"❌ القائمة **{name}** غير موجودة.", ephemeral=True)
                return
            items = lst.get("items", [])
            if not items:
                await interaction.response.send_message(f"📭 القائمة **{name}** فارغة.", ephemeral=True)
                return
            embed = build_item_embed(name, items, 0)
            view  = BrowseView(name, items, 0)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        return callback

# ─── Panel refresh ────────────────────────────────────────
async def refresh_panel(guild: discord.Guild, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())

    lines = "\n".join(
        f"📋 **{k}** · {len(v.get('items', []))} عنصر"
        for k, v in data["lists"].items()
    ) if list_names else "*لا توجد قوائم بعد. يمكن للمسؤول إنشاء قائمة بأمر `/list_create`.*"

    embed = discord.Embed(
        title="🗂️ الأرشيف — تصفح القوائم",
        description="مرحباً بك في **الأرشيف**!\nاضغط على أي قائمة لتصفحها بشكل خاص.\n\n" + lines,
        color=0x2F3136
    )
    embed.set_footer(text="القائمة تظهر لك فقط عند الضغط على الزر.")

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
        await interaction.response.send_message("❌ تحتاج صلاحية **Archive Manager** أو أدمن.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await refresh_panel(interaction.guild, interaction.channel)
    await interaction.followup.send("✅ تم نشر/تحديث لوحة الأرشيف!", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /list_create
# ══════════════════════════════════════════════════════════
@tree.command(name="list_create", description="Create a new archive list.")
@app_commands.describe(name="List name", description="Short description (optional)")
async def cmd_list_create(interaction: discord.Interaction, name: str, description: str = ""):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if name in data["lists"]:
        await interaction.response.send_message(f"❌ القائمة **{name}** موجودة مسبقاً.", ephemeral=True)
        return
    data["lists"][name] = {"description": description, "items": []}
    save_data(data)
    await interaction.response.send_message(f"✅ تم إنشاء القائمة **{name}**!", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /list_delete
# ══════════════════════════════════════════════════════════
@tree.command(name="list_delete", description="Delete an archive list.")
@app_commands.describe(name="List name to delete")
async def cmd_list_delete(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if name not in data["lists"]:
        await interaction.response.send_message(f"❌ القائمة **{name}** غير موجودة.", ephemeral=True)
        return
    del data["lists"][name]
    save_data(data)
    await interaction.response.send_message(f"🗑️ تم حذف القائمة **{name}**.", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /list_rename
# ══════════════════════════════════════════════════════════
@tree.command(name="list_rename", description="Rename an archive list.")
@app_commands.describe(old_name="Current name", new_name="New name")
async def cmd_list_rename(interaction: discord.Interaction, old_name: str, new_name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if old_name not in data["lists"]:
        await interaction.response.send_message(f"❌ القائمة **{old_name}** غير موجودة.", ephemeral=True)
        return
    if new_name in data["lists"]:
        await interaction.response.send_message(f"❌ الاسم **{new_name}** مستخدم مسبقاً.", ephemeral=True)
        return
    data["lists"][new_name] = data["lists"].pop(old_name)
    save_data(data)
    await interaction.response.send_message(f"✅ تمّ تغيير الاسم من **{old_name}** إلى **{new_name}**.", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /item_add
# ══════════════════════════════════════════════════════════
@tree.command(name="item_add", description="Add an entry to a list.")
@app_commands.describe(
    list_name="Target list",
    title="Title (e.g. Iron Man)",
    poster="Poster image URL (optional)",
    desc="Short description (optional)"
)
async def cmd_item_add(interaction: discord.Interaction, list_name: str, title: str, poster: str = "", desc: str = ""):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if list_name not in data["lists"]:
        await interaction.response.send_message(f"❌ القائمة **{list_name}** غير موجودة.", ephemeral=True)
        return
    data["lists"][list_name]["items"].append({"title": title, "poster": poster, "desc": desc})
    save_data(data)
    count = len(data["lists"][list_name]["items"])
    await interaction.response.send_message(
        f"✅ تمّت إضافة **{title}** إلى **{list_name}** (#{count}).", ephemeral=True
    )

# ══════════════════════════════════════════════════════════
#  /item_poster
# ══════════════════════════════════════════════════════════
@tree.command(name="item_poster", description="Update the poster of an existing entry.")
@app_commands.describe(list_name="Target list", number="Entry number", poster="New poster URL")
async def cmd_item_poster(interaction: discord.Interaction, list_name: str, number: int, poster: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if list_name not in data["lists"]:
        await interaction.response.send_message(f"❌ القائمة **{list_name}** غير موجودة.", ephemeral=True)
        return
    items = data["lists"][list_name]["items"]
    if number < 1 or number > len(items):
        await interaction.response.send_message(f"❌ رقم غير صحيح. القائمة تحتوي {len(items)} عنصر.", ephemeral=True)
        return
    item = items[number - 1]
    if isinstance(item, str):
        items[number - 1] = {"title": item, "poster": poster, "desc": ""}
    else:
        items[number - 1]["poster"] = poster
    save_data(data)
    await interaction.response.send_message(f"🖼️ تمّ تحديث صورة **{get_title(items[number-1])}**!", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /item_remove
# ══════════════════════════════════════════════════════════
@tree.command(name="item_remove", description="Remove an entry by its number.")
@app_commands.describe(list_name="Target list", number="Entry number to remove")
async def cmd_item_remove(interaction: discord.Interaction, list_name: str, number: int):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if list_name not in data["lists"]:
        await interaction.response.send_message(f"❌ القائمة **{list_name}** غير موجودة.", ephemeral=True)
        return
    items = data["lists"][list_name]["items"]
    if number < 1 or number > len(items):
        await interaction.response.send_message(f"❌ رقم غير صحيح. القائمة تحتوي {len(items)} عنصر.", ephemeral=True)
        return
    removed = items.pop(number - 1)
    save_data(data)
    await interaction.response.send_message(f"🗑️ تمّ حذف **{get_title(removed)}** من **{list_name}**.", ephemeral=True)

# ══════════════════════════════════════════════════════════
#  /lists
# ══════════════════════════════════════════════════════════
@tree.command(name="lists", description="Show all archive lists.")
async def cmd_lists(interaction: discord.Interaction):
    data = load_data()
    if not data["lists"]:
        await interaction.response.send_message("📭 لا توجد قوائم بعد.", ephemeral=True)
        return
    embed = discord.Embed(title="🗂️ جميع القوائم", color=0x5865F2)
    for name, lst in data["lists"].items():
        embed.add_field(
            name=f"📋 {name}",
            value=f"**{len(lst.get('items', []))}** عنصر",
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
            if query.lower() in get_title(item).lower():
                results.append((list_name, get_title(item)))
    if not results:
        await interaction.response.send_message(f"🔍 لا توجد نتائج لـ **{query}**.", ephemeral=True)
        return
    embed = discord.Embed(
        title=f"🔍 نتائج البحث: {query}",
        description=f"تمّ العثور على **{len(results)}** نتيجة:",
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
    embed = discord.Embed(title="📚 أوامر البوت", color=0x57F287)
    embed.add_field(
        name="👀 للجميع",
        value="`/search` — البحث في جميع القوائم\n`/lists` — عرض جميع القوائم",
        inline=False
    )
    embed.add_field(
        name="🔧 للمسؤولين",
        value=(
            "`/panel` — نشر/تحديث لوحة الأرشيف\n"
            "`/list_create` — إنشاء قائمة جديدة\n"
            "`/list_delete` — حذف قائمة\n"
            "`/list_rename` — تغيير اسم قائمة\n"
            "`/item_add` — إضافة عنصر (+ صورة ووصف اختياري)\n"
            "`/item_poster` — تحديث صورة عنصر موجود\n"
            "`/item_remove` — حذف عنصر برقمه"
        ),
        inline=False
    )
    embed.set_footer(text="اضغط زر القائمة ← تصفح بـ ◀ ▶ ← اضغط 📋 عرض الكل")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─── Run ──────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN environment variable not set!")

bot.run(TOKEN)
