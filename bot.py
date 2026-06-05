import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import urllib.parse
import aiohttp
from pathlib import Path
import traceback
import asyncio

# ─── Config ───────────────────────────────────────────────
DATA_FILE = "data/lists.json"
MANAGER_ROLE_NAME = "Archive Manager"
OMDB_API_KEY = "911582c4"

# ─── Data helpers ─────────────────────────────────────────
def load_data() -> dict:
    Path("data").mkdir(parents=True, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        return {"lists": {}, "panel_message": {}}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {"lists": {}, "panel_message": {}}
            if "lists" not in data or not isinstance(data["lists"], dict):
                data["lists"] = {}
            if "panel_message" not in data or not isinstance(data["panel_message"], dict):
                data["panel_message"] = {}
            return data
    except Exception as e:
        print(f"🚨 [Data Error] فشل قراءة الملف: {e}")
        return {"lists": {}, "panel_message": {}}

def save_data(data: dict):
    Path("data").mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def can_manage(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(r.name == MANAGER_ROLE_NAME for r in member.roles)

def get_title(item) -> str:
    return item.get("title", "—") if isinstance(item, dict) else str(item)

def get_poster(item) -> str:
    return item.get("poster", "") if isinstance(item, dict) else ""

def get_desc(item) -> str:
    return item.get("desc", "") if isinstance(item, dict) else ""

def get_ratings(item) -> dict:
    return item.get("ratings", {}) if isinstance(item, dict) else {}

def get_year(item) -> str:
    return item.get("year", "") if isinstance(item, dict) else ""

# ─── OMDB Async Fetcher ───────────────────────────────────
async def fetch_official_theatrical_details(query: str) -> dict:
    try:
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://www.omdbapi.com/?apikey={OMDB_API_KEY}&t={encoded_query}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=6) as response:
                if response.status == 200:
                    data = json.loads(await response.text())
                    if data.get("Response") == "True":
                        return {
                            "title": data.get("Title", query),
                            "poster": data.get("Poster") if data.get("Poster") != "N/A" else "",
                            "year": data.get("Year", ""),
                            "ratings": {}}
    except Exception as e:
        print(f"🚨 [OMDb Error]: {e}")
    return {"title": query, "poster": "", "year": "", "ratings": {}}

# ─── Embeds Builder ───────────────────────────────────────
def _build_item_embed(list_name: str, item: dict, real_index: int, total_items: int, all_lists_data: dict) -> discord.Embed:
    embed = discord.Embed(color=0xd3beab)
    year = get_year(item)
    
    embed.set_author(name=f"🔴 List: {list_name.upper()}")
    embed.title = f"[{real_index + 1}] {get_title(item)}" + (f" ({year})" if year else "")
    
    content = ""
    desc = get_desc(item).strip()
    if desc:
        content += f"**📝 الوصف:**\n{desc}"
        
    ratings = get_ratings(item)
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
    poster = get_poster(item)
    if poster and poster.startswith("http"):
        embed.set_image(url=poster)
    return embed

def build_panel_embed(data: dict) -> discord.Embed:
    list_names = list(data["lists"].keys())
    if list_names:
        lines = []
        for k, v in data["lists"].items():
            lines.append(f"🔴 **{k.upper()}** —  `{len(v.get('items', []))} Entries`")
        lines_str = "\n".join(lines)
    else:
        lines_str = "لا توجد قوائم متوفرة حالياً."
    return discord.Embed(title="🌿 Wonderland Lists", description=f"\n{lines_str}\n", color=0xd3beab)

# ─── Ephemeral Reaction Listener Helper ───────────────────
async def setup_ephemeral_close_reaction(interaction: discord.Interaction):
    try:
        msg = await interaction.original_response()
        await msg.add_reaction("❌")

        def check(reaction, user):
            return user.id == interaction.user.id and str(reaction.emoji) == "❌" and reaction.message.id == msg.id

        try:
            await interaction.client.wait_for("reaction_add", check=check)
            await interaction.delete_original_message()
        except Exception:
            pass
    except Exception as e:
        print(f"🚨 [Reaction Close Error]: {e}")

# ─── Modals ───────────────────────────────────────────────
class RenameListModal(discord.ui.Modal):
    def __init__(self, current_list_name: str):
        super().__init__(title="تغيير اسم اللستة")
        self.current_list_name = current_list_name
        self.new_name = discord.ui.TextInput(label="اسم اللستة الجديد", placeholder="مثال: MARVEL", required=True)
        self.add_item(self.new_name)

    async def on_submit(self, interaction: discord.Interaction):
        new_list_name = self.new_name.value.strip()
        if not new_list_name:
            await interaction.response.defer(ephemeral=True)
            return
        data = load_data()
        if new_list_name in data["lists"]:
            await interaction.response.defer(ephemeral=True)
            return
        if self.current_list_name in data["lists"]:
            data["lists"][new_list_name] = data["lists"].pop(self.current_list_name)
            save_data(data)
            
        embed = discord.Embed(
            title=f"تخصيص اللستة — {new_list_name}",
            description="اختر الإجراء المطلوب:\n\n🗑️ **حذف اللستة بالكامل**\n📝 **تعديل اسم اللستة**\n🔀 **تغيير ترتيب اللستات**",
            color=0x5865F2
        )
        cust_view = CustomizeListView(new_list_name, list(data["lists"].keys()))
        await interaction.response.edit_message(embeds=[embed], view=cust_view)
        await refresh_panel_silent(interaction.client)

# ─── Rating System ────────────────────────────────────────
class RateItemSelectView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str], items: list, page: int = 0, origin_index: int = 0):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.list_names = list_names
        self.items = items
        self.page = page
        self.origin_index = origin_index

        options = []
        start = page * 23
        end = start + 23
        page_items = items[start:end]

        if page > 0:
            options.append(discord.SelectOption(label=f"◀️ الصفحة السابقة ({start-23+1} - {start})", value="prev_page_rate"))

        for i, item in enumerate(page_items):
            real_idx = start + i
            title = get_title(item)
            year = get_year(item)
            label = f"{real_idx+1:02d}. {title}" + (f" ({year})" if year else "")
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(label=label, value=str(real_idx)))

        if len(items) > end:
            options.append(discord.SelectOption(label=f"▶️ الصفحة التالية ({end+1} - {min(end+23, len(items))})", value="next_page_rate"))

        select = discord.ui.Select(
            placeholder="⭐ اختر العمل المراد تقييمه...",
            min_values=1, max_values=1,
            options=options, row=0
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "next_page_rate":
            view = RateItemSelectView(self.list_name, self.list_names, self.items, self.page + 1, self.origin_index)
            await interaction.response.edit_message(view=view)
            return
        elif val == "prev_page_rate":
            view = RateItemSelectView(self.list_name, self.list_names, self.items, self.page - 1, self.origin_index)
            await interaction.response.edit_message(view=view)
            return

        index = int(val)
        item = self.items[index]
        view = RateStarsView(self.list_name, self.list_names, index, item, self.origin_index)
        
        embed = interaction.message.embeds[0]
        embed.title = f"⭐ تقييم: {get_title(item)}"
        await interaction.response.edit_message(embeds=[embed], view=view)

class RateStarsView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str], index: int, item: dict, origin_index: int):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.list_names = list_names
        self.index = index
        self.item = item
        self.origin_index = origin_index

        stars_options = [
            discord.SelectOption(label="⭐ نجمة واحدة", value="1"),
            discord.SelectOption(label="⭐⭐ نجمتان", value="2"),
            discord.SelectOption(label="⭐⭐⭐ ثلاث نجوم", value="3"),
            discord.SelectOption(label="⭐⭐⭐⭐ أربع نجوم", value="4"),
            discord.SelectOption(label="⭐⭐⭐⭐⭐ خمس نجوم", value="5"),
        ]
        select = discord.ui.Select(
            placeholder="اختر عدد النجوم للاعتماد...",
            min_values=1, max_values=1,
            options=stars_options, row=0
        )
        select.callback = self.on_stars_select
        self.add_item(select)

    async def on_stars_select(self, interaction: discord.Interaction):
        stars = int(interaction.data["values"][0])
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 0 <= self.index < len(items):
            if "ratings" not in items[self.index] or not isinstance(items[self.index]["ratings"], dict):
                items[self.index]["ratings"] = {}
            items[self.index]["ratings"][interaction.user.display_name] = stars
            save_data(data)
            
        await interaction.response.send_message(f"✅ تم تسجيل تقييمك ({stars} نجوم) لـ **{get_title(items[self.index])}** بنجاح!", ephemeral=True)
        try:
            await interaction.delete_original_message()
        except Exception:
            pass
            
        await update_global_list_message(interaction, self.list_name, self.origin_index)

