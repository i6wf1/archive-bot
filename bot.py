import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import urllib.parse
import aiohttp
from pathlib import Path
import traceback
from typing import List, Dict, Any

# ─── CONFIGURATION & THEME ────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"
OMDB_API_KEY = "911582c4"

# ثيم الألوان الفخم والمريح للعين (الذهبي الداكن المطفي مع الرمادي السينمائي)
THEME_COLOR = 0xC29D53  
ERROR_COLOR = 0xE74C3C
SUCCESS_COLOR = 0x2ECC71

# ─── DATA ACCESS LAYER ────────────────────────────────────
def load_data() -> dict:
    Path("data").mkdir(parents=True, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {"lists": {}, "panel_message": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"lists": {}, "panel_message": {}}
            data.setdefault("lists", {})
            data.setdefault("panel_message", {})
            return data
    except Exception as e:
        print(f"🚨 [Data Error] {e}")
        return {"lists": {}, "panel_message": {}}

def save_data(data: dict):
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def can_manage(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(r.name == MANAGER_ROLE_NAME for r in member.roles)

# ─── OMDB API EXTENSION ──────────────────────────────────
async def fetch_movie_details(query: str) -> dict:
    try:
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_query}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=8) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("Response") == "True":
                        return {
                            "title": data.get("Title", query),
                            "poster": data.get("Poster") if data.get("Poster") != "N/A" else "",
                            "year": data.get("Year", ""),
                            "genre": data.get("Genre", "Unknown"),
                            "imdb": data.get("imdbRating", "N/A"),
                            "ratings": {}
                        }
    except Exception as e:
        print(f"🚨 [OMDb API Error]: {e}")
    return {"title": query, "poster": "", "year": "", "genre": "Unknown", "imdb": "N/A", "ratings": {}}

