"""
Проверка MCP-сервера официальным клиентом (pip install mcp):
создание мира, скрипты, объекты, запуск игры, игра за игрока, ассеты.

    python tests/test_mcp.py
"""

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent

PLAYER = """
greetings = world.require('Greetings')

@self.on_event('on_connect')
def connected():
    self.send(greetings.hello(self.attributes['title']))

@self.on_event('on_message')
def message(text):
    room = world.do_get_object_by_name('Tavern')
    self.send(f"echo {text} | room: {room.attributes['description']} | npcs: {len(room.children)}")

@self.on_event('on_disconnect')
def left():
    self.die()
"""

LIBRARY = """
def hello(title):
    return f'<green>Привет, {title}!</>'
"""


async def run():
    work = Path(tempfile.mkdtemp(prefix='kuznya-test-'))
    world_a = work / 'a.wrld'
    world_b = work / 'b.wrld'
    parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'src' / 'mcp_server.py')])

    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            server_info = getattr(initialized, 'server_info', None) or initialized.serverInfo
            assert server_info.name == 'kuznya'

            async def call(tool_name, expect_error=False, **arguments):
                result = await session.call_tool(tool_name, arguments)
                text = result.content[0].text
                is_error = result.is_error if hasattr(result, 'is_error') else result.isError
                assert bool(is_error) == expect_error, f'{tool_name}: {text}'
                try:
                    return json.loads(text)
                except ValueError:
                    return text

            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert {'script_create', 'object_create', 'character_create', 'asset_export', 'play_send'} <= names
            print(f'инструментов: {len(names)}')

            assert 'No world is open' in await call('script_list', expect_error=True)
            assert 'world.require' in await call('engine_docs')

            # -- мир А: библиотека, шаблон игрока, комната с персонажем
            await call('world_new', path=str(world_a))
            await call('script_create', name='Greetings', code=LIBRARY)
            assert 'Syntax error' in await call('script_create', expect_error=True, name='Bad', code='def (:')
            await call('script_create', name='Player', code=PLAYER)
            await call('character_create', name='Player', playable=True, scripts=['Player'],
                       attributes={'title': 'странник'})
            await call('object_create', name='Tavern', attributes={'description': 'дымно'},
                       children=[{'name': 'Table'}])
            await call('character_create', name='Bartender', location='/Tavern', description='Протирает кружку')
            await call('object_update', object='/Tavern/Bartender', attributes={'job': 'bartender'})
            assert (await call('object_get', object='Bartender'))['attributes']['job'] == 'bartender'
            assert (await call('object_find', attribute='kind', value='character'))['count'] == 1
            await call('object_copy', object='/Tavern/Table', new_parent='/Tavern', name='Table 2')
            assert 'ambiguous' not in str(await call('object_get', object='/Tavern/Table 2'))
            info = await call('world_info')
            assert info['player_prefab'] == 'Player' and info['objects'] == 5, info

            # -- запуск и игра
            await call('server_settings', port_wss=18337, port_web=18339)
            status = await call('server_start')
            assert status['running'], status
            connected = await call('play_connect')
            assert connected['messages'] == ['Привет, странник!'], connected
            answer = await call('play_send', session=connected['session'], text='ping')
            assert answer['messages'] == ['echo ping | room: дымно | npcs: 3'], answer
            await call('play_disconnect', session=connected['session'])
            assert (await call('server_status'))['script_errors'] == 0
            await call('server_stop')
            assert (await call('world_info'))['objects'] == 5

            # -- ассеты: скрипт с библиотекой и объект с поддеревом уезжают в другой мир
            script_asset = await call('asset_export', kind='script', target='Player',
                                      path=str(work / 'player.kasset'), author='test')
            assert [s['name'] for s in script_asset['scripts']] == ['Player', 'Greetings'], script_asset
            object_asset = await call('asset_export', kind='object', target='prefab:/Player',
                                      path=str(work / 'player_prefab.kasset'))
            tavern_asset = await call('asset_export', kind='object', target='/Tavern',
                                      path=str(work / 'tavern.kasset'))
            assert tavern_asset['objects'] == 4

            await call('world_new', path=str(world_b))
            assert (await call('asset_inspect', source=object_asset['file']))['kind'] == 'object'
            report = await call('asset_import', source=object_asset['file'])
            assert report['scripts_added'] == ['Player', 'Greetings'] and report['object']['prefab'], report
            report = await call('asset_import', source=tavern_asset['file'], parent='/')
            assert report['object']['name'] == 'Tavern', report
            report = await call('asset_import', source=script_asset['file'])
            assert report['scripts_reused'] == ['Player', 'Greetings'], report

            await call('server_settings', port_wss=18337, port_web=18339, player_prefab='Player')
            await call('server_start')
            connected = await call('play_connect')
            answer = await call('play_send', session=connected['session'], text='hi')
            assert answer['messages'] == ['echo hi | room: дымно | npcs: 3'], answer
            await call('server_stop')
            assert len(await call('asset_list', directory=str(work))) == 3

    print('MCP: все проверки пройдены')


if __name__ == '__main__':
    asyncio.run(run())
