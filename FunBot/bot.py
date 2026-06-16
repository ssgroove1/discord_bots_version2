import discord, os, asyncio, aiohttp, random, re
from dotenv import load_dotenv
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from pathlib import Path

env_path = Path(__file__).parent.parent / "shared.env"
load_dotenv(env_path)
PREFIX = os.getenv('COMMAND_PREFIX')
COUNT_ROLE = int(os.getenv('COUNT_BAD_ROLE'))
COMMANDS_CHANNEL = int(os.getenv('COMMANDS_CHANNEL_ID'))
MOD_COMMANDS_CHANNEL = int(os.getenv('MOD_COMMANDS_CHANNEL_ID'))
COUNT_CHANNEL = int(os.getenv('COUNT_CHANNEL_ID'))
GUILD_ID = int(os.getenv('GUILD_ID'))
DEVELOPER_ID = int(os.getenv('DEVELOPER_ID'))

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ========== КЛАССЫ КНОПОК ==========

# --- КНОПКА УЧАСТИЯ (Для публичного сообщения) ---
class PublicGiveawayView(discord.ui.View):
    def __init__(self, manager):
        super().__init__(timeout=None)
        self.manager = manager

    @discord.ui.button(label="учᴀᴄᴛʙоʙᴀᴛь (0)", style=discord.ButtonStyle.green, custom_id="public_join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.manager.is_ended or self.manager.is_cancelled:
            return await interaction.response.send_message("Розыгрыш уже завершен или отменен.", ephemeral=True)

        user_id = interaction.user.id
        if user_id in self.manager.participants:
            self.manager.participants.remove(user_id)
            await interaction.response.send_message("Вы вышли из розыгрыша.", ephemeral=True)
        else:
            self.manager.participants.add(user_id)
            await interaction.response.send_message("Вы успешно зарегистрировались в розыгрыше!", ephemeral=True)

        button.label = f"учᴀᴄᴛʙоʙᴀᴛь ({len(self.manager.participants)})"
        await interaction.message.edit(view=self)


# --- КНОПКИ УПРАВЛЕНИЯ (Для скрытого сообщения) ---
class AdminControlView(discord.ui.View):
    def __init__(self, manager):
        super().__init__(timeout=None)
        self.manager = manager

    @discord.ui.button(label="оᴛʍᴇниᴛь ᴩозыᴦᴩыɯ", style=discord.ButtonStyle.red, custom_id="admin_cancel")
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("У вас нет прав для отмены этого розыгрыша.", ephemeral=True)

        if self.manager.is_ended or self.manager.is_cancelled:
            return await interaction.response.send_message("Этот розыгрыш уже нельзя отменить.", ephemeral=True)

        self.manager.is_cancelled = True
        self.manager.event.set()

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        for child in self.manager.public_view.children:
            child.disabled = True
        
        self.manager.public_embed.description = f"{self.manager.description}\n\n<:forbiddenemoji:1515790567555203123> **ᴩозыᴦᴩыɯ быᴧ оᴛʍᴇнᴇн ᴀдʍиниᴄᴛᴩᴀᴛоᴩоʍ.**"
        self.manager.public_embed.color = discord.Color.red()
        await self.manager.public_message.edit(embed=self.manager.public_embed, view=self.manager.public_view)
        
        await interaction.followup.send("Вы успешно отменили розыгрыш.", ephemeral=True)

    @discord.ui.button(label="зᴀʙᴇᴩɯиᴛь доᴄᴩочно", style=discord.ButtonStyle.blurple, custom_id="admin_end_fast")
    async def end_fast_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("У вас нет прав для досрочного завершения.", ephemeral=True)

        if self.manager.is_ended or self.manager.is_cancelled:
            return await interaction.response.send_message("Розыгрыш нельзя завершить.", ephemeral=True)

        self.manager.is_ended = True
        self.manager.event.set()

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        await interaction.followup.send("Розыгрыш завершается досрочно...", ephemeral=True)

# --- ГЛАВНЫЙ КОНТРОЛЛЕР РОЗЫГРЫША ---
class GiveawayManager:
    def __init__(self, description, prize_text_after, mention_role):
        self.description = description
        self.prize_text_after = prize_text_after
        self.mention_role = mention_role
        self.participants = set()
        self.is_cancelled = False
        self.is_ended = False
        self.event = asyncio.Event()
        
        self.public_message = None
        self.public_embed = None
        self.public_view = None

class get_flower(discord.ui.View):
    def __init__(self, user, target, text):
        super().__init__(timeout=300)
        self.user = user
        self.target = target
        self.text = text
    
    @discord.ui.button(label="Получить цветы", style=discord.ButtonStyle.primary, emoji="💐")
    async def get_flower_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user == self.user:
            await interaction.response.send_message(f"🤗 Вы не можете отменить действие!", ephemeral=True)
            return
        elif interaction.user != self.target:
            await interaction.response.send_message(f"😡 Цветы не для вас!", ephemeral=True)
            return
        button.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(f"🌹 {self.user.mention} дарит вам цветы!\n💌 С пожеланиями: {self.text}", ephemeral=True)

# ========== НЕКОТОРЫЙ РЕФЕРЕНС ==========

next_number_in_count_channel = 1

with open('gifs\hug_gifs.txt', 'r', encoding='utf-8') as f:
    hug_gifs = f.readlines()
with open('gifs\kiss_gifs.txt', 'r', encoding='utf-8') as f:
    kiss_gifs = f.readlines()
with open('gifs\hello_gifs.txt', 'r', encoding='utf-8') as f:
    hello_gifs = f.readlines()
with open('gifs\\flower_gifs.txt', 'r', encoding='utf-8') as f:
    flower_gifs = f.readlines()
with open('gifs\pat_gifs.txt', 'r', encoding='utf-8') as f:
    pat_gifs = f.readlines()
with open('gifs\slap_gifs.txt', 'r', encoding='utf-8') as f:
    slap_gifs = f.readlines()
with open('gifs\\bite_gifs.txt', 'r', encoding='utf-8') as f:
    bite_gifs = f.readlines()
with open('gifs\cry_gifs.txt', 'r', encoding='utf-8') as f:
    cry_gifs = f.readlines()

async def remove_role_at_time(member: discord.Member, role: discord.Role, minutes: int):
    """Снимает роль в определённое время"""
    remove_time = datetime.now() + timedelta(minutes=minutes)
    await discord.utils.sleep_until(remove_time)
    
    if role in member.roles:
        await member.remove_roles(role, reason="✅ Автоматическое снятие роли")

def make_interaction_command(gifs_list: list, embed_title: str, action_verb: str, color: discord.Color, self_error: str, no_gifs_error: str = "❌ Нет доступных гифок! Проверьте файл"):
    async def command_func(interaction: discord.Interaction, member: discord.Member):
        if not gifs_list:
            await interaction.response.send_message(no_gifs_error, ephemeral=True)
            return
        if member == interaction.user:
            await interaction.response.send_message(self_error, ephemeral=True)
            return
        random_gif = random.choice(gifs_list)
        embed = discord.Embed(
            title=embed_title,
            description=f"{interaction.user.mention} {action_verb} {member.mention}!",
            color=color
        )
        embed.set_image(url=random_gif)
        await interaction.response.send_message(embed=embed, ephemeral=False)
    
    return command_func

def parse_duration(duration_str: str) -> int:
    match = re.match(r"^(\d+)([smhd])$", duration_str.lower())
    if not match:
        return 0
    amount, unit = match.groups()
    amount = int(amount)
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return amount * units[unit]

# ========== КОМАНДА ДЛЯ РЕГУЛИРОВКИ ==========

@bot.tree.command(name='sync', description='Синхронизировать команды.')
@app_commands.default_permissions(administrator=True)
async def sync_command(interaction: discord.Interaction):
    if interaction.user.id != DEVELOPER_ID:
        await interaction.response.send_message("❌ У тебя нет прав для этой команды.", ephemeral=True)
        return
    # Синхронизация
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)
    await interaction.response.send_message("✅ Команды синхронизированы для текущего сервера.", ephemeral=False)

