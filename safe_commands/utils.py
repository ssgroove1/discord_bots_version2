from .safe_commands import SafeCommands

# Глобальный экземпляр
_safe = None

def init_safe(bot):
    """Инициализация SafeCommands"""
    global _safe
    _safe = SafeCommands(bot)
    return _safe

def get_safe():
    """Получить экземпляр SafeCommands"""
    return _safe

# ========== ФУНКЦИИ-ОБЕРТКИ ==========

async def safe_send(destination, content=None, **kwargs):
    """Безопасная отправка"""
    s = get_safe()
    if s:
        return await s.safe_send(destination, content, **kwargs)
    return None

async def send_with_view(embed=None, view=None, content=None, **kwargs):
    """Безопасная отправка"""
    s = get_safe()
    if s:
        return await s.send_with_view(embed, view, content, **kwargs)
    return None

async def safe_reply(destination, content=None, **kwargs):
    """Безопасный ответ"""
    s = get_safe()
    if s:
        return await s.safe_reply(destination, content, **kwargs)
    return None

async def safe_edit(destination, content=None, **kwargs):
    """Безопасное редактирование"""
    s = get_safe()
    if s:
        return await s.safe_edit(destination, content, **kwargs)
    return None

async def safe_delete(message, delay=0):
    """Безопасное удаление"""
    s = get_safe()
    if s:
        return await s.safe_delete(message, delay)
    return False

async def safe_dm_send(user_or_id, content=None, embed=None):
    """Безопасная отправка в ЛС"""
    s = get_safe()
    if s:
        return await s.safe_dm_send(user_or_id, content, embed)
    return False

async def safe_fetch_channel(bot, channel_id):
    """Безопасное получение канала"""
    s = get_safe()
    if s:
        s.bot = bot  # Обновляем бота
        return await s.safe_fetch_channel(bot, channel_id)
    return None

async def safe_fetch_user(bot, user_id):
    """Безопасное получение пользователя"""
    s = get_safe()
    if s:
        s.bot = bot  # Обновляем бота
        return await s.safe_fetch_user(bot, user_id)
    return None