# ─── Global Message Update Helper ────────────────────────
async def update_global_list_message(interaction: discord.Interaction, list_name: str, item_index: int):
    data = load_data()
    items = data["lists"].get(list_name, {}).get("items", [])
    if items:
        embed = _build_item_embed(list_name, items[item_index], item_index, len(items), data["lists"])
        target_jump_page = item_index // 23
        view = ListView(list_name, items, can_manage(interaction.user), list(data["lists"].keys()), data["lists"], item_index, target_jump_page)
        
        panel_info = data.get("panel_message", {})
        guild_key = str(interaction.guild.id)
        msg_id = panel_info.get(guild_key)
        if msg_id:
            try:
                msg = await interaction.channel.fetch_message(int(msg_id))
                await msg.edit(embeds=[embed], view=view)
            except Exception:
                pass

# ─── Modals: إضافة وتعديل الأعمال ──────────────────────────
class AddItemModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(title="إضافة عمل للستة")
        self.list_name = list_name
        self.list_names = list_names
        self.item_title = discord.ui.TextInput(label="اسم الفيلم أو المسلسل (للبحث)", placeholder="مثال: Iron Man", required=True)
        self.item_desc = discord.ui.TextInput(label="الوصف أو تقييمك الخاص", style=discord.TextStyle.paragraph, required=False, placeholder="يمكنك ترك هذا الحقل فارغاً تماماً...")
        self.add_item(self.item_title)
        self.add_item(self.item_desc)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        details = await fetch_official_theatrical_details(self.item_title.value)
        details["desc"] = self.item_desc.value.strip() if self.item_desc.value else ""
        data = load_data()
        if self.list_name in data["lists"]:
            data["lists"][self.list_name]["items"].append(details)
            save_data(data)
            items = data["lists"][self.list_name]["items"]
            
            last_idx = len(items) - 1
            await update_global_list_message(interaction, self.list_name, last_idx)
            
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        dash_view = ManageDashboardView(self.list_name, self.list_names)
        await interaction.message.edit(embeds=[mgr_embed], view=dash_view)

