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

# ─── Clean Cinema Embed ───────────────────────────────────
# دالة تقوم ببناء مصفوفة من الـ Embeds لعرض الأفلام بشكل منفصل وكبير جداً داخل نفس الرسالة
def build_clean_cinema_embeds(list_name: str, items: list) -> list[discord.Embed]:
    if not items:
        embed = discord.Embed(title=list_name, description="القائمة فارغة حالياً.", color=0x111111)
        return [embed]
    
    embeds = []
    for i, item in enumerate(items):
        title = get_title(item)
        desc = get_desc(item)
        poster = get_poster(item)
        
        # الـ Embed الأول يحتوي على اسم القائمة كعنوان جانبي وبداية العرض الأول
        if i == 0:
            embed = discord.Embed(title=f"{list_name} — {i+1:02d}. {title}", color=0x111111)
        else:
            embed = discord.Embed(title=f"{i+1:02d}. {title}", color=0x111111)
            
        if desc:
            embed.description = desc
            
        if poster:
            # تم جعل البوستر يظهر كصورة كاملة الحجم وعريضة أسفل الاسم والوصف مباشرة لمظهر سينمائي ضخم
            embed.set_image(url=poster)
            
        embeds.append(embed)
        
    return embeds

# ─── Modals (إدارة نظيفة) ───────────────────────────────────
class AddItemModal(discord.ui.Modal, title="إضافة"):
    item_title = discord.ui.TextInput(label="الاسم", placeholder="اسم الفيلم أو العرض", required=True)
    item_desc = discord.ui.TextInput(label="الوصف", style=discord.TextStyle.paragraph, required=False)
    item_poster = discord.ui.TextInput(label="رابط البوستر", placeholder="https://...", required=False)

    def __init__(self, list_name: str):
        super().__init__()
        self.list_name = list_name

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        if self.list_name in data["lists"]:
            data["lists"][self.list_name]["items"].append({
                "title": self.item_title.value,
                "poster": self.item_poster.value,
                "desc": self.item_desc.value
            })
            save_data(data)
            
            items = data["lists"][self.list_name]["items"]
            embeds = build_clean_cinema_embeds(self.list_name, items)
            view = ListView(self.list_name, items, can_manage(interaction.user))
            # تم تحديد الـ embeds كمصفوفة لتحديث الواجهة الكبيرة بالكامل
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.response.send_message("خطأ: القائمة غير موجودة.", ephemeral=True)

class RemoveItemModal(discord.ui.Modal, title="حذف"):
    item_number = discord.ui.TextInput(label="رقم العنصر للحذف", placeholder="مثال: 1", required=True)

    def __init__(self, list_name: str):
        super().__init__()
        self.list_name = list_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.item_number.value)
        except ValueError:
            await interaction.response.send_message("يرجى إدخال رقم صحيح.", ephemeral=True)
            return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        
        if num < 1 or num > len(items):
            await interaction.response.send_message("رقم غير صحيح.", ephemeral=True)
            return

        items.pop(num - 1)
        save_data(data)
        
        embeds = build_clean_cinema_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user))
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── Manage View ──────────────────────────────────────────
class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name: str):
        super().__init__(timeout=60)
        self.list_name = list_name

    @discord.ui.button(label="إضافة فيلم جديد", style=discord.ButtonStyle.success, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name))

    @discord.ui.button(label="حذف فيلم بالرقم", style=discord.ButtonStyle.secondary, row=0)
    async def remove_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveItemModal(self.list_name))

    @discord.ui.button(label="حذف القائمة نهائياً", style=discord.ButtonStyle.danger, row=1)
    async def delete_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        await return_to_main_panel(interaction)

    @discord.ui.button(label="العودة للتصفح", style=discord.ButtonStyle.primary, row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embeds = build_clean_cinema_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user))
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── List View ────────────────────────────────────────────
class ListView(discord.ui.View):
    def __init__(self, list_name: str, items: list, is_manager: bool):
        super().__init__(timeout=180)
        self.list_name = list_name
        self.items = items
        
        if not is_manager:
            self.remove_item(self.manage_btn)

    @discord.ui.button(label="إدارة القائمة", style=discord.ButtonStyle.secondary, row=0)
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل بمحتويات القائمة الحالية من خلال الأزرار أدناه.",
            color=0x111111
        )
        await interaction.response.edit_message(embed=embed, view=ManageDashboardView(self.list_name))

    @discord.ui.button(label="الرئيسية", style=discord.ButtonStyle.primary, row=0)
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
                style=discord.ButtonStyle.secondary
            )
            btn.callback = self.make_callback(name)
            self.add_item(btn)

    def make_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data  = load_data()
            lst   = data["lists"].get(name)
            if not lst:
                await interaction.response.send_message("القائمة غير موجودة.", ephemeral=True)
                return
            items = lst.get("items", [])
            
            embeds = build_clean_cinema_embeds(name, items)
            view  = ListView(name, items, can_manage(interaction.user))
            await interaction.response.edit_message(embeds=embeds, view=view)
        return callback

# ─── Return to Main Dashboard ─────────────────────────────
async def return_to_main_panel(interaction: discord.Interaction):
    data       = load_data()
    list_names = list(data["lists"].keys())

    # التعديل: إزالة كل النصوص والشروحات الفرعية والإيموجيات من الواجهة الرئيسية
    if list_names:
        lines = "\n".join(f"**{k.upper()}** — `{len(v.get('items', []))}`" for k, v in data["lists"].items())
    else:
        lines = "لا توجد قوائم متوفرة."

    embed = discord.Embed(
        title="Wonderland Lists",
        description=lines,
        color=0x111111
    )
    view = PanelView(list_names)
    await interaction.response.edit_message(embed=embed, view=view)

# ─── Panel refresh ────────────────────────────────────────
async def refresh_panel(guild: discord.Guild, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())

    if list_names:
        lines = "\n".join(f"**{k.upper()}** — `{len(v.get('items', []))}`" for k, v in data["lists"].items())
    else:
        lines = "لا توجد قوائم متوفرة."

    embed = discord.Embed(
        title="Wonderland Lists",
        description=lines,
        color=0x111111
    )

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
# Commands
# ══════════════════════════════════════════════════════════
@tree.command(name="panel", description="Post/refresh the main dashboard.")
async def cmd_panel(interaction: discord.Interaction):
    if not can_manage(interaction.user):
        await interaction.response.send_message("خطأ في الصلاحية.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await refresh_panel(interaction.guild, interaction.channel)
    await interaction.followup.send("تم تحديث الواجهة.", ephemeral=True)

@tree.command(name="list_create", description="Create a new category.")
@app_commands.describe(name="Category name")
async def cmd_list_create(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("خطأ في الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if name in data["lists"]:
        await interaction.response.send_message("القائمة موجودة مسبقاً.", ephemeral=True)
        return
    data["lists"][name] = {"description": "", "items": []}
    save_data(data)
    await interaction.response.send_message(f"تم إنشاء القائمة {name}.", ephemeral=True)

# ─── Run ──────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN environment variable not set!")

bot.run(TOKEN)
