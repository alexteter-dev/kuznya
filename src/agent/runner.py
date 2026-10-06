"""
Запуск игрового сервера и тестовые подключения к нему: агент может сам сыграть в то, что сделал.
"""

# -- импорт библиотек
import collections
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

INTERPRETER = Path(__file__).resolve().parent.parent.parent / 'interpreter' / 'src' / 'main.py'
COLOR_TAG = re.compile(r'</?color[^>]*>')


class RunnerError(Exception):
    pass


class ServerRunner:
    def __init__(self):
        self.process = None
        self.lines = collections.deque(maxlen=5000)

    def running(self):
        return self.process is not None and self.process.poll() is None

    def _read(self, pipe):
        for line in iter(pipe.readline, ''):
            self.lines.append(line.rstrip('\n'))

    def start(self, world_file):
        if self.running():
            raise RunnerError("The server is already running. Call server_stop first.")
        self.lines.clear()

        environment = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        options = {}
        if os.name == 'nt':
            # отдельная группа процессов, чтобы серверу можно было послать CTRL_BREAK
            options['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options['start_new_session'] = True
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(INTERPRETER), str(Path(world_file))],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', bufsize=1, env=environment,
            cwd=str(INTERPRETER.parent), **options,
        )
        threading.Thread(target=self._read, args=(self.process.stdout,), daemon=True).start()

        # ждем, пока сервер поднимется или упадет
        deadline = time.time() + 15
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RunnerError("The server exited on startup:\n" + '\n'.join(self.lines))
            if any('ws://' in line for line in self.lines):
                break
            time.sleep(0.1)
        time.sleep(0.3)

    def stop(self):
        if self.process is None:
            raise RunnerError("The server is not running.")
        if self.process.poll() is None:
            try:
                if os.name == 'nt':
                    self.process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGINT)
                self.process.wait(timeout=15)
            except (subprocess.TimeoutExpired, OSError):
                self.process.kill()
                self.process.wait()
        self.process = None
        return list(self.lines)[-15:]

    def status(self, world):
        running = self.running()
        host = 'localhost' if world.host in ('0.0.0.0', '') else world.host
        status = {'running': running}
        if running:
            status['web_client'] = f"http://{host}:{world.port_web}"
            status['websocket'] = f"ws://{host}:{world.port_wss}"
        errors = [line for line in self.lines if 'script error' in line or 'Traceback' in line]
        status['script_errors'] = len(errors)
        if not running and self.lines:
            status['last_logs'] = list(self.lines)[-10:]
        return status

    def logs(self, tail=60, contains=None):
        lines = list(self.lines)
        if contains:
            lines = [line for line in lines if contains in line]
        return '\n'.join(lines[-tail:]) or '(no output)'


class PlaySessions:
    def __init__(self):
        self.sessions = {}

    def _get(self, session):
        if session not in self.sessions:
            raise RunnerError(f"Unknown play session '{session}'. Call play_connect.")
        return self.sessions[session]

    def connect(self, url, wait):
        from websockets.sync.client import connect

        try:
            socket = connect(url, open_timeout=5)
        except OSError as error:
            raise RunnerError(f"Cannot connect to {url}: {error}")
        entry = {'socket': socket, 'inbox': [], 'lock': threading.Lock(), 'open': True}

        def reader():
            try:
                for message in socket:
                    with entry['lock']:
                        entry['inbox'].append(message if isinstance(message, str) else message.decode('utf-8'))
            except Exception:
                pass
            entry['open'] = False

        threading.Thread(target=reader, daemon=True).start()
        session = secrets.token_hex(3)
        self.sessions[session] = entry
        return {'session': session, **self.read(session, wait, False)}

    def read(self, session, wait=0.0, raw=False):
        entry = self._get(session)
        if wait > 0:
            time.sleep(min(wait, 60))
        with entry['lock']:
            messages, entry['inbox'] = entry['inbox'], []
        if not raw:
            messages = [COLOR_TAG.sub('', message) for message in messages]
        return {'connected': entry['open'], 'messages': messages}

    def send(self, session, text, wait=0.6, raw=False):
        entry = self._get(session)
        if not entry['open']:
            raise RunnerError("The session is closed by the server.")
        entry['socket'].send(text)
        return self.read(session, wait, raw)

    def close(self, session):
        entry = self._get(session)
        try:
            entry['socket'].close()
        except Exception:
            pass
        del self.sessions[session]
        return {'closed': session}

    def close_all(self):
        for session in list(self.sessions):
            self.close(session)
