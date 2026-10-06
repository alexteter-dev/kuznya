"""
Встроенный ИИ-помощник: Claude правит мир по текстовому запросу теми же инструментами, что и MCP-сервер.
Нужен пакет anthropic и ключ в переменной окружения ANTHROPIC_API_KEY.

    python src/assistant.py world.wrld "Добавь таверну с барменом, который здоровается с игроками"
    python src/assistant.py world.wrld            - диалог в терминале
"""

# -- импорт модулей
import argparse
import json
import sys
from pathlib import Path

import anthropic

from agent import ToolError, Workspace
from agent.mcp import INSTRUCTIONS
from world import WorldFile

# -- константы
MODEL = 'claude-opus-5-5'
SYSTEM = INSTRUCTIONS + (
    " You are the assistant built into the Kuznya editor. The world is already open. Make the requested change, "
    "test it by running the game when scripts changed, and finish with a short summary of what you did. "
    "Answer in the language of the request."
)


def ask(client, workspace, messages, tools):
    """Один запрос пользователя: цикл вызовов инструментов до итогового ответа"""
    while True:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            thinking={'type': 'adaptive'},
            output_config={'effort': 'high'},
            # при отказе модели запрос автоматически повторяется на запасной
            betas=['server-side-fallback-2026-07-01'],
            fallbacks='default',
            tools=tools,
            messages=messages,
        )
        messages.append({'role': 'assistant', 'content': response.content})

        if response.stop_reason == 'refusal':
            return 'Модель отказалась выполнять запрос.'
        if response.stop_reason == 'max_tokens':
            return 'Ответ оборван: достигнут предел длины.'
        if response.stop_reason != 'tool_use':
            return '\n'.join(block.text for block in response.content if block.type == 'text')

        results = []
        for block in response.content:
            if block.type != 'tool_use':
                continue
            print(f'  > {block.name}', file=sys.stderr)
            try:
                result = workspace.call(block.name, block.input)
                text = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                results.append({'type': 'tool_result', 'tool_use_id': block.id, 'content': text})
            except ToolError as error:
                results.append({'type': 'tool_result', 'tool_use_id': block.id, 'content': str(error),
                                'is_error': True})
        messages.append({'role': 'user', 'content': results})


def main():
    parser = argparse.ArgumentParser(description='ИИ-помощник движка КУЗНЯ')
    parser.add_argument('world_file', help='Путь к файлу мира (будет создан, если его нет)')
    parser.add_argument('prompt', nargs='?', help='Запрос. Без него запускается диалог')
    args = parser.parse_args()

    workspace = Workspace(WorldFile())
    path = Path(args.world_file)
    workspace.call('world_open' if path.is_file() else 'world_new', {'path': str(path)})
    hidden = ('world_open', 'world_new')
    tools = [{'name': tool['name'], 'description': tool['description'], 'input_schema': tool['inputSchema']}
             for tool in workspace.list_tools() if tool['name'] not in hidden]

    client = anthropic.Anthropic()
    messages = []
    try:
        while True:
            prompt = args.prompt or input('> ')
            if not prompt.strip():
                break
            messages.append({'role': 'user', 'content': prompt})
            try:
                print(ask(client, workspace, messages, tools))
            except anthropic.AuthenticationError:
                print('Не задан или неверен ключ: переменная окружения ANTHROPIC_API_KEY.')
                break
            except anthropic.RateLimitError:
                print('Превышен лимит запросов, попробуйте позже.')
            except anthropic.APIStatusError as error:
                print(f'Ошибка API {error.status_code}: {error.message}')
            except anthropic.APIConnectionError:
                print('Нет связи с API.')
            if args.prompt:
                break
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        workspace.shutdown()


if __name__ == '__main__':
    main()
