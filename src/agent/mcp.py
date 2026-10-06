"""
MCP-сервер Кузни: протокол Model Context Protocol поверх stdio и поверх HTTP.
Реализован без внешних зависимостей: JSON-RPC 2.0, методы initialize, ping, tools/list, tools/call.
"""

# -- импорт библиотек
import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .tools import ToolError

# -- константы
PROTOCOL_VERSIONS = ['2025-11-25', '2025-06-18', '2025-03-26', '2024-11-05']
SERVER_INFO = {'name': 'kuznya', 'title': 'Кузня', 'version': '1.0.0'}
INSTRUCTIONS = (
    "Kuznya is an engine for online text RPGs (MU*). These tools edit a world file: scripts (Python), "
    "objects, prefabs and characters, shareable assets, and they can run the game and play it. "
    "Call engine_docs first to learn the scripting API. Open a world with world_open or world_new before "
    "anything else. After changing scripts, run the game (server_start, play_connect, play_send) and check "
    "server_logs for script errors."
)


class McpDispatcher:
    """Обработка сообщений JSON-RPC. Не зависит от транспорта."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.lock = threading.Lock()

    def handle(self, message):
        """Возвращает ответ или None, если ответа не требуется (уведомление)"""
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0':
            return self.error(None, -32600, 'Invalid Request')
        method = message.get('method')
        identifier = message.get('id')
        if method is None or identifier is None:
            # ответы клиента и уведомления: отвечать не нужно
            return None
        try:
            result = self.dispatch(method, message.get('params') or {})
        except LookupError:
            return self.error(identifier, -32601, f'Method not found: {method}')
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            return self.error(identifier, -32603, f'Internal error: {error}')
        return {'jsonrpc': '2.0', 'id': identifier, 'result': result}

    def error(self, identifier, code, text):
        return {'jsonrpc': '2.0', 'id': identifier, 'error': {'code': code, 'message': text}}

    def dispatch(self, method, params):
        if method == 'initialize':
            requested = params.get('protocolVersion')
            return {
                'protocolVersion': requested if requested in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                'capabilities': {'tools': {'listChanged': False}},
                'serverInfo': SERVER_INFO,
                'instructions': INSTRUCTIONS,
            }
        if method == 'ping':
            return {}
        if method == 'tools/list':
            return {'tools': self.workspace.list_tools()}
        if method == 'tools/call':
            return self.call_tool(params.get('name'), params.get('arguments') or {})
        raise LookupError(method)

    def call_tool(self, name, arguments):
        try:
            with self.lock:
                result = self.workspace.call(name, arguments)
        except ToolError as error:
            return {'content': [{'type': 'text', 'text': str(error)}], 'isError': True}
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            return {'content': [{'type': 'text', 'text': f'{type(error).__name__}: {error}'}], 'isError': True}
        text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, indent=1)
        return {'content': [{'type': 'text', 'text': text}], 'isError': False}


# -- транспорт stdio: по одному сообщению JSON на строку
def serve_stdio(workspace):
    dispatcher = McpDispatcher(workspace)
    reader = sys.stdin.buffer
    writer = sys.stdout.buffer
    # все, что печатают инструменты, не должно попасть в канал протокола
    sys.stdout = sys.stderr

    try:
        for line in iter(reader.readline, b''):
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line.decode('utf-8'))
            except ValueError:
                response = dispatcher.error(None, -32700, 'Parse error')
            else:
                response = dispatcher.handle(message)
            if response is not None:
                writer.write(json.dumps(response, ensure_ascii=False).encode('utf-8') + b'\n')
                writer.flush()
    finally:
        workspace.shutdown()


# -- транспорт HTTP (Streamable HTTP): POST /mcp
def make_http_server(workspace, port, host='127.0.0.1'):
    dispatcher = McpDispatcher(workspace)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def reply(self, status, body=None):
            data = json.dumps(body, ensure_ascii=False).encode('utf-8') if body is not None else b''
            self.send_response(status)
            if data:
                self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            # запросы с чужих сайтов отклоняются: сервер умеет менять файлы и запускать код
            origin = self.headers.get('Origin')
            if origin and not origin.startswith(('http://localhost', 'http://127.0.0.1')):
                return self.reply(403, dispatcher.error(None, -32600, 'Forbidden origin'))
            if self.path.rstrip('/') != '/mcp':
                return self.reply(404)
            try:
                length = int(self.headers.get('Content-Length', 0))
                message = json.loads(self.rfile.read(length).decode('utf-8'))
            except ValueError:
                return self.reply(400, dispatcher.error(None, -32700, 'Parse error'))

            if isinstance(message, list):
                responses = [r for r in (dispatcher.handle(m) for m in message) if r is not None]
                return self.reply(200, responses) if responses else self.reply(202)
            response = dispatcher.handle(message)
            return self.reply(200, response) if response is not None else self.reply(202)

        def do_GET(self):
            # поток событий от сервера не используется
            self.reply(405)

        def do_DELETE(self):
            self.reply(200)

        def log_message(self, format, *args):
            pass

    return ThreadingHTTPServer((host, port), Handler)
