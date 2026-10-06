# settings должен импортироваться первым: он и пакет world ссылаются друг на друга
import settings

from .tools import Workspace, ToolError

_editor_workspace = None


def editor_workspace():
    """Рабочее пространство поверх мира, открытого в редакторе: агент и редактор видят одни и те же объекты."""
    global _editor_workspace
    if _editor_workspace is None:
        def redraw():
            try:
                from prompt_toolkit.application import get_app
                get_app().invalidate()
            except Exception:
                pass

        # в редакторе сохранение остается за пользователем
        _editor_workspace = Workspace(settings.app_state.world, on_change=redraw, autosave=False)
        _editor_workspace.opened = True
    return _editor_workspace
