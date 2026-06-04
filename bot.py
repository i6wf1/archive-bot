import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import urllib.request
import urllib.parse
from pathlib import Path

# ─── Config ───────────────────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"
TMDB_API_KEY = "0bce26c0165650e02aec5943e60395ad"

# ─── Data helpers ─────────────────────────────────────────
def load_data() -> dict:
    Path("data").mkdir(parents=True, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {"lists": {}, "panel_message": {}}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data: dict):
    Path("data").mkdir(parents=True, exist_ok=True)
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

def get_ratings(item) -> dict:
    return item.get("ratings", {}) if isinstance(item, dict) else {}

def get_year(item) -> str:
    return item.get("year", "") if isinstance(item, dict) else ""

# ─── TMDB Official Primary Poster & Year Fetcher ──────────
def fetch_official_theatrical_details(query: str) -> dict:
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={encoded_query}&language=en-US"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            res_data = json.loads(response.read().decode('utf-8'))
            results = res_data.get("results", [])
            if results:
                movie = results[0]
                title = movie.get("original_title") or movie.get("original_name") or movie.get("title") or query
                poster_path = movie.get("poster_path")
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
                
                release_date = movie.get("release_date") or movie.get("first_air_date") or ""
                year = release_date.split("-")[0] if "-" in release_date else ""
                
                return {"title": title, "poster": poster_url, "year": year, "ratings": {}}
    except Exception as e:
        print(f"Error fetching from TMDB: {e}")
    return {"title": query, "poster": "", "year": "", "ratings": {}}

# ─── Clean Natural Embeds Builder ─────────────────────────
def build_separate_embeds(list_name: str, items: list) -> list[discord.Embed]:
    if not items:
        embed = discord.Embed(
            title=f"Wonderland • {list_name.upper()}", 
            description="هذه القائمة فارغة حالياً.", 
            color=0xd3beab
        )
        return [embed]
    
    embeds = []
    
    for i, item in enumerate(items[:10]):
        title = get_title(item)
        desc = get_desc(item).strip()
        poster = get_poster(item)
        ratings = get_ratings(item)
        year = get_year(item)
        
        embed = discord.Embed(color=0xd3beab)
        
        if year:
            embed.title = f"{i+1:02d}. {title} ({year})"
        else:
            embed.title = f"{i+1:02d}. {title}"
        
        content = f"{desc}" if desc else ""
        
        if ratings:
            if content:
                content += "\n\n"
            content += "**👥 تقييمات الأعضاء:**"
            for user_name, star_count in ratings.items():
                try:
                    stars_display = "⭐" * int(star_count)
                except ValueError:
                    stars_display = "⭐"
                content += f"\n▫️ {user_name}: {stars_display}"
                
        embed.description = content if content else None
        
        if poster:
            embed.set_thumbnail(url=poster)
            
        embeds.append(embed)
    return embeds

# ─── Modals ───────────────────────────────────────────────
class RenameListModal(discord.ui.Modal, title="تغيير اسم اللستة"):
    new_name = discord.ui.TextInput(label="اسم اللستة الجديد", placeholder="مثال: MARVEL", required=True)

    def __init__(self, current_list_name: str):
        super().__init__()
        self.current_list_name = current_list_name

    async def on_submit(self, interaction: discord.Interaction):
        new_list_name = self.new_name.value.strip()
        data = load_data()
        
        if not new_list_name or new_list_name in data["lists"]:
            await interaction.response.defer() # صامت
            return

        if self.current_list_name in data["lists"]:
            data["lists"][new_list_name] = data["lists"].pop(self.current_list_name)
            save_data(data)
            await return_to_main_panel(interaction)

class RateItemModal(discord.ui.Modal, title="تقييم العمل بالنجوم"):
    item_number = discord.ui.TextInput(label="رقم الفيلم المراد تقييمه", placeholder="مثال: 1", required=True)
    user_rating = discord.ui.TextInput(label="التقييم (1-5)", placeholder="رقم من 1 إلى 5", min_length=1, max_length=1, required=True)

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.item_number.value)
            stars = int(self.user_rating.value)
        except: return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 1 <= num <= len(items):
            user_key = interaction.user.display_name
            items[num - 1].setdefault("ratings", {})[user_key] = stars
            save_data(data)
            embeds = build_separate_embeds(self.list_name, items)
            view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await interaction.response.edit_message(embeds=embeds, view=view)

class AddItemModal(discord.ui.Modal, title="إضافة عمل للستة"):
    item_title = discord.ui.TextInput(label="اسم العمل", required=True)
    item_desc = discord.ui.TextInput(label="الوصف", style=discord.TextStyle.paragraph, required=False)

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

    async def on_submit(self, interaction: discord.Interaction):
        details = fetch_official_theatrical_details(self.item_title.value)
        details["desc"] = self.item_desc.value.strip()
        data = load_data()
        if self.list_name in data["lists"]:
            data["lists"][self.list_name]["items"].append(details)
            save_data(data)
            items = data["lists"][self.list_name]["items"]
            embeds = build_separate_embeds(self.list_name, items)
            view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
            await interaction.response.edit_message(embeds=embeds, view=view)

class ChooseItemToManageModal(discord.ui.Modal, title="اختيار فيلم للإدارة"):
    item_number = discord.ui.TextInput(label="رقم الفيلم", placeholder="مثال: 1", required=True)

    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__()
        self.list_name = list_name
        self.list_names = list_names

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.item_number.value)
            data = load_data()
            items = data["lists"].get(self.list_name, {}).get("items", [])
            item = items[num - 1]
            embed = discord.Embed(title=f"تعديل: {get_title(item)}", color=0xd3beab)
            view = ItemEditorDashboard(self.list_name, self.list_names, num, item)
            await interaction.response.edit_message(embed=embed, view=view)
        except: await interaction.response.defer()

