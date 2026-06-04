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

    # التعديل 1: تم إزالة إيموجي الكاميرا من بجانب الاسم هنا
    embed = discord.Embed(title=title, color=0xE74C3C)
    embed.set_footer(text=f"📂 {list_name}  •  {index+1} من {total}")

    if desc:
        embed.description = f"> {desc}"

    if poster:
        embed.set_image(url=poster)
    else:
        embed.description = (embed.description or "") + "\n\n*لا توجد صورة لهذا العنصر.*"

    return embed

# ─── All items embed ──────────────────────────────────────
# التعديل 2: خانة عرض الكل تعرض الأسماء مع البوسترات والوصف بشكل مرتب
def build_all_embed(list_name: str, items: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 القائمة الكاملة — {list_name}",
        color=0x5865F2
    )
    if not items:
        embed.description = "*القائمة فارغة.*"
    else:
        for i, item in enumerate(items):
            title = get_title(item)
            desc = get_desc(item) or "لا يوجد وصف."
            poster = get_poster(item)
            
            # عرض رابط البوستر بجانب الوصف إن وجد لجعلها منسقة وثابتة
            poster_text = f"\n🖼️ [اضغط لعرض البوستر]({poster})" if poster else ""
            
            embed.add_field(
                name=f"`{i+1:02d}.` {title}",
                value=f"{desc}{poster_text}",
                inline=False
            )
            
            # إذا كان هناك عنصر واحد فقط، نضعه كصورة كبيرة، وإلا نكتفي بالروابط لعدم تخريب المظهر
            if len(items) == 1 and poster:
                embed.set_thumbnail(url=poster)
                
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
        back_view = BackView(self.list_name, self.items, self.index)
        await interaction.response.edit_message(embed=embed, view=back_view)

    # زر للعودة للقائمة الرئيسية دون الخروج من الرسالة
    @discord.ui.button(label="🏠 العودة للرئيسية", style=discord.ButtonStyle.danger, row=1)
    async def go_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        await return_to_main_panel(interaction)

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

    @discord.ui.button(label="🏠 العودة للرئيسية", style=discord.ButtonStyle.danger)
    async def go_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        await return_to_main_panel(interaction)

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
            
            # التعديل 3: التعديل يتم داخل نفس رسالة البانل بدلاً من إرسال رسالة جديدة تماماً
            await interaction.response.edit_message(embed=embed, view=view)
        return callback

# ─── Helper to return to main panel screen ────────────────
# دالة مساعدة لتوليد شكل البانل الرئيسي عند الضغط على "العودة للرئيسية"
async def return_to_main_panel(interaction: discord.Interaction):
    data       = load_data()
    list_names = list(data["lists"].keys())

    lines = "\n".join(
        f"📋 **{k}** · {len(v.get('items', []))} عنصر"
        for k, v in data["lists"].items()
    ) if list_names else "*لا توجد قوائم بعد. يمكن للمسؤول إنشاء قائمة بأمر `/list_create`.*"

    embed = discord.Embed(
        title="🗂️ الأرشيف — تصفح القوائم",
        description="مرحباً بك في **الأرشيف**!\nاضغط على أي قائمة لتصفحها مباشرة.\n\n" + lines,
        color=0x2F3136
    )
    embed.set_footer(text="يمكنك التنقل والعودة لهذه القائمة في أي وقت.")
    view = PanelView(list_names)
    await interaction.response.edit_message(embed=embed, view=view)

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
        description="مرحباً بك في **الأرشيف**!\nاضغط على أي قائمة لتصفحها مباشرة.\n\n" + lines,
        color=0x2F3136
    )
    embed.set_footer(text="يمكنك التنقل والعودة لهذه القائمة في أي وقت.")

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

# ─── Run ──────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN environment variable not set!")

bot.run(TOKEN)