class EditItemDetailsModal(discord.ui.Modal):
    def __init__(self, list_name: str, list_names: list[str], index: int, item: dict):
        super().__init__(title="تعديل تفاصيل العمل")
        self.list_name = list_name
        self.list_names = list_names
        self.index = index
        self.new_title = discord.ui.TextInput(label="اسم الفيلم الجديد", default=get_title(item), required=True)
        self.new_desc = discord.ui.TextInput(label="الوصف الجديد (اتركه فارغاً لإلغائه)", style=discord.TextStyle.paragraph, default=get_desc(item), required=False)
        self.new_order = discord.ui.TextInput(label="الترتيب الجديد في القائمة (رقم)", default=str(index + 1), required=True)
        self.new_year = discord.ui.TextInput(label="السنة (مثال: 2008)", default=get_year(item), required=False)
        self.add_item(self.new_title)
        self.add_item(self.new_desc)
        self.add_item(self.new_order)
        self.add_item(self.new_year)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_pos = int(self.new_order.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True)
            return
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if target_pos < 1 or target_pos > len(items):
            target_pos = len(items)
        curr_item = items.pop(self.index)
        curr_item["title"] = self.new_title.value
        curr_item["desc"] = self.new_desc.value.strip() if self.new_desc.value else ""
        curr_item["year"] = self.new_year.value.strip()
        items.insert(target_pos - 1, curr_item)
        save_data(data)
        
        new_idx = target_pos - 1
        await update_global_list_message(interaction, self.list_name, new_idx)
        
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        dash_view = ManageDashboardView(self.list_name, self.list_names)
        await interaction.response.edit_message(embeds=[mgr_embed], view=dash_view)

