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
    Path("data").mkdir(keep_parents=True, parents=True, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {"lists": {}, "panel_message": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: dict):
    Path("data").mkdir(keep_parents=True, parents=True, exist_ok=True)
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

# ─── Premium Letterboxd Grid ──────────────────────────────
def build_premium_cinema_embeds(list_name: str, items: list) -> list[discord.Embed]:
    if not items:
        embed = discord.Embed(
            title=list_name, 
            description="هذه القائمة فارغة حالياً.", 
            color=0x1a1a1a
        )
        return [embed]
    
    embeds = []
    for i, item in enumerate(items[:10]): 
        title = get_title(item)
        desc = get_desc(item)
        poster = get_poster(item)
        
        embed = discord.Embed(color=0x1a1a1a)
        
        if i == 0:
            embed.title = f"{list_name.upper()}  •  {i+1:02d}. {title}"
        else:
            embed.title = f"{i+1:02d}. {title}"
            
        if desc:
            embed.description = f"*{desc}*"
            
        if poster:
            embed.set_image(url=poster)
            
        embeds.append(embed)
        
    return embeds

# ─── Modals ───────────────────────────────────────────────
class AddItemModal(discord.ui.Modal, title="إضافة فيلم"):
    item_title = discord.ui.TextInput(label="اسم الفيلم", required=True)
    item_desc = discord.ui.TextInput(label="الوصف أو التقييم", style=discord.TextStyle.paragraph, required=False)
    item_poster = discord.ui.TextInput(label="رابط صورة البوستر المباشر", placeholder="https://...", required=False)

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

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
            embeds = build_premium_cinema_embeds(self.list_name, items)
            view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names)
            await interaction.response.edit_message(embeds=embeds, view=view)
        else:
            await interaction.response.send_message("خطأ: القائمة غير موجودة.", ephemeral=True)

class RemoveItemModal(discord.ui.Modal, title="حذف فيلم"):
    item_number = discord.ui.TextInput(label="رقم الفيلم في القائمة", placeholder="مثال: 1", required=True)

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

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
        
        embeds = build_premium_cinema_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names)
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── Manage Dashboard View ────────────────────────────────
class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(timeout=60)
        self.list_name = list_name
        self.list_names = list_names

    @discord.ui.button(label="إضافة فيلم جديد", style=discord.ButtonStyle.success, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name, self.list_names))

    @discord.ui.button(label="حذف فيلم بالرقم", style=discord.ButtonStyle.secondary, row=0)
    async def remove_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveItemModal(self.list_name, self.list_names))

    @discord.ui.button(label="حذف اللستة كاملة", style=discord.ButtonStyle.danger, row=0)
    async def delete_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        await return_to_main_panel(interaction)

    @discord.ui.button(label="← عودة للتصفح", style=discord.ButtonStyle.primary, row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embeds = build_premium_cinema_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names)
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── Dynamic List View ────────────────────────────────────
class ListView(discord.ui.View):
    def __init__(self, current_list_name: str, items: list, is_manager: bool, list_names: list[str]):
        super().__init__(timeout=None)
        self.current_list_name = current_list_name
        self.list_names = list_names
        
        if is_manager:
            self.add_item(ManageButton(current_list_name, list_names))
        self.add_item(HomeButton())

        for name in list_names:
            style = discord.ButtonStyle.success if name == current_list_name else discord.ButtonStyle.secondary
            btn = discord.ui.Button(
                label=name,
                custom_id=f"quick_nav_{name}",
                style=style,
                row=1 if len(list_names) <= 5 else 2
            )
            btn.callback = self.make_navigation_callback(name)
            self.add_item(btn)

    def make_navigation_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data  = load_data()
            lst   = data["lists"].get(name)
            if not lst:
                await interaction.response.send_message("القائمة غير موجودة.", ephemeral=True)
                return
            items = lst.get("items", [])
            
            embeds = build_premium_cinema_embeds(name, items)
            view  = ListView(name, items, can_manage(interaction.user), self.list_names)
            await interaction.response.edit_message(embeds=embeds, view=view)
        return callback

# ─── Specialized Panel Buttons ────────────────────────────
class ManageButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(label="إدارة القائمة", style=discord.ButtonStyle.danger, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم بمحتوى وتفاصيل القائمة الحالية بشكل مباشر ونظيف.",
            color=0x1a1a1a
        )
        # تم تصحيح المعرّف هنا إلى embeds=
        await interaction.response.edit_message(embeds=[embed], view=ManageDashboardView(self.list_name, self.list_names))

class HomeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="الرئيسية", style=discord.ButtonStyle.primary, row=0)

    async def callback(self, interaction: discord.Interaction):
        await return_to_main_panel(interaction)

# ─── Main Panel View ──────────────────────────────────────
class PanelView(discord.ui.View):
    def __init__(self, list_names: list[str]):
        super().__init__(timeout=None)
        self.list_names = list_names
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
            
            embeds = build_premium_cinema_embeds(name, items)
            view  = ListView(name, items, can_manage(interaction.user), self.list_names)
            await interaction.response.edit_message(embeds=embeds, view=view)
        return callback

# ─── Return to Main Dashboard ─────────────────────────────
async def return_to_main_panel(interaction: discord.Interaction):
    data       = load_data()
    list_names = list(data["lists"].keys())

    if list_names:
        lines = "\n".join(f"▫️  **{k.upper()}** —  `{len(v.get('items', []))} Entries`" for k, v in data["lists"].items())
    else:
        lines = "لا توجد قوائم متوفرة حالياً."

    embed = discord.Embed(
        title="Wonderland Lists",
        description=f"\n{lines}\n",
        color=0x1a1a1a
    )
    view = PanelView(list_names)
    # تم تصحيح المعرّف هنا إلى embeds=
    await interaction.response.edit_message(embeds=[embed], view=view)

# ─── Panel refresh ────────────────────────────────────────
async def refresh_panel(guild: discord.Guild, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())

    if list_names:
        lines = "\n".join(f"▫️  **{k.upper()}** —  `{len(v.get('items', []))} Entries`" for k, v in data["lists"].items())
    else:
        lines = "لا توجد قوائم متوفرة حالياً."

    embed = discord.Embed(
        title="Wonderland Lists",
        description=f"\n{lines}\n",
        color=0x1a1a1a
    )

    panel_info = data.get("panel_message", {})
    guild_key  = str(guild.id)
    old_msg_id = panel_info.get(guild_key)
    view       = PanelView(list_names)

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(old_msg_id)
            # تم تصحيح المعرّف هنا إلى embeds=
            await old_msg.edit(embeds=[embed], view=view)
            return
        except discord.NotFound:
            pass

    # هنا نرسل الـ embed الأول كبداية للوحة التحكم الأساسية
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
    await interaction.followup.send("تم تحديث الواجهة الرسمية بنجاح.", ephemeral=True)

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
