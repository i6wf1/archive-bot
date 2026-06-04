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

# ─── Netflix Style Embed (عرض كأنه نتفليكس) ───────────────────
def build_netflix_embed(list_name: str, items: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"🎬  {list_name}",
        color=0xE74C3C
    )
    if not items:
        embed.description = "*هذه القائمة فارغة حالياً.*"
    else:
        description_lines = []
        for i, item in enumerate(items):
            title = get_title(item)
            desc = get_desc(item)
            poster = get_poster(item)
            
            # تنسيق مظهر الفيلم: الرقم والاسم بخط عريض
            item_text = f"**{i+1:02d}. {title}**"
            if desc:
                item_text += f"\n> {desc}"
            if poster:
                item_text += f"\n🖼️ [شاهد البوستر]({poster})"
            
            description_lines.append(item_text)
        
        # دمج العناصر بمسافات لتبدو منسقة ومتسلسلة
        embed.description = "\n\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n".join(description_lines)
        
        # وضع بوستر أول فيلم كصورة مصغرة جانبية كطابع مميز للقائمة
        first_poster = get_poster(items[0])
        if first_poster:
            embed.set_thumbnail(url=first_poster)

    embed.set_footer(text=f"إجمالي العروض: {len(items)}  •  Wonderland Lists")
    return embed

# ─── Modals (النوافذ المنبثقة للتحكم التلقائي) ───────────────────
class AddItemModal(discord.ui.Modal, title="إضافة عنصر جديد"):
    item_title = discord.ui.TextInput(label="اسم الفيلم / العرض", placeholder="مثال: Iron Man", required=True)
    item_desc = discord.ui.TextInput(label="الوصف (اختياري)", style=discord.TextStyle.paragraph, required=False)
    item_poster = discord.ui.TextInput(label="رابط صورة البوستر (اختياري)", placeholder="https://...", required=False)

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
            
            # إعادة تحديث العرض فوراً بعد الإضافة
            items = data["lists"][self.list_name]["items"]
            embed = build_netflix_embed(self.list_name, items)
            view = ListView(self.list_name, items, can_manage(interaction.user))
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("❌ حدث خطأ، القائمة لم تعد موجودة.", ephemeral=True)

class RemoveItemModal(discord.ui.Modal, title="حذف عنصر من القائمة"):
    item_number = discord.ui.TextInput(label="رقم العنصر المراد حذفه", placeholder="مثال: 1", required=True)

    def __init__(self, list_name: str):
        super().__init__()
        self.list_name = list_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.item_number.value)
        except ValueError:
            await interaction.response.send_message("❌ يرجى إدخال رقم صحيح.", ephemeral=True)
            return

        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        
        if num < 1 or num > len(items):
            await interaction.response.send_message(f"❌ رقم غير صحيح. القائمة تحتوي على {len(items)} عناصر فقط.", ephemeral=True)
            return

        items.pop(num - 1)
        save_data(data)
        
        embed = build_netflix_embed(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user))
        await interaction.response.edit_message(embed=embed, view=view)

# ─── Manage Dashboard View (لوحة التحكم الداخلية للستة) ───────────
class ManageDashboardView(discord.ui.View):
    def __init__(self, list_name: str):
        super().__init__(timeout=60)
        self.list_name = list_name

    @discord.ui.button(label="➕ إضافة فيلم", style=discord.ButtonStyle.success, row=0)
    async def add_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AddItemModal(self.list_name))

    @discord.ui.button(label="🗑️ حذف فيلم محدد", style=discord.ButtonStyle.secondary, row=0)
    async def remove_item_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RemoveItemModal(self.list_name))

    @discord.ui.button(label="❌ حذف هذه اللستة بالكامل", style=discord.ButtonStyle.danger, row=1)
    async def delete_list_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        if self.list_name in data["lists"]:
            del data["lists"][self.list_name]
            save_data(data)
        await return_to_main_panel(interaction)

    @discord.ui.button(label="← عودة للمشاهدة", style=discord.ButtonStyle.primary, row=1)
    async def back_to_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_data()
        items = data["lists"].get(self.list_name, {}).get("items", [])
        embed = build_netflix_embed(self.list_name, items)
        view = ListView(self.list_name, items, can_manage(interaction.user))
        await interaction.response.edit_message(embed=embed, view=view)