class ReorderListsModal(discord.ui.Modal):
    def __init__(self, list_names: list[str]):
        super().__init__(title="تغيير ترتيب اللستات")
        self.list_names = list_names
        current_order = "\n".join(f"{i+1}. {name}" for i, name in enumerate(list_names))
        self.new_order_input = discord.ui.TextInput(
            label="الترتيب الجديد (اكتب أسماء اللستات)",
            style=discord.TextStyle.paragraph,
            placeholder=current_order,
            default=current_order,
            required=True
        )
        self.add_item(self.new_order_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_lines = self.new_order_input.value.strip().splitlines()
        new_order = []
        for line in raw_lines:
            line = line.strip()
            if not line:
                continue
            if line[0].isdigit():
                parts = line.split(".", 1)
                if len(parts) == 2:
                    line = parts[1].strip()
            new_order.append(line)
        data = load_data()
        existing = list(data["lists"].keys())
        invalid = [n for n in new_order if n not in existing]
        if invalid:
            await interaction.response.defer(ephemeral=True)
            return
        missing = [n for n in existing if n not in new_order]
        new_order += missing
        data["lists"] = {name: data["lists"][name] for name in new_order}
        save_data(data)
        
        await refresh_panel_silent(interaction.client)
        await interaction.response.send_message("✅ تم إعادة ترتيب القوائم بنجاح في البانل الرئيسي العامة!", ephemeral=True)

# ─── Item Editor Dashboard ────────────────────────────────
class ItemEditorDashboard(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str], num: int, item: dict):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.list_names = list_names
        self.index = num - 1
        self.item = item

    @discord.ui.button(label="✏️ تعديل (الاسم / الوصف / التترتيب / السنة)", style=discord.ButtonStyle.primary, row=0)
    async def edit_fields(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EditItemDetailsModal(self.list_name, self.list_names, self.index, self.item))

    @discord.ui.button(label="🗑️ حذف هذا العمل نهائياً", style=discord.ButtonStyle.danger, row=0)
    async def delete_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if 0 <= self.index < len(items):
            items.pop(self.index)
            save_data(data)
            
        panel_info = data.get("panel_message", {})
        guild_key = str(interaction.guild.id)
        msg_id = panel_info.get(guild_key)
        if msg_id:
            try:
                msg = await interaction.channel.fetch_message(int(msg_id))
                if not items:
                    embed = discord.Embed(title=f"{self.list_name.upper()}", description="هذه القائمة فارغة حالياً.", color=0xd3beab)
                    view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"], 0)
                else:
                    embed = _build_item_embed(self.list_name, items[0], 0, len(items), data["lists"])
                    view = ListView(self.list_name, items, can_manage(interaction.user), self.list_names, data["lists"], 0)
                await msg.edit(embeds=[embed], view=view)
            except Exception:
                pass
                
        mgr_embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        dash_view = ManageDashboardView(self.list_name, self.list_names)
        await interaction.response.edit_message(embeds=[mgr_embed], view=dash_view)

    @discord.ui.button(label="⬅️ عودة للوحة التحكم", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_mgr(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        dash_view = ManageDashboardView(self.list_name, self.list_names)
        await interaction.response.edit_message(embeds=[embed], view=dash_view)

# ─── Dropdowns ───────────────────────────────────────────
class ManageItemDropdown(discord.ui.Select):
    def __init__(self, list_name: str, list_names: list[str], items: list, page: int = 0):
        self.list_name = list_name
        self.list_names = list_names
        self.items = items
        self.page = page

        options = []
        start = page * 23
        end = start + 23
        page_items = items[start:end]

        if page > 0:
            options.append(discord.SelectOption(label=f"◀️ إدارة الصفحة السابقة ({start-23+1} - {start})", value="prev_page_mgr"))

        for i, item in enumerate(page_items):
            real_idx = start + i
            title = get_title(item)
            year = get_year(item)
            label = f"{real_idx+1:02d}. {title}" + (f" ({year})" if year else "")
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(label=label, value=str(real_idx)))

        if len(items) > end:
            options.append(discord.SelectOption(label=f"▶️ إدارة الصفحة التالية ({end+1} - {min(end+23, len(items))})", value="next_page_mgr"))

        placeholder = f"✏️ تعديل الأعمال ({start+1} - {min(end, len(items))})..." if items else "✏️ تعديل محتويات اللستة..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "next_page_mgr":
            view = ManageDashboardView(self.list_name, self.list_names, self.page + 1)
            await interaction.response.edit_message(view=view)
            return
        if val == "prev_page_mgr":
            view = ManageDashboardView(self.list_name, self.list_names, self.page - 1)
            await interaction.response.edit_message(view=view)
            return

        index = int(val)
        item = self.items[index]
        embed = discord.Embed(
            title=f"🛠️ التحكم بالعمل: {get_title(item)}",
            description=(
                f"**الترتيب الحالي:** {index + 1}\n"
                f"**السنة:** {get_year(item) or 'غير محددة'}\n"
                f"**الوصف الحالي:** {get_desc(item) or 'لا يوجد وصف حالي لهذا العمل.'}"
            ),
            color=0xd3beab
        )
        editor_view = ItemEditorDashboard(self.list_name, self.list_names, index + 1, item)
        await interaction.response.edit_message(embeds=[embed], view=editor_view)


class JumpToMovieDropdown(discord.ui.Select):
    def __init__(self, list_name: str, list_names: list[str], items: list, page: int = 0):
        self.list_name = list_name
        self.list_names = list_names
        self.items = items
        self.page = page

        options = []
        start = page * 23
        end = start + 23
        page_items = items[start:end]

        if page > 0:
            options.append(discord.SelectOption(label=f"◀️ عرض الصفحة السابقة", value="prev_page_jump"))

        for i, item in enumerate(page_items):
            real_idx = start + i
            title = get_title(item)
            year = get_year(item)
            label = f"{real_idx+1:02d}. {title}" + (f" ({year})" if year else "")
            if len(label) > 100:
                label = label[:97] + "..."
            options.append(discord.SelectOption(label=label, value=str(real_idx)))

        if len(items) > end:
            options.append(discord.SelectOption(label=f"▶️ عرض بقية الأفلام", value="next_page_jump"))

        placeholder = "🔍 الانتقال السريع..."
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options, row=3)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        data = load_data()
        if val == "next_page_jump":
            embed = interaction.message.embeds[0]
            view = ListView(self.list_name, self.items, can_manage(interaction.user), self.list_names, data["lists"], current_item_idx=self.page*23, jump_page=self.page + 1)
            await interaction.response.edit_message(embeds=[embed], view=view)
            return
        elif val == "prev_page_jump":
            embed = interaction.message.embeds[0]
            view = ListView(self.list_name, self.items, can_manage(interaction.user), self.list_names, data["lists"], current_item_idx=(self.page-1)*23, jump_page=self.page - 1)
            await interaction.response.edit_message(embeds=[embed], view=view)
            return

        index = int(val)
        embed = _build_item_embed(self.list_name, self.items[index], index, len(self.items), data["lists"])
        view = ListView(self.list_name, self.items, can_manage(interaction.user), self.list_names, data["lists"], current_item_idx=index, jump_page=self.page)
        await interaction.response.edit_message(embeds=[embed], view=view)

