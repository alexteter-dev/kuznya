import argparse
import os
import pathlib
import sys

# скрипт запускается как __main__, а остальные модули импортируют его как main:
# без этой строки мир загружался бы дважды
sys.modules.setdefault('main', sys.modules[__name__])

from loop import run
from utils.game import World
import time

# -- объявление функций
def valid_world_file(path):
    if not os.path.isfile(path):
        raise argparse.ArgumentTypeError(f"Файл мира '{path}' не существует")
    if not os.access(path, os.R_OK):
        raise argparse.ArgumentTypeError(f"Файл мира '{path}' недоступен для чтения")
    return path

# -- объявление переменных
parser = argparse.ArgumentParser(
    prog='Игровой сервер приложения КУЗНЯ.',
    description='Это часть движка КУЗНЯ, запускаемая для симуляции мира. Может быть запущена отдельно.',
    epilog='Исходный код: https://github.com/DanielBash/kuznya')
parser.add_argument('world_file', type=valid_world_file, help='Путь к файлу игрового мира')

# -- константы
args = parser.parse_args()
world = World().load_filename(pathlib.Path(args.world_file))

if __name__ == "__main__":
    run()
