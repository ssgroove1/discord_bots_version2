import subprocess, os, sys
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent.parent / 'shared.env'
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ Загружен .env: {env_file}")
else:
    print(f"⚠️ Файл .env не найден: {env_file}")
# Текущая директория: /home/container
base_dir = os.getcwd()  # /home/container

# Пути к ботам
bots = [
    {"path": os.path.join(base_dir, "FightClubBot"), "file": "bot.py"},
    {"path": os.path.join(base_dir, "FunBot"), "file": "bot.py"},
    {"path": os.path.join(base_dir, "TheEconomic"), "file": "bot.py"},
]

# Определяем, какой Python использовать
python_executable = sys.executable  # полный путь к python

print(f"Использую Python: {python_executable}")

processes = []
for bot in bots:
    bot_file = os.path.join(bot["path"], bot["file"])
    
    # Проверяем, существует ли файл бота
    if not os.path.exists(bot_file):
        print(f"❌ Файл не найден: {bot_file}")
        continue
    
    print(f"🚀 Запускаю: {bot_file}")
    
    # Запускаем процесс
    process = subprocess.Popen(
        [python_executable, bot["file"]],  # используем полный путь к python
        cwd=bot["path"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    processes.append(process)
    print(f"✅ Запущен бот в {bot['path']} (PID: {process.pid})")

print(f"\n🎯 Запущено ботов: {len(processes)}")
print("📝 Логи будут выводиться ниже...")
print("🛑 Нажмите Ctrl+C для остановки всех ботов\n")

# Функция для чтения вывода процессов
def read_output(process, name):
    try:
        stdout, stderr = process.communicate(timeout=0.1)
        if stdout:
            print(f"[{name}] {stdout.strip()}")
        if stderr:
            print(f"[{name} ERROR] {stderr.strip()}")
    except subprocess.TimeoutExpired:
        pass

# Ждём завершения или Ctrl+C
try:
    while True:
        for i, p in enumerate(processes):
            read_output(p, f"Bot{i+1}")
        import time
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Останавливаем ботов...")
    for p in processes:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    print("✅ Все боты остановлены")