@bot.tree.command(name='set', description='Техническая команда. (Игнорируйте)')
@app_commands.default_permissions(administrator=True)
async def set_count(interaction: discord.Interaction, last_count: int = 0):
    global next_number_in_count_channel
    if interaction.user.id != DEVELOPER_ID:
        await interaction.response.send_message("❌ У тебя нет прав для этой команды.", ephemeral=True)
        return
    next_number_in_count_channel = int(last_count+1)
    await interaction.response.send_message(f"✅ Счетчик в подсчетах изменен. Следующее число {int(next_number_in_count_channel)}", ephemeral=True)

# ========== КОМАНДЫ РАЗВЛЕЧЕНИЯ ==========

@bot.tree.command(name='hug', description='Обнимите дорогого вам человека!')
async def hug_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        hug_gifs,
        "🤗 Обнимашки!",
        "обнимает",
        discord.Color.pink(),
        "😥 Простите, вы не можете обнять самого себя!"
    )(interaction, member)

@bot.tree.command(name='kiss', description='Поцелуйте дорогого вам человека!')
async def kiss_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        kiss_gifs,
        "🤗 Поцелуйчики!",
        "поцеловал",
        discord.Color.brand_red(),
        "😥 Простите, вы не можете поцеловать самого себя!"
    )(interaction, member)

