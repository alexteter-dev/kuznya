"""
Plays Brockton Bay as a player through the MCP server: connects, creates a character, walks, shops,
takes a job, picks a fight. Works on a temporary copy of the world with the clock sped up.

    pip install mcp
    python tests/play_worm.py
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
WORLD = ROOT / 'games' / 'worm' / 'brockton_bay.wrld'


async def run():
    copy = Path(tempfile.mkdtemp(prefix='kuznya-worm-')) / 'play.wrld'
    parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT / 'src' / 'mcp_server.py'), str(WORLD)])
    async with stdio_client(parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            async def call(tool, **arguments):
                result = await session.call_tool(tool, arguments)
                text = result.content[0].text
                failed = result.is_error if hasattr(result, 'is_error') else result.isError
                assert not failed, f'{tool}: {text}'
                try:
                    return json.loads(text)
                except ValueError:
                    return text

            await call('world_save', path=str(copy))
            await call('object_update', object='/Simulation', attributes={'tick_seconds': 0.25})
            await call('server_settings', port_wss=18437, port_web=18439)
            status = await call('server_start')
            assert status['running'], status
            connected = await call('play_connect', wait=1.0)
            sid = connected['session']

            def show(label, reply):
                lines = [m for m in reply['messages'] if not m.startswith('@@hud')]
                print(f'\n>>> {label}')
                print('\n'.join(lines))
                return '\n'.join(lines)

            async def say(text, wait=0.5):
                return show(text, await call('play_send', session=sid, text=text, wait=wait))

            show('(connect)', connected)
            await say('Tess Marlowe')
            arrived = await say('hunter2')
            assert 'Brockton Bay Bus Station' in arrived
            await say('help')
            await say('status')
            assert 'Lord Street' in await say('go 1')
            await say('go bakery')
            await say('prices')
            await say('buy 1 bread')
            await say('eat')
            await say('talk baker')
            await say('jobs')
            await say('market')
            await say('where docks')
            await say('go lord street')
            await say('go docks', wait=1.5)
            await say('who')
            await say('news')
            await say('time')
            # wait a few game hours and see the city move around us
            show('(waiting)', await call('play_read', session=sid, wait=6))
            await say('look')
            await say('tasks')
            await say('power')
            # pick a fight we cannot win, to exercise combat, knock-out and the trigger roll
            await say('go cargo pier')
            await say('attack dockworker', wait=5)
            show('(aftermath)', await call('play_read', session=sid, wait=6))
            await say('status')

            # reconnect: the character must still be there
            await call('play_disconnect', session=sid)
            again = await call('play_connect', wait=0.8)
            sid = again['session']
            await say('Tess Marlowe')
            back = await say('hunter2', wait=1.0)
            assert 'Welcome back' in back, back
            await call('play_disconnect', session=sid)

            status = await call('server_status')
            errors = await call('server_logs', contains='error', tail=20)
            await call('server_stop')
            print('\nscript errors on the server:', status['script_errors'])
            if status['script_errors']:
                print(await call('server_logs', tail=60))
            assert status['script_errors'] == 0, errors
    print('\nplay test passed')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    asyncio.run(run())
