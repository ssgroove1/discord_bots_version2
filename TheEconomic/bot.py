import discord, random, sqlite3, os, time, sys
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from shared.db_logic import DB_Manager

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True

env_path = Path(__file__).parent.parent / "shared.env"
load_dotenv(env_path)
PREFIX = os.getenv('COMMAND_PREFIX')
COMMANDS_CHANNEL, MOD_COMMANDS_CHANNEL = int(os.getenv('COMMANDS_CHANNEL_ID')), int(os.getenv('MOD_COMMANDS_CHANNEL_ID'))
GUILD_ID = int(os.getenv('GUILD_ID'))
DEVELOPER_ID = int(os.getenv('DEVELOPER_ID'))
MOD_LOGS_COMMANDS = int(os.getenv('MOD_LOGS_CHANNEL_ID2'))

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

ADMIN_ROLE_IDS = [1515424488014221524, 1513261409209811055] 
TREE_COST = 10       
MAX_TREES = 10       

roles_shop = {   
    "📖 | 𝘼𝙧𝙘𝙝𝙞𝙫𝙞𝙨𝙩": {'role_id': 1515397238447411362, 'cost': 30}, 
    "📈 | 𝙏𝙧𝙚𝙣𝙙𝙘𝙖𝙨𝙩𝙚𝙧": {'role_id': 1515397844318687233, 'cost': 50}, 
    "🔗 | 𝘾𝙧𝙤𝙨𝙨𝙡𝙞𝙣𝙠𝙚𝙧": {'role_id': 1515396953440129229, 'cost': 100}, 
    "👁️‍🗨️ | 𝙊𝙗𝙨𝙚𝙧𝙫𝙚𝙧": {'role_id': 1515396410231750700, 'cost': 250}, 
    "🎩 | 𝘼𝙧𝙞𝙨𝙩𝙤𝙘𝙧𝙖𝙩": {'role_id': 1515398117426462730, 'cost': 500}, 
}

def is_admin_or_has_role():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator:
            return True
        if hasattr(interaction.user, 'roles') and ADMIN_ROLE_IDS:
            user_role_ids = [role.id for role in interaction.user.roles]
            if any(int(role_id) in user_role_ids for role_id in ADMIN_ROLE_IDS):
                return True
        raise app_commands.errors.MissingPermissions(["administrator"])
    return app_commands.check(predicate)

@bot.tree.command(name='sync', description='Синхронизировать команды.')
@app_commands.default_permissions(administrator=True)
async def sync(interaction: discord.Interaction):
    # Твой ID разработчика, чтобы никто другой не мог вызвать синхронизацию
    if interaction.user.id != DEVELOPER_ID:
        await interaction.response.send_message("❌ У тебя нет прав для этой команды.", ephemeral=True)
        return
    
    # Синхронизация
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)
    await interaction.response.send_message("✅ Команды синхронизированы для текущего сервера.", ephemeral=False)

@bot.tree.command(name="claim", description="Забрать награду.")
async def claim(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    await interaction.response.defer()
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)
    current_time = time.time()
    cooldown_period = 43200
    time_passed = current_time - user_data["last_claim"]

    if time_passed < cooldown_period:
        seconds_left = int(cooldown_period - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        await interaction.followup.send(f"**❌ {interaction.user.mention}, вы уже забирали награду!**\n⌛ Осталось: **{hours} ч. {minutes} мин.**", ephemeral=True)
        return
    chance_max = max(5, 100 - (user_data["points"] * 5))
    reward = random.randint(5, 10) if random.randint(1, 100) <= chance_max else random.randint(1, 5)
    new_points = user_data["points"] + reward

    await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], current_time, user_data["last_water"])
    await interaction.followup.send(f"{interaction.user.mention}, ʙы ᴨоᴧучиᴧи **{reward} <:physpoints:1515371982571704361>**!\nʙᴀɯ ᴛᴇᴋущий бᴀᴧᴀнᴄ: **{new_points} <:physpoints:1515371982571704361>**.")

@bot.tree.command(name="balance", description="Посмотреть баланс.")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is None:
        member = interaction.user
    user_data = await manager.get_user_economic(member.id)
    embed = discord.Embed(title=f"{member.name}'𝙨 𝙥𝙧𝙤𝙛𝙞𝙡𝙚 <:killau1:1515061286969413683>", color=discord.Color.darker_grey())
    garden_status = f"ᴨᴩиобᴩᴇᴛᴇнныᴇ дᴇᴩᴇʙья: **{user_data['trees']}/{MAX_TREES}** <:scarytree:1515372061839589417>"

    embed.add_field(name=f"<:physpoints:1515371982571704361> 𝘽𝙖𝙡𝙖𝙣𝙘𝙚:", value=f"**ʙᴀɯ ᴛᴇᴋущий бᴀᴧᴀнᴄ: {user_data['points']}** <:physpoints:1515371982571704361>", inline=False)
    if user_data["bugs"] > 0:
        garden_status += f"\n**𝙒𝙖𝙧𝙣𝙞𝙣𝙜:** ᴀᴛᴀᴋоʙᴀн жуᴋᴀʍи! оᴄᴛᴀᴧоᴄь ᴨоᴧиʙоʙ: **{user_data['bugs']}** <:scarybug:1515371896173101126>"
    else:
        garden_status += f"\nчиᴄᴛ оᴛ ʙᴩᴇдиᴛᴇᴧᴇй."
        
    embed.add_field(name=f"<:scarytree:1515372061839589417> 𝙂𝙖𝙧𝙙𝙚𝙣:", value=garden_status, inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="shop", description="Показать доступные для покупки товары и роли")
