"""
Скрипт входа MCP-сервера. Дает ИИ-агентам (Claude Code и другим) доступ к миру без запуска редактора.

    python src/mcp_server.py [файл мира]            - транспорт stdio
    python src/mcp_server.py [файл мира] --http 1341 - транспорт HTTP на http://127.0.0.1:1341/mcp
"""

# -- импорт модулей
import argparse
import os
import sys
from pathlib import Path

from agent import Workspace
from agent.mcp import make_http_server, serve_stdio
from world import WorldFile


def main():
    parser = argparse.ArgumentParser(description='MCP-сервер движка КУЗНЯ')
    parser.add_argument('world_file', nargs='?', default=os.environ.get('KUZNYA_WORLD'),
                        help='Путь к файлу мира. Можно не указывать и открыть мир инструментом world_open')
    parser.add_argument('--http', type=int, metavar='PORT', help='Запустить транспорт HTTP на указанном порту')
    args = parser.parse_args()

    workspace = Workspace(WorldFile())
    if args.world_file:
        path = Path(args.world_file)
        workspace.call('world_open' if path.is_file() else 'world_new', {'path': str(path)})

    if args.http:
        server = make_http_server(workspace, args.http)
        print(f'MCP-сервер Кузни: http://127.0.0.1:{args.http}/mcp', file=sys.stderr)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            workspace.shutdown()
    else:
        serve_stdio(workspace)


if __name__ == '__main__':
    main()