# ─── Customize List View ──────────────────────────────────
class CustomizeListView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.list_names = list_names

    @discord.ui.button(label="📝 اسم اللستة", style=discord.ButtonStyle.blurple, row=0)
    async def rename_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameListModal(self.list_name))

    @discord.ui.button(label="❌ حذف اللستة", style=discord.ButtonStyle.danger, row=0)
    async def delete_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        await refresh_panel_silent(interaction.client)
        await interaction.response.delete_original_message()

    @discord.ui.button(label="🔀 ترتيب اللستات", style=discord.ButtonStyle.secondary, row=1)
    async def reorder_lists_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReorderListsModal(self.list_names))

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back_to_mgr(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"إدارة — {self.list_name}",
            description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.",
            color=0xd3beab
        )
        dash_view = ManageDashboardView(self.list_name, self.list_names)
        await interaction.response.edit_message(embeds=[embed], view=dash_view)

# ─── Manage Dashboard View ───────────────────────────────
class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name: str, list_names: list[str], page: int = 0):
        super().__init__(timeout=None)
        self.list_name = list_name
        self.list_names = list_names
        self.page = page
        
        data = load_data()
        items = data["lists"].get(list_name, {}).get("items", [])
        
        if items:
            self.add_item(ManageItemDropdown(list_name, list_names, items, page))
        else:
            self.add_item(discord.ui.Select(
                placeholder="❌ اللستة فارغة حالياً، لا توجد أعمال لتعديلها.",
                disabled=True,
                options=[discord.SelectOption(label="قائمة الأفلام فارغة تماماً", value="empty_fallback")],
                row=2
            ))

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.primary, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name, self.list_names))

    @discord.ui.button(emoji="🎨", style=discord.ButtonStyle.blurple, row=0)
    async def customize_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"تخصيص اللستة — {self.list_name}",
            description="اختر الإجراء المطلوب:\n\n🗑️ **حذف اللستة بالكامل**\n📝 **تعديل اسم اللستة**\n🔀 **تغيير ترتيب اللستات**",
            color=0x5865F2
        )
        cust_view = CustomizeListView(self.list_name, self.list_names)
        await interaction.response.edit_message(embeds=[embed], view=cust_view)

