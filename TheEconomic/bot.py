import discord, random, os, time, sys, asyncio
from datetime import datetime
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from database.db_logic import DB_Manager
from discord.errors import HTTPException, Forbidden, NotFound
from discord.ui import Button, View
from discord import Interaction, Message

env_path = Path(__file__).parent.parent / "shared.env"
load_dotenv(env_path)
PREFIX = os.getenv('COMMAND_PREFIX')
COMMANDS_CHANNEL, MOD_COMMANDS_CHANNEL, MOD_LOGS_COMMANDS = int(os.getenv('COMMANDS_CHANNEL_ID')), int(os.getenv('MOD_COMMANDS_CHANNEL_ID')), int(os.getenv('MOD_LOGS_CHANNEL_ID2'))
GUILD_ID, DEVELOPER_ID = int(os.getenv('GUILD_ID')), int(os.getenv('DEVELOPER_ID'))
TREE_COST = 10  
ANIMAL_COST = 25     
MAX_TREES, MAX_ANIMALS = 10, 10
roles_shop = {   
    "𝘼𝙧𝙘𝙝𝙞𝙫𝙞𝙨𝙩": {'role_id': 1515397238447411362, 'cost': 50}, 
    "𝙏𝙧𝙚𝙣𝙙𝙘𝙖𝙨𝙩𝙚𝙧": {'role_id': 1515397844318687233, 'cost': 150}, 
    "𝘾𝙧𝙤𝙨𝙨𝙡𝙞𝙣𝙠𝙚𝙧": {'role_id': 1515396953440129229, 'cost': 350}, 
    "𝙊𝙗𝙨𝙚𝙧𝙫𝙚𝙧": {'role_id': 1515396410231750700, 'cost': 650}, 
    "𝘼𝙧𝙞𝙨𝙩𝙤𝙘𝙧𝙖𝙩": {'role_id': 1515398117426462730, 'cost': 1000}, 
}
chest = {'ready': False, 'reward': 0, 'claimed': False, 'time': 0}

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

class ClaimButton(Button):
    def __init__(self):
        super().__init__(label="ᴛᴀᴋᴇ ᴀ ᴄᴏɴᴛᴀɪɴᴇʀ", style=discord.ButtonStyle.grey)
    
    async def callback(self, interaction):
        await interaction.response.defer()
        if not chest['ready']:
            return await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Нет сундука", ephemeral=True, is_followup=True)
        if chest['claimed']:
            return await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Уже забрали!", ephemeral=True, is_followup=True)
           
        chest['claimed'] = True
        chest['ready'] = False
        user_id = interaction.user.id
        user_data = await manager.get_user_economic(user_id)
        new_points = int(user_data["points"]+chest["reward"])
        await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"],
        user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
        
        # Отключаем кнопку
        self.disabled = True
        await safe_edit(interaction, 
            content=f"<:trophyemoji:1517928090708345032> **{interaction.user.mention}** зᴀбᴩᴀᴧ ᴄ ᴋонᴛᴇйнᴇᴩᴀ `{chest['reward']}` <:physpoints:1515371982571704361>!",
            view=self.view
        )

# ========== ДЕКОРАТОР ==========

