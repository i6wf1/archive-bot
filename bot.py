import discord
from discord.ext import commands
import json
import os
from pathlib import Path

# ─── Config & Data ─────────────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"

def load_data():
    Path("data").mkdir(exist_ok=True)
    if not os.path.exists(DATA_FILE): return {"lists": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def can_manage(member):
    return member.guild_permissions.administrator or any(r.name == MANAGER_ROLE_NAME for r in member.roles)

# ─── UI Views ──────────────────────────────────────────────
class ListView(discord.ui.View):
    def __init__(self, list_name, list_names, is_manager):
        super().__init__(timeout=None)
        self.list_name, self.list_names = list_name, list_names
        self.add_item(HomeButton())
        if is_manager: self.add_item(ManageButton(list_name, list_names))

class HomeButton(discord.ui.Button):
    def __init__(self): super().__init__(emoji="🏠", style=discord.ButtonStyle.success)
    async def callback(self, interaction): await return_to_main_panel(interaction)

class ManageButton(discord.ui.Button):
    def __init__(self, list_name, list_names):
        super().__init__(emoji="⚙️", style=discord.ButtonStyle.secondary)
        self.list_name, self.list_names = list_name, list_names
    async def callback(self, interaction):
        await interaction.response.edit_message(view=ManageDashboardView(self.list_name, self.list_names))

class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name, list_names):
        super().__init__()
        self.list_name, self.list_names = list_name, list_names

    @discord.ui.button(label="اضافة", style=discord.ButtonStyle.primary)
    async def add(self, interaction, btn):
        # هنا يتم تحديث المحتوى بدون رسائل اضافية
        await interaction.response.edit_message(content="تم فتح نافذة الإضافة (أدخل البيانات في المودال)...", view=self)
        await interaction.followup.send_modal(AddItemModal(self.list_name, self.list_names))

    @discord.ui.button(label="التعديل", style=discord.ButtonStyle.secondary)
    async def mod(self, interaction, btn):
        await interaction.response.edit_message(view=ListModificationSubView(self.list_name, self.list_names))

# ─── Modals (Updates content directly) ─────────────────────
class AddItemModal(discord.ui.Modal, title="إضافة"):
    title = discord.ui.TextInput(label="اسم العمل")
    def __init__(self, list_name, list_names):
        super().__init__()
        self.list_name, self.list_names = list_name, list_names
    async def on_submit(self, interaction):
        data = load_data()
        data["lists"][self.list_name]["items"].append({"title": self.title.value})
        save_data(data)
        # تحديث الرسالة الأصلية فوراً
        embed = discord.Embed(title=self.list_name, description="تمت الإضافة بنجاح.")
        await interaction.response.edit_message(embed=embed, view=ListView(self.list_name, self.list_names, True))

class ListModificationSubView(discord.ui.View):
    def __init__(self, list_name, list_names):
        super().__init__()
        self.list_name, self.list_names = list_name, list_names

    @discord.ui.button(label="حذف اللستة", style=discord.ButtonStyle.danger)
    async def delete(self, interaction, btn):
        data = load_data()
        del data["lists"][self.list_name]
        save_data(data)
        await return_to_main_panel(interaction)

# ─── Panel Logic ───────────────────────────────────────────
async def return_to_main_panel(interaction):
    data = load_data()
    embed = discord.Embed(title="القوائم الرئيسية", description="\n".join(data["lists"].keys()), color=0xd3beab)
    view = PanelView(list(data["lists"].keys()))
    await interaction.response.edit_message(embed=embed, view=view)

class PanelView(discord.ui.View):
    def __init__(self, list_names):
        super().__init__(timeout=None)
        for name in list_names:
            btn = discord.ui.Button(label=name, style=discord.ButtonStyle.primary)
            btn.callback = self.make_callback(name, list_names)
            self.add_item(btn)
    def make_callback(self, name, list_names):
        async def callback(interaction):
            embed = discord.Embed(title=f"قائمة: {name}")
            await interaction.response.edit_message(embed=embed, view=ListView(name, list_names, can_manage(interaction.user)))
        return callback

# ─── Bot Run ──────────────────────────────────────────────
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
@bot.tree.command(name="panel")
async def cmd_panel(interaction): await return_to_main_panel(interaction)
bot.run(os.environ.get("DISCORD_TOKEN"))
