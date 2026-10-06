"""
Объявление специфичных для приложения виджетов и контейнеров.
Объявление вкладки ИИ-агентов: MCP-сервер, через который агент правит открытый в редакторе мир.
"""

# -- импортирование модулей
# - глобальные
import threading

from prompt_toolkit.layout import HSplit, Dimension, WindowAlign
from prompt_toolkit.widgets import Frame, TextArea, Box, Button, Label

# - локальные
import agent
from agent.mcp import make_http_server

# -- состояние сервера общее для всех вкладок
state = {'server': None, 'port': None}


# -- объявление виджетов
# - вкладка агентов
class AgentsContainer:
    def __init__(self):
        self.port_area = TextArea(text='1341', multiline=False, focus_on_click=True)
        self.info_area = TextArea(multiline=True, focusable=False, height=9)
        self.toggle_button = Button(text='', width=30, handler=self.on_toggle)
        self.frame = Frame(
            HSplit([
                Label(text='ИИ-агент редактирует открытый мир: скрипты, объекты, персонажи, ассеты',
                      align=WindowAlign.CENTER),
                Frame(body=self.port_area, title="Порт MCP", height=3),
                self.toggle_button,
                Frame(body=self.info_area, title="Подключение"),
            ]),
            title='ИИ-агенты')
        self.container = Box(self.frame, height=Dimension())
        self.on_update()

    def __pt_container__(self):
        return self.container

    def on_toggle(self):
        if state['server'] is not None:
            state['server'].shutdown()
            state['server'].server_close()
            state['server'] = None
        else:
            try:
                port = int(self.port_area.text)
                state['server'] = make_http_server(agent.editor_workspace(), port)
                state['port'] = port
            except (ValueError, OSError) as error:
                self.info_area.text = f'Не удалось запустить MCP-сервер: {error}'
                return
            threading.Thread(target=state['server'].serve_forever, daemon=True).start()
        self.on_update()

    def on_update(self):
        if state['server'] is not None:
            url = f"http://127.0.0.1:{state['port']}/mcp"
            self.toggle_button.text = 'Остановить MCP-сервер'
            self.info_area.text = (
                f'MCP-сервер запущен: {url}\n\n'
                f'Claude Code:\n  claude mcp add --transport http kuznya {url}\n\n'
                'Агент работает с миром, открытым в редакторе. Изменения видны сразу,\n'
                'сохранение - как обычно, во вкладке "Экспорт".'
            )
        else:
            self.toggle_button.text = 'Запустить MCP-сервер'
            self.info_area.text = (
                'MCP-сервер остановлен.\n\n'
                'Без редактора агент подключается командой:\n'
                '  python src/mcp_server.py <файл мира>\n'
                'Подробности: AGENTS.md'
            )
