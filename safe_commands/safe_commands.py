import os, discord, asyncio
from pathlib import Path
from discord.errors import HTTPException, Forbidden, NotFound
from discord import Interaction, Message

BASE_DIR = Path(__file__).parent
class SafeCommands():
    def __init__(self, bot=None):
        self.bot = bot
        
    # ========== БЕЗОПАСНАЯ ОТПРАВКА СООБЩЕНИЙ ==========
    async def safe_delete(self, message, delay=0, max_retries=3):
        if delay > 0:
            await asyncio.sleep(delay)
        
        for attempt in range(max_retries):
            try:
                await message.delete()
                return True
            except HTTPException as e:
                if e.status == 429:  # Rate limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after)
                    continue
                elif e.status == 403:  # Forbidden - нет прав
                    return False
                elif e.status == 404:  # Not Found - уже удалено
                    return True
                else:
                    return False
            except (Forbidden, NotFound):
                return False
            except:
                return False
        return False

    async def safe_reply(self, message, content=None, max_retries=3, **kwargs):
        if content is None and not kwargs.get('embed') and not kwargs.get('file'):
            return None
        
        for attempt in range(max_retries):
            try:
                return await message.reply(content, **kwargs)
            except HTTPException as e:
                if e.status == 429:  # Rate limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    return None
            except:
                return None
        return None

    async def safe_send(self, destination, content=None, max_retries=3, **kwargs):
        if content is None and not kwargs.get('embed') and not kwargs.get('file'):
            return None
        
        # Определяем объект для отправки
        send_target = None
        
        # Проверяем, является ли destination Interaction
        if isinstance(destination, Interaction):
            # Для Interaction используем response или followup
            if not destination.response.is_done():
                # Если ответ еще не отправлен
                for attempt in range(max_retries):
                    try:
                        if kwargs.get('ephemeral'):
                            await destination.response.send_message(content, **kwargs)
                        else:
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
            else:
                # Если ответ уже отправлен, используем followup
                for attempt in range(max_retries):
                    try:
                        if kwargs.get('ephemeral', False):
                            return await destination.followup.send(content, **kwargs)
                        else:
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
            return None
        
        # Для остальных объектов
        if hasattr(destination, 'send'):
            send_target = destination
        elif hasattr(destination, 'channel') and hasattr(destination.channel, 'send'):
            # Для контекста команд
            send_target = destination.channel
        elif hasattr(destination, 'message') and hasattr(destination.message, 'channel'):
            # Для некоторых объектов
            send_target = destination.message.channel
        else:
            return None
        
        for attempt in range(max_retries):
            try:
                return await send_target.send(content, **kwargs)
            except HTTPException as e:
                if e.status == 429:  # Rate limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    return None
            except:
                return None
        return None
    
    async def send_with_view(interaction, embed, view, content=None, ephemeral=False):
        try:
            if interaction.response.is_done():
                # Если уже отвечали - используем followup
                message = await interaction.followup.send(
                    content=content,
                    embed=embed,
                    view=view,
                    ephemeral=ephemeral
                )
            else:
                # Отправляем новый ответ
                await interaction.response.send_message(
                    content=content,
                    embed=embed,
                    view=view,
                    ephemeral=ephemeral
                )
                message = await interaction.original_response()
            
            # ✅ Сохраняем сообщение в view
            if isinstance(message, discord.Message):
                view.message = message
            else:
                print(f"⚠️ Получен не-Message объект: {type(message)}")
            
            return message
        except Exception as e:
            print(f"❌ Ошибка при отправке: {e}")
            return None

    async def safe_dm_send(self, user_or_id, content=None, embed=None, view=None, max_retries=3):
        # Получаем пользователя, если передан ID
        if isinstance(user_or_id, int):
            user = await self.safe_fetch_user(self.bot, user_or_id)
            if not user:
                print(f"❌ Пользователь {user_or_id} не найден!")
                return False
        else:
            user = user_or_id
        
        # Проверяем, что пользователь существует
        if not user:
            print("❌ Пользователь не указан!")
            return False
        
        # Отправляем с повторными попытками
        for attempt in range(max_retries):
            try:
                await user.send(content=content, embed=embed, view=view)
                return True
                
            except discord.Forbidden:
                print(f"❌ Нет доступа к ЛС {user.name} (закрытые DM или бот заблокирован)")
                return False
                
            except discord.HTTPException as e:
                if e.status == 429:  # Rate Limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    wait_time = retry_after * (attempt + 1)
                    print(f"⏳ Rate limit, ждем {wait_time} сек...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    print(f"❌ HTTP ошибка: {e.status}")
                    return False
                    

    async def safe_edit(self, interaction_or_message, content=None, max_retries=3, **kwargs):
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

    @staticmethod
    async def safe_fetch_user(bot, user_id: int):
        # 1. Пытаемся взять из быстрой памяти
        user = bot.get_user(user_id)
        if user is not None:
            return user

        # 2. Безопасное ожидание авторизации бота
        attempts = 0
        while not bot.is_ready():
            if attempts > 20:
                return None
            await asyncio.sleep(0.5)
            attempts += 1
            
            user = bot.get_user(user_id)
            if user is not None:
                return user

        # 3. Запрашиваем у серверов Discord
        try:
            return await bot.fetch_user(user_id)
        except discord.NotFound:
            return None
        except Exception as e:
            print(f"❌ Не удалось получить пользователя {user_id}: {e}")
            return None
        
    @staticmethod
    async def safe_fetch_channel(bot, channel_id: int, max_retries: int = 3):
        # 1. Сначала ВСЕГДА ищем в быстром кэше (это не требует сети и никогда не падает)
        channel = bot.get_channel(channel_id)
        if channel is not None:
            return channel

        # 2. Безопасное ожидание запуска бота без использования wait_until_ready()
        # Если бот еще не вошел в сеть, мы просто засыпаем на 0.5 секунды по кругу
        attempts = 0
        while not bot.is_ready():
            if attempts > 20: # Защита от вечного цикла (максимум ждем 10 секунд)
                print(f"⚠️ Бот так и не авторизовался за 10 секунд. Канал {channel_id} пропущен.")
                return None
            print(f"⏳ Канал {channel_id} запрошен до авторизации бота. Ожидаем готовности клиента...")
            await asyncio.sleep(0.5)
            attempts += 1
            
            # Пытаемся снова забрать из кэша после паузы
            channel = bot.get_channel(channel_id)
            if channel is not None:
                return channel

        # 3. Делаем безопасный запрос к API Discord
        for attempt in range(max_retries):
            try:
                return await bot.fetch_channel(channel_id)
            except discord.HTTPException as e:
                if e.status == 429:  # Rate Limit
                    retry_after = float(e.response.headers.get('Retry-After', 1))
                    await asyncio.sleep(retry_after * (attempt + 1))
                    continue
                else:
                    print(f"❌ HTTP ошибка при получении канала {channel_id}: {e}")
                    return None
            except discord.Forbidden:
                print(f"❌ Нет доступа к каналу {channel_id}")
                return None
            except discord.NotFound:
                print(f"❌ Канал {channel_id} не найден")
                return None
            except Exception as e:
                print(f"❌ Ошибка при получении канала {channel_id}: {e}")
                return None
                
        return None