@bot.tree.command(name='pat', description='Погладить пользователя!')
async def pat_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        pat_gifs,
        "🤗 Прижимашки!",
        "погладил",
        discord.Color.purple(),
        "😥 Простите, вы не можете погладить себя!"
    )(interaction, member)

@bot.tree.command(name='hello', description='Поздоровайтесь с пользователем!')
async def hello_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        hello_gifs,
        "🤗 Приветствие!",
        "поздоровался с",
        discord.Color.gold(),
        "😥 Простите, вы не можете поздороваться с собой!"
    )(interaction, member)

@bot.tree.command(name='slap', description='Дать леща пользователю!')
async def slap_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        slap_gifs,
        "😨 Рукоприкладство!",
        "дал леща",
        discord.Color.darker_grey(),
        "😏 Вы не можете ударить себя самого!"
    )(interaction, member)

@bot.tree.command(name='bite', description='Укусить пользователя!')
async def bite_command(interaction: discord.Interaction, member: discord.Member):
    await make_interaction_command(
        bite_gifs,
        "😨 Укусики!",
        "кусает",
        discord.Color.darker_grey(),
        "😱 Вы не можете кусать себя самого!"
    )(interaction, member)

@bot.tree.command(name='cry', description='Заплакать в чате.')
async def cry_func(interaction: discord.Interaction):
    if not cry_gifs:
        await interaction.response.send_message("❌ Нет доступных гифок! Проверьте файл cry_gifs.txt", ephemeral=True)
        return
    random_gif = random.choice(cry_gifs)
    embed = discord.Embed(
        title="😭 Слезки!",
        description=f"{interaction.user.mention} плачет. 😢",
        color=discord.Color.blue()
    )
    embed.set_image(url=random_gif)
    await interaction.response.send_message(embed=embed, ephemeral=False)

@bot.tree.command(name='flower', description='Подарить пользователю записку с цветами!')
async def gift_user(interaction: discord.Interaction, member: discord.Member, text: str = "Всего самого наилучшего! 🤗"):
    if not flower_gifs:
        await interaction.response.send_message("❌ Нет доступных гифок! Проверьте файл flower_gifs.txt", ephemeral=True)
        return
    if member == interaction.user:
        await interaction.response.send_message("😥 Простите, вы не можете подарить цветы себе!", ephemeral=True)
        return
    if member.bot:
        await interaction.response.send_message("🤖 Нельзя подарить цветы боту!", ephemeral=True)
        return
    if len(text) > 150:
        await interaction.response.send_message("❌ Пожелание не может быть длиннее 150 символов!", ephemeral=True)
        return
    view = get_flower(user=interaction.user, target=member, text=text)
    random_gif = random.choice(flower_gifs)
    embed = discord.Embed(
        title="🤗 Цветочки, подарочки!",
        description=f"{interaction.user.mention} подарил {member.mention} цветы! 💕",
        color=discord.Color.brand_red()
    )
    embed.set_image(url=random_gif)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

