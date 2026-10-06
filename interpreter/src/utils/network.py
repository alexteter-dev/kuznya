import asyncio
import queue
import threading
import traceback
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler

from websockets.asyncio.server import serve


class WebsocketClientServer(SimpleHTTPRequestHandler):
    def do_GET(self):
        import main
        if self.path == '/' or self.path == '/index.html':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(main.world.web_client_code.encode('utf-8'))))
            self.end_headers()
            self.wfile.write(main.world.web_client_code.encode('utf-8'))
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass


class Connection:
    def __init__(self, websocket):
        self.websocket = websocket
        self.message_queue = queue.Queue()
        self.connected = True
        self.connected_object = None

    def get_messages(self):
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def send(self, message):
        if self.connected:
            asyncio.run_coroutine_threadsafe(
                self._send_async(message),
                event_loop
            )

    async def _send_async(self, message):
        try:
            await self.websocket.send(message)
        except:
            self.connected = False


class WebSocketManager:
    def __init__(self):
        self.connections = []
        self.new_connections = queue.Queue()
        self.disconnections = queue.Queue()

    def add_connection(self, connection):
        self.new_connections.put(connection)

    def remove_connection(self, connection):
        self.disconnections.put(connection)

    def update(self):
        import main
        while not self.new_connections.empty():
            try:
                conn = self.new_connections.get_nowait()
                # объект игрока создается в игровом потоке, а не в потоке сети
                try:
                    main.world.connect(conn)
                except Exception as e:
                    print(f"[СЕРВЕР] Не удалось создать объект игрока: {e}")
                    traceback.print_exc()
                    conn.connected = False
                    continue
                self.connections.append(conn)
                print(f"[СЕРВЕР] Новое подключение. Подключения: {len(self.connections)}")
            except queue.Empty:
                break

        while not self.disconnections.empty():
            try:
                conn = self.disconnections.get_nowait()
                if conn in self.connections:
                    self.connections.remove(conn)
                    try:
                        conn.connected_object.trigger('on_disconnect')
                    except Exception as e:
                        print(f"[script error] {e}")
                        traceback.print_exc()
                    print(f"[СЕРВЕР] Подключение прервано. Подключения: {len(self.connections)}")
            except queue.Empty:
                break

    def broadcast(self, message):
        for conn in self.connections:
            conn.send(message)


async def handle_connection(websocket):
    conn = Connection(websocket)
    ws_manager.add_connection(conn)

    try:
        async for message in websocket:
            conn.message_queue.put(message)
    except Exception as e:
        print(f"Ошибка подключения: {e}")
    finally:
        conn.connected = False
        ws_manager.remove_connection(conn)


def run_async_loop():
    global event_loop
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    event_loop.run_until_complete(start_websocket_server())


def start_http_server():
    import main
    print(f'[СЕРВЕР] Запуск http-сервера, на порту: {main.world.port_web}')
    address = 'localhost' if main.world.host in ('0.0.0.0', '') else main.world.host
    print(f'[СЕРВЕР] Играть: откройте в браузере http://{address}:{main.world.port_web}')
    httpd = HTTPServer((main.world.host, main.world.port_web), WebsocketClientServer)
    httpd.serve_forever()


def redirect_browser(connection, request):
    """Порт веб-сокета открыли в браузере как обычную страницу: отправляем на веб-клиент."""
    import main
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        return None
    host = request.headers.get('Host', 'localhost').rsplit(':', 1)[0]
    address = f'http://{host}:{main.world.port_web}'
    response = connection.respond(
        HTTPStatus.FOUND, f'Это порт веб-сокета. Веб-клиент игры: {address}\n')
    response.headers['Location'] = address
    return response


async def start_websocket_server():
    import main
    async with serve(handle_connection, main.world.host, main.world.port_wss,
                     process_request=redirect_browser) as server:
        print(f"[СЕРВЕР] Запуск веб-сокет сервера на ws://{main.world.host}:{main.world.port_wss}")
        await server.serve_forever()


ws_manager = WebSocketManager()
event_loop = None

http_thread = threading.Thread(target=start_http_server, daemon=True)
http_thread.start()

ws_thread = threading.Thread(target=run_async_loop, daemon=True)
ws_thread.start()
