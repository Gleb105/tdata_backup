import os
import re

def join_parts(base_name='data.zip'):
    part_files = [f for f in os.listdir('.') if re.match(re.escape(base_name) + r'\.part\d{3}$', f)]
    if not part_files:
        print('Части архива не найдены!')
        return
    part_files.sort(key=lambda x: int(x.split('.part')[-1]))
    print(f'Найдено частей: {len(part_files)}')
    with open(base_name, 'wb') as outfile:
        for part in part_files:
            print(f'Добавляю {part}...')
            with open(part, 'rb') as infile:
                while True:
                    chunk = infile.read(1024 * 1024)
                    if not chunk:
                        break
                    outfile.write(chunk)
    print(f'Готово! Архив {base_name} собран.')

if __name__ == '__main__':
    join_parts('data.zip') 