# ─── List Content View (واجهة عرض الأفلام) ───────────────────
class ListView(discord.ui.View):
    def __init__(self, list_name: str, items: list, is_manager: bool):
        super().__init__(timeout=180)
        self.list_name = list_name
        self.items = items
        
        # إخفاء زر الإدارة إذا لم يكن العضو مسؤولاً
        if not is_manager:
            self.remove_item(self.manage_btn)

    @discord.ui.button(label="⚙️ إدارة القائمة", style=discord.ButtonStyle.secondary, row=0)
    async def manage_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title=f"⚙️ لوحة التحكم — {self.list_name}",
            description="يمكنك إضافة أو حذف محتويات القائمة مباشرة من الأزرار أدناه دون أية أوامر.",
            color=0x2F3136
        )
        await interaction.response.edit_message(embed=embed, view=ManageDashboardView(self.list_name))

    @discord.ui.button(label="🏠 العودة للرئيسية", style=discord.ButtonStyle.primary, row=0)
    async def go_home(self, interaction: discord.Interaction, button: discord.ui.Button):
        await return_to_main_panel(interaction)

# ─── Main Panel View (الواجهة الرئيسية النظيفة) ───────────────────
class PanelView(discord.ui.View):
    def __init__(self, list_names: list[str]):
        super().__init__(timeout=None)
        for name in list_names:
            # التعديل: تم إزالة الإيموجي من اسم الأزرار لتصبح نظيفة تماماً
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
                await interaction.response.send_message(f"❌ القائمة **{name}** غير موجودة.", ephemeral=True)
                return
            items = lst.get("items", [])
            
            # العرض بأسلوب نتفليكس المباشر والمرتب
            embed = build_netflix_embed(name, items)
            view  = ListView(name, items, can_manage(interaction.user))
            await interaction.response.edit_message(embed=embed, view=view)
        return callback

# ─── Return to Main Dashboard Screen ───────────────────────────
async def return_to_main_panel(interaction: discord.Interaction):
    data       = load_data()
    list_names = list(data["lists"].keys())

    # عرض اللستات بطريقة ضخمة، واضحة ومقسمة
    if list_names:
        lines = ""
        for k, v in data["lists"].items():
            lines += f"🔴  **{k.upper()}**\n┗ يحتوي على `{len(v.get('items', []))}` عرض حالياً\n\n"
    else:
        lines = "*لا توجد قوائم متوفرة حالياً.*"

    embed = discord.Embed(
        title="✨ Wonderland Lists",
        description=lines,
        color=0x111111
    )
    embed.set_footer(text="اختر التصنيف المفضل لديك من الأسفل لبدء العرض.")
    view = PanelView(list_names)
    await interaction.response.edit_message(embed=embed, view=view)

# ─── Panel refresh ────────────────────────────────────────
async def refresh_panel(guild: discord.Guild, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())

    if list_names:
        lines = ""
        for k, v in data["lists"].items():
            lines += f"🔴  **{k.upper()}**\n┗ يحتوي على `{len(v.get('items', []))}` عرض حالياً\n\n"
    else:
        lines = "*لا توجد قوائم متوفرة حالياً. يمكنك إنشاؤها عبر أمر /list_create.*"

    embed = discord.Embed(
        title="✨ Wonderland Lists",
        description=lines,
        color=0x111111
    )
    embed.set_footer(text="اختر التصنيف المفضل لديك من الأسفل لبدء العرض.")

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
#  الأمر الوحيد المتبقي لإنشاء اللوحة أو إضافة تصنيف رئيسي جديد
# ══════════════════════════════════════════════════════════
@tree.command(name="panel", description="Post/refresh the main Wonderland Lists dashboard.")
async def cmd_panel(interaction: discord.Interaction):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await refresh_panel(interaction.guild, interaction.channel)
    await interaction.followup.send("✅ تم تحديث واجهة Wonderland Lists!", ephemeral=True)

@tree.command(name="list_create", description="Create a new category list.")
@app_commands.describe(name="Category name")
async def cmd_list_create(interaction: discord.Interaction, name: str):
    if not can_manage(interaction.user):
        await interaction.response.send_message("❌ لا تملك الصلاحية.", ephemeral=True)
        return
    data = load_data()
    if name in data["lists"]:
        await interaction.response.send_message(f"❌ القائمة موجودة مسبقاً.", ephemeral=True)
        return
    data["lists"][name] = {"description": "", "items": []}
    save_data(data)
    await interaction.response.send_message(f"✅ تم إنشاء القائمة المخصصة **{name}**! يرجى تحديث الـ panel.", ephemeral=True)

# ─── Run ──────────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ DISCORD_TOKEN environment variable not set!")

bot.run(TOKEN)