@bot.tree.command(name='8ball', description="Получить предсказание.")
async def eight_ball(interaction: discord.Interaction, question: str = None):
    if question == None:
        await interaction.response.send_message("❌ Вы должны написать вопрос!", ephemeral=True)
        return
    if len(question) < 5:
        await interaction.response.send_message("❌ Чуть длинее, пожалуйста!", ephemeral=True)
        return
    responses = ["Определённо да!", "Нет, даже не думай...", "Спроси позже...", "Мой источник говорит, что нет.", "Это запретные знания!", "Ответ неоднозначен..."]
    embed = discord.Embed(
        title=f"🔮 Гадание для {interaction.user.display_name}!",
        description=f"಄ **Вопрос:** {question}\n✘ **Ответ:** {random.choice(responses)}",
        color=discord.Color.darker_grey()
    )
    await interaction.response.send_message(embed=embed, ephemeral=False)

# @bot.tree.command(name="herb", description="Смешать травы (Resident Evil)")
# @app_commands.describe(color="Выберите цвет, примеры: зеленая, зеленая+красная")
# async def herb(interaction: discord.Interaction, color: str):
#     herbs = {
#         "зеленая": "Вы восстанавливаете 30 HP 🌿",
#         "красная": "Вы наносите 20 урона + временный бафф 🩸",
#         "синяя": "Снимает отравление (и глупые эффекты) 💙",
#         "зеленая+красная": "60 HP + бафф 💚❤️",
#         "зеленая+синяя": "40 HP + антидот 💚💙"
#     }
    
#     color_lower = color.lower().strip()
#     result = herbs.get(color_lower, "🧪 Трава не сочетается... Попробуй еще раз.")
#     await interaction.response.send_message(f"🍃 {result}")

@bot.tree.command(name="giveaway", description="Запустить новый розыгрыш")
@app_commands.describe(
    описание="Текст самого розыгрыша (что происходит)",
    приз_после_выигрыша="Текст, который пишется при победе",
    время="Через сколько итоги? (Пример: 10m, 2h, 1d)",
    количество_победителей="Сколько человек должно выиграть?",
    роль_для_упоминания="Какую роль пингануть при победе (необязательно)",
    канал="Канал, куда отправить розыгрыш (необязательно)"
)
@app_commands.default_permissions(administrator=True)
async def giveaway(
    interaction: discord.Interaction,
    описание: str,
    приз_после_выигрыша: str,
    время: str,
    количество_победителей: int,
    роль_для_упоминания: discord.Role = None,
    канал: discord.TextChannel = None
):
    if количество_победителей <= 0:
        return await interaction.response.send_message("Количество победителей должно быть больше 0!", ephemeral=True)

    seconds = parse_duration(время)
    if seconds <= 0:
        return await interaction.response.send_message("Неверный формат времени! Используйте например: 30s, 15m, 2h, 1d.", ephemeral=True)

    target_channel = канал if канал else interaction.channel
    end_time = datetime.now(timezone.utc) + timedelta(seconds=seconds)
    timestamp = int(end_time.timestamp())

    manager = GiveawayManager(описание, приз_после_выигрыша, роль_для_упоминания)

    manager.public_embed = discord.Embed(
        title="<:giveawayemoji:1515792000279121930> ⲏⲟⲃыύ ⲣⲟⳅыⲅⲣыɯ! <:giveawayemoji:1515792000279121930>",
        description=f"{описание}\n\n<:luckyemoji:1515790408922173450> **ᴨобᴇдиᴛᴇᴧᴇй:** {количество_победителей}\n⏳ **зᴀʙᴇᴩɯиᴛᴄя:** <t:{timestamp}:R>",
        color=discord.Color.gold(),
    )
    manager.public_embed.set_footer(text="нᴀжʍиᴛᴇ нᴀ ᴋноᴨᴋу нижᴇ, чᴛобы ᴨᴩиняᴛь учᴀᴄᴛиᴇ!")
    manager.public_view = PublicGiveawayView(manager)

    manager.public_message = await target_channel.send(embed=manager.public_embed, view=manager.public_view)
    
    admin_view = AdminControlView(manager)
    await interaction.response.send_message(
        f"✅ Розыгрыш успешно запущен в канале {target_channel.mention}!\nПанель управления доступна только вам ниже:", 
        view=admin_view,
        ephemeral=True
    )

    try:
        await asyncio.wait_for(manager.event.wait(), timeout=float(seconds))
    except asyncio.TimeoutError:
        pass

    if manager.is_cancelled:
        return

    for child in manager.public_view.children:
        child.disabled = True
    
    manager.public_embed.description = f"{описание}\n\n<:luckyemoji:1515790408922173450> **ᴨобᴇдиᴛᴇᴧᴇй:** {количество_победителей}\n<:forbiddenemoji:1515790567555203123> **ᴩозыᴦᴩыɯ зᴀʙᴇᴩɯᴇн!**"
    await manager.public_message.edit(embed=manager.public_embed, view=manager.public_view)

    if not manager.participants:
        await target_channel.send(f"ʙ ᴩозыᴦᴩыɯᴇ **'{описание}'** ниᴋᴛо нᴇ ᴨᴩиняᴧ учᴀᴄᴛиᴇ. ᴨобᴇдиᴛᴇᴧи нᴇ ʙыбᴩᴀны. <:forbiddenemoji:1515790567555203123>")
    else:
        participants_list = list(manager.participants)
        actual_winners_count = min(количество_победителей, len(participants_list))
        winners_ids = random.sample(participants_list, k=actual_winners_count)
        
        winners_mentions = [f"<@{w_id}>" for w_id in winners_ids]
        winners_text = ", ".join(winners_mentions)
        mention_str = f"\n🔔 Уведомление для роли: {manager.mention_role.mention}" if manager.mention_role else ""
        title_text = "<:giveawayemoji:1515792000279121930> ⲣⲉⳅⲩⲗьⲧⲁⲧы ⲣⲟⳅыⲅⲣыɯⲁ! <:giveawayemoji:1515792000279121930>" if actual_winners_count > 1 else "<:giveawayemoji:1515792000279121930> ⲣⲉⳅⲩⲗьⲧⲁⲧ ⲣⲟⳅыⲅⲣыɯⲁ! <:giveawayemoji:1515792000279121930>"

        success_embed = discord.Embed(
            title=title_text,
            description=f"ʙ ᴩозыᴦᴩыɯᴇ **'{описание}'\n**<:luckyemoji:1515790408922173450> ᴨобᴇждᴀюᴛ: {winners_text}!\n\n**<:treasureemoji:1515794261839188199> Ваш выигрыш:** {manager.prize_text_after}{mention_str}",
            color=discord.Color.green(),
        )
        await target_channel.send(content=winners_text, embed=success_embed)

