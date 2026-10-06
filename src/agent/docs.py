"""
Справка по движку для ИИ-агентов. Отдается инструментом engine_docs.
"""

ENGINE_DOCS = """# Kuznya engine: reference for agents

Kuznya is an engine for online text games (MU*). A game is one world file (.wrld). Players connect with a
browser (WebSocket), type text, and receive text. Everything the game does is written in Python scripts.

## Building blocks
- OBJECT: a node of the scene tree. Has an identity, `attributes` (a dict of JSON values, `name` is the display
  name), attached scripts and children. Rooms, items, NPCs, players, managers are all objects. Containment is
  the tree: a character standing in a room is a child of the room object.
- PREFAB: a template object (with children) stored outside the scene. Scripts spawn copies of it:
  `obj = world.do_get_prefab_by_name('Goblin').instance(); room.adopt(obj)`.
- PLAYER PREFAB: the prefab instantiated for every new connection (server_settings player_prefab=...). The new
  object is adopted by the scene root and receives `on_connect`. Without a player prefab nobody can connect.
- SCRIPT: Python source. Attached to an object it runs once per object when the world loads (or when the prefab
  is instantiated), with these globals: `self` (the object), `world`, `script`. A script normally only registers
  event handlers and defines functions. One script can be attached to many objects.
- LIBRARY: any script can be loaded from another script with `lib = world.require('Script name')`. Its code runs
  once (self is None) and `lib.some_function(...)` / `lib.SOME_DATA` are available. Put shared logic and data
  tables in libraries and keep attached scripts thin.

## Script API
Object (`self` and any other object):
- `self.attributes` dict, saved with the world. Keep it JSON-serializable (no objects, sets, tuples as keys).
- `self.name`, `self.identity`, `self.parent`, `self.children`, `self.alive`
- `self.send(text)` - text to the connected player (no-op for objects without a connection).
  Color markup: `<red>text</>`, `<#ffcc00>text</>`; a literal `<` must be escaped with `self.safe(text)`.
- `self.on_event(name)` decorator - subscribe to an event on this object; `self.trigger(name, *args)` fires it.
- `self.schedule(func, delay_seconds, *args)` - call later (cancelled if the object dies).
  `@self.on_schedule(delay)` - decorator form.
- `parent.adopt(obj)` - move obj under a new parent. `self.die()` - destroy the object and its children.
- `self.find_child(name=...)`, `self.get_script_by_name('Script').function(...)` - call into another script
  attached to that object.
- `self.transfer_user_connection_to(other)` - hand the player's connection to another object.
World:
- `world.root_object`, `world.get_objects()`, `world.do_get_object_by_name(name)`,
  `world.do_get_object_by_identity(id)`, `world.do_get_prefab_by_name(name)`
- `world.on_event('on_start')` decorator, `world.trigger(name, *args)`, `world.schedule(func, delay, *args)`
- `world.require(name)` - load a library script.
- `world.save_filename(world.filename)` - save now (the world is also saved when the server stops).

## Events fired by the engine
- world `on_start` - after the whole world is loaded. Do cross-object setup here, not at script top level:
  while scripts are being compiled the tree is still loading.
- object `on_spawn` - on a fresh prefab instance (before it has a parent).
- object `on_connect` / `on_disconnect` - a player attached to / left this object.
- object `on_message(text)` - the connected player typed a line.
- object `on_die` - just before the object is destroyed.
Any other event name is yours: `room.trigger('on_enter', who)`.

## Minimal game
Script "Player" attached to prefab "Player" (set as player prefab):

    @self.on_event('on_connect')
    def connected():
        self.send('<green>Welcome!</> Type something.')

    @self.on_event('on_message')
    def message(text):
        for other in self.parent.children:
            other.send(f'{self.name}: {self.safe(text)}')

    @self.on_event('on_disconnect')
    def left():
        self.die()

## Rules that save time
- A script error in a handler is printed to the server log with a traceback and the server keeps running:
  after testing always check server_logs / server_status.script_errors.
- The game loop is single threaded: never block (no sleep, no long loops, no network calls in handlers).
  Use schedule for anything periodic.
- Running the game changes the world file: attributes are saved back when the server stops. Design scripts so
  that `on_start` works both for a fresh world and for a saved one.
- Scripts and objects referenced by name must have unique names.

## Workflow
1. world_open or world_new. 2. Create scripts (script_create), objects/prefabs/characters (object_create,
character_create), set the player prefab (server_settings). 3. server_start, then play_connect / play_send to
play as a player, server_logs for errors, server_stop. 4. Share parts with asset_export; load other people's
parts with asset_import.
"""
