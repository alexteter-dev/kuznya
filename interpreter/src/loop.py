import atexit
import signal
import sys
import time
import traceback


def game_loop(world):
    from utils import network

    print("[СЕРВЕР] Запуск сервера.")

    def save_on_exit():
        print("[СЕРВЕР] Сохранение мира...")
        world.save_filename(world.filename)
        print("[СЕРВЕР] Мир сохранен.")

    atexit.register(save_on_exit)

    # мягкая остановка (в том числе на Windows), чтобы мир успел сохраниться
    def stop(*args):
        sys.exit(0)

    for name in ('SIGTERM', 'SIGBREAK'):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), stop)

    world.start()

    while True:
        network.ws_manager.update()

        for conn in network.ws_manager.connections:
            messages = conn.get_messages()
            for message in messages:
                try:
                    conn.connected_object.trigger('on_message', message)
                except Exception as e:
                    # ошибка в скрипте не должна ронять весь сервер
                    print(f"[script error] {e}")
                    traceback.print_exc()

        world.tick()
        time.sleep(0.005)


def run():
    from main import world

    try:
        game_loop(world)
    except KeyboardInterrupt:
        print("\n[СЕРВЕР] Выключение сервера.")