# ========== ТЕКСТОВЫЕ СОБЫТИЕ ==========

@bot.event
async def on_message(message):
    global next_number_in_count_channel
    # Игнорируем сообщения от самого бота
    if message.author == bot.user:
        return
    if bot.user in message.mentions and message.author.id == DEVELOPER_ID:
        await message.channel.send(f"{message.author.mention}, бот ещё жив! ✅")
    if message.channel.id == COUNT_CHANNEL:
        role = message.guild.get_role(COUNT_ROLE)
        special_messages = {
            13: " ᴨоᴧучиᴧ чᴇᴩную ʍᴇᴛᴋу. <:treasureemoji:1515794261839188199>",
            18: " ʙᴨᴀᴧ ʙ ᴄʙои ʙоᴄᴨинᴀния <:level18:1515649945481384016>",
            20: " ᴄъᴇдᴀᴇᴛ ʙᴄᴇ 20 ᴨᴀᴧьцᴇʙ... <:sukuna:1515650121612923041>",
            22: " ᴨᴩоʙᴀᴧиᴧᴄя из ᴩᴇᴀᴧьноᴄᴛи. <:level22:1515650174129537115>",
            40: " дᴀёᴛ ʙᴄᴇʍ 40 ᴄᴇᴋунд... <:deathnote:1515650128789115051>",
            42: ", сорок два, братуха! <a:42:1515650117510758451>",
            52: " ᴨᴇᴩᴇᴇзжᴀᴇᴛ ʙ ᴄᴀнᴋᴛ-ᴨᴇᴛᴇᴩбуᴩᴦ. <:gumball:1514171441803825153>",
            67: ", ᴄиᴋᴄᴛᴇн ᴄᴇʙᴇн. <a:trollge:1515650182044450826>",
            69: ", ⲟⳝⲏⲁⲣⲩⲿⲉⲏⲁ ⲅυⲡⲉⲣⲁⲕⲧυⲃⲏⲟⲥⲧь ⲃ ⲕⲣⲟⲃⲁⲧυ. <:himeno:1514606900506005625>",
            77: " ᴄᴀʍый ᴄчᴀᴄᴛᴧиʙый чᴇᴧоʙᴇᴋ! <:luckyemoji:1515790408922173450>",
            94: " жиʙᴇᴛ ʙ ᴋуᴋоᴧьной ᴀниʍᴀциᴇй. <:level94:1515650133033746493>",
            100: " обнᴀᴩужиᴧ ʙᴄᴇ 100 ʍонᴇᴛ. <:gleipner:1515650176113446974>",
            106: " ᴨᴩоʙᴀᴧиᴧᴄя ʙ ᴘᴏᴄᴋᴇᴛ ᴅᴏᴍᴀɪɴ. <a:106:1515656067323924560>",
            110: " ᴨоᴛᴇᴩяᴧᴄя ʙ ʍоᴄᴋоʙᴄᴋоʍ ʍᴇᴛᴩо. <:110:1515661590941270056>",
            112: " ʙызʙᴀᴧ ϶ᴋᴄᴛᴩᴇнныᴇ ᴄᴧужбы. <:numb112:1515650143612047503>",
            123: " ⲣⲩɯυⲧ ⲃⲥю ⲙⲁⲧⲉⲙⲁⲧυⲕⲩ. <:100000iq:1515650152247853136>",
            131: " иᴦᴩᴀᴇᴛ ʙ ᴦᴧядᴇᴧᴋи! <:131:1515658286827835492>",
            143: " ᴨодчиниᴧ ᴄᴇбᴇ боᴧь. <:kaneki2:1515650126574784544>",
            149: " ʍᴇчᴛᴀᴇᴛ о ᴋоᴋоᴄоʙоʍ оᴄᴛᴩоʙᴇ <:cocao:1515650123135455272>",
            173: ", *хᴩуᴄᴛ ɯᴇи* <:173:1515654169393107024>",
            188: " ᴨᴩоᴨᴀᴧ ʙ оᴛᴇᴧи. <:level188:1515650161253027860>",
            217: " ᴨᴧохо зᴀᴋᴩуᴛиᴧ ɯᴇᴄᴛᴇᴩᴇнᴋу... <:217:1515658577446961204>",
            228: ", ⲙы ⲥ ⲏⲟⲅυ ⲉⳝⲁⲗⲟ ⲥⲏⲟⲥυⲙ! <a:doorbreak:1515650166479130784>",
            300: " υ 300 ⲥⲡⲁⲣⲧⲁⲏⳡⲉⲃ. <:spartan:1515650146602319892>",
            323: " ⲅⲩⲗяⲗ ⲃ ⲗⲉⲥⲩ ⲃ ⲟⲇυⲏⲟɥⲕⲩ... <:323:1515660111279030422>",
            354: " зᴀᴄᴛᴩяᴧ ʙ ᴄᴋоᴩой ʍᴀɯинᴇ. <:level354:1515650155720999033>",
            360: " ⲕⲣⲩⲧυⲧⲥя ⲃⲟⲕⲣⲩⲅ ⲥⲃⲟⲉύ ⲟⲥυ <:360:1515654004271612037>",
            387: " ⲁⲧⲁⲕⲟⲃⲁⲏ ⲗⲉⲅⲟ ⲕⲟⲏⲥⲧⲣⲩⲕⲧⲟⲣⲟⲙ. <:387:1515663226983944324>",
            400: " ⲩⲡⲣⲁⲃⲗяⲉⲧ ⲃⲥⲉⲙυ ⲥⲩⲇьⳝⲁⲙυ... <:deathnote:1515650128789115051>",
            404: " быᴧ удᴀᴧᴇн из ᴩᴇᴀᴧьноᴄᴛи. <:404:1515650144878727310>",
            610: " ⲩⲣⲟⲏυⲗ ⲡⲣⲟⳝυⲣⲕⲩ ⲃ ⲗⲁⳝⲟⲣⲁⲧⲟⲣυυ. <:610:1515656931363262504>",
            650: " ⳅⲁⲥⲏⲩⲗ ⲏⲁ ⲕⲗⲁⲇⳝυպⲉ. <:level650:1515650158615068692>",
            666: ", ᴦоᴄᴛь 666 нᴀɯёᴧ ʙᴀᴄ! <:quest666:1515650185353498674>",
            682: ": ''чᴇɯуя ᴧи ϶ᴛо?'' <a:682:1515654685007020052>",
            699: " быᴧ ᴨоᴛᴇᴩян ᴄᴩᴇди бᴀᴄᴄᴇйноʙ. <:level699:1515650162700058645>",
            777: " ʙыйᴦᴩыʙᴀᴇᴛ ϶ᴛу жизнь. <:hakari:1515650148120658092>",
            830: ", неведомое существо наблюдает. <:level830:1515650160024096798>",
            888: " зᴀᴄᴛᴩяᴧ ʙ бᴇᴄᴋонᴇчноᴄᴛи. <:infinity:1515650142081126400>",
            899: " ⲥⲗυɯⲕⲟⲙ ⲇⲟⲗⲅⲟ ⲥⲙⲟⲧⲣⲉⲗ ⲏⲁ ⳅⲃⲉⳅⲇы. <:level899:1515650157117575319>",
            911: " ᴨозʙониᴧ ʙ ϶ᴋᴄᴛᴩᴇнныᴇ ᴄᴧужбы <:level354:1515650155720999033>",
            939: " ⳅⲁⲅⲣыⳅⲉⲏ ⲇⲟ ⲥⲙⲉⲣⲧυ... <a:939:1515660109395529768>",
            966: " ⲡⲟⲧⲉⲣяⲗⲥя ⲃⲟ ⲥⲏⲉ... <:966:1515660756748730518>",
            974: " очᴇнь ᴧюбиᴛ ᴋиᴛᴛи. <:level974:1514905188928979074>",
            993: " ⳝⲟⲗьɯⲉ ⲏⲉ ɥⲩⲃⲥⲧⲃⲩⲉⲧ ⳝⲟⲗυ... <:kaneki:1515650130135744593>",
            999: " зᴀщᴇᴋоᴛᴀн до ᴄʍᴇᴩᴛи. <:999:1515657420884676618>",
            1111: " ⲡⲣⲟⳝⲩⲇυⲗ 1ⲭ1ⲭ1ⲭ1 <:1x1x1x1:1515650153674051635>", 
            1471: " ᴄбᴩоᴄиᴧ ɸоᴛоᴦᴩᴀɸии нᴇ ʙ ᴛоᴛ чᴀᴛ... <:1471:1515657690494275645>",
            1488: ", нᴇуʍᴇᴄᴛноᴇ чиᴄᴧо. <:gojoplane:1515650183453478943>",
            1492: " оᴛᴋᴩыᴧ ᴀʍᴇᴩиᴋу! <:ship:1515650140352938055>",
            1715: " ᴨⲟⳅⲏᴀᴋⲟʍυᴧᴄя ᴄ υⲏᴛᴇᴩⲏᴇᴛ-ⲇᴩⲩᴦⲟʍ... <:1715:1515661435353432135>",
            1969: " ᴨоᴨᴀᴧ нᴀ ᴧуну! <:moon:1515650138792661042>",
            2012: " объяʙиᴧ о ᴋонцᴇ ᴄʙᴇᴛᴀ! <:explosion:1515650137425449010>",
            2077: " ᴨоᴨᴀᴧ ʙ ᴄʏʙᴇʀᴘᴜɴᴋ! <:Cyberpunk:1515650135948791888>",
            3000: " быᴧ зᴀᴦᴧоᴛᴀн ᴨоᴧноᴄᴛью. <:3000:1515656502072049766>",
            3008: " ᴨᴩоᴨᴀᴧ ʙ ɪᴋᴇᴀ. <:ikea:1515650177405554750>",
            4666: " ⳝыᴧ ᴨⲟⲭυպᴇⲏ ʙ ᴩⲟⲿⲇᴇᴄᴛʙⲟ... <:4666:1515659304777154590>"
        }
        try:
            user_number = int(message.content.strip())
            if user_number != next_number_in_count_channel:
                raise ValueError("Не по порядку")
            if user_number in special_messages:
                await message.channel.send(f"**{message.author.mention}{special_messages[user_number]}**")
            elif user_number % 100 == 0:
                await message.channel.send(f"**ⲡⲟⲗьⳅⲟⲃⲁⲧⲉⲗυ, ⲃы ⲇⲟⲥⲧυⲅⲁⲉⲧⲉ ⲃⲉⲣɯυⲏ! ⲅⲟⲣⲿⲩⲥь ⲃⲁⲙυ! <a:yuik:1514940189988880507>**\nʙы ᴨᴩᴇодоᴧᴇʙᴀᴇᴛᴇ оᴛʍᴇᴛᴋу ʙ {user_number}, нᴇ ᴄдᴀʙᴀйᴛᴇᴄь! <a:oshimai:1514940166626742382>")
            elif user_number % 50 == 0:
                await message.channel.send(f"**ⲡⲟⲗьⳅⲟⲃⲁⲧⲉⲗυ, ⲡⲟⳅⲇⲣⲁⲃⲗяю! <a:makise:1514939694624800818>**\nʙы доɯᴧи до {user_number}, ᴨᴩодоᴧжᴀйᴛᴇ ʙ ᴛоʍ жᴇ духᴇ! <a:oshimai:1514940166626742382>")
            next_number_in_count_channel += 1
        except (ValueError, TypeError):
            await message.delete()
            if role:
                await message.author.add_roles(role, reason="❌ Не число в канале счёта")
            asyncio.create_task(remove_role_at_time(message.author, role, 10))
            await message.channel.send(f"😡 {message.author.mention}, балбес, соблюдай порядок чисел!", delete_after=5)       
    await bot.process_commands(message)