# ─── Buttons ──────────────────────────────────────────────
class RateButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str], origin_index: int):
        super().__init__(emoji="⭐", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names
        self.origin_index = origin_index

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        if not items:
            await interaction.response.defer(ephemeral=True)
            return
        
        embed = discord.Embed(
            title="⭐ قائمة التقييم السريعة", 
            description="اختر العمل الذي ترغب في تقييمه من القائمة المنسدلة بالأسفل.\n\n❌ *اضغط على ريأكشن الاكس بالأسفل لإغلاق هذه اللوحة في أي وقت.*", 
            color=0xd3beab
        )
        target_page = self.origin_index // 23
        rate_view = RateItemSelectView(self.list_name, self.list_names, items, target_page, self.origin_index)
        await interaction.response.send_message(embeds=[embed], view=rate_view, ephemeral=True)
        
        asyncio.create_task(setup_ephemeral_close_reaction(interaction))


class ManageButton(discord.ui.Button):
    def __init__(self, list_name: str, list_names: list[str]):
        super().__init__(emoji="⚙️", style=discord.ButtonStyle.success, row=0)
        self.list_name = list_name
        self.list_names = list_names

    async def callback(self, interaction: discord.Interaction):
        if not can_manage(interaction.user):
            await interaction.response.send_message("❌ لا تملك الصلاحيات الكافية (Archive Manager) لاستخدام لوحة التحكم.", ephemeral=True)
            return
        try:
            embed = discord.Embed(
                title=f"إدارة — {self.list_name}",
                description="التحكم الكامل والذكي بمحتوى وتعديل القائمة، ترتيب الأعمال، تغيير اسم اللستة أو حذفها.\n\n❌ *اضغط على ريأكشن الاكس بالأسفل لإغلاق هذه اللوحة في أي وقت.*",
                color=0xd3beab
            )
            dash_view = ManageDashboardView(self.list_name, self.list_names, 0)
            await interaction.response.send_message(embeds=[embed], view=dash_view, ephemeral=True)
            
            asyncio.create_task(setup_ephemeral_close_reaction(interaction))
        except Exception as e:
            print(f"🚨 خطأ أثناء فتح لوحة التحكم: {e}")
            traceback.print_exc()


class HomeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(emoji="🏠", style=discord.ButtonStyle.success, row=0)

    async def callback(self, interaction: discord.Interaction):
        data = load_data()
        list_names = list(data["lists"].keys())
        embed = build_panel_embed(data)
        view = PanelView(list_names, data["lists"])
        await interaction.response.edit_message(embeds=[embed], view=view)

# ─── Panel View ───────────────────────────────────────────
class PanelView(discord.ui.View):
    def __init__(self, list_names: list[str], all_lists_data: dict, page: int = 0):
        super().__init__(timeout=None)
        self.list_names = list_names
        self.all_lists_data = all_lists_data
        self.page = page

        LISTS_PER_PAGE = 20
        total_pages = max(1, (len(list_names) + LISTS_PER_PAGE - 1) // LISTS_PER_PAGE)
        start = page * LISTS_PER_PAGE
        page_lists = list_names[start:start + LISTS_PER_PAGE]

        for i, name in enumerate(page_lists):
            row = i // 5
            btn = discord.ui.Button(
                label=name,
                custom_id=f"archive_list_{name}_{page}",
                style=discord.ButtonStyle.danger,
                row=row
            )
            btn.callback = self.make_callback(name)
            self.add_item(btn)

        if total_pages > 1:
            if page > 0:
                prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=4, custom_id=f"panel_prev_{page}")
                prev_btn.callback = self.make_page_callback(page - 1)
                self.add_item(prev_btn)

            page_indicator = discord.ui.Button(
                label=f"{page + 1} / {total_pages}",
                style=discord.ButtonStyle.secondary,
                row=4,
                disabled=True,
                custom_id="panel_page_indicator"
            )
            self.add_item(page_indicator)

            if page < total_pages - 1:
                next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=4, custom_id=f"panel_next_{page}")
                next_btn.callback = self.make_page_callback(page + 1)
                self.add_item(next_btn)

    def make_callback(self, name: str):
        async def callback(interaction: discord.Interaction):
            data = load_data()
            lst = data["lists"].get(name)
            if not lst:
                await interaction.response.defer(ephemeral=True)
                return
            items = lst.get("items", [])
            if not items:
                embed = discord.Embed(title=f"{name.upper()}", description="هذه القائمة فارغة حالياً.", color=0xd3beab)
                view = ListView(name, items, can_manage(interaction.user), self.list_names, data["lists"], 0)
            else:
                embed = _build_item_embed(name, items[0], 0, len(items), data["lists"])
                view = ListView(name, items, can_manage(interaction.user), self.list_names, data["lists"], 0)
            await interaction.response.edit_message(embeds=[embed], view=view)
        return callback

    def make_page_callback(self, new_page: int):
        async def callback(interaction: discord.Interaction):
            data = load_data()
            list_names = list(data["lists"].keys())
            embed = build_panel_embed(data)
            view = PanelView(list_names, data["lists"], page=new_page)
            await interaction.response.edit_message(embeds=[embed], view=view)
        return callback

