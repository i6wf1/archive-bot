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

    # ❌ removed emoji from title
    embed = discord.Embed(title=title, color=0xE74C3C)
    embed.set_footer(text=f"📂 {list_name}  •  {index+1} من {total}")

    if desc:
        embed.description = f"> {desc}"

    if poster:
        embed.set_image(url=poster)
    else:
        embed.description = (embed.description or "") + "\n\n*لا توجد صورة لهذا العنصر.*"

    return embed

# ─── ALL ITEMS (NOW WITH POSTERS) ─────────────────────────
def build_all_embed(list_name: str, items: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 قائمة كاملة — {list_name}",
        color=0x5865F2
    )

    if not items:
        embed.description = "*القائمة فارغة.*"
        return embed

    desc = ""
    for i, item in enumerate(items, 1):
        title = get_title(item)
        poster = get_poster(item)

        desc += f"**{i:02d}. {title}**\n"
        if poster:
            desc += f"{poster}\n\n"
        else:
            desc += "*لا يوجد بوستر*\n\n"

    embed.description = desc
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

    # 🔁 changed: now edit message instead of new spam
    @discord.ui.button(label="📋 عرض الكل", style=discord.ButtonStyle.secondary, row=1)
    async def show_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = build_all_embed(self.list_name, self.items)
        back_view = BackView(self.list_name, self.items, self.index)

        await interaction.response.edit_message(embed=embed, view=back_view)


# ─── Back View ────────────────────────────────────────────
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


# ─── PANEL VIEW ───────────────────────────────────────────
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
                await interaction.response.send_message("❌ القائمة غير موجودة.", ephemeral=True)
                return

            items = lst.get("items", [])

            if not items:
                await interaction.response.send_message("📭 القائمة فارغة.", ephemeral=True)
                return

            embed = build_item_embed(name, items, 0)
            view  = BrowseView(name, items, 0)

            # 🔁 IMPORTANT: still ephemeral for user-only session
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        return callback


# ─── PANEL REFRESH (EDIT SAME MESSAGE) ────────────────────
async def refresh_panel(guild: discord.Guild, channel: discord.TextChannel):
    data       = load_data()
    list_names = list(data["lists"].keys())

    lines = "\n".join(
        f"📋 **{k}** · {len(v.get('items', []))} عنصر"
        for k, v in data["lists"].items()
    ) if list_names else "*لا توجد قوائم بعد.*"

    embed = discord.Embed(
        title="🗂️ الأرشيف — تصفح القوائم",
        description="اضغط على أي قائمة لتصفحها.\n\n" + lines,
        color=0x2F3136
    )

    panel_info = data.get("panel_message", {})
    guild_key  = str(guild.id)
    old_msg_id = panel_info.get(guild_key)

    view = PanelView(list_names)

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