async def shop(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    embed = discord.Embed(title="𝙎𝙚𝙧𝙫𝙚𝙧'𝙨 𝙨𝙝𝙤𝙥 <:killau2:1515061312244289546>", color=discord.Color.darker_grey())
    text = f"**<:scarytree:1515372061839589417> 𝙎𝙥𝙚𝙘𝙞𝙖𝙡 𝙜𝙤𝙤𝙙𝙨:**\n▪️ **дᴇᴩᴇʙо дᴧя ᴄᴀдᴀ** — цᴇнᴀ: {TREE_COST} <:physpoints:1515371982571704361> (ᴧиʍиᴛ: {MAX_TREES} <:scarytree:1515372061839589417>)\n*(Используйте `/buy_tree`)*\n\n**🎭 𝙍𝙤𝙡𝙚𝙨:**\n"
    for name, info in roles_shop.items():
        text += f"▪️ **@{name}** — цᴇнᴀ: {info['cost']} <:physpoints:1515371982571704361>\n"
    text += f"*(Используйте `/buy_role`)*"
    embed.description = text
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="buy_role", description="Купить роль из магазина.")
@app_commands.describe(role_name="Выберите роль для покупки.")
async def buy_role(interaction: discord.Interaction, role_name: str):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    user_id = interaction.user.id
    if role_name not in roles_shop:
        await interaction.response.send_message("❌ Роль не найдена.", ephemeral=True)
        return

    role_info = roles_shop[role_name]
    user_data = await manager.get_user_economic(user_id)

    if user_data["points"] < role_info['cost']:
        await interaction.response.send_message(f"❌ Недостаточно очков. Нужно: {role_info['cost']} <:physpoints:1515371982571704361>.", ephemeral=True)
        return

    role = interaction.guild.get_role(role_info['role_id'])
    if role is None or role in interaction.user.roles:
        await interaction.response.send_message("❌ Вы уже приобрели эту роль.", ephemeral=True)
        return

    try:
        await interaction.user.add_roles(role)
        new_points = user_data["points"] - role_info['cost']
        await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], user_data["last_claim"], user_data["last_water"])
        await interaction.response.send_message(f"{interaction.user.mention}, ʙы уᴄᴨᴇɯно ᴋуᴨиᴧи ᴩоᴧь **{role_name}**!\nоᴄᴛᴀᴛоᴋ: {new_points} <:physpoints:1515371982571704361>.")
    except discord.Forbidden:
        await interaction.response.send_message("❌ У бота нет прав. Переместите роль бота выше.", ephemeral=True)

@buy_role.autocomplete('role_name')
async def buy_role_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=ch, value=ch) for ch in roles_shop.keys() if current.lower() in ch.lower()][:25]

@bot.tree.command(name="buy_tree", description="Купить дерево сада (+Прибыль).")
async def buy_tree(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)

    if user_data["trees"] >= MAX_TREES:
        await interaction.response.send_message(f"❌ Достигнут лимит {MAX_TREES} <:scarytree:1515372061839589417>.", ephemeral=True)
        return

    if user_data["points"] < TREE_COST:
        await interaction.response.send_message(f"❌ Недостаточно очков. Нужно: {TREE_COST} <:physpoints:1515371982571704361>.", ephemeral=True)
        return

    new_points = user_data["points"] - TREE_COST
    new_trees = user_data["trees"] + 1
    await manager.update_user_economic(user_id, new_points, new_trees, user_data["bugs"], user_data["last_claim"], user_data["last_water"])
    await interaction.response.send_message(f"<:scarytree:1515372061839589417> ᴋуᴨᴧᴇно дᴇᴩᴇʙо зᴀ {TREE_COST} <:physpoints:1515371982571704361>! ʙᴄᴇᴦо ʙ ᴄᴀду: **{new_trees}/{MAX_TREES}**.")