# ─── List View ───────────────────────────────────────────
class ListView(discord.ui.View):
    def __init__(self, current_list_name: str, items: list, is_manager: bool, list_names: list[str], all_lists_data: dict, current_item_idx: int = 0, jump_page: int = 0):
        super().__init__(timeout=None)
        self.current_list_name = current_list_name
        self.list_names = list_names
        self.all_lists_data = all_lists_data
        self.items = items
        self.current_item_idx = current_item_idx

        self.add_item(ManageButton(current_list_name, list_names))
        self.add_item(HomeButton())
        self.add_item(RateButton(current_list_name, list_names, current_item_idx))

        if len(items) > 1:
            prev_btn = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary, row=1)
            prev_btn.callback = self.make_move_cb(-1)
            self.add_item(prev_btn)

            indicator_btn = discord.ui.Button(
                label=f"{current_item_idx + 1}/{len(items)}",
                style=discord.ButtonStyle.primary,
                disabled=True,
                row=1
            )
            self.add_item(indicator_btn)

            next_btn = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self.make_move_cb(1)
            self.add_item(next_btn)
        else:
            current_btn = discord.ui.Button(
                label=f"1/1" if items else "0/0",
                style=discord.ButtonStyle.primary,
                disabled=True,
                row=1
            )
            self.add_item(current_btn)

        if items:
            self.add_item(JumpToMovieDropdown(current_list_name, list_names, items, jump_page))

    def make_move_cb(self, direction: int):
        async def callback(interaction: discord.Interaction):
            new_idx = self.current_item_idx + direction
            if new_idx < 0 or new_idx >= len(self.items):
                await interaction.response.defer(ephemeral=True)
                return
                
            data = load_data()
            embed = _build_item_embed(self.current_list_name, self.items[new_idx], new_idx, len(self.items), data["lists"])
            target_jump_page = new_idx // 23
            view = ListView(self.current_list_name, self.items, can_manage(interaction.user), self.list_names, data["lists"], current_item_idx=new_idx, jump_page=target_jump_page)
            await interaction.response.edit_message(embeds=[embed], view=view)
        return callback