# ========== ОБРАБОТКА ОШИБОК ==========

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f"❌ У вас недостаточно прав для выполнения команды!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Не хватает аргументов! Используйте `!help {ctx.command.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Неверный аргумент! Укажите существующего пользователя.")
    elif isinstance(error, commands.CommandNotFound):
        pass  # Игнорируем неизвестные команды
    else:
        await ctx.send(f"⚠️ Произошла ошибка: {error}")

# ========== ПАРСИНГ САЙТА С ГИФКАМИ ==========

async def fetch_all_gifs(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            html = await response.text()
    soup = BeautifulSoup(html, 'html.parser')
    gif_links = set()  # Используем set, чтобы не было дубликатов

    # 1. Ищем прямые ссылки в тегах <img>
    for img in soup.find_all('img'):
        # Смотрим атрибуты: src, data-src, data-lazy-src
        for attr in ['src', 'data-src', 'data-lazy-src']:
            src = img.get(attr)
            if src and src.endswith('.gif'):
                # Превращаем относительную ссылку //site.com/img.gif в https://site.com/img.gif
                if src.startswith('//'):
                    src = 'https:' + src
                gif_links.add(src)

    # 2. Ищем ссылки в тегах <a> (если гифка обернута в ссылку)
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.endswith('.gif'):
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = url.rstrip('/') + href
            gif_links.add(href)

    return list(gif_links)

# ========== ЗАПУСК БОТА ==========

@bot.event
async def on_ready():
    # page_url = 'https://aniyuki.com/anime-girl-crying-gifs/'
    # links = await fetch_all_gifs(page_url)
    # print(f"✅ Найдено {len(links)} гифок!")
    # for link in links:
    #    print(link)
    try:
        await bot.tree.sync(guild=None)
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    print(f"✅ Бот {bot.user} запущен!")
    print(f"📊 На серверах: {len(bot.guilds)}")
    print(f"🔧 Команд: {len(bot.commands)}")
    await bot.change_presence(
        activity=discord.CustomActivity(
            name="Отвечаю за актив 🍀",
        )
    )
# Запуск бота
if __name__ == "__main__":
    # Загружаем токен из .env файла 
    TOKEN = os.getenv('BOT_TOKEN_FUNBOT')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Токен не найден! Создайте .env файл с BOT_TOKEN")