class EditItemDetailsModal(discord.ui.Modal, title="تعديل التفاصيل"):
    def __init__(self, list_name: str, list_names: list[str], index: int, item: dict):
        super().__init__()
        self.list_name, self.list_names, self.index, self.item = list_name, list_names, index, item
        self.new_title = discord.ui.TextInput(label="الاسم", default=get_title(item))
        self.new_desc = discord.ui.TextInput(label="الوصف", default=get_desc(item), style=discord.TextStyle.paragraph, required=False)
        self.add_item(self.new_title)
        self.add_item(self.new_desc)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        items = data["lists"][self.list_name]["items"]
        items[self.index]["title"] = self.new_title.value
        items[self.index]["desc"] = self.new_desc.value
        save_data(data)
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)

# ─── Dashboards & Views ────────────────────────────────────
class ItemEditorDashboard(discord.ui.View):
    def __init__(self, list_name, list_names, num, item):
        super().__init__()
        self.list_name, self.list_names, self.index, self.item = list_name, list_names, num-1, item

    @discord.ui.button(label="تعديل", style=discord.ButtonStyle.primary)
    async def edit(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(EditItemDetailsModal(self.list_name, self.list_names, self.index, self.item))

    @discord.ui.button(label="حذف", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, btn: discord.ui.Button):
        data = load_data()
        data["lists"][self.list_name]["items"].pop(self.index)
        save_data(data)
        items = data["lists"][self.list_name]["items"]
        embeds = build_separate_embeds(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"])
        await interaction.response.edit_message(embeds=embeds, view=view)

class ListModificationSubView(discord.ui.View):
    def __init__(self, list_name, list_names):
        super().__init__()
        self.list_name, self.list_names = list_name, list_names

    @discord.ui.button(label="تعديل الأفلام", style=discord.ButtonStyle.primary)
    async def edit_items(self, interaction, btn): await interaction.response.send_modal(ChooseItemToManageModal(self.list_name, self.list_names))
    
    @discord.ui.button(label="تعديل الاسم", style=discord.ButtonStyle.secondary)
    async def rename(self, interaction, btn): await interaction.response.send_modal(RenameListModal(self.list_name))
    
    @discord.ui.button(label="حذف اللستة", style=discord.ButtonStyle.danger)
    async def delete(self, interaction, btn):
        data = load_data()
        del data["lists"][self.list_name]
        save_data(data)
        await return_to_main_panel(interaction)

class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name, list_names):
        super().__init__()
        self.list_name, self.list_names = list_name, list_names

    @discord.ui.button(label="اضافة", style=discord.ButtonStyle.primary)
    async def add(self, interaction, btn): await interaction.response.send_modal(AddItemModal(self.list_name, self.list_names))
    
    @discord.ui.button(label="التعديل", style=discord.ButtonStyle.primary)
    async def mod(self, interaction, btn): await interaction.response.edit_message(view=ListModificationSubView(self.list_name, self.list_names))

class ListView(discord.ui.View):
    def __init__(self, current_list_name, items, is_manager, list_names, all_lists_data):
        super().__init__(timeout=None)
        if is_manager: self.add_item(ManageButton(current_list_name, list_names))
        self.add_item(HomeButton())
        self.add_item(RateButton(current_list_name, list_names))

class RateButton(discord.ui.Button):
    def __init__(self, list_name, list_names):
        super().__init__(emoji="⭐", style=discord.ButtonStyle.success)
        self.list_name, self.list_names = list_name, list_names
    async def callback(self, interaction): await interaction.response.send_modal(RateItemModal(self.list_name, self.list_names))

class ManageButton(discord.ui.Button):
    def __init__(self, list_name, list_names):
        super().__init__(emoji="⚙️", style=discord.ButtonStyle.success)
        self.list_name, self.list_names = list_name, list_names
    async def callback(self, interaction): await interaction.response.edit_message(view=ManageDashboardView(self.list_name, self.list_names))

class HomeButton(discord.ui.Button):
    def __init__(self): super().__init__(emoji="🏠", style=discord.ButtonStyle.success)
    async def callback(self, interaction): await return_to_main_panel(interaction)

class PanelView(discord.ui.View):
    def __init__(self, list_names, all_lists_data):
        super().__init__(timeout=None)
        for name in list_names:
            btn = discord.ui.Button(label=f"{name}", style=discord.ButtonStyle.danger)
            btn.callback = self.make_callback(name)
            self.add_item(btn)
    def make_callback(self, name):
        async def callback(interaction):
            data = load_data()
            items = data["lists"][name]["items"]
            embeds = build_separate_embeds(name, items)
            await interaction.response.edit_message(embeds=embeds, view=ListView(name, items, can_manage(interaction.user), list(data["lists"].keys()), data["lists"]))
        return callback

async def return_to_main_panel(interaction):
    data = load_data()
    embed = discord.Embed(title="Wonderland Lists", description="\n".join(f"🔴 **{k.upper()}**" for k in data["lists"]), color=0xd3beab)
    await interaction.response.edit_message(embeds=[embed], view=PanelView(list(data["lists"].keys()), data["lists"]))

# ─── Bot setup ────────────────────────────────────────────
bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())
@bot.event
async def on_ready(): await bot.tree.sync()
@bot.tree.command(name="panel")
async def cmd_panel(interaction): 
    data = load_data()
    embed = discord.Embed(title="Wonderland Lists", color=0xd3beab)
    await interaction.response.send_message(embed=embed, view=PanelView(list(data["lists"].keys()), data["lists"]))
bot.run(os.environ.get("DISCORD_TOKEN"))