def guild_only():
    async def predicate(interaction: discord.Interaction):
        if not interaction.guild:
            await safe_send(interaction, "<:deniedemoji:1519737463126360294> Только на сервере!", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ========== БЕЗОПАСНАЯ ОТПРАВКА СООБЩЕНИЙ ==========

async def safe_send(destination, content=None, max_retries=3, **kwargs):
    if content is None and not kwargs.get('embed') and not kwargs.get('file'):
        return None
    
    # Проверяем, является ли destination Interaction
    if isinstance(destination, Interaction):
        # Если явно указан is_followup или ответ уже отправлен
        if kwargs.get('is_followup', False) or destination.response.is_done():
            # Если есть is_followup - удаляем его из kwargs, чтобы не мешал
            kwargs.pop('is_followup', None)
            # Используем followup
            for attempt in range(max_retries):
                try:
                    return await destination.followup.send(content, **kwargs)
                except HTTPException as e:
                    if e.status == 429:
                        retry_after = float(e.response.headers.get('Retry-After', 1))
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        return None
                except:
                    return None
        else:
            # Если ответ еще не отправлен
            for attempt in range(max_retries):
                try:
                    await destination.response.send_message(content, **kwargs)
                    return True
                except HTTPException as e:
                    if e.status == 429:
                        retry_after = float(e.response.headers.get('Retry-After', 1))
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        return None
                except:
                    return None
        return None
    
    # Для остальных объектов
    if hasattr(destination, 'send'):
        send_target = destination
    elif hasattr(destination, 'channel') and hasattr(destination.channel, 'send'):
        send_target = destination.channel
    elif hasattr(destination, 'message') and hasattr(destination.message, 'channel'):
        send_target = destination.message.channel
    else:
        return None
    
    for attempt in range(max_retries):
        try:
            return await send_target.send(content, **kwargs)
        except HTTPException as e:
            if e.status == 429:
                retry_after = float(e.response.headers.get('Retry-After', 1))
                await asyncio.sleep(retry_after)
                continue
            else:
                return None
        except:
            return None
    return None

async def safe_edit(interaction_or_message, content=None, max_retries=3, **kwargs):
    if content is None and not kwargs.get('embed') and not kwargs.get('view'):
        return None
    if isinstance(interaction_or_message, Interaction):
        interaction = interaction_or_message
        
        for attempt in range(max_retries):
            try:
                # Проверяем, был ли уже ответ
                if interaction.response.is_done():
                    # Если ответ уже отправлен - используем edit_original_response
                    await interaction.edit_original_response(content=content, **kwargs)
                else:
                    # Если ответа еще не было - отправляем новый
                    await interaction.response.send_message(content=content, **kwargs)
                return True
                
            except HTTPException as e:
                if e.status == 429:  # Rate Limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after * (attempt + 1))
                    continue
                else:
                    print(f"HTTP ошибка при редактировании Interaction: {e.status}")
                    return False
                    
            except Forbidden:
                print("Нет прав для редактирования Interaction")
                return False
                
            except NotFound:
                print("Interaction или сообщение не найдены")
                return False
                
            except Exception as e:
                print(f"Ошибка при редактировании Interaction: {e}")
                return False
        
        print(f"Не удалось отредактировать Interaction после {max_retries} попыток")
        return False
    
    # ====== РЕДАКТИРОВАНИЕ MESSAGE ======
    elif isinstance(interaction_or_message, Message):
        message = interaction_or_message
        
        for attempt in range(max_retries):
            try:
                return await message.edit(content=content, **kwargs)
                
            except HTTPException as e:
                if e.status == 429:  # Rate Limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after * (attempt + 1))
                    continue
                else:
                    print(f"HTTP ошибка при редактировании Message: {e.status}")
                    return None
                    
            except Forbidden:
                print("Нет прав для редактирования Message")
                return None
                
            except NotFound:
                print("Message не найдено")
                return None
                
            except Exception as e:
                print(f"Ошибка при редактировании Message: {e}")
                return None
        
        print(f"Не удалось отредактировать Message после {max_retries} попыток")
        return None
    
    else:
        print("Ошибка: передан не Interaction и не Message")
        return None

async def event_loop():
    while True:
        if time.time() - chest['time'] > 28800 and not chest['ready']:
            chest.update({'ready': True, 'claimed': False, 'reward': random.randint(35, 53), 'time': time.time()})
            
            view = View(timeout=None)
            view.add_item(ClaimButton())
            
            channel = bot.get_channel(COMMANDS_CHANNEL)
            if channel:
                embed = discord.Embed(
                    title=f"**ⳅⲁⲅⲁⲇⲟɥⲏыύ ⲕⲟⲏⲧⲉύⲏⲉⲣ** <:containeremoji:1518184249906171945>",
                    description=f"зᴀᴦᴀдочный ᴋонᴛᴇйнᴇᴩ быᴧ зᴀᴛᴇᴩян ᴄᴩᴇди ᴦᴧубин ʍоᴩᴄᴋих...\nнᴇдᴀʙно у бᴇᴩᴇᴦоʙ быᴧ нᴀйдᴇн зᴀᴛᴇᴩянный ᴋонᴛᴇйнᴇᴩ, ϶ᴋᴄᴨᴇᴩᴛы уʙᴇᴩяюᴛ, чᴛо ᴄᴛоиʍоᴄᴛь ϶ᴛоᴦо ᴋонᴛᴇйнᴇᴩᴀ: `{chest['reward']}` <:physpoints:1515371982571704361>!\n||@here||",
                    color=discord.Color.darker_grey()
                )
                embed.set_image(url="https://t4.ftcdn.net/jpg/06/21/67/39/360_F_621673926_NCCh335JeAsxl6Q0n1mmFzHtXSVsaUq3.jpg")
                await safe_send(channel, embed=embed, view=view)
        
        if chest['ready'] and time.time() - chest['time'] > 28800:
            chest['ready'] = False
            channel = bot.get_channel(COMMANDS_CHANNEL)
            if channel:
                await safe_send(channel, f"<:boxesemoji:1518191594371678278> ᴋонᴛᴇйнᴇᴩ ᴄᴦниᴧ!")
        
        await asyncio.sleep(60)

@bot.tree.command(name='sync', description='Синхронизировать команды.')
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def sync(interaction: discord.Interaction):
    if interaction.user.id != DEVELOPER_ID:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> У тебя нет прав для этой команды.", ephemeral=True)
        return
    bot.tree.clear_commands(guild=None)
    await bot.tree.sync(guild=None)
    await safe_send(interaction, "<:accessemoji:1518684370410541158> Команды синхронизированы для текущего сервера.", ephemeral=False)

@bot.tree.command(name="работа", description="Забрать награду.")
@app_commands.guild_only()
async def claim(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    await interaction.response.defer()
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)
    current_time = time.time()
    time_passed = current_time - user_data["last_claim"]

    if time_passed < 14400:
        seconds_left = int(14400 - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        await safe_send(interaction, f"**<:accessdeniedemoji:1517986918573408318> {interaction.user.mention}, вы уже забирали награду!**\n⌛ Осталось: **{hours} ч. {minutes} мин.**", ephemeral=True)
        return
    reward = random.randint(6, 14)
    new_points = user_data["points"] + reward

    await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"], current_time, user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"{interaction.user.mention}, ʙы ᴨоᴧучиᴧи **{reward} <:physpoints:1515371982571704361>**!\nʙᴀɯ ᴛᴇᴋущий бᴀᴧᴀнᴄ: **{new_points} <:physpoints:1515371982571704361>**.")

@bot.tree.command(name="рыбалка", description="Порыбачить для прибыли.")
@app_commands.guild_only()
async def fish(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    await interaction.response.defer()
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)
    current_time = time.time()
    time_passed = current_time - user_data["last_fish"]

    if time_passed < 28800:
        seconds_left = int(28800 - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        await safe_send(interaction, f"**<:accessdeniedemoji:1517986918573408318> {interaction.user.mention}, вы уже забирали награду!**\n⌛ Осталось: **{hours} ч. {minutes} мин.**", ephemeral=True)
        return
    chance = random.random()
    fish_text = ""
    if chance < 0.01:
        fish_text = "ⲏⲁⲥⲧⲟяպⲉⲅⲟ ⲙⲉⲅⲁⲗⲁⲇⲟⲏⲁ! <:megaladonemoji:1518011720499593246>"
        reward = random.randint(124, 157)
        role = interaction.guild.get_role(1518011868709388339)
        if role:
            await interaction.user.add_roles(role, reason=f"Выловил улов!")
            await safe_send(interaction, "<:trophyemoji:1517928090708345032> Вам выдана роль за улов!", ephemeral=True)
    elif chance < 0.1:
        fish_text = "ⲿυⲃⲩю ⲁⲕⲩⲗⲩ! <:sharkemoji:1518009750078492944>"
        reward = random.randint(27, 36)
        role = interaction.guild.get_role(1518010342410686606)
        if role:
            await interaction.user.add_roles(role, reason=f"Выловил улов!")
            await safe_send(interaction,"<:trophyemoji:1517928090708345032> Вам выдана роль за улов!", ephemeral=True)
    elif chance < 0.3:
        fish_text = "պⲩⲕⲩ! <:fish2emoji:1518009317129715843>"
        reward = random.randint(11, 19)
    else:  
        fish_text = "ⲟⲕⲩⲏя. <:fish1emoji:1518008900941774870>"
        reward = random.randint(4, 8)

    new_points = user_data["points"] + reward

    await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"], current_time, user_data["last_water"], user_data["last_collect"], current_time, user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"{interaction.user.mention}, ʙы ʙыᴧоʙиᴧи **{fish_text}** ʙᴀɯᴀ нᴀᴦᴩᴀдᴀ: **{reward} <:physpoints:1515371982571704361>**!\nʙᴀɯ ᴛᴇᴋущий бᴀᴧᴀнᴄ: **{new_points} <:physpoints:1515371982571704361>**.")

@bot.tree.command(name="бонус", description="Забрать дополнительную награду.")
@app_commands.guild_only()
async def bonus(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    await interaction.response.defer()
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)
    current_time = time.time()
    time_passed = current_time - user_data["last_bonus"]

    if time_passed < 43200:
        seconds_left = int(43200 - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        await safe_send(interaction, f"**<:accessdeniedemoji:1517986918573408318> {interaction.user.mention}, вы уже забирали награду!**\n⌛ Осталось: **{hours} ч. {minutes} мин.**", ephemeral=True)
        return
    reward = random.randint(6, 11)
    new_points = user_data["points"] + reward

    await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"], user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], current_time, user_data["last_rob"])
    await safe_send(interaction, f"{interaction.user.mention}, ʙы ᴨоᴧучиᴧи бонуᴄ: **{reward} <:physpoints:1515371982571704361>**!\nʙᴀɯ ᴛᴇᴋущий бᴀᴧᴀнᴄ: **{new_points} <:physpoints:1515371982571704361>**.")

@bot.tree.command(name="баланс", description="Посмотреть баланс.")
@app_commands.guild_only()
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if member is None:
        member = interaction.user
    user_data = await manager.get_user_economic(member.id)
    embed = discord.Embed(title=f"{member.name}'𝙨 𝙥𝙧𝙤𝙛𝙞𝙡𝙚 <:killau1:1515061286969413683>", color=discord.Color.darker_grey())
    garden_status = f"ᴨᴩиобᴩᴇᴛᴇнныᴇ дᴇᴩᴇʙья: **{user_data['trees']}/{MAX_TREES}** <:scarytree:1515372061839589417>"
    paddock_status = f"ᴨᴩиобᴩᴇᴛᴇнный доʍᴀɯний ᴄᴋоᴛ: **{user_data['animals']}/{MAX_ANIMALS}** <:animalsemoji:1517996442470580295>"

    embed.add_field(name=f"<:physpoints:1515371982571704361> 𝘽𝙖𝙡𝙖𝙣𝙘𝙚:", value=f"**ʙᴀɯ ᴛᴇᴋущий бᴀᴧᴀнᴄ: {user_data['points']}** <:physpoints:1515371982571704361>", inline=False)
    if user_data["bugs"] > 0:
        garden_status += f"\n**𝙒𝙖𝙧𝙣𝙞𝙣𝙜:** ᴀᴛᴀᴋоʙᴀн жуᴋᴀʍи! оᴄᴛᴀᴧоᴄь ᴨоᴧиʙоʙ: **{user_data['bugs']}** <:scarybug:1515371896173101126>"
    else:
        garden_status += f"\nчиᴄᴛ оᴛ ʙᴩᴇдиᴛᴇᴧᴇй."
    embed.add_field(name=f"<:scarytree:1515372061839589417> 𝙂𝙖𝙧𝙙𝙚𝙣:", value=garden_status, inline=False)

    if user_data["werewolfs"] > 0:
        paddock_status += f"\n**𝙒𝙖𝙧𝙣𝙞𝙣𝙜:** ʙ зᴀᴦонᴇ зᴀʙᴇᴧиᴄь обоᴩоᴛни! оᴄᴛᴀᴧоᴄь обоᴩоᴛнᴇй: **{user_data['werewolfs']}** <:werewolfsemoji:1517998966468378827>"
    else:
        paddock_status += f"\nжиʙоᴛныᴇ ʙ бᴇзоᴨᴀᴄноᴄᴛи."
    embed.add_field(name=f"<:animalsemoji:1517996442470580295> 𝙋𝙖𝙙𝙙𝙤𝙘𝙠:", value=paddock_status, inline=False)
    await safe_send(interaction, embed=embed)

@bot.tree.command(name="магазин", description="Показать доступные для покупки товары и роли.")
@app_commands.guild_only()
async def shop(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    embed = discord.Embed(title="𝙎𝙚𝙧𝙫𝙚𝙧'𝙨 𝙨𝙝𝙤𝙥 <:killau2:1515061312244289546>", color=discord.Color.darker_grey())
    text = f"**<:scarytree:1515372061839589417><:animalsemoji:1517996442470580295> 𝙎𝙥𝙚𝙘𝙞𝙖𝙡 𝙜𝙤𝙤𝙙𝙨:**\n▪️ **дᴇᴩᴇʙо дᴧя ᴄᴀдᴀ** — цᴇнᴀ: {TREE_COST} <:physpoints:1515371982571704361> (ᴧиʍиᴛ: {MAX_TREES} <:scarytree:1515372061839589417>)\n*(Используйте `/купить_дерево`)*\n▪️ **доʍᴀɯний ᴄᴋоᴛ** — цᴇнᴀ: {ANIMAL_COST} <:physpoints:1515371982571704361> (ᴧиʍиᴛ: {MAX_ANIMALS} <:animalsemoji:1517996442470580295>)\n*(Используйте `/купить_животное`)*\n\n**🎭 𝙍𝙤𝙡𝙚𝙨:**\n"
    for name, info in roles_shop.items():
        text += f"▪️ **{name}** — цᴇнᴀ: {info['cost']} <:physpoints:1515371982571704361>\n"
    text += f"*(Используйте `/купить_роль`)*"
    embed.description = text
    await safe_send(interaction, embed=embed)

@bot.tree.command(name="купить_роль", description="Купить роль из магазина.")
@app_commands.describe(role_name="Выберите роль для покупки.")
@app_commands.guild_only()
async def buy_role(interaction: discord.Interaction, role_name: str):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    user_id = interaction.user.id
    if role_name not in roles_shop:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Роль не найдена.", ephemeral=True)
        return
    role_info = roles_shop[role_name]
    user_data = await manager.get_user_economic(user_id)
    if user_data["points"] < role_info['cost']:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Недостаточно очков. Нужно: {role_info['cost']} <:physpoints:1515371982571704361>.", ephemeral=True)
        return
    role = interaction.guild.get_role(role_info['role_id'])
    if role is None or role in interaction.user.roles:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Вы уже приобрели эту роль.", ephemeral=True)
        return
    try:
        await interaction.user.add_roles(role)
        new_points = user_data["points"] - role_info['cost']
        await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"], user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
        await safe_send(interaction, f"{interaction.user.mention}, ʙы уᴄᴨᴇɯно ᴋуᴨиᴧи ᴩоᴧь **{role_name}**!\nоᴄᴛᴀᴛоᴋ: {new_points} <:physpoints:1515371982571704361>.")
    except discord.Forbidden:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> У бота нет прав. Переместите роль бота выше.", ephemeral=True)

@buy_role.autocomplete('role_name')
async def buy_role_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=ch, value=ch) for ch in roles_shop.keys() if current.lower() in ch.lower()][:25]

@bot.tree.command(name="купить_дерево", description="Купить дерево сада (+Прибыль).")
@app_commands.guild_only()
async def buy_tree(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)
    if user_data["trees"] >= MAX_TREES:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Достигнут лимит {MAX_TREES} <:scarytree:1515372061839589417>.", ephemeral=True)
        return
    if user_data["points"] < TREE_COST:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Недостаточно очков. Нужно: {TREE_COST} <:physpoints:1515371982571704361>.", ephemeral=True)
        return

    new_points = user_data["points"] - TREE_COST
    new_trees = user_data["trees"] + 1
    await manager.update_user_economic(user_id, new_points, new_trees, user_data["bugs"], user_data["animals"], user_data["werewolfs"], user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"<:scarytree:1515372061839589417> ᴋуᴨᴧᴇно дᴇᴩᴇʙо зᴀ {TREE_COST} <:physpoints:1515371982571704361>! ʙᴄᴇᴦо ʙ ᴄᴀду: **{new_trees}/{MAX_TREES}**.")

@bot.tree.command(name="купить_животное", description="Купить животное (+Прибыль).")
@app_commands.guild_only()
async def buy_animal(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)
    if user_data["animals"] >= MAX_ANIMALS:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Достигнут лимит {MAX_ANIMALS} <:animalsemoji:1517996442470580295>.", ephemeral=True)
        return
    if user_data["points"] < ANIMAL_COST:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Недостаточно очков. Нужно: {ANIMAL_COST} <:physpoints:1515371982571704361>.", ephemeral=True)
        return

    new_points = user_data["points"] - ANIMAL_COST
    new_animals = user_data["animals"] + 1
    await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], new_animals, user_data["werewolfs"], user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"<:animalsemoji:1517996442470580295> ᴋуᴨᴧᴇно доʍᴀɯнᴇᴦо ᴄᴋоᴛᴀ зᴀ {ANIMAL_COST} <:physpoints:1515371982571704361>! ʙᴄᴇᴦо ʙ зᴀᴦонᴇ: **{new_animals}/{MAX_ANIMALS}**.")

@bot.tree.command(name="полить_сад", description="Полить сад (Собрать прибыль).")
@app_commands.guild_only()
async def water(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    await interaction.response.defer()
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)

    my_trees = user_data["trees"]
    active_bugs = user_data["bugs"]
    if my_trees == 0:
        await safe_send(interaction, f"<:scarytree:1515372061839589417> У вас в саду еще нет деревьев!", ephemeral=True)
        return
    current_time = time.time()
    
    time_passed = current_time - user_data["last_water"]
    if time_passed < 28800:
        seconds_left = int(28800 - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        seconds = seconds_left % 60
        time_left = f"{hours} ч. {minutes} мин." if hours > 0 else (f"{minutes} мин. {seconds} сек." if minutes > 0 else f"{seconds} сек.")
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Земля еще влажная! Вода будет доступна через: **{time_left}**.", ephemeral=True)
        return

    base_reward = sum(random.randint(2, 5) for _ in range(my_trees))
    penalty_text = ""
    if active_bugs > 0:
        active_bugs -= 1
        penalty = int(my_trees * 1.5)
        base_reward = max(0, base_reward - penalty)
        penalty_text = f"<:scarybug:1515371896173101126> **нᴀᴧᴇᴛ жуᴋоʙ!** ᴨоᴛᴇᴩяно {penalty} <:physpoints:1515371982571704361>. оᴄᴛᴀᴧоᴄь зᴀᴩᴀжᴇнных ᴨоᴧиʙоʙ: {active_bugs} <:scarybug:1515371896173101126>.\n"

    bug_event_text = ""
    if active_bugs == 0 and random.randint(1, 100) <= 20:
        active_bugs = random.randint(2, 4)
        bug_event_text = f"\n**о нᴇᴛ! нᴀ ʙᴀɯ ᴄᴀд нᴀᴨᴀᴧи жуᴋи!** ɯᴛᴩᴀɸ нᴀ {active_bugs} ᴨоᴧиʙᴀ."

    new_points = user_data["points"] + base_reward
    await manager.update_user_economic(user_id, new_points, my_trees, active_bugs, user_data["animals"], user_data["werewolfs"], user_data["last_claim"], current_time, user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"{interaction.user.mention}, ʙы ᴨоᴧиᴧи ᴄᴀд из **{my_trees}** <:scarytree:1515372061839589417>!\n{penalty_text}ᴨᴩибыᴧь: **+{base_reward}** <:physpoints:1515371982571704361>. бᴀᴧᴀнᴄ: {new_points} <:physpoints:1515371982571704361>.{bug_event_text}")

@bot.tree.command(name="собрать_загон", description="Продать продукты собранные с животных (Собрать прибыль).")
@app_commands.guild_only()
async def collect(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    await interaction.response.defer()
    user_id = interaction.user.id
    user_data = await manager.get_user_economic(user_id)

    my_animals = user_data["animals"]
    active_werewolfs = user_data["werewolfs"]
    if my_animals == 0:
        await safe_send(interaction, f"<:animalsemoji:1517996442470580295> У вас в загоне нету ещё животных!", ephemeral=True)
        return
    current_time = time.time()
    
    time_passed = current_time - user_data["last_collect"]
    if time_passed < 28800:
        seconds_left = int(28800 - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        seconds = seconds_left % 60
        time_left = f"{hours} ч. {minutes} мин." if hours > 0 else (f"{minutes} мин. {seconds} сек." if minutes > 0 else f"{seconds} сек.")
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Домашний скот ещё не готов! Продукты питания будут через: **{time_left}**.", ephemeral=True)
        return

    base_reward = sum(random.randint(7, 13) for _ in range(my_animals))
    penalty_text = ""
    if active_werewolfs > 0:
        active_werewolfs -= 1
        penalty = int(my_animals * 2.5)
        base_reward = max(0, base_reward - penalty)
        penalty_text = f"<:werewolfsemoji:1517998966468378827> **ᴋᴩоʙь ᴨᴩиʙᴧᴇᴋᴧᴀ обоᴩоᴛнᴇй!** ᴨоᴛᴇᴩяно {penalty} <:physpoints:1515371982571704361>. оᴄᴛᴀᴧоᴄь обоᴩоᴛнᴇй: {active_werewolfs} <:werewolfsemoji:1517998966468378827>.\n"

    werewolf_event_text = ""
    if active_werewolfs == 0 and random.randint(1, 100) <= 15:
        active_werewolfs = random.randint(2, 4)
        werewolf_event_text = f"\n**о нᴇᴛ! нᴀ ʙᴀɯ зᴀᴦон нᴀᴨᴀᴧи обоᴩоᴛни!** ɯᴛᴩᴀɸ нᴀ {active_werewolfs} ᴄбоᴩᴀ."

    new_points = user_data["points"] + base_reward
    await manager.update_user_economic(user_id, new_points, user_data["trees"], user_data["bugs"], my_animals, active_werewolfs, user_data["last_claim"], user_data["last_water"], current_time, user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"{interaction.user.mention}, ʙы ᴨозᴀбоᴛиᴧиᴄь о **{my_animals}** <:animalsemoji:1517996442470580295>!\n{penalty_text}ᴨᴩибыᴧь: **+{base_reward}** <:physpoints:1515371982571704361>. бᴀᴧᴀнᴄ: {new_points} <:physpoints:1515371982571704361>.{werewolf_event_text}")

@bot.tree.command(name="лидерборд", description="Показывает топ игроков.")
@app_commands.guild_only()
async def top_players(interaction: discord.Interaction):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    rows = manager.get_leaderboard()
    if not rows:
        await safe_send(interaction, "📊 Пока нет игроков с очками!", ephemeral=True)
        return
    embed = discord.Embed(
        title="<:trophyemoji:1517928090708345032> ᴛоᴨ ᴨоᴧьзоʙᴀᴛᴇᴧᴇй ᴨо очᴋᴀʍ",
        color=discord.Color.darker_grey(),
        timestamp=datetime.now()
    )
    leaderboard_text = ""
    
    for i, row in enumerate(rows, 1):
        user_id = row[0]
        points = row[1]
        
        # Получаем пользователя
        user = interaction.guild.get_member(user_id)
        if not user:
            try:
                user = await bot.fetch_user(user_id)
            except:
                user = None
        
        # Имя пользователя
        if user:
            name = user.mention
        else:
            name = f"Неизвестный #{user_id}"
        
        # Эмодзи для топ-3
        medal = ""
        if i == 1:
            medal = "👑 "
        elif i == 2:
            medal = "🥈 "
        elif i == 3:
            medal = "🥉 "
        
        # Добавляем в текст
        leaderboard_text += f"{medal}`#{i}` **{name}** — `{points}` <:physpoints:1515371982571704361>\n"
    
    embed.description = leaderboard_text
    embed.set_footer(text=f"Всего игроков: {len(rows)}")
    
    await safe_send(interaction, embed=embed)

@bot.tree.command(name="казино", description="Дэпнуть...")
@app_commands.describe(bet="Сумма ставки.")
@app_commands.guild_only()
async def casino(interaction: discord.Interaction, bet: int):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if bet < 10:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Минимальная ставка: `10` <:physpoints:1515371982571704361>!", ephemeral=True)
        return
    if bet > 100:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Максимальная ставка: `100` <:physpoints:1515371982571704361>!", ephemeral=True)
        return
    user_data = await manager.get_user_economic(interaction.user.id)
    if user_data["points"] < bet:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Недостаточно монет! У вас: `{user_data['points']}` <:physpoints:1515371982571704361>", ephemeral=True)
        return
    symbols = ["<a:cherryemoji:1518682902827896973>", "<a:lemonemoji:1518683734411444224>", "<a:orangeemoji:1518685108578680863>", "<a:grapesemoji:1518685654907621546>", "<a:littlediamondemoji:1518554727023902730>", "<a:staremoji:1518554397750202460>", "<a:hakariemoji:1518552999214055424>"]
    
    slot1 = random.choice(symbols)
    slot2 = random.choice(symbols)
    slot3 = random.choice(symbols)

    win = False
    multiplier = 0
    text = ""
    winning_combos = {
        "<a:hakariemoji:1518552999214055424>": (5, "**джᴇᴋᴨоᴛ! ᴨоᴧучᴀᴇᴛ ᴄиᴧу хᴀᴋᴀᴩи!**"),
        "<a:littlediamondemoji:1518554727023902730>": (3.5, "**ᴀᴧʍᴀзнᴀя ᴧихоᴩᴀдᴋᴀ!**"),
        "<a:staremoji:1518554397750202460>": (2.75, "**ᴄᴇᴦодняɯний зʙᴇздоᴨᴀд!**"),
        "<a:cherryemoji:1518682902827896973>": (2.25, "**иᴄᴨоᴧьзуᴇᴛ оᴦнᴇʙую ʍощь ʙиɯни из ᴘᴠᴢ!**"),
        "<a:lemonemoji:1518683734411444224>": (2, "**ᴧиʍонᴀдноᴇ нᴀᴄᴧᴀждᴇньᴇ!**"),
        "<a:orangeemoji:1518685108578680863>": (2, "**ᴀᴨᴇᴧьᴄинᴋи!**"),
        "<a:grapesemoji:1518685654907621546>": (2.25, "**ᴧучɯᴇᴇ ʙино!**")
    }

    if slot1 == slot2 == slot3 and slot1 in winning_combos:
        multiplier, text = winning_combos[slot1]
        win = True
    elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
        multiplier = 1.15
        win = True
        text = "**<:accessemoji:1518684370410541158> дʙᴇ одинᴀᴋоʙых!**"
    else:
        text = "<:accessdeniedemoji:1517986918573408318> **ничᴇᴦо нᴇ ʙыᴨᴀᴧо...**"
    if win:
        winnings = int(bet * multiplier)
        await manager.update_user_economic(interaction.user.id, int(user_data["points"]+winnings), user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"], user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
        embed = discord.Embed(
            title="🎰 ᴍᴀᴄʜɪɴᴇ's sʟᴏᴛs",
            description=f"{slot1} {slot2} {slot3}\n\n"
                        f"{text}\n"
                        f"<:moneybagemoji:1518230296078843964> ʙыиᴦᴩыɯ: `{winnings}` <:physpoints:1515371982571704361> (x{multiplier})",
            color=discord.Color.green()
        )
    else:
        await manager.update_user_economic(interaction.user.id, int(user_data["points"]-bet), user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"], user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
        embed = discord.Embed(
            title="🎰 ᴍᴀᴄʜɪɴᴇ's sʟᴏᴛs",
            description=f"{slot1} {slot2} {slot3}\n\n"
                        f"{text}\n"
                        f"<:accessdeniedemoji:1517986918573408318> ᴨоᴛᴇᴩяно: `{bet}` <:physpoints:1515371982571704361>",
            color=discord.Color.red()
        )
    new_balance = user_data["points"] + (winnings if win else -bet)
    embed.add_field(
        name="<:moneybagemoji:1518230296078843964> ʙᴀɯ бᴀᴧᴀнᴄ",
        value=f"`{new_balance}` <:physpoints:1515371982571704361>",
        inline=False
    )
    embed.set_footer(text="удᴀчᴀ доᴄᴛиᴦнᴇᴛ ʙᴀᴄ! 🍀")
    
    await safe_send(interaction, embed=embed)

@bot.tree.command(name="заплатить", description="Передать пользователю монет.")
@app_commands.describe(user="Пользователь.", points="Кол-во монет.")
@app_commands.guild_only()
async def pay(interaction: discord.Interaction, user: discord.User, points: int):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if interaction.user.id == user.id:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Вы не можете перевести монеты самому себе!", ephemeral=True)
        return
    if user.bot:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Вы не можете переводить монеты ботам!", ephemeral=True)
        return
    if points <= 0:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Сумма должна быть больше 0!", ephemeral=True)
        return
    MIN_PAY = 10
    if points < MIN_PAY:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Минимальная сумма для перевода - {MIN_PAY} монет!", ephemeral=True)
        return
    MAX_PAY = 10000
    if points > MAX_PAY:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Максимальная сумма для перевода - {MAX_PAY} монет!", ephemeral=True)
        return
    user_data = await manager.get_user_economic(interaction.user.id)
    target_data = await manager.get_user_economic(user.id)
    if user_data["points"] < points:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Недостаточно монет! У вас: {user_data['points']} монет.", ephemeral=True)
        return
    try:
        await manager.update_user_economic(interaction.user.id, int(user_data["points"]-points), user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"], user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
        await manager.update_user_economic(user.id, int(target_data["points"]+points), target_data["trees"], target_data["bugs"], target_data["animals"], target_data["werewolfs"], target_data["last_claim"], target_data["last_water"], target_data["last_collect"], target_data["last_fish"], target_data["last_bonus"], target_data["last_rob"])
    except Exception as e:
        await safe_send(interaction, f"❌ Произошла ошибка при переводе: {str(e)}", ephemeral=True)
        return
    embed = discord.Embed(
        title="<:moneybagemoji:1518230296078843964> уᴄᴨᴇɯный ᴨᴇᴩᴇʙод!",
        color=discord.Color.darker_grey()
    )
    embed.add_field(
        name="оᴛᴨᴩᴀʙиᴛᴇᴧь",
        value=f"<@{interaction.user.id}>",
        inline=True
    )
    embed.add_field(
        name="ᴨоᴧучᴀᴛᴇᴧь",
        value=f"<@{user.id}>",
        inline=True
    )
    embed.add_field(
        name="ᴨоᴧучиᴧ",
        value=f"**{points}** <:physpoints:1515371982571704361>",
        inline=True
    )
    await safe_send(interaction, embed=embed)

@bot.tree.command(name="ограбить", description="Ограбить другого игрока.")
@app_commands.describe(user="Кого хотите ограбить?")
@app_commands.guild_only()
async def rob(interaction: discord.Interaction, user: discord.User):
    if interaction.channel.id != COMMANDS_CHANNEL and interaction.channel.id != MOD_COMMANDS_CHANNEL:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Эта команда работает только в канале <#{COMMANDS_CHANNEL}>!", ephemeral=True)
        return
    if interaction.user.id == user.id:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Вы не можете ограбить самого себя!", ephemeral=True)
        return
    if user.bot:
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> Вы не можете ограбить ботов!", ephemeral=True)
        return
    robber_data = await manager.get_user_economic(interaction.user.id)
    victim_data = await manager.get_user_economic(user.id)
    if robber_data["points"] < 30:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> У вас слишком мало денег! Нужно хотя бы 30 монет, чтобы начать грабить.", ephemeral=True)
        return
    if victim_data["points"] < 30:
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> У <@{user.id}> слишком мало денег!\nУ него всего {victim_data['points']} монет.", ephemeral=True)
        return
    current_time = time.time()
    
    time_passed = current_time - robber_data["last_rob"]
    if time_passed < 43200:
        seconds_left = int(43200 - time_passed)
        hours = seconds_left // 3600
        minutes = (seconds_left % 3600) // 60
        seconds = seconds_left % 60
        time_left = f"{hours} ч. {minutes} мин." if hours > 0 else (f"{minutes} мин. {seconds} сек." if minutes > 0 else f"{seconds} сек.")
        await safe_send(interaction, f"<:accessdeniedemoji:1517986918573408318> Вы не можете грабить так часто! Будет доступно: **{time_left}**.", ephemeral=True)
        return
    success = random.random() < 0.4
    if success:
        new_points = random.randint(8, 21)
        await manager.update_user_economic(interaction.user.id, int(robber_data["points"]+new_points), robber_data["trees"], robber_data["bugs"], robber_data["animals"], robber_data["werewolfs"], robber_data["last_claim"], robber_data["last_water"], robber_data["last_collect"], robber_data["last_fish"], robber_data["last_bonus"], current_time)
        await manager.update_user_economic(user.id, int(victim_data["points"]-new_points), victim_data["trees"], victim_data["bugs"], victim_data["animals"], victim_data["werewolfs"], victim_data["last_claim"], victim_data["last_water"], victim_data["last_collect"], victim_data["last_fish"], victim_data["last_bonus"], victim_data["last_rob"])
        
        embed = discord.Embed(
            title="<:moneybagemoji:1518230296078843964> **ⲩⲥⲡⲉɯⲏⲟⲉ ⲟⲅⲣⲁⳝⲗⲉⲏυⲉ!**",
            description=f"ʙы оᴦᴩᴀбиᴧи <@{user.id}> и уᴋᴩᴀᴧи `{new_points}` <:physpoints:1515371982571704361>!",
            color=discord.Color.green()
        )
        embed.add_field(
            name="ʙᴀɯ бᴀᴧᴀнᴄ",
            value=f"**{int(robber_data['points']+new_points)}** <:physpoints:1515371982571704361>",
            inline=True
        )
        embed.add_field(
            name="бᴀᴧᴀнᴄ жᴇᴩᴛʙы",
            value=f"**{int(victim_data['points']-new_points)}** <:physpoints:1515371982571704361>",
            inline=True
        )
        embed.set_footer(text="ну и зᴧодᴇй жᴇ ʙы... <:werewolfsemoji:1517998966468378827>")
        try:
            await user.send(f"<:moneybagemoji:1518230296078843964> ʙᴀᴄ оᴦᴩᴀбиᴧ <@{interaction.user.id}> нᴀ `{new_points}` <:physpoints:1515371982571704361>!")
        except:
            pass
        
        await safe_send(interaction, embed=embed)
        
    else:
        new_points = random.randint(4, 13)
        await manager.update_user_economic(interaction.user.id, int(robber_data["points"]-new_points), robber_data["trees"], robber_data["bugs"], robber_data["animals"], robber_data["werewolfs"], robber_data["last_claim"], robber_data["last_water"], robber_data["last_collect"], robber_data["last_fish"], robber_data["last_bonus"], current_time)
        await manager.update_user_economic(user.id, int(victim_data["points"]+new_points), victim_data["trees"], victim_data["bugs"], victim_data["animals"], victim_data["werewolfs"], victim_data["last_claim"], victim_data["last_water"], victim_data["last_collect"], victim_data["last_fish"], victim_data["last_bonus"], victim_data["last_rob"])
        
        embed = discord.Embed(
            title="<:accessdeniedemoji:1517986918573408318> **ⲏⲉⲩⲇⲁɥⲏⲁя ⲡⲟⲡыⲧⲕⲁ!**",
            description=f"ʙы ᴨоᴨыᴛᴀᴧиᴄь оᴦᴩᴀбиᴛь <@{user.id}>,\nно у ʙᴀᴄ ничᴇᴦо нᴇ ʙыɯᴧо! <:moneybagemoji:1518230296078843964>",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="ɯᴛᴩᴀɸ",
            value=f"**{new_points}** <:physpoints:1515371982571704361>",
            inline=True
        )
        embed.add_field(
            name="ʙᴀɯ бᴀᴧᴀнᴄ",
            value=f"**{int(robber_data['points']-new_points)}** <:physpoints:1515371982571704361>",
            inline=True
        )
        embed.set_footer(text="ʙоᴩ228...")
        try:
            await user.send(f"<:moneybagemoji:1518230296078843964> <@{interaction.user.id}> ᴨыᴛᴀᴧᴄя ʙᴀᴄ оᴦᴩᴀбиᴛь нᴀ `{new_points}` <:physpoints:1515371982571704361>, но у нᴇᴦо ничᴇᴦо нᴇ ʙыɯᴧо!")
        except:
            pass
        
        await safe_send(interaction, embed=embed)

@bot.tree.command(name="выдать", description="Выдать награду пользователю.")
@app_commands.describe(user="Пользователь.", points="Кол-во награды.")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def give(interaction: discord.Interaction, user: discord.User, points: int):
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    user_data = await manager.get_user_economic(user.id)
    new_points = user_data["points"] + points
    await manager.update_user_economic(user.id, new_points, user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"],
    user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"Пользователю {user.mention} добавлено {points} <:physpoints:1515371982571704361>. Баланс: {new_points} <:physpoints:1515371982571704361>.")
    await safe_send(channel, f"Пользователь {interaction.user.mention} использовал команду **/give** на игроке {user.mention} и дал {points} <:physpoints:1515371982571704361>")

@bot.tree.command(name="забрать", description="Забрать награду у пользователя.")
@app_commands.describe(user="Пользователь.", points="Кол-во награды.")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def take(interaction: discord.Interaction, user: discord.User, points: int):
    channel = bot.get_channel(MOD_LOGS_COMMANDS)
    user_data = await manager.get_user_economic(user.id)
    new_points = max(0, user_data["points"] - points)
    await manager.update_user_economic(user.id, new_points, user_data["trees"], user_data["bugs"], user_data["animals"], user_data["werewolfs"],
    user_data["last_claim"], user_data["last_water"], user_data["last_collect"], user_data["last_fish"], user_data["last_bonus"], user_data["last_rob"])
    await safe_send(interaction, f"У пользователя {user.mention} забрано {points} <:physpoints:1515371982571704361>. Теперь: {new_points} <:physpoints:1515371982571704361>.")
    await safe_send(channel, f"Пользователь {interaction.user.mention} использовал команду **/take** на игроке {user.mention} и забрал {points} <:physpoints:1515371982571704361>")

@bot.event
async def on_message(message):
    if not message.guild:
        return
    if bot.user in message.mentions and message.author.id == DEVELOPER_ID:
        await safe_send(message, f"{message.author.mention}, бот ещё жив! <:accessemoji:1518684370410541158>", delete_after=5)

@give.error
@take.error
async def admin_commands_error(interaction: discord.Interaction, error: 
    app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await safe_send(interaction, "<:accessdeniedemoji:1517986918573408318> ОТКАЗАНО В ДОСТУПЕ: Недостаточно прав.", ephemeral=True)

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
    await event_loop()

# Запуск бота
if __name__ == "__main__":
    TOKEN = os.getenv('BOT_TOKEN_ECONOMIC')
    manager = DB_Manager('/app/database/fg_db.db')
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Токен не найден! Создайте .env файл с BOT_TOKEN")