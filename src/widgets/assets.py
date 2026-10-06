"""
Объявление специфичных для приложения виджетов и контейнеров.
Объявление вкладки ассетов: экспорт скриптов и объектов в файл, загрузка чужих ассетов.
"""

# -- импортирование модулей
# - глобальные
from prompt_toolkit.completion import PathCompleter, WordCompleter
from prompt_toolkit.layout import HSplit, Dimension, WindowAlign, FloatContainer, Float, CompletionsMenu
from prompt_toolkit.widgets import Frame, TextArea, Box, Button, Label

# - локальные
import agent


# -- объявление виджетов
# - вкладка ассетов
class AssetsContainer:
    def __init__(self):
        self.target_area = TextArea(multiline=False, focus_on_click=True, completer=self.make_completer())
        self.path_area = TextArea(text='assets/', multiline=False, focus_on_click=True, completer=PathCompleter())
        self.description_area = TextArea(multiline=False, focus_on_click=True)
        self.status_area = TextArea(text='Нам нечего отобразить.', multiline=True, focusable=False, height=6)

        self.frame = Frame(
            HSplit([
                Label(text='Ассеты - скрипты и объекты, которые можно передать в другой проект',
                      align=WindowAlign.CENTER),
                Frame(body=self.target_area, title="Скрипт или объект (имя, путь /a/b, prefab:/имя)", height=3),
                Frame(body=self.path_area, title="Файл ассета или ссылка", height=3),
                Frame(body=self.description_area, title="Описание", height=3),
                Button(text='Экспорт скрипта', width=30, handler=self.on_export_script),
                Button(text='Экспорт объекта', width=30, handler=self.on_export_object),
                Button(text='Загрузить ассет', width=30, handler=self.on_import),
                Button(text='Загрузить в объект', width=30, handler=self.on_import_into),
                Frame(body=self.status_area, title="Результат"),
            ]),
            title='Ассеты')
        self.container = FloatContainer(
            content=Box(self.frame, height=Dimension()),
            floats=[
                Float(
                    xcursor=True,
                    ycursor=True,
                    content=CompletionsMenu(max_height=16, scroll_offset=1),
                )
            ]
        )

    def __pt_container__(self):
        return self.container

    def make_completer(self):
        workspace = agent.editor_workspace()
        words = [script.name for script in workspace.world.scripts]
        words += [path for node, parent, path in workspace.walk_scene()]
        words += [path for node, parent, path in workspace.walk_prefabs()]
        return WordCompleter(words, sentence=True)

    def run(self, tool, **arguments):
        try:
            result = agent.editor_workspace().call(tool, arguments)
        except Exception as error:
            self.status_area.text = f'Ошибка: {error}'
            return
        self.status_area.text = '\n'.join(f'{key}: {value}' for key, value in result.items())

    def on_export_script(self):
        self.run('asset_export', kind='script', target=self.target_area.text, path=self.path_area.text,
                 description=self.description_area.text)

    def on_export_object(self):
        self.run('asset_export', kind='object', target=self.target_area.text, path=self.path_area.text,
                 description=self.description_area.text)

    def on_import(self):
        self.run('asset_import', source=self.path_area.text)

    def on_import_into(self):
        self.run('asset_import', source=self.path_area.text, parent=self.target_area.text or '/')

    def on_update(self):
        self.target_area.completer = self.make_completer()