# ─── THE ARTISTIC EMBED BUILDERS ─────────────────────────
def build_main_panel_embed(lists_data: dict) -> discord.Embed:
    embed = discord.Embed(
        title="✨ W O N D E R L A N D   A R C H I V E ✨",
        description="```📌 أهلاً بك في الأرشيف السينمائي الفاخر. تنقل عبر القوائم بالضغط على الأزرار أدناه.
```\n",
        color=THEME_COLOR
    )
    
    if lists_data:
        for name, content in lists_data.items():
            items_count = len(content.get("items", []))
            embed.add_field(
                name=f"🎬 {name.upper()}",
                value=f"┗ 📝 `{items_count:02d}` مادة مؤرشفة\n \u200e",
                inline=True
            )
    else:
        embed.description += "⚠️ لا توجد قوائم تم إنشاؤها حتى الآن. استخدم `/list_create` للبدء."
        
    embed.set_footer(text="Premium Archive Experience • Wonderland System")
    return embed

def build_item_embed(list_name: str, item: dict, current_index: int, total_items: int) -> discord.Embed:
    title = item.get("title", "—")
    year = item.get("year", "")
    genre = item.get("genre", "غير محدد")
    imdb = item.get("imdb", "N/A")
    desc = item.get("desc", "").strip()
    poster = item.get("poster", "")
    ratings = item.get("ratings", {})

    display_title = f"{current_index}/{total_items} • {title}"
    if year:
        display_title += f" ({year})"

    embed = discord.Embed(
        title=display_title,
        description=f"🎨 **القسم:** `{list_name.upper()}`\n✨ **التصنيف:** `{genre}` | ⭐️ **IMDb:** `{imdb}/10`\n" + "─" * 32,
        color=THEME_COLOR
    )

    if desc:
        embed.add_field(name="💬 مراجعة وتفاصيل", value=f"```fix\n{desc}```", inline=False)
    else:
        embed.add_field(name="💬 مراجعة وتفاصيل", value="*لا يوجد وصف مضاف لهذا العمل بعد.*", inline=False)

    if ratings:
        rating_lines = []
        total_stars = 0
        for user_name, stars in ratings.items():
            stars_str = "⭐" * int(stars)
            rating_lines.append(f"▫️ **{user_name}** » {stars_str}")
            total_stars += int(stars)
        
        avg_rating = total_stars / len(ratings)
        embed.add_field(
            name=f"👥 تقييمات مجتمع وندرلاند ({avg_rating:.1f}/5)", 
            value="\n".join(rating_lines), 
            inline=False
        )
    else:
        embed.add_field(name="👥 تقييمات المجتمع", value="*لم يقم أحد بتقييم هذا العمل بعد. كن الأول!*", inline=False)

    if poster and poster.startswith("http"):
        embed.set_image(url=poster) # صدمة بصرية: البوستر يعرض بحجم كبير فخم بدلاً من ثمنيل صغير!

    embed.set_footer(text="استخدم الأزرار أدناه للتنقل أو الإدارة بسرعة وسلاسة")
    return embed

# ─── INTERACTIVE INTERFACES (VIEWS) ──────────────────────

class MainPanelView(discord.ui.View):
    def __init__(self, list_names: List[str]):
        super().__init__(timeout=None)
        
        # قائمة منسدلة ذكية جداً وفخمة لتبديل الأقسام بلمسة واحدة
        if list_names:
            options = [discord.SelectOption(label=f"قسم: {name.upper()}", emoji="🎬", value=name) for name in list_names[:25]]
            self.add_item(MainPanelDropdown(options))

class MainPanelDropdown(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="🎯 اختر القائمة السينمائية المراد استعراضها...", min_values=1, max_values=1, options=options, custom_id="wd_main_dropdown")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        data = load_data()
        list_name = self.values[0]
        items = data["lists"].get(list_name, {}).get("items", [])
        
        if not items:
            embed = discord.Embed(title=f"🎬 {list_name.upper()}", description="```⚠️ هذه القائمة فارغة تماماً حالياً.
```", color=THEME_COLOR)
            view = EmptyListView(list_name, list(data["lists"].keys()))
            await interaction.message.edit(embeds=[embed], view=view)
            return

        embed = build_item_embed(list_name, items[0], 1, len(items))
        view = DynamicListView(list_name, items, 0, list(data["lists"].keys()))
        await interaction.message.edit(embeds=[embed], view=view)

class EmptyListView(discord.ui.View):
    def __init__(self, list_name: str, all_lists: List[str]):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.all_lists = all_lists

    @discord.ui.button(label="➕ إضافة عمل", style=discord.ButtonStyle.primary, emoji="✨")
    async def add_first(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_manage(interaction.user):
            return await interaction.response.send_message("⚠️ عذراً، هذا الزر مخصص للمشرفين فقط.", ephemeral=True)
        await interaction.response.send_modal(AddItemModal(self.list_name, self.all_lists, 0))

    @discord.ui.button(label="⚙️ لوحة التحكم", style=discord.ButtonStyle.secondary, emoji="🛠️")
    async def go_mgr(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_manage(interaction.user):
            return await interaction.response.send_message("⚠️ عذراً، هذا الزر مخصص للمشرفين فقط.", ephemeral=True)
        await show_management_dashboard(interaction, self.list_name, self.all_lists)

    @discord.ui.button(label="🏠 الرئيسية", style=discord.ButtonStyle.success, emoji="🌿")
    async def go_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        await return_to_hub(interaction)

class DynamicListView(discord.ui.View):
    def __init__(self, list_name: str, items: list, current_index: int, all_lists: List[str]):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.items = items
        self.index = current_index
        self.all_lists = all_lists

        # تعطيل الأزرار تلقائياً بناءً على موضع الصفحة لمنع الأخطاء البصرية
        self.btn_prev.disabled = (self.index == 0)
        self.btn_next.disabled = (self.index >= len(items) - 1)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.index -= 1
        embed = build_item_embed(self.list_name, self.items[self.index], self.index + 1, len(self.items))
        await interaction.message.edit(embeds=[embed], view=DynamicListView(self.list_name, self.items, self.index, self.all_lists))

    @discord.ui.button(label="⭐ قيم الآن", style=discord.ButtonStyle.success, row=0)
    async def btn_rate(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DirectRateModal(self.list_name, self.items, self.index, self.all_lists))

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.index += 1
        embed = build_item_embed(self.list_name, self.items[self.index], self.index + 1, len(self.items))
        await interaction.message.edit(embeds=[embed], view=DynamicListView(self.list_name, self.items, self.index, self.all_lists))

    @discord.ui.button(label="⚙️ الإدارة الذكية", style=discord.ButtonStyle.danger, emoji="🛠️", row=1)
    async def btn_manage(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not can_manage(interaction.user):
            return await interaction.response.send_message("⚠️ لوحة الإدارة مخصصة لإداريي الأرشيف فقط!", ephemeral=True)
        await show_management_dashboard(interaction, self.list_name, self.all_lists)

    @discord.ui.button(label="🏠 القائمة الرئيسية", style=discord.ButtonStyle.primary, emoji="⚜️", row=1)
    async def btn_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        await return_to_hub(interaction)


# ─── MANAGEMENT DASHBOARD SYSTEM ──────────────────────────
async def show_management_dashboard(interaction: discord.Interaction, list_name: str, all_lists: List[str]):
    embed = discord.Embed(
        title=f"🛠️ نظام التحكم — {list_name.upper()}",
        description="```fix\nمن هنا يمكنك ترميم وتعديل محتوى القائمة بالكامل، إضافة أعمال جديدة، تغيير مكان الترتيب أو الحذف الفوري.```",
        color=THEME_COLOR
    )
    view = ManagementDashboardView(list_name, all_lists)
    if interaction.response.is_done():
        await interaction.message.edit(embeds=[embed], view=view)
    else:
        await interaction.response.edit_message(embeds=[embed], view=view)

class ManagementDashboardView(discord.ui.View):
    def __init__(self, list_name: str, all_lists: List[str]):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.all_lists = all_lists

        data = load_data()
        items = data["lists"].get(list_name, {}).get("items", [])
        
        # قائمة منسدلة داخل لوحة التحكم لتحديد فيلم وتعديله فوراً دون تعقيد
        if items:
            options = []
            for i, item in enumerate(items[:25]):
                label = f"{i+1:02d}. {item.get('title')}"
                options.append(discord.SelectOption(label=label[:100], description=f"السنة: {item.get('year') or 'غير محددة'}", value=str(i)))
            self.add_item(ManagementDropdownSelector(list_name, all_lists, options))

    @discord.ui.button(label="➕ إضافة عمل للأرشيف", style=discord.ButtonStyle.primary, row=0)
    async def add_item_dash(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name, self.all_lists))

    @discord.ui.button(label="✏️ تعديل اسم اللستة", style=discord.ButtonStyle.secondary, row=0)
    async def rename_list_dash(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameListModal(self.list_name))

    @discord.ui.button(label="🗑️ حذف اللستة بالكامل", style=discord.ButtonStyle.danger, row=0)
    async def delete_list_dash(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        await return_to_hub(interaction)

    @discord.ui.button(label="⬅️ العودة لاستعراض القائمة", style=discord.ButtonStyle.success, emoji="🎬", row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if not items:
            embed = discord.Embed(title=f"🎬 {self.list_name.upper()}", description="```⚠️ هذه القائمة فارغة تماماً حالياً.
```", color=THEME_COLOR)
            await interaction.message.edit(embeds=[embed], view=EmptyListView(self.list_name, self.all_lists))
            return
        embed = build_item_embed(self.list_name, items[0], 1, len(items))
        await interaction.message.edit(embeds=[embed], view=DynamicListView(self.list_name, items, 0, self.all_lists))

class ManagementDropdownSelector(discord.ui.Select):
    def __init__(self, list_name: str, all_lists: List[str], options: list):
        super().__init__(placeholder="🎯 اختر فيلماً لتعديله أو نقله أو حذفه فوراً...", min_values=1, max_values=1, options=options, row=2)
        self.list_name = list_name
        self.all_lists = all_lists

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        item = items[index]
        
        embed = discord.Embed(
            title=f"🛠️ خيارات تعديل: {item.get('title')}",
            description=f"**الترتيب الحالي:** `{index + 1}`\n**سنة الإنتاج:** `{item.get('year') or '—'}`\n" + "─"*30,
            color=THEME_COLOR
        )
        await interaction.response.edit_message(embeds=[embed], view=ItemEditorDashboard(self.list_name, self.all_lists, index, item))

class ItemEditorDashboard(discord.ui.View):
    def __init__(self, list_name: str, all_lists: List[str], index: int, item: dict):
        super().__init__(timeout=120)
        self.list_name = list_name
        self.all_lists = all_lists
        self.index = index
        self.item = item

    @discord.ui.button(label="✏️ تعديل كامل البيانات والترتيب", style=discord.ButtonStyle.primary, row=0)
    async def edit_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditItemDetailsModal(self.list_name, self.all_lists, self.index, self.item))

    @discord.ui.button(label="🗑️ حذف هذا العمل", style=discord.ButtonStyle.danger, row=0)
    async def delete_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 0 <= self.index < len(items):
            items.pop(self.index)
            save_data(data)
        await show_management_dashboard(interaction, self.list_name, self.all_lists)

    @discord.ui.button(label="⬅️ إلغاء والعودة للوحة الإدارة", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_management_dashboard(interaction, self.list_name, self.all_lists)


# ─── MODALS SYSTEM (POPUP WINDOWS) ───────────────────────

class DirectRateModal(discord.ui.Modal):
    def __init__(self, list_name: str, items: list, index: int, all_lists: List[str]):
        super().__init__(title="⭐ تقييم العمل السينمائي")
        self.list_name = list_name
        self.items = items
        self.index = index
        self.all_lists = all_lists
        
        self.stars = discord.ui.TextInput(label="التقييم من 1 إلى 5 نجوم فقط", placeholder="أدخل رقم من 1 إلى 5...", min_length=1, max_length=1, required=True)
        self.add_item(self.stars)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            val = int(self.stars.value)
            if not (1 <= val <= 5): raise ValueError
        except ValueError:
            return await interaction.followup.send("❌ التقييم يجب أن يكون رقماً بين 1 و 5 فقط.", ephemeral=True)

        data = load_data()
        current_items = data["lists"].get(self.list_name, {}).get("items", [])
        if self.index < len(current_items):
            current_items[self.index].setdefault("ratings", {})[interaction.user.display_name] = val
            save_data(data)
            
            embed = build_item_embed(self.list_name, current_items[self.index], self.index + 1, len(current_items))
            await interaction.message.edit(embeds=[embed], view=DynamicListView(self.list_name, current_items, self.index, self.all_lists))
            await interaction.followup.send("✅ تم تسجيل تقييمك الفخم بنجاح وتحديث اللوحة!", ephemeral=True)

class AddItemModal(discord.ui.Modal):
    def __init__(self, list_name: str, all_lists: List[str], target_index: int = None):
        super().__init__(title="➕ إضافة فيلم / مسلسل جديد")
        self.list_name = list_name
        self.all_lists = all_lists
        
        self.query = discord.ui.TextInput(label="اسم العمل (بالإنجليزي لبحث تلقائي دقيق)", placeholder="مثال: Interstellar أو Breaking Bad", required=True)
        self.desc = discord.ui.TextInput(label="اكتب رأيك الشخصي أو الوصف (اختياري)", style=discord.TextStyle.paragraph, required=False)
        self.add_item(self.query)
        self.add_item(self.desc)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        details = await fetch_movie_details(self.query.value)
        details["desc"] = self.desc.value.strip() if self.desc.value else ""
        
        data = load_data()
        if self.list_name in data["lists"]:
            data["lists"][self.list_name]["items"].append(details)
            save_data(data)
            
            items = data["lists"][self.list_name]["items"]
            # فتح الصفحة الجديدة فوراً لعرض العمل المضاف بصدمة بصرية سريعة
            embed = build_item_embed(self.list_name, items[-1], len(items), len(items))
            await interaction.message.edit(embeds=[embed], view=DynamicListView(self.list_name, items, len(items) - 1, self.all_lists))
            await interaction.followup.send("✨ تم سحب بيانات العمل تلقائياً وإدراجه في الأرشيف الفاخر!", ephemeral=True)

class EditItemDetailsModal(discord.ui.Modal):
    def __init__(self, list_name: str, all_lists: List[str], index: int, item: dict):
        super().__init__(title="✏️ تعديل تفاصيل وترتيب العمل")
        self.list_name = list_name
        self.all_lists = all_lists
        self.index = index
        
        self.title_in = discord.ui.TextInput(label="العنوان", default=item.get("title"), required=True)
        self.desc_in = discord.ui.TextInput(label="الوصف والمراجعة", style=discord.TextStyle.paragraph, default=item.get("desc"), required=False)
        self.year_in = discord.ui.TextInput(label="السنة", default=item.get("year"), required=False)
        self.order_in = discord.ui.TextInput(label="رقم الترتيب في اللستة حالياً", default=str(index + 1), required=True)
        
        self.add_item(self.title_in)
        self.add_item(self.desc_in)
        self.add_item(self.year_in)
        self.add_item(self.order_in)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            target_pos = int(self.order_in.value) - 1
        except ValueError:
            return await interaction.followup.send("❌ الترتيب يجب أن يكون رقماً صحيحاً.", ephemeral=True)

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        
        if 0 <= self.index < len(items):
            curr_item = items.pop(self.index)
            curr_item["title"] = self.title_in.value
            curr_item["desc"] = self.desc_in.value.strip() if self.desc_in.value else ""
            curr_item["year"] = self.year_in.value.strip()
            
            # حماية لمنع خروج الترتيب عن الحدود
            if target_pos < 0: target_pos = 0
            if target_pos > len(items): target_pos = len(items)
            
            items.insert(target_pos, curr_item)
            save_data(data)
        
        await show_management_dashboard(interaction, self.list_name, self.all_lists)
        await interaction.followup.send("✅ تم تحديث تفاصيل العمل وإعادة تعيين ترتيبه بذكاء!", ephemeral=True)

class RenameListModal(discord.ui.Modal):
    def __init__(self, current_name: str):
        super().__init__(title="📝 إعادة تسمية القسم")
        self.current_name = current_name
        self.new_name = discord.ui.TextInput(label="اسم القسم الجديد", placeholder="مثال: Anime", required=True)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        name = self.new_name.value.strip()
        if not name: return
        
        data = load_data()
        if name in data["lists"]:
            return await interaction.followup.send("❌ يوجد قسم آخر بنفس هذا الاسم بالفعل.", ephemeral=True)
            
        if self.current_name in data["lists"]:
            data["lists"][name] = data["lists"].pop(self.current_name)
            save_data(data)
            await return_to_hub(interaction)
            await interaction.followup.send(f"✅ تم تغيير اسم القسم بنجاح إلى **{name.upper()}**!", ephemeral=True)


# ─── CORE GLOBAL UTILITIES ────────────────────────────────
async def return_to_hub(interaction: discord.Interaction):
    data = load_data()
    all_lists = list(data["lists"].keys())
    embed = build_main_panel_embed(data["lists"])
    view = MainPanelView(all_lists)
    if interaction.response.is_done():
        await interaction.message.edit(embeds=[embed], view=view)
    else:
        await interaction.response.edit_message(embeds=[embed], view=view)

async def refresh_panel(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_data()
    all_lists = list(data["lists"].keys())
    embed = build_main_panel_embed(data["lists"])
    view = MainPanelView(all_lists)
    
    guild_key = str(interaction.guild.id)
    old_msg_id = data.get("panel_message", {}).get(guild_key)

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(int(old_msg_id))
            await old_msg.edit(embeds=[embed], view=view)
            await interaction.followup.send("🔄 تم تحديث لوحة التحكم الرئيسية الفاخرة!", ephemeral=True)
            return
        except Exception:
            pass

    msg = await channel.send(embed=embed, view=view)
    data.setdefault("panel_message", {})[guild_key] = msg.id
    save_data(data)
    await interaction.followup.send("👑 تم إنشاء لوحة التحكم الأسطورية الجديدة في الروم!", ephemeral=True)


# ─── BOT INITIALIZATION ───────────────────────────────────
class WonderlandBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("✨ [System] الهيكل الجديد مستقر وجاهز للتشغيل والتحليق بالكامل.")

bot = WonderlandBot()

@bot.event
async def on_ready():
    print(f"👑 [Online] تم تشغيل الفخامة بنجاح باسم: {bot.user}")

# ─── SLASH COMMANDS LAYER ─────────────────────────────────
@bot.tree.command(name="panel", description="👑 قم بنشر وتحديث لوحة التحكم الرئيسية والأرشيف الفاخر.")
@app_commands.guild_only()
async def cmd_panel(interaction: discord.Interaction):
    if not can_manage(interaction.user):
        return await interaction.response.send_message("⚠️ عذراً، هذا الأمر مخصص لإدارة الأرشيف فقط.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await refresh_panel(interaction, interaction.channel)

@bot.tree.command(name="list_create", description="➕ إنشاء قسم أو تصنيف سينمائي جديد داخل الأرشيف.")
@app_commands.guild_only()
@app_commands.describe(name="اسم القسم الفاخر الجديد (مثال: HORROR)")
async def cmd_list_create(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user):
        return await interaction.response.send_message("⚠️ عذراً، ليس لديك الصلاحيات الكافية لإنشاء أقسام.", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    name = name.strip()
    data = load_data()
    
    if name in data["lists"]:
        return await interaction.followup.send("⚠️ هذا القسم موجود ومدرج مسبقاً في الأرشيف.", ephemeral=True)
        
    data["lists"][name] = {"description": "", "items": []}
    save_data(data)
    await interaction.followup.send(f"✅ تم تأسيس القسم الفاخر الجديد **{name.upper()}** بنجاح!", ephemeral=True)

@bot.command(name="sync")
async def manual_sync(ctx):
    if ctx.author.guild_permissions.administrator:
        await ctx.send("⏳ جاري مزامنة الـ Slash Commands إلى ديسكورد فوراً...")
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"👑 تم تحديث ومزامنة `{len(synced)}` أمر بنجاح خارق!")
        except Exception as e:
            await ctx.send(f"❌ فشلت المزامنة: {e}")

# نظام ذكي لالتقاط الأخطاء لضمان عدم توقف البوت أو انهياره أبداً
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print("🚨 [Critical Error Captured]:")
    traceback.print_exc()
    try:
        msg = "❌ حدث خطأ غير متوقع أثناء معالجة الأمر البصري. تم حفظ تفاصيل المشكلة لحلها فوراً."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)
