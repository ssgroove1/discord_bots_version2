import subprocess
import os
import sys
import time
import threading
from pathlib import Path

# 1. Определяем корневую папку проекта
BASE_DIR = Path(__file__).parent.absolute()
print(f"📁 Корень проекта: {BASE_DIR}")

# 2. Загружаем переменные из shared.env с очисткой кавычек
env_file = BASE_DIR / 'shared.env'
if env_file.exists():
    print(f"✅ Найден файл .env: {env_file}")
    with open(env_file, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                try:
                    key, value = line.split('=', 1)
                    # Очищаем возможные кавычки по краям значения
                    value = value.strip('\'"')
                    os.environ[key] = value
                except ValueError:
                    continue
else:
    print(f"❌ Файл .env НЕ НАЙДЕН: {env_file}")

# 3. Проверяем токены
print("\n🔍 Проверка токенов:")
for name in ['BOT_TOKEN_RULER', 'BOT_TOKEN_FUNBOT', 'BOT_TOKEN_ECONOMIC']:
    token = os.getenv(name)
    print(f"  {'✅' if token else '❌'} {name}: {'найден' if token else 'НЕ НАЙДЕН!'}")

# 4. Список ботов
bots_config = [
    {"path": BASE_DIR / "FightClubBot", "name": "FightClubBot"},
    {"path": BASE_DIR / "FunBot", "name": "FunBot"},
    {"path": BASE_DIR / "TheEconomic", "name": "TheEconomic"},
]

python_executable = sys.executable
print(f"\n🐍 Использую Python: {python_executable}")

# Глобальные структуры для управления процессами
active_processes = {}  # {bot_name: subprocess.Popen}
running = True

def read_output(process, name):
    """Считывает вывод конкретного процесса и выводит его в консоль."""
    try:
        # Читаем построчно, пока процесс активен и поток вывода открыт
        while process.poll() is None:
            line = process.stdout.readline()
            if line:
                print(f"[{name}] {line.strip()}")
            else:
                time.sleep(0.1)
        # Дочитываем остатки после завершения процесса
        for line in process.stdout:
            print(f"[{name}] {line.strip()}")
    except Exception as e:
        if running:  # Не выводим ошибки чтения при намеренной остановке
            print(f"[{name}] ⚠️ Ошибка чтения вывода: {e}")

def run_bot_manager(bot):
    """Управляет жизненным циклом одного бота (запуск и авто-рестарт)."""
    global running
    bot_name = bot["name"]
    bot_file = bot["path"] / "bot.py"
    
    if not bot_file.exists():
        print(f"❌ [{bot_name}] Файл не найден: {bot_file}")
        return

    env = os.environ.copy()

    while running:
        print(f"🚀 [{bot_name}] Запуск процесса...")
        try:
            process = subprocess.Popen(
                [python_executable, "-u", str(bot_file)],  # <- Добавили "-u" для моментального сброса логов
                cwd=str(bot["path"]),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1  # Построчный буфер на стороне менеджера
            )
            active_processes[bot_name] = process
            print(f"✅ [{bot_name}] Успешно запущен (PID: {process.pid})")
            
            # Запускаем поток для чтения логов конкретно этого запуска
            log_thread = threading.Thread(
                target=read_output, 
                args=(process, bot_name), 
                daemon=True
            )
            log_thread.start()
            
            # Ждем, пока процесс работает
            process.wait()
            
            if running:
                print(f"⚠️ [{bot_name}] Процесс завершился с кодом {process.returncode}. Перезапуск через 5 секунд...")
                time.sleep(5)
                
        except Exception as e:
            print(f"❌ [{bot_name}] Ошибка при запуске: {e}")
            if running:
                time.sleep(10)

# Запуск менеджеров для каждого бота в отдельных потоках
manager_threads = []
for bot in bots_config:
    t = threading.Thread(target=run_bot_manager, args=(bot,), daemon=True)
    t.start()
    manager_threads.append(t)

print(f"\n🎯 Инициализировано ботов: {len(bots_config)}")
print("📝 Логи выводятся в реальном времени ниже...")
print("🛑 Для остановки нажмите Ctrl+C\n")

# Основной цикл ожидания прерывания
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Получен сигнал остановки. Завершаем работу ботов...")
    running = False  # Отключает триггер авто-перезапуска
    
    for name, p in list(active_processes.items()):
        print(f"⏳ Останавливаем {name} (PID: {p.pid})...")
        p.terminate()
        try:
            p.wait(timeout=5)
            print(f"✅ {name} остановлен.")
        except subprocess.TimeoutExpired:
            print(f"💀 {name} не ответил на вежливое закрытие. Принудительное уничтожение (kill)...")
            p.kill()
            
    print("👋 Все процессы успешно завершены.")