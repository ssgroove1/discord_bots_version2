import os, discord, datetime, asyncio, aiohttp, io
from pathlib import Path
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageOps
from safe_commands import *
from config import BotConfig
from database.db_logic import DB_Manager

BASE_DIR = Path(__file__).parent
class ModerationFunc():
    def __init__(self, bot):
        self.bot = bot
        self.manager = DB_Manager(BotConfig.DB_PATH)

    # =================================================== BAN FUNC ===============================================
    async def ban_func(
        self, 
        target,  # Принимает discord.Interaction или discord.TextChannel
        user: discord.User | discord.Member, 
        rule: str,
        reason: str = "Не указана",
        delete_message_days: int = 1):
        # Определяем контекст вызова (команда или AntiSpam/канал)
        is_interaction = isinstance(target, discord.Interaction) or hasattr(target, 'response')
        
        # Получаем объект сервера (Guild)
        guild = target.guild if hasattr(target, 'guild') and target.guild else getattr(user, 'guild', None)
        if not guild:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Не удалось определить сервер!", ephemeral=True)
            return

        # Преобразуем User в Member для проверки ролей и прав на сервере (если возможно)
        member = guild.get_member(user.id) if isinstance(user, discord.User) else user

        # 1. Проверки безопасности и прав
        if is_interaction and hasattr(target, 'user') and target.user:
            if user.id == target.user.id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя забанить самого себя!", ephemeral=True)
                return
                
            # Проверка иерархии ролей (только если пользователь находится на сервере)
            if member and isinstance(member, discord.Member):
                if member.top_role >= target.user.top_role and target.user.id != guild.owner_id:
                    await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя забанить пользователя с ролью выше или равной вашей!", ephemeral=True)
                    return

        if user.bot:
            await safe_send(target, "🤖 Нельзя модерировать бота!", ephemeral=True)
            return

        if member and isinstance(member, discord.Member):
            if member.guild_permissions.administrator:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя забанить администратора!", ephemeral=True)
                return

        # 2. Откладываем ответ при вызове из Interaction
        if is_interaction:
            try:
                if not target.response.is_done():
                    await target.response.defer()
            except Exception:
                pass

        # 3. Данные модератора и нарушителя
        moderator_mention = target.user.mention if (is_interaction and hasattr(target, 'user') and target.user) else self.bot.user.mention
        
        user_mention = user.mention
        user_avatar = user.display_avatar.url if user.display_avatar else None

        # 4. Отправка ЛС перед баном (пока пользователь еще не забанен)
        dm_embed = discord.Embed(
            title="<:banemoji:1515689296118677534> ʙы быᴧи нᴇйᴛᴩᴀᴧизоʙᴀны нᴀ ᴄᴇᴩʙᴇᴩᴇ",
            description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                        f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                        f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
            color=discord.Color.dark_blue(),
            timestamp=datetime.now()
        )
        if user_avatar:
            dm_embed.set_thumbnail(url=user_avatar)
        if guild.icon:
            dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

        try:
            await safe_dm_send(user.id, embed=dm_embed)
        except Exception as e:
            print(f"⚠️ Ошибка отправки ЛС перед баном ({user.id}): {e}")

        # 5. Исполнение БАНА
        try:
            # Учитываем модератора в причине бана для Audit Logs Discord
            ban_reason = f"Причина: {reason} | Модератор: {moderator_mention}"
            await guild.ban(user, reason=ban_reason, delete_message_days=delete_message_days)
            
            # Уведомление в чат/канал
            await safe_send(
                target, 
                f"<:banemoji:1515689296118677534> {user_mention} **был(а) уᴄᴛᴩᴀнён(а)** <:neutralizeemoji:1515694760990347325>. ᴨᴩичинᴀ: {rule}", 
                ephemeral=False)

            # 6. Отправка в канал логов
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id:
                log_channel = await safe_fetch_channel(self.bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:banemoji:1515689296118677534> /нейтрализовать",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                    f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                                    f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
                        color=discord.Color.brand_red(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)
                    
                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Недостаточно прав у бота для бана данного пользователя!", ephemeral=True)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка при выполнении бана: {e}", ephemeral=True)
            
    # =================================================== UNBAN FUNC ===============================================
    async def unban_func(self, target, name_or_id: str):
        # Определяем, вызвана ли функция через Interaction или обычный канал
        is_interaction = isinstance(target, discord.Interaction) or hasattr(target, 'response')
        bot = getattr(target, 'client', None) or getattr(target, 'bot', None) or getattr(self, 'bot', None)
        guild = target.guild if hasattr(target, 'guild') else None

        if not guild:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Не удалось определить сервер!", ephemeral=True)
            return

        # 1. Откладываем ответ для Interaction
        if is_interaction:
            try:
                if not target.response.is_done():
                    await target.response.defer()
            except Exception:
                pass

        # 2. Получаем список забаненных пользователей
        try:
            banned_users = [entry async for entry in guild.bans()]
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка получения бан-листа: {e}", ephemeral=True)
            return

        if not banned_users:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Бан-лист пуст!", ephemeral=True)
            return

        # 3. Ищем пользователя в бан-листе (ID / Username / Display Name)
        user = None
        query = name_or_id.strip().lower()

        if query.isdigit():
            user_id = int(query)
            for entry in banned_users:
                if entry.user.id == user_id:
                    user = entry.user
                    break
        else:
            for entry in banned_users:
                u = entry.user
                if (query in u.name.lower()) or (u.display_name and query in u.display_name.lower()):
                    user = u
                    break

        if not user:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Пользователь не найден в бан-листе!", ephemeral=True)
            return

        # 4. Локальное извлечение данных пользователя (без лишних HTTP-запросов к API)
        user_mention = user.mention
        user_id = user.id
        user_avatar = user.display_avatar.url if user.display_avatar else None
        moderator_mention = target.user.mention if (is_interaction and hasattr(target, 'user') and target.user) else (bot.user.mention if bot else "Система")

        # 5. Выполняем разбан
        try:
            await guild.unban(user, reason=f"Разбанен модератором: {moderator_mention}")

            # Уведомление в чат
            await safe_send(target, f"<:unbanemoji:1515696568156557433> ᴨоᴧьзоʙᴀᴛᴇᴧь {user_mention} **нᴇ ʙиноʙᴇн(на)**!", ephemeral=False)

            # 6. Логирование
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id and bot:
                log_channel = await safe_fetch_channel(bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:unbanemoji:1515696568156557433> /аппелировать",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                    f"`ᴀйди`: {user_id} <:peopleemoji:1517486620939649044>",
                        color=discord.Color.brand_green(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> У бота недостаточно прав для разбана!", ephemeral=True)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка при разбане: {e}", ephemeral=True)

    # =================================================== WARN FUNC ===============================================
    @staticmethod
    def warn_text(num: int) -> str:
        return {1: "ⲡⲉⲣⲃыⲙ", 2: "ⲃⲧⲟⲣыⲙ", 3: "ⲧⲣⲉⲧьⲉⲙ"}.get(num, "очᴇᴩᴇдныʍ")
    async def warn_func(
        self, 
        target, 
        member: discord.Member | discord.User, 
        rule: str,
        reason: str = "Не указана"):
        # Определяем контекст
        is_interaction = isinstance(target, discord.Interaction) or hasattr(target, 'response')
        bot = getattr(target, 'client', None) or getattr(target, 'bot', None) or getattr(self, 'bot', None)
        guild = target.guild if hasattr(target, 'guild') and target.guild else getattr(member, 'guild', None)

        if not guild:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Не удалось определить сервер!", ephemeral=True)
            return

        # Приводим User к Member для работы с ролями
        guild_member = guild.get_member(member.id) if isinstance(member, discord.User) else member

        if not guild_member:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Пользователь не найден на сервере!", ephemeral=True)
            return

        # 1. Проверки прав и безопасности
        if guild_member.bot:
            await safe_send(target, "🤖 Нельзя модерировать бота!", ephemeral=True)
            return

        if is_interaction and hasattr(target, 'user') and target.user:
            if guild_member.id == target.user.id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя модерировать самого себя!", ephemeral=True)
                return

            target_member = target if isinstance(target, discord.Member) else guild.get_member(target.id)
            if target_member and guild_member.top_role >= target_member.top_role and target_member.id != guild.owner_id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя выдать предупреждение пользователю с ролью выше или равной вашей!", ephemeral=True)
                return

        if guild_member.guild_permissions.administrator:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя выдавать предупреждение администратору!", ephemeral=True)
            return

        # 2. Проверка ролей из BotConfig
        category_role_id = BotConfig.ROLES.get('warnings_category')
        warn_role_ids = {
            1: BotConfig.ROLES.get('first_warn'),
            2: BotConfig.ROLES.get('second_warn'),
            3: BotConfig.ROLES.get('third_warn')
        }

        # 3. Данные из базы
        try:
            user_data = await self.manager.get_user_ruler(guild_member.id)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка базы данных: {e}", ephemeral=True)
            return

        if not user_data:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Пользователь не найден в базе данных!", ephemeral=True)
            return

        # 4. Откладываем ответ для Interaction
        if is_interaction:
            try:
                if not target.response.is_done():
                    await target.response.defer()
            except Exception:
                pass

        current_warns = user_data.get("warnings", 0)
        next_warn = current_warns + 1

        moderator_mention = target.user.mention if (is_interaction and hasattr(target, 'user') and target.user) else (bot.user.mention if bot else "Система")
        user_mention = guild_member.mention
        user_avatar = guild_member.display_avatar.url if guild_member.display_avatar else None

        try:
            # 5. Выдача ролей варнов
            if current_warns > 0 and current_warns in warn_role_ids:
                old_role = guild.get_role(warn_role_ids[current_warns])
                if old_role and old_role in guild_member.roles:
                    await guild_member.remove_roles(old_role)

            if next_warn in warn_role_ids:
                new_role = guild.get_role(warn_role_ids[next_warn])
                if new_role:
                    await guild_member.add_roles(new_role, reason=f"Предупреждение #{next_warn} | {reason}")

            # Выдача категории
            if category_role_id:
                category_role = guild.get_role(category_role_id)
                if category_role and category_role not in guild_member.roles:
                    await guild_member.add_roles(category_role)

            # 6. Обновление БД
            await self.manager.update_user_ruler(
                guild_member.id, 
                next_warn, 
                user_data.get('reputation', 0), 
                user_data.get('last_time_reputation', 0.0)
            )

            # 7. Отправка ЛС
            dm_embed = discord.Embed(
                title="<:warnemoji:1515687856549658774> ʙᴀʍ быᴧо ʙыдᴀно ᴨᴩᴇдуᴨᴩᴇждᴇниᴇ",
                description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                            f"`ʙᴀᴩноʙ ᴛᴇᴨᴇᴩь`: {next_warn} <:warningemoji:1515756604178305054>\n"
                            f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                            f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
                color=discord.Color.brand_red(),
                timestamp=datetime.now()
            )
            if user_avatar:
                dm_embed.set_thumbnail(url=user_avatar)
            if guild.icon:
                dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

            try:
                await safe_dm_send(guild_member.id, embed=dm_embed)
            except Exception as e:
                print(f"⚠️ Ошибка отправки ЛС варна ({guild_member.id}): {e}")

            # 8. Отправка ответа в чат
            await safe_send(
                target, 
                f"<:warnemoji:1515687856549658774> {user_mention} нᴀᴋᴀзᴀн **{self.warn_text(next_warn)}** ᴨᴩᴇдуᴨᴩᴇждᴇниᴇʍ! ᴨᴩичинᴀ: {rule}", 
                ephemeral=False
            )

            # 9. Авто-бан при 3 варнах
            if next_warn >= 3:
                try:
                    ban_dm = discord.Embed(
                        title="<:banemoji:1515689296118677534> ʙы быᴧи нᴇйᴛᴩᴀᴧизоʙᴀны нᴀ ᴄᴇᴩʙᴇᴩᴇ",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                                    f"`ᴨᴩиʍᴇчᴀниᴇ`: Достигнуто 3 предупреждения ({reason}) <:clearemoji:1515691240476377218>",
                        color=discord.Color.brand_red(),
                        timestamp=datetime.now()
                    )
                    if guild.icon:
                        ban_dm.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)
                    await safe_dm_send(guild_member.id, embed=ban_dm)
                except Exception:
                    pass

                await guild_member.ban(reason=f"3 предупреждения | Последнее: {reason} (Модератор: {moderator_mention})", delete_message_days=1)
                await safe_send(target, f"<:neutralizeemoji:1515694760990347325> {user_mention} **быᴧ нᴇйᴛᴩᴀᴧизоʙᴀн** зᴀ ᴨᴧохоᴇ ᴨоʙᴇдᴇниᴇ...")

            # 10. Логирование
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id and bot:
                log_channel = await safe_fetch_channel(bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:warnemoji:1515687856549658774> /выдать_предупреждение",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                    f"`ʙᴀᴩноʙ ᴛᴇᴨᴇᴩь`: {next_warn} <:warningemoji:1515756604178305054>\n"
                                    f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                                    f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
                        color=discord.Color.brand_red(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> У бота недостаточно прав для выдачи роли или бана!", ephemeral=True)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка при выдаче предупреждения: {e}", ephemeral=True)
    
    # =================================================== UNWARN FUNC ===============================================
    async def unwarn_member(self, target, member: discord.Member | discord.User, reason: str = "Аппеляция"):
        # Определяем контекст вызова (Interaction или канал)
        is_interaction = isinstance(target, discord.Interaction) or hasattr(target, 'response')
        bot = getattr(target, 'client', None) or getattr(target, 'bot', None) or getattr(self, 'bot', None)
        guild = target.guild if hasattr(target, 'guild') and target.guild else getattr(member, 'guild', None)

        if not guild:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Не удалось определить сервер!", ephemeral=True)
            return

        # Приводим User к Member
        guild_member = guild.get_member(member.id) if isinstance(member, discord.User) else member

        if not guild_member:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Пользователь не найден на сервере!", ephemeral=True)
            return

        # 1. Проверки безопасности и прав
        if guild_member.bot:
            await safe_send(target, "🤖 Нельзя модерировать бота!", ephemeral=True)
            return

        if is_interaction and hasattr(target, 'user') and target.user:
            if guild_member.id == target.user.id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя модерировать самого себя!", ephemeral=True)
                return

            if guild_member.top_role >= target.user.top_role and target.user.id != guild.owner_id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя убирать предупреждение пользователю с ролью выше или равной вашей!", ephemeral=True)
                return

        # 2. Получение данных из БД
        try:
            user_data = await self.manager.get_user_ruler(guild_member.id)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка получения данных из БД: {e}", ephemeral=True)
            return

        if not user_data:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Пользователь {guild_member.mention} не найден в базе данных!", ephemeral=True)
            return

        current_warns = user_data.get("warnings", 0)
        if current_warns <= 0:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> {guild_member.mention} не имеет предупреждений.", ephemeral=True)
            return

        # 3. Откладываем ответ для Interaction
        if is_interaction:
            try:
                if not target.response.is_done():
                    await target.response.defer()
            except Exception:
                pass

        # 4. Локальные данные модератора и пользователя
        moderator_mention = target.user.mention if (is_interaction and hasattr(target, 'user') and target.user) else (bot.user.mention if bot else "Система")
        user_mention = guild_member.mention
        user_avatar = guild_member.display_avatar.url if guild_member.display_avatar else None

        # 5. Вычисление ролей и обновление в Discord
        roles = {
            1: BotConfig.ROLES.get('first_warn'),
            2: BotConfig.ROLES.get('second_warn'),
            3: BotConfig.ROLES.get('third_warn'),
        }

        new_warns = current_warns - 1

        try:
            # Снимаем текущую роль предупреждения
            current_role_id = roles.get(current_warns)
            if current_role_id:
                current_role = guild.get_role(current_role_id)
                if current_role and current_role in guild_member.roles:
                    await guild_member.remove_roles(current_role)

            if new_warns > 0:
                # Выдаем предыдущую роль
                prev_role_id = roles.get(new_warns)
                if prev_role_id:
                    prev_role = guild.get_role(prev_role_id)
                    if prev_role and prev_role not in guild_member.roles:
                        await guild_member.add_roles(prev_role)
            else:
                # Если 0 варнов, снимаем общую категорию предупреждений
                category_role_id = BotConfig.ROLES.get('warnings_category')
                if category_role_id:
                    category_role = guild.get_role(category_role_id)
                    if category_role and category_role in guild_member.roles:
                        await guild_member.remove_roles(category_role)

            # 6. Обновление записи в базе данных
            await self.manager.update_user_ruler(
                guild_member.id,
                new_warns,
                user_data.get('reputation', 0),
                user_data.get('last_time_reputation', None)
            )

            # 7. Отправка ЛС пользователю
            dm_embed = discord.Embed(
                title="<:unbanemoji:1515696568156557433> ᴄ ʙᴀᴄ быᴧо ᴄняᴛо ᴨᴩᴇдуᴨᴩᴇждᴇниᴇ",
                description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                            f"`ʙᴀᴩноʙ оᴄᴛᴀᴧоᴄь`: {new_warns} <:warningemoji:1515756604178305054>",
                color=discord.Color.brand_green(),
                timestamp=datetime.now()
            )
            if user_avatar:
                dm_embed.set_thumbnail(url=user_avatar)
            if guild.icon:
                dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

            try:
                await safe_dm_send(guild_member.id, embed=dm_embed)
            except Exception as e:
                print(f"⚠️ Ошибка отправки ЛС при снятии варна ({guild_member.id}): {e}")

            # 8. Отправка ответа в чат
            await safe_send(
                target, 
                f"<:unbanemoji:1515696568156557433> {user_mention} **ᴀᴨᴨᴇᴧᴧиᴩоʙᴀн**. оᴄᴛᴀᴧоᴄь ᴨᴩᴇдуᴨᴩᴇждᴇний: **{new_warns}** <:warningemoji:1515756604178305054>", 
                ephemeral=False
            )

            # 9. Логирование
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id and bot:
                log_channel = await safe_fetch_channel(bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:unbanemoji:1515696568156557433> /снять_предупреждение",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                    f"`ʙᴀᴩноʙ оᴄᴛᴀᴧоᴄь`: {new_warns} <:warningemoji:1515756604178305054>",
                        color=discord.Color.brand_green(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Недостаточно прав у бота для изменения ролей пользователя!", ephemeral=True)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка при снятии предупреждения: {e}", ephemeral=True)

    # =================================================== KICK FUNC ===============================================
    async def kick_func(
        self, 
        target, 
        member: discord.Member | discord.User, 
        rule: str,
        reason: str = "Не указана"):
        # Определяем контекст вызова (Interaction или обычный канал)
        is_interaction = isinstance(target, discord.Interaction) or hasattr(target, 'response')
        bot = getattr(target, 'client', None) or getattr(target, 'bot', None) or getattr(self, 'bot', None)
        guild = target.guild if hasattr(target, 'guild') and target.guild else getattr(member, 'guild', None)

        if not guild:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Не удалось определить сервер!", ephemeral=True)
            return

        # Приводим User к Member для работы с ролями на сервере
        guild_member = guild.get_member(member.id) if isinstance(member, discord.User) else member

        if not guild_member:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Пользователь не найден на сервере!", ephemeral=True)
            return

        # 1. Проверки безопасности и прав
        if is_interaction and hasattr(target, 'user') and target.user:
            if guild_member.id == target.user.id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя кикнуть самого себя!", ephemeral=True)
                return

            # Проверка иерархии ролей
            if guild_member.top_role >= target.user.top_role and target.user.id != guild.owner_id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя кикнуть пользователя с ролью выше или равной вашей!", ephemeral=True)
                return

        if guild_member.bot:
            await safe_send(target, "🤖 Нельзя модерировать бота!", ephemeral=True)
            return

        if guild_member.guild_permissions.administrator:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя кикнуть администратора!", ephemeral=True)
            return

        # 2. Откладываем ответ для Interaction
        if is_interaction:
            try:
                if not target.response.is_done():
                    await target.response.defer()
            except Exception:
                pass

        # 3. Локальные данные модератора и пользователя (без HTTP-запросов к API)
        moderator_mention = target.user.mention if (is_interaction and hasattr(target, 'user') and target.user) else (bot.user.mention if bot else "Система")
        user_mention = guild_member.mention
        user_avatar = guild_member.display_avatar.url if guild_member.display_avatar else None

        # 4. Отправка ЛС перед киком
        dm_embed = discord.Embed(
            title="<:kickemoji:1515693208783425617> ʙы быᴧи ʙыᴦнᴀны ᴄ ᴄᴇᴩʙᴇᴩᴇ",
            description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                        f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                        f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
            color=discord.Color.brand_red(),
            timestamp=datetime.now()
        )
        if user_avatar:
            dm_embed.set_thumbnail(url=user_avatar)
        if guild.icon:
            dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

        try:
            await safe_dm_send(guild_member.id, embed=dm_embed)
        except Exception as e:
            print(f"⚠️ Ошибка отправки ЛС перед киком ({guild_member.id}): {e}")

        # 5. Выполняем КИК
        try:
            kick_reason = f"Причина: {rule} | Модератор: {moderator_mention}"
            await guild_member.kick(reason=kick_reason)

            # Сообщение в чат
            await safe_send(
                target, 
                f"<:kickemoji:1515693208783425617> {user_mention} **ʙᴩᴇʍᴇнно оᴛᴄᴛᴩᴀнён**. ᴨᴩичинᴀ: {rule}", 
                ephemeral=False
            )

            # 6. Отправка в канал логов
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id and bot:
                log_channel = await safe_fetch_channel(bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:kickemoji:1515693208783425617> /выгнать",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                    f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                                    f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
                        color=discord.Color.brand_red(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Недостаточно прав у бота для кика этого пользователя!", ephemeral=True)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка при выполнении кика: {e}", ephemeral=True)
        
    # =================================================== MUTE FUNC ===============================================
    async def mute_func(self, target, member: discord.Member, minutes: int, rule: str, reason: str = "Не указана"):
        # Определяем, вызвана ли функция через Interaction (слэш-команда)
        is_interaction = isinstance(target, discord.Interaction) or hasattr(target, 'response')
        
        # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: берем только живой, авторизованный клиент бота из взаимодействия!
        active_bot = target.client if is_interaction else self.bot
        
        # 1. Проверки безопасности
        if is_interaction and hasattr(target, 'user') and target.user:
            if member == target.user:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя замутить самого себя!", ephemeral=True)
                return
            if member.top_role >= target.user.top_role and target.user.id != target.guild.owner_id:
                await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя замутить пользователя с ролью выше вашей!", ephemeral=True)
                return

        if member.bot:
            await safe_send(target, "🤖 Нельзя модерировать бота!", ephemeral=True)
            return

        if member.guild_permissions.administrator:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Нельзя замутить администратора!", ephemeral=True)
            return

        # 2. Откладываем ответ для Interaction (если еще не отложен)
        if is_interaction:
            try:
                if not target.response.is_done():
                    await target.response.defer()
            except Exception:
                pass
                
        # 3. Расчет времени тайм-аута
        duration = timedelta(minutes=minutes)
        end_time = datetime.now() + duration
        end_timestamp = int(end_time.timestamp())

        guild = target.guild if hasattr(target, 'guild') and target.guild else member.guild

        # 4. Получение данных для ЛС и Логов (используем active_bot вместо self.bot)
        moderator_mention = target.user.mention if (is_interaction and hasattr(target, 'user') and target.user) else active_bot.user.mention
        
        user_mention = member.mention
        user_avatar = member.display_avatar.url if member.display_avatar else None

        # 5. Отправка ЛС пользователю
        dm_embed = discord.Embed(
            title="<:muteemoji:1515688038867538000> ʙы быᴧи зᴀдᴇᴩжᴀны нᴀ ᴄᴇᴩʙᴇᴩᴇ",
            description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                        f"`оᴄʙобождᴇниᴇ`: <t:{end_timestamp}:T> <:unmuteemoji:1515698075367112857>\n"
                        f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                        f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
            color=discord.Color.brand_red(),
            timestamp=datetime.now()
        )
        if user_avatar:
            dm_embed.set_thumbnail(url=user_avatar)
        if guild and guild.icon:
            dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)
        try:
            await safe_dm_send(member.id, embed=dm_embed)
        except Exception as e:
            print(f"⚠️ Не удалось отправить ЛС пользователю {member.id}: {e}")

        # 6. Применение Timeout через Discord API
        try:
            await member.timeout(duration, reason=f"Мут на {minutes} мин. Причина: {reason}")
            
            # Сообщение в чат/ответ на команду
            await safe_send(
                target, 
                f"<:muteemoji:1515688038867538000> {user_mention} **ᴀᴩᴇᴄᴛоʙᴀн**. оᴄʙобождᴇниᴇ ʙ <t:{end_timestamp}:T>. ᴨᴩичинᴀ: {rule}", 
                ephemeral=False
            )

            # Логирование
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id:
                # ИСПРАВЛЕНИЕ: Передаем в safe_fetch_channel гарантированно активный инстанс бота
                log_channel = await safe_fetch_channel(active_bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:muteemoji:1515688038867538000> /арестовать",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                    f"`оᴄʙобождᴇниᴇ`: <t:{end_timestamp}:T> <:unmuteemoji:1515698075367112857>\n"
                                    f"`нᴀᴩуɯᴇниᴇ`: {rule} <:pencilemoji:1525177241749950464>\n"
                                    f"`ᴨᴩиʍᴇчᴀниᴇ`: {reason} <:clearemoji:1515691240476377218>",
                        color=discord.Color.brand_red(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild and guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)
                    
                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Недостаточно прав у бота для применения Timeout!", ephemeral=True)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка при выполнении мута: {e}", ephemeral=True)
            
    # =================================================== UNMUTE FUNC ===============================================
    async def unmute_func(self, target, member: discord.Member, reason: str = "Досрочное освобождение"):
        # Определяем контекст вызова (Interaction или обычный канал)
        is_interaction = isinstance(target, discord.Interaction) or hasattr(target, 'response')
        bot = getattr(target, 'client', None) or getattr(target, 'bot', None) or getattr(self, 'bot', None)
        guild = target.guild if hasattr(target, 'guild') and target.guild else member.guild

        if not guild:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Не удалось определить сервер!", ephemeral=True)
            return

        # 1. Проверяем, находится ли пользователь в муте (через Timeout или роль)
        mute_role_id = BotConfig.ROLES.get('muted')
        mute_role = guild.get_role(mute_role_id) if mute_role_id else None

        has_timeout = member.is_timed_out()
        has_mute_role = mute_role in member.roles if mute_role else False

        if not has_timeout and not has_mute_role:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> У этого пользователя нет активного мута!", ephemeral=True)
            return

        # 2. Откладываем ответ для Interaction
        if is_interaction:
            try:
                if not target.response.is_done():
                    await target.response.defer()
            except Exception:
                pass

        # 3. Локальное получение данных пользователя (без HTTP-запросов к API)
        user_mention = member.mention
        user_avatar = member.display_avatar.url if member.display_avatar else None
        moderator_mention = target.user.mention if (is_interaction and hasattr(target, 'user') and target.user) else (bot.user.mention if bot else "Система")

        # 4. Отправка ЛС пользователю
        dm_embed = discord.Embed(
            title="<:unmuteemoji:1515698075367112857> ʙы быᴧи оᴄʙобождᴇны",
            description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                        f"`ᴨᴩичинᴀ`: {reason} <:clearemoji:1515691240476377218>",
            color=discord.Color.brand_green(),
            timestamp=datetime.now()
        )
        if user_avatar:
            dm_embed.set_thumbnail(url=user_avatar)
        if guild.icon:
            dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

        try:
            await safe_dm_send(member.id, embed=dm_embed)
        except Exception as e:
            print(f"⚠️ Ошибка отправки ЛС при размуте ({member.id}): {e}")

        # 5. Снятие мута (Timeout и Role)
        try:
            action_reason = f"Снятие мута | Модератор: {moderator_mention}"

            # Снимаем системный Timeout
            if has_timeout:
                await member.timeout(None, reason=action_reason)

            # Снимаем роль, если она была выдана
            if has_mute_role and mute_role:
                await member.remove_roles(mute_role, reason=action_reason)

            # Сообщение в чат
            await safe_send(
                target, 
                f"<:unmuteemoji:1515698075367112857> {user_mention} **зᴀᴋончиᴧ ᴄᴩоᴋ** доᴄᴩочно!", 
                ephemeral=False
            )

            # 6. Логирование
            log_channel_id = BotConfig.CHANNELS.get('mod_logs_commands')
            if log_channel_id and bot:
                log_channel = await safe_fetch_channel(bot, log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="<:unmuteemoji:1515698075367112857> /освободить",
                        description=f"`ʍодᴇᴩᴀᴛоᴩ`: {moderator_mention} <:forbbiden2emoji:1517479332866429008>\n"
                                    f"`ᴨоᴧьзоʙᴀᴛᴇᴧь`: {user_mention} <:reputationemoji:1517480379286556832>\n"
                                    f"`ᴨᴩичинᴀ`: {reason} <:clearemoji:1515691240476377218>",
                        color=discord.Color.brand_green(),
                        timestamp=datetime.now()
                    )
                    if user_avatar:
                        embed.set_thumbnail(url=user_avatar)
                    if guild.icon:
                        embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)

                    await safe_send(log_channel, embed=embed)

        except discord.Forbidden:
            await safe_send(target, "<:forbbiden2emoji:1517479332866429008> Недостаточно прав для снятия мута с пользователя!", ephemeral=True)
        except Exception as e:
            await safe_send(target, f"<:forbbiden2emoji:1517479332866429008> Ошибка при снятии мута: {e}", ephemeral=True)
            
    # =================================================== DM WELCOME FUNC ===============================================
    async def send_dm_welcome(self, member: discord.Member):
        guild = member.guild
        
        # Можно получить ID каналов из BotConfig (если они там прописаны)
        rules_channel_id = BotConfig.CHANNELS.get('rules')
        chat_channel_id = BotConfig.CHANNELS.get('chat')
        help_channel_id = BotConfig.CHANNELS.get('help')

        # Формируем кликабельные упоминания или оставляем красивый текст
        rules_mention = f"<#{rules_channel_id}>" if rules_channel_id else "`#правила`"
        chat_mention = f"<#{chat_channel_id}>" if chat_channel_id else "`#чат`"
        help_mention = f"<#{help_channel_id}>" if help_channel_id else "`#вопросы`"

        dm_embed = discord.Embed(
            title=f"Добро пожаловать в {guild.name}!",
            description=(
                f"Спасибо, что присоединились к нашему сообществу!\n\n"
                f"📖 Ознакомьтесь с правилами в канале {rules_mention}\n"
                f"🎉 Общайтесь и знакомьтесь в канале {chat_mention}\n"
                f"❓ Если есть вопросы, пишите в {help_mention}"
            ),
            color=discord.Color.darker_grey(),
            timestamp=datetime.now()
        )

        # Изображение и иконки
        dm_embed.set_image(url='https://aniyuki.com/wp-content/uploads/2022/08/aniyuki-hello-19.gif')
        
        if member.display_avatar:
            dm_embed.set_thumbnail(url=member.display_avatar.url)

        if guild.icon:
            dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁', icon_url=guild.icon.url)
        else:
            dm_embed.set_footer(text='𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁')

        # Отправка
        try:
            # Передаем member.id для соответствия safe_dm_send
            await safe_dm_send(member.id, embed=dm_embed)
        except discord.Forbidden:
            print(f"⚠️ У пользователя {member} (ID: {member.id}) закрыты ЛС.")
        except discord.HTTPException as e:
            print(f"❌ HTTP Ошибка при отправке приветствия в ЛС {member.id}: {e}")
        except Exception as e:
            print(f"❌ Ошибка отправки приветственного сообщения: {e}")

    async def get_base_roles(self, member: discord.Member):
        roles_to_add = set()

        # 1. Получение ранее сохраненных ролей из БД
        try:
            saved_role_ids = await self.manager.get_user_roles_ruler(member.id)
            for r_id in saved_role_ids:
                role = member.guild.get_role(r_id)
                if role and role.name != "@everyone" and role.is_assignable():
                    roles_to_add.add(role)
        except Exception as e:
            print(f"❌ Ошибка получения ролей из БД для {member}: {e}")

        # 2. Получение стандартных ролей при входе
        for role_id in BotConfig.WELCOME_ROLES.values():
            role = member.guild.get_role(role_id)
            if role and role.is_assignable():
                roles_to_add.add(role)

        # 3. Формирование списка параллельных задач
        tasks = []

        # Добавление всех ролей одним запросом
        if roles_to_add:
            tasks.append(
                member.add_roles(*roles_to_add, reason="Выдача ролей при входе (стандартные + восстановление)")
            )

        # Отправка Embed-приветствия в канал
        welcome_channel = await safe_fetch_channel(self.bot, BotConfig.CHANNELS['welcome'])
        if welcome_channel:
            joined_timestamp = int(member.joined_at.timestamp()) if member.joined_at else int(discord.utils.utcnow().timestamp())
            
            embed = discord.Embed(
                title="👋 Welcome!",
                description=f"ᴨᴩиʙᴇᴛ, {member.mention}!\nᴩᴀды ʙидᴇᴛь ᴛᴇбя нᴀ **{member.guild.name}**",
                color=discord.Color.dark_grey()
            )
            embed.add_field(name="📅 Присоединился", value=f"<t:{joined_timestamp}:R>", inline=True)
            embed.add_field(name="👤 Участников", value=str(member.guild.member_count), inline=True)
            
            if member.display_avatar:
                embed.set_thumbnail(url=member.display_avatar.url)

            tasks.append(safe_send(welcome_channel, embed=embed))

        # Отправка приветствия в личные сообщения
        tasks.append(self.send_dm_welcome(member))

        # ==================== ВЫПОЛНЕНИЕ ЗАДАЧ ====================
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"❌ Ошибка при обработке входа участника {member.name} (Задача #{i}): {result}")

    # =================================================== INFO COMMANDS ===============================================
    async def user_info_func(self, interaction: discord.Interaction, member: discord.Member):
        # 1. Проверка каналов (используем множество для быстрой проверки)
        allowed_channels = {BotConfig.CHANNELS['commands'], BotConfig.CHANNELS['mod_commands']}
        if interaction.channel_id not in allowed_channels:
            channels_mentions = ", ".join(f"<#{cid}>" for cid in allowed_channels)
            await safe_send(
                interaction, 
                f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в каналах: {channels_mentions}!", 
                ephemeral=True)
            return

        # 2. Проверка на бота
        if member is not None and member.bot:
            await safe_send(interaction, "🤖 Нельзя использовать команду на боте!", ephemeral=True)
            return

        # Определение цели (если пользователь не указан, берем автора команды)
        target_member = member or interaction.user

        # 3. Получение данных из базы данных
        user_data = await self.manager.get_user_ruler(target_member.id) or {}
        reputation = user_data.get("reputation", 0)

        # 4. Форматирование временных меток Discord
        created_ts = int(target_member.created_at.timestamp()) if target_member.created_at else 0
        
        # joined_at есть только у объектов discord.Member (участников сервера)
        if isinstance(target_member, discord.Member) and target_member.joined_at:
            joined_ts = int(target_member.joined_at.timestamp())
        else:
            joined_ts = 0

        # 5. Сборка Embed-сообщения
        embed = discord.Embed(
            title=f"<:techicalemoji:1515678259767939262> ɪɴꜰᴏʀᴍᴀᴛɪᴏɴ ᴀʙᴏᴜᴛ {target_member.display_name}",
            color=discord.Color.darker_grey(),
            timestamp=discord.utils.utcnow()
        )
        
        # Метод display_avatar.url автоматически обрабатывает отсутствие аватара и серверные аватары
        embed.set_thumbnail(url=target_member.display_avatar.url)

        embed.add_field(
            name="ɪᴅ <:peopleemoji:1517486620939649044>",
            value=f"`{target_member.id}`",
            inline=True
        )
        embed.add_field(
            name="иʍя ᴨоᴧьзоʙᴀᴛᴇᴧя <:coolemoji:1517487042018410577>",
            value=f"`{target_member.name}`",
            inline=True
        )
        embed.add_field(
            name="ʀᴇᴘᴜᴛᴀᴛɪᴏɴ <:reputationemoji:1517480379286556832>",
            value=f"**{reputation}**",
            inline=True
        )

        # Вывод даты создания с относительным временем (например: 12 июля 2024 г., 3 месяца назад)
        if created_ts:
            embed.add_field(
                name="ᴀᴋᴋᴀунᴛ ᴄоздᴀн",
                value=f"<t:{created_ts}:F> (<t:{created_ts}:R>)",
                inline=False
            )
        else:
            embed.add_field(
                name="ᴀᴋᴋᴀунᴛ ᴄоздᴀн",
                value="<:forbbiden2emoji:1517479332866429008> нᴇизʙᴇᴄᴛно",
                inline=False
            )

        # Вывод даты входа на сервер
        if joined_ts:
            embed.add_field(
                name="ᴨᴩиᴄоᴇдиниᴧᴄя",
                value=f"<t:{joined_ts}:F> (<t:{joined_ts}:R>)",
                inline=False
            )
        else:
            embed.add_field(
                name="ᴨᴩиᴄоᴇдиниᴧᴄя",
                value="<:forbbiden2emoji:1517479332866429008> нᴇизʙᴇᴄᴛно",
                inline=False
            )

        # Установка футера
        guild_icon = interaction.guild.icon.url if interaction.guild and interaction.guild.icon else None
        embed.set_footer(
            text=f"𝐅𝐈𝐆𝐇𝐓 𝐂𝐋𝐔𝐁 • Запросил: {interaction.user.display_name}",
            icon_url=guild_icon
        )

        await safe_send(interaction, embed=embed, ephemeral=False)

    async def reputation_info_func(self, interaction: discord.Interaction, member: discord.Member):
        allowed_channels = {BotConfig.CHANNELS['commands'], BotConfig.CHANNELS['mod_commands']}
        if interaction.channel_id not in allowed_channels:
            await safe_send(
                interaction, 
                f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в канале <#{BotConfig.CHANNELS['commands']}>!", 
                ephemeral=True
            )
            return

        if member is not None and member.bot:
            await safe_send(interaction, "🤖 Нельзя использовать команду на боте!", ephemeral=True)
            return

        target_member = member or interaction.user

        user_data = await self.manager.get_user_ruler(target_member.id) or {}
        reputation = user_data.get("reputation", 0)

        embed = discord.Embed(
            title=f"<:peopleemoji:1517486620939649044> {target_member.display_name}'s ʀᴇᴘᴜᴛᴀᴛɪᴏɴ",
            description=(
                f"у ᴨоᴧьзоʙᴀᴛᴇᴧя **{reputation} очᴋоʙ ᴩᴇᴨуᴛᴀции** <:reputationemoji:1517480379286556832>\n"
                f"дᴧя уʙᴇᴧичᴇния чьᴇй-ᴛо ᴩᴇᴨуᴛᴀции иᴄᴨоᴧьзуйᴛᴇ `+rep @User`"
            ),
            color=discord.Color.darker_grey()
        )
        
        embed.set_thumbnail(url=target_member.display_avatar.url)
        
        await safe_send(interaction, embed=embed, ephemeral=False)

    async def level_info_func(self, interaction: discord.Interaction, member: discord.Member):
        # 1. Проверка каналов
        allowed_channels = {BotConfig.CHANNELS['commands'], BotConfig.CHANNELS['mod_commands']}
        if interaction.channel_id not in allowed_channels:
            channels_mentions = ", ".join(f"<#{cid}>" for cid in allowed_channels)
            await safe_send(
                interaction, 
                f"<:forbbiden2emoji:1517479332866429008> Эта команда работает только в каналах: {channels_mentions}!", 
                ephemeral=True)
            return

        # 2. Проверка на бота
        if member is not None and member.bot:
            await safe_send(interaction, "🤖 Нельзя использовать команду на боте!", ephemeral=True)
            return

        # 3. Откладываем ответ (defer), так как генерация картинки может занять время
        await interaction.response.defer()

        target_member = member or interaction.user

        # 4. Получение данных из БД
        data = await self.manager.get_user_data(target_member.id) or {}
        user_level = data.get("level", 0)
        current_xp = data.get("xp", 0)
        role_name = data.get("role")

        next_level_xp = await self.manager.get_xp_needed(user_level) or 100

        # 5. Определение роли по уровню, если она не установлена в БД
        if not role_name or role_name == "Нет роли":
            role_name = "Участник"  # Значение по умолчанию
            for lvl, r_id in sorted(BotConfig.LEVEL_ROLES.items(), key=lambda item: item[0], reverse=True):
                if user_level >= lvl:
                    role = interaction.guild.get_role(r_id)
                    if role:
                        role_name = role.name
                        break

        # 6. Генерация и отправка карточки
        avatar_url = target_member.display_avatar.url

        try:
            image_buf = await self.generate_level_card(
                username=target_member.display_name,
                avatar_url=avatar_url,
                level=user_level,
                current_xp=current_xp,
                next_level_xp=next_level_xp,
                role_name=role_name
            )
            
            discord_file = discord.File(fp=image_buf, filename="level_card.png")
            
            # После defer() отправка идет через followup или safe_send
            await safe_send(interaction, file=discord_file)

        except Exception as e:
            print(f"❌ Ошибка при отправке карточки уровня для {target_member}: {e}")
            # После defer() нельзя отправить ephemeral-сообщение, если defer не был ephemeral
            await safe_send(interaction, "⚠️ Произошла ошибка при генерации карточки уровня.")

    # ========== ГЕНЕРАЦИЯ КАРТИНКИ ==========

    async def generate_level_card(self, username: str, avatar_url: str, level: int, current_xp: int, next_level_xp: int, role_name: str) -> io.BytesIO:
        width, height = 600, 200
        card = Image.new("RGBA", (width, height), (24, 25, 28, 255))
        draw = ImageDraw.Draw(card)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as response:
                if response.status == 200:
                    avatar_bytes = await response.read()
                    avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                else:
                    avatar_img = Image.new("RGBA", (120, 120), (100, 100, 100, 255))

        avatar_img = avatar_img.resize((120, 120))
        mask = Image.new("L", (120, 120), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, 120, 120), fill=255)
        avatar_rounded = ImageOps.fit(avatar_img, (120, 120), centering=(0.5, 0.5))
        avatar_rounded.putalpha(mask)
        
        card.paste(avatar_rounded, (40, 40), avatar_rounded)
        
        try:
            font_name = ImageFont.truetype(BotConfig.FONT_PATH, 28)
            font_info = ImageFont.truetype(BotConfig.FONT_PATH, 22)
            font_sub = ImageFont.truetype(BotConfig.FONT_PATH, 16)
        except IOError:
            font_name = font_info = font_sub = ImageFont.load_default()

        draw.text((190, 35), username, font=font_name, fill=(255, 255, 255, 255))
        draw.text((190, 75), f"Уровень: {level}", font=font_info, fill=(114, 137, 218, 255))
        draw.text((190, 110), f"Роль по лвлу: {role_name}", font=font_sub, fill=(185, 187, 190, 255))
        
        xp_text = f"{current_xp} / {next_level_xp} XP"
        draw.text((560, 125), xp_text, font=font_sub, fill=(185, 187, 190, 255), anchor="ra")

        bar_x, bar_y = 190, 150
        bar_width, bar_height = 370, 16
        
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], radius=8, fill=(47, 49, 54, 255))
        
        xp_percentage = min(current_xp / next_level_xp, 1.0)
        if xp_percentage > 0:
            current_bar_width = int(bar_width * xp_percentage)
            draw.rounded_rectangle([bar_x, bar_y, bar_x + current_bar_width, bar_y + bar_height], radius=8, fill=(114, 137, 218, 255))

        image_binary = io.BytesIO()
        card.save(image_binary, "PNG")
        image_binary.seek(0)
        return image_binary