@bot.tree.command(name="water", description="Полить сад (Собрать прибыль).")
async def water(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await interaction.response.send_message(f"❌ Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    await interaction.response.defer()
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)
    my_trees = user_data["trees"]
    active_bugs = user_data["bugs"]

    if my_trees == 0:
        await interaction.followup.send(f"<:scarytree:1515372061839589417> У вас в саду еще нет деревьев!", ephemeral=True)
        return

    current_time = time.time()
    cooldown_period = 10800  
    
    time_passed = current_time - user_data["last_water"]
    if time_passed < cooldown_period:
        seconds_left = int(cooldown_period - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        seconds = seconds_left % 60
        time_left = f"{hours} ч. {minutes} мин." if hours > 0 else (f"{minutes} мин. {seconds} сек." if minutes > 0 else f"{seconds} сек.")
        await interaction.followup.send(f"❌ Земля еще влажная! Вода будет доступна через: **{time_left}**.", ephemeral=True)
        return

    base_reward = sum(random.randint(3, 5) for _ in range(my_trees))
    penalty_text = ""
    if active_bugs > 0:
        active_bugs -= 1
        penalty = my_trees * 1
        base_reward = max(0, base_reward - penalty)
        penalty_text = f"<:scarybug:1515371896173101126> **нᴀᴧᴇᴛ жуᴋоʙ!** ᴨоᴛᴇᴩяно {penalty} <:physpoints:1515371982571704361>. оᴄᴛᴀᴧоᴄь зᴀᴩᴀжᴇнных ᴨоᴧиʙоʙ: {active_bugs} <:scarybug:1515371896173101126>.\n"

    bug_event_text = ""
    if active_bugs == 0 and random.randint(1, 100) <= 15:
        active_bugs = 3
        bug_event_text = "\n**о нᴇᴛ! нᴀ ʙᴀɯ ᴄᴀд нᴀᴨᴀᴧи жуᴋи!** ɯᴛᴩᴀɸ нᴀ 3 ᴨоᴧиʙᴀ."

    new_points = user_data["points"] + base_reward
    await manager.update_user_economic(user_id, new_points, my_trees, active_bugs, user_data["last_claim"], current_time)
    await interaction.followup.send(f"{interaction.user.mention}, ʙы ᴨоᴧиᴧи ᴄᴀд из **{my_trees}** <:scarytree:1515372061839589417>!\n{penalty_text}ᴨᴩибыᴧь: **+{base_reward}** <:physpoints:1515371982571704361>. бᴀᴧᴀнᴄ: {new_points} <:physpoints:1515371982571704361>.{bug_event_text}")

@bot.tree.command(name="give", description="Выдать награду пользователю.")
@app_commands.describe(user="Пользователь.", points="Кол-во награды.")
@is_admin_or_has_role()
async def give(interaction: discord.Interaction, user: discord.User, points: int):
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    user_data = await manager.get_user_economic(user.id)
    new_points = user_data["points"] + points
    await manager.update_user_economic(user.id, new_points, user_data["trees"], user_data["bugs"], 
    user_data["last_claim"], user_data["last_water"])
    await interaction.response.send_message(f"Пользователю {user.mention} добавлено {points} <:physpoints:1515357132474679317>. Баланс: {new_points} <:physpoints:1515357132474679317>.")
    await channel.send(f"Пользователь {interaction.user.mention} использовал команду **/give** на игроке {user.mention} и дал {points} <:physpoints:1515357132474679317>")

@bot.tree.command(name="take", description="Забрать награду у пользователя.")
@app_commands.describe(user="Пользователь.", points="Кол-во награды.")
@is_admin_or_has_role()
async def take(interaction: discord.Interaction, user: discord.User, points: int):
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    user_data = await manager.get_user_economic(user.id)
    new_points = max(0, user_data["points"] - points)
    await manager.update_user_economic(user.id, new_points, user_data["trees"], user_data["bugs"], 
    user_data["last_claim"], user_data["last_water"])
    await interaction.response.send_message(f"У пользователя {user.mention} забрано {points} <:physpoints:1515357132474679317>. Теперь: {new_points} <:physpoints:1515357132474679317>.")
    await channel.send(f"Пользователь {interaction.user.mention} использовал команду **/take** на игроке {user.mention} и забрал {points} <:physpoints:1515357132474679317>")

@bot.event
async def on_message(message):
    if bot.user in message.mentions and message.author.id == DEVELOPER_ID:
        await message.channel.send(f"{message.author.mention}, бот ещё жив! ✅")

@give.error
@take.error
async def admin_commands_error(interaction: discord.Interaction, error: 
    app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ ОТКАЗАНО В ДОСТУПЕ: Недостаточно прав.", ephemeral=True)

@bot.event
async def on_ready():
    try:
        await bot.tree.sync(guild=None) 
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    print(f"✅ Бот {bot.user} запущен!")
    print(f"📊 На серверах: {len(bot.guilds)}")
    print(f"🔧 Команд: {len(bot.commands)}")
    await bot.change_presence(
        activity=discord.CustomActivity(
            name="Ох уж инвестиции 💵",
        )
    )

# Запуск бота
if __name__ == "__main__":
    TOKEN = os.getenv('BOT_TOKEN_ECONOMIC')
    manager = DB_Manager('fg_db.db')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Токен не найден! Создайте .env файл с BOT_TOKEN")