# ─── Global Panel Message Freshner ────────────────────────
async def refresh_panel_silent(bot: commands.Bot):
    data = load_data()
    list_names = list(data["lists"].keys())
    embed = build_panel_embed(data)
    view = PanelView(list_names, data["lists"])

    panel_info = data.get("panel_message", {})
    for guild_id_str, msg_id in panel_info.items():
        try:
            guild = bot.get_guild(int(guild_id_str))
            if not guild:
                continue
            for channel in guild.text_channels:
                try:
                    msg = await channel.fetch_message(int(msg_id))
                    await msg.edit(embeds=[embed], view=view)
                    print(f"✅ [Panel] تم تحديث البانل في #{channel.name}")
                    break
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    continue
                except Exception:
                    continue
        except Exception as e:
            print(f"🚨 [Panel Restore] خطأ: {e}")

async def refresh_panel_interaction(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_data()
    list_names = list(data["lists"].keys())
    embed = build_panel_embed(data)
    view = PanelView(list_names, data["lists"])
    panel_info = data.get("panel_message", {})
    guild_key = str(interaction.guild.id)
    old_msg_id = panel_info.get(guild_key)

    if old_msg_id:
        try:
            old_msg = await channel.fetch_message(int(old_msg_id))
            await old_msg.edit(embeds=[embed], view=view)
            return
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"🚨 Error updating panel: {e}")

    msg = await channel.send(embed=embed, view=view)
    data.setdefault("panel_message", {})[guild_key] = msg.id
    save_data(data)

# ─── Bot Core ─────────────────────────────────────────────
class WonderlandBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("✨ [Bot] setup_hook تم تشغيله")

bot = WonderlandBot()
tree = bot.tree

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await refresh_panel_silent(bot)

@bot.command(name="sync")
async def manual_sync(ctx):
    if ctx.author.guild_permissions.administrator:
        await ctx.send("⏳ جاري مزامنة الأوامر...")
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ تم تحديث {len(synced)} أمر بنجاح!")
        except Exception as e:
            await ctx.send(f"❌ فشلت المزامنة: {e}")
    else:
        await ctx.send("❌ هذا أمر للمشرفين فقط.")

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print("🚨 [Slash Command Error]:")
    traceback.print_exc()
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(".", ephemeral=True, delete_after=0)
    except Exception:
        pass

# ─── Slash Commands ───────────────────────────────────────
@tree.command(name="panel", description="Post/refresh the main dashboard.")
@app_commands.guild_only()
async def cmd_panel(interaction: discord.Interaction):
    await interaction.response.send_message(".", ephemeral=True, delete_after=0)
    try:
        await refresh_panel_interaction(interaction, interaction.channel)
    except Exception as e:
        print(f"🚨 Error in panel command: {e}")
        traceback.print_exc()

@tree.command(name="list_create", description="Create a new category.")
@app_commands.guild_only()
@app_commands.describe(name="Category name")
async def cmd_list_create(interaction: discord.Interaction, name: str):
    await interaction.response.send_message(".", ephemeral=True, delete_after=0)
    if not can_manage(interaction.user):
        return
    name = name.strip()
    data = load_data()
    if name not in data["lists"]:
        data["lists"][name] = {"items": []}
        save_data(data)
        await refresh_panel_silent(interaction.client)

TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)
