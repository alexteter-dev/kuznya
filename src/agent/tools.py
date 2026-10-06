"""
Инструменты для ИИ-агентов: все, что агент может сделать с миром.
Один и тот же набор используется MCP-сервером и встроенным помощником.
"""

# -- импорт библиотек
import ast
import copy
import json
from pathlib import Path

from world import assets
from world.loader import ObjectFile, PrefabFile, ScriptFile

from .docs import ENGINE_DOCS
from .runner import PlaySessions, RunnerError, ServerRunner


# -- ошибки, текст которых показывается агенту
class ToolError(Exception):
    pass


# -- описание параметров
def S(description, **extra):
    return {'type': 'string', 'description': description, **extra}


def I(description, **extra):
    return {'type': 'integer', 'description': description, **extra}


def N(description, **extra):
    return {'type': 'number', 'description': description, **extra}


def B(description, **extra):
    return {'type': 'boolean', 'description': description, **extra}


def O(description, **extra):
    return {'type': 'object', 'description': description, **extra}


def A(description, items=None, **extra):
    return {'type': 'array', 'description': description, 'items': items or {}, **extra}


OBJECT_REF = ("Object reference: an identity, a unique name, or a path of names from the scene root "
              "('/City/Docks/Bakery'). '/' is the scene root. Prefix with 'prefab:' to address prefabs "
              "('prefab:/Player').")
SCRIPT_REF = "Script name or identity."
NODE_SCHEMA = O("Object description", properties={
    'name': S("Object name (stored in the 'name' attribute)."),
    'attributes': O("Attributes: any JSON values."),
    'scripts': A("Names or identities of scripts to attach.", {'type': 'string'}),
    'children': A("Nested child objects, same shape.", {'type': 'object'}),
})


class Workspace:
    """Открытый мир и все, что вокруг него: игровой сервер, тестовые подключения."""

    def __init__(self, world, on_change=None, autosave=True):
        self.world = world
        self.on_change = on_change
        self.autosave = autosave
        self.opened = False
        self.runner = ServerRunner()
        self.sessions = PlaySessions()
        self.tools = {}
        self._register()

    # -- реестр инструментов
    def tool(self, name, description, properties=None, required=(), mutates=False):
        def decorator(func):
            self.tools[name] = {
                'name': name,
                'description': description,
                'schema': {'type': 'object', 'properties': properties or {}, 'required': list(required)},
                'func': func,
                'mutates': mutates,
            }
            return func

        return decorator

    def list_tools(self):
        return [{'name': t['name'], 'description': t['description'], 'inputSchema': t['schema']}
                for t in self.tools.values()]

    def call(self, name, arguments=None):
        if name not in self.tools:
            raise ToolError(f"Unknown tool '{name}'")
        entry = self.tools[name]
        arguments = arguments or {}
        unknown = [key for key in arguments if key not in entry['schema']['properties']]
        if unknown:
            raise ToolError(f"Unknown arguments for {name}: {', '.join(unknown)}")
        missing = [key for key in entry['schema']['required'] if key not in arguments]
        if missing:
            raise ToolError(f"Missing arguments for {name}: {', '.join(missing)}")
        try:
            result = entry['func'](**arguments)
        except RunnerError as error:
            raise ToolError(str(error))
        if entry['mutates']:
            self.changed()
        return result

    def changed(self):
        if self.autosave and self.opened:
            self.world.save_filename(self.world.filename)
        if self.on_change:
            self.on_change()

    def require_world(self):
        if not self.opened:
            raise ToolError("No world is open. Call world_open(path) or world_new(path) first.")

    # -- поиск скриптов и объектов
    def find_script(self, ref):
        self.require_world()
        script = self.world.do_get_script_by_identity(ref) or self.world.do_get_script_by_name(ref)
        if script is None:
            raise ToolError(f"Script '{ref}' not found. Use script_list.")
        return script

    def _walk(self, node, parent, path):
        yield node, parent, path
        for child in node.children:
            yield from self._walk(child, node, f"{path.rstrip('/')}/{child.get_name()}")

    def walk_scene(self):
        yield from self._walk(self.world.root_object, None, '/')

    def walk_prefabs(self):
        for prefab in self.world.prefabs:
            yield from self._walk(prefab, None, f'prefab:/{prefab.get_name()}')

    def find_object(self, ref):
        """Возвращает (объект, родитель, путь, это_шаблон)"""
        self.require_world()
        ref = str(ref).strip()
        if ref in ('/', 'root', ''):
            return self.world.root_object, None, '/', False

        is_prefab = ref.startswith('prefab:')
        if is_prefab:
            ref = ref[len('prefab:'):]
        candidates = list(self.walk_prefabs()) if is_prefab else list(self.walk_scene()) + list(self.walk_prefabs())

        def result(found):
            node, parent, path = found
            return node, parent, path, path.startswith('prefab:')

        for found in candidates:
            if found[0].identity == ref:
                return result(found)
        if ref.startswith('/'):
            wanted = ('prefab:' if is_prefab else '') + ref.rstrip('/')
            matches = [found for found in candidates if found[2] == wanted]
        else:
            matches = [found for found in candidates if found[0].attributes.get('name') == ref]
        if len(matches) == 1:
            return result(matches[0])
        if not matches:
            raise ToolError(f"Object '{ref}' not found. Use object_tree or object_find.")
        listing = ', '.join(f"{m[2]} ({m[0].identity})" for m in matches[:8])
        raise ToolError(f"'{ref}' is ambiguous, use an identity or a full path: {listing}")

    def describe(self, node, path, depth=0):
        info = {
            'identity': node.identity,
            'name': node.get_name(),
            'path': path,
            'scripts': [script.name for script in node.scripts if script is not None],
            'attributes': node.attributes,
        }
        if depth > 0:
            info['children'] = [self.describe(child, f"{path.rstrip('/')}/{child.get_name()}", depth - 1)
                                for child in node.children]
        else:
            info['children'] = [child.get_name() for child in node.children]
        return info

    def build(self, spec, cls):
        """Создание дерева объектов по описанию {name, attributes, scripts, children}"""
        if not isinstance(spec, dict):
            raise ToolError("Object description must be an object with name/attributes/scripts/children")
        node = cls()
        node.attributes = copy.deepcopy(spec.get('attributes') or {})
        if spec.get('name') is not None:
            node.attributes['name'] = spec['name']
        node.scripts = [self.find_script(ref) for ref in spec.get('scripts') or []]
        node.children = [self.build(child, cls) for child in spec.get('children') or []]
        return node

    # -- объявление инструментов
    def _register(self):
        tool = self.tool

        # ---------------- справка
        @tool('engine_docs',
              "Read this first. Returns the Kuznya scripting reference: how worlds, objects, prefabs and scripts "
              "work, the script API (self/world/events/schedule/require), and how to test a game.")
        def engine_docs():
            return ENGINE_DOCS

        # ---------------- мир
        @tool('world_info', "Summary of the open world: file, ports, player prefab, object/script/prefab counts.")
        def world_info():
            self.require_world()
            world = self.world
            prefab = world.do_get_prefab_by_identity(world.connection_prefab_identity)
            return {
                'file': str(world.filename),
                'host': world.host,
                'port_wss': world.port_wss,
                'port_web': world.port_web,
                'player_prefab': prefab.get_name() if prefab else None,
                'objects': len(world.get_objects()),
                'prefabs': [p.get_name() for p in world.prefabs],
                'scripts': len(world.scripts),
                'server_running': self.runner.running(),
            }

        @tool('world_open', "Open an existing world file (.wrld). Unsaved state of the previous world is kept on disk "
                            "because every change is saved automatically.",
              {'path': S("Path to the world file.")}, ['path'])
        def world_open(path):
            path = Path(path).expanduser()
            if not path.is_file():
                raise ToolError(f"File '{path}' does not exist. Use world_new to create a world.")
            self.world.load_filename(path)
            self.opened = True
            if self.on_change:
                self.on_change()
            return world_info()

        @tool('world_new', "Create a new empty world and save it to the given path.",
              {'path': S("Where to save the new world, e.g. 'games/my_game.wrld'."),
               'overwrite': B("Replace the file if it already exists.")}, ['path'])
        def world_new(path, overwrite=False):
            path = Path(path).expanduser()
            if path.exists() and not overwrite:
                raise ToolError(f"File '{path}' already exists. Pass overwrite=true to replace it.")
            path.parent.mkdir(parents=True, exist_ok=True)
            self.world.load_new()
            self.world.root_object.attributes['name'] = 'root'
            self.world.filename = path.resolve()
            self.world.save_filename(self.world.filename)
            self.opened = True
            if self.on_change:
                self.on_change()
            return world_info()

        @tool('world_save', "Save the world. Changes are saved automatically; use this to write a copy elsewhere.",
              {'path': S("Optional different path (save as).")})
        def world_save(path=None):
            self.require_world()
            if path:
                target = Path(path).expanduser()
                target.parent.mkdir(parents=True, exist_ok=True)
                self.world.save_filename(target)
                self.world.filename = target.resolve()
            else:
                self.world.save_filename(self.world.filename)
            return {'saved': str(self.world.filename)}

        @tool('server_settings', "Change server settings: ports, bind host and which prefab is spawned for every "
                                 "connecting player.",
              {'port_wss': I("WebSocket port."), 'port_web': I("Port of the built-in web client."),
               'host': S("Bind address: 'localhost' for local play, '0.0.0.0' to accept players from the network."),
               'player_prefab': S("Prefab (name or identity) instantiated for each new connection.")},
              mutates=True)
        def server_settings(port_wss=None, port_web=None, host=None, player_prefab=None):
            self.require_world()
            for port in (port_wss, port_web):
                if port is not None and not 0 < port < 65536:
                    raise ToolError("Ports must be in 1..65535")
            if port_wss is not None:
                self.world.port_wss = port_wss
            if port_web is not None:
                self.world.port_web = port_web
            if host is not None:
                self.world.host = host
            if player_prefab is not None:
                node, parent, path, is_prefab = self.find_object(
                    player_prefab if player_prefab.startswith('prefab:') else 'prefab:' + player_prefab)
                self.world.connection_prefab_identity = node.identity
            return world_info()

        @tool('web_client_get', "Return the HTML of the web client served to players.")
        def web_client_get():
            self.require_world()
            return self.world.web_client_code

        @tool('web_client_set', "Replace the HTML of the web client. The page must open a WebSocket to the world's "
                                "port_wss, send player input as text and display received text.",
              {'code': S("Full HTML document.")}, ['code'], mutates=True)
        def web_client_set(code):
            self.require_world()
            self.world.web_client_code = code
            return {'length': len(code)}

        # ---------------- скрипты
        def check(code, name='script'):
            try:
                ast.parse(code, filename=name)
            except SyntaxError as error:
                raise ToolError(f"Syntax error in {name}, line {error.lineno}: {error.msg}\n{error.text or ''}")

        @tool('script_list', "List all scripts: name, identity, size and where each is attached.")
        def script_list():
            self.require_world()
            usage = {}
            for node, parent, path in list(self.walk_scene()) + list(self.walk_prefabs()):
                for script in node.scripts:
                    if script is not None:
                        usage.setdefault(script.identity, []).append(path)
            return [{'name': script.name, 'identity': script.identity,
                     'lines': script.code.count('\n') + 1,
                     'attached_to': len(usage.get(script.identity, [])),
                     'attached_examples': usage.get(script.identity, [])[:3]} for script in self.world.scripts]

        @tool('script_get', "Return the source code of a script.", {'script': S(SCRIPT_REF)}, ['script'])
        def script_get(script):
            found = self.find_script(script)
            return {'name': found.name, 'identity': found.identity, 'code': found.code}

        @tool('script_create', "Create a script (Python). Attach it to objects with object_update, or load it from "
                               "other scripts as a library with world.require('<name>'). Names must be unique.",
              {'name': S("Unique script name."), 'code': S("Python source."),
               'attach_to': A("Objects to attach the new script to.", {'type': 'string'})},
              ['name', 'code'], mutates=True)
        def script_create(name, code, attach_to=None):
            self.require_world()
            if self.world.do_get_script_by_name(name) is not None:
                raise ToolError(f"Script '{name}' already exists. Use script_update.")
            check(code, name)
            targets = [self.find_object(ref)[0] for ref in attach_to or []]
            script = ScriptFile(code=code, name=name)
            self.world.scripts.append(script)
            for target in targets:
                target.scripts.append(script)
            return {'name': script.name, 'identity': script.identity, 'attached_to': len(targets)}

        @tool('script_update', "Edit a script: replace its whole code, or replace one exact fragment, and/or rename.",
              {'script': S(SCRIPT_REF), 'code': S("New full source code."),
               'old_text': S("Exact fragment to replace (must occur exactly once)."),
               'new_text': S("Replacement for old_text."), 'name': S("New name.")},
              ['script'], mutates=True)
        def script_update(script, code=None, old_text=None, new_text=None, name=None):
            found = self.find_script(script)
            new_code = found.code
            if code is not None:
                new_code = code
            if old_text is not None:
                if new_text is None:
                    raise ToolError("new_text is required together with old_text")
                occurrences = new_code.count(old_text)
                if occurrences != 1:
                    raise ToolError(f"old_text must occur exactly once, found {occurrences} times")
                new_code = new_code.replace(old_text, new_text)
            check(new_code, found.name)
            if name is not None and name != found.name:
                if self.world.do_get_script_by_name(name) is not None:
                    raise ToolError(f"Script '{name}' already exists")
                found.name = name
            found.code = new_code
            return {'name': found.name, 'identity': found.identity, 'lines': found.code.count('\n') + 1}

        @tool('script_delete', "Delete a script and detach it from every object.", {'script': S(SCRIPT_REF)},
              ['script'], mutates=True)
        def script_delete(script):
            found = self.find_script(script)
            detached = 0
            for node, parent, path in list(self.walk_scene()) + list(self.walk_prefabs()):
                if found in node.scripts:
                    node.scripts = [s for s in node.scripts if s is not found]
                    detached += 1
            self.world.do_delete_script(found.identity)
            return {'deleted': found.name, 'detached_from': detached}

        # ---------------- объекты, шаблоны, персонажи
        @tool('object_tree', "Show the object tree as indented text (names, script names, key attributes).",
              {'root': S(OBJECT_REF + " Default: the scene root."), 'depth': I("How many levels to show (default 3)."),
               'prefabs': B("Show prefabs instead of the scene.")})
        def object_tree(root=None, depth=3, prefabs=False):
            self.require_world()
            lines = []

            def render(node, level):
                scripts = ', '.join(script.name for script in node.scripts if script is not None)
                kind = node.attributes.get('kind')
                extra = (f" <{kind}>" if kind else '') + (f" [{scripts}]" if scripts else '')
                lines.append(f"{'  ' * level}{node.get_name()}{extra}")
                if level + 1 > depth and node.children:
                    lines.append(f"{'  ' * (level + 1)}... {len(node.children)} children")
                    return
                for child in node.children:
                    render(child, level + 1)

            if prefabs and root is None:
                for prefab in self.world.prefabs:
                    render(prefab, 0)
            else:
                render(self.find_object(root or '/')[0], 0)
            return '\n'.join(lines) or '(empty)'

        @tool('object_get', "Full description of an object: attributes, attached scripts, children.",
              {'object': S(OBJECT_REF), 'depth': I("Levels of children to include in full (default 0: names only).")},
              ['object'])
        def object_get(object, depth=0):
            node, parent, path, is_prefab = self.find_object(object)
            return self.describe(node, path, depth)

        @tool('object_find', "Search objects by name fragment and/or attribute value.",
              {'name_contains': S("Case-insensitive name fragment."), 'attribute': S("Attribute key that must exist."),
               'value': {'description': "Required value of that attribute (any JSON value)."},
               'prefabs': B("Search prefabs instead of the scene."), 'limit': I("Max results (default 50).")})
        def object_find(name_contains=None, attribute=None, value=None, prefabs=False, limit=50):
            self.require_world()
            found = []
            for node, parent, path in (self.walk_prefabs() if prefabs else self.walk_scene()):
                if name_contains and name_contains.lower() not in node.get_name().lower():
                    continue
                if attribute is not None:
                    if attribute not in node.attributes:
                        continue
                    if value is not None and node.attributes[attribute] != value:
                        continue
                found.append({'path': path, 'identity': node.identity})
            return {'count': len(found), 'objects': found[:limit]}

        @tool('object_create',
              "Create an object in the scene (a room, an item, an NPC...), optionally with a whole subtree of "
              "children. With prefab=true creates a prefab (template) instead; prefabs are spawned from scripts via "
              "world.do_get_prefab_by_name(name).instance().",
              {'parent': S(OBJECT_REF + " Ignored for a new top-level prefab."), 'name': S("Object name."),
               'attributes': O("Attributes: any JSON values."),
               'scripts': A("Scripts to attach.", {'type': 'string'}),
               'children': A("Nested children: [{name, attributes, scripts, children}].", NODE_SCHEMA),
               'prefab': B("Create a top-level prefab.")},
              ['name'], mutates=True)
        def object_create(name, parent='/', attributes=None, scripts=None, children=None, prefab=False):
            self.require_world()
            spec = {'name': name, 'attributes': attributes, 'scripts': scripts, 'children': children}
            if prefab:
                node = self.build(spec, PrefabFile)
                self.world.prefabs.append(node)
                return self.describe(node, f'prefab:/{name}')
            target, _, path, is_prefab = self.find_object(parent)
            node = self.build(spec, PrefabFile if is_prefab else ObjectFile)
            target.children.append(node)
            return self.describe(node, f"{path.rstrip('/')}/{name}")

        @tool('object_create_many', "Create many objects in one call. Each item is {parent, name, attributes, "
                                    "scripts, children}. Items are created in order, so later items may use earlier "
                                    "ones as parents.",
              {'objects': A("Objects to create.", O("Object with its parent", properties={
                  'parent': S(OBJECT_REF), **NODE_SCHEMA['properties']}))},
              ['objects'], mutates=True)
        def object_create_many(objects):
            self.require_world()
            created = []
            for spec in objects:
                target, _, path, is_prefab = self.find_object(spec.get('parent', '/'))
                node = self.build(spec, PrefabFile if is_prefab else ObjectFile)
                target.children.append(node)
                created.append(node.identity)
            return {'created': len(created), 'identities': created if len(created) <= 30 else created[:30] + ['...']}

        @tool('character_create',
              "Create a character (NPC or playable): an object with kind='character', a description and stats. "
              "Characters are ordinary objects, so everything else (object_update, scripts, assets) works on them.",
              {'name': S("Character name."), 'location': S("Where the character stands. " + OBJECT_REF),
               'description': S("How the character looks and behaves."),
               'attributes': O("Extra attributes: stats, job, faction, inventory, dialogue..."),
               'scripts': A("Behaviour scripts to attach.", {'type': 'string'}),
               'playable': B("Create it as a prefab and make it the player prefab for new connections.")},
              ['name'], mutates=True)
        def character_create(name, location='/', description='', attributes=None, scripts=None, playable=False):
            self.require_world()
            merged = {'kind': 'character', 'description': description}
            merged.update(attributes or {})
            created = object_create(name, parent=location, attributes=merged, scripts=scripts, prefab=playable)
            if playable:
                self.world.connection_prefab_identity = created['identity']
            return created

        @tool('object_update',
              "Edit an object: rename, merge attributes, remove attributes, replace or add/remove attached scripts.",
              {'object': S(OBJECT_REF), 'name': S("New name."),
               'attributes': O("Attributes to set (merged into existing ones)."),
               'remove_attributes': A("Attribute keys to delete.", {'type': 'string'}),
               'scripts': A("Replace the whole list of attached scripts.", {'type': 'string'}),
               'add_scripts': A("Scripts to attach.", {'type': 'string'}),
               'remove_scripts': A("Scripts to detach.", {'type': 'string'})},
              ['object'], mutates=True)
        def object_update(object, name=None, attributes=None, remove_attributes=None, scripts=None,
                          add_scripts=None, remove_scripts=None):
            node, parent, path, is_prefab = self.find_object(object)
            new_scripts = list(node.scripts)
            if scripts is not None:
                new_scripts = [self.find_script(ref) for ref in scripts]
            for ref in add_scripts or []:
                script = self.find_script(ref)
                if script not in new_scripts:
                    new_scripts.append(script)
            for ref in remove_scripts or []:
                script = self.find_script(ref)
                new_scripts = [s for s in new_scripts if s is not script]
            node.scripts = new_scripts
            node.attributes.update(copy.deepcopy(attributes or {}))
            for key in remove_attributes or []:
                node.attributes.pop(key, None)
            if name is not None:
                node.attributes['name'] = name
            return self.describe(node, path)

        @tool('object_delete', "Delete an object (or prefab) together with all its children.",
              {'object': S(OBJECT_REF)}, ['object'], mutates=True)
        def object_delete(object):
            node, parent, path, is_prefab = self.find_object(object)
            if node is self.world.root_object:
                raise ToolError("The scene root cannot be deleted")
            if parent is not None:
                parent.delete_child(node.identity)
            else:
                self.world.prefabs[:] = [p for p in self.world.prefabs if p is not node]
                if self.world.connection_prefab_identity == node.identity:
                    self.world.connection_prefab_identity = ''
            return {'deleted': path}

        def clone(node, cls):
            data = json.loads(json.dumps(node.save()))
            assets._renew_identities(data)
            return cls().load(data, self.world)

        @tool('object_move', "Move an object under another parent (within the scene or within prefabs).",
              {'object': S(OBJECT_REF), 'new_parent': S(OBJECT_REF)}, ['object', 'new_parent'], mutates=True)
        def object_move(object, new_parent):
            node, parent, path, is_prefab = self.find_object(object)
            target, _, target_path, target_is_prefab = self.find_object(new_parent)
            if parent is None:
                raise ToolError("Top-level prefabs and the scene root cannot be moved; use object_copy")
            if is_prefab != target_is_prefab:
                raise ToolError("Cannot move between the scene and prefabs; use object_copy")
            if any(found[0] is target for found in self._walk(node, None, '')):
                raise ToolError("Cannot move an object into itself")
            parent.delete_child(node.identity)
            target.children.append(node)
            return {'moved': f"{target_path.rstrip('/')}/{node.get_name()}"}

        @tool('object_copy',
              "Copy an object with its subtree. Works across the scene/prefab boundary: copy a prefab into the scene "
              "to place an instance at edit time, or copy a scene object with to_prefab=true to make a template.",
              {'object': S(OBJECT_REF), 'new_parent': S(OBJECT_REF + " Ignored when to_prefab=true."),
               'name': S("Name for the copy."), 'attributes': O("Attributes to override in the copy."),
               'to_prefab': B("Create the copy as a new top-level prefab.")},
              ['object'], mutates=True)
        def object_copy(object, new_parent='/', name=None, attributes=None, to_prefab=False):
            node, parent, path, is_prefab = self.find_object(object)
            if to_prefab:
                copied = clone(node, PrefabFile)
                self.world.prefabs.append(copied)
                new_path = 'prefab:/'
            else:
                target, _, target_path, target_is_prefab = self.find_object(new_parent)
                copied = clone(node, PrefabFile if target_is_prefab else ObjectFile)
                target.children.append(copied)
                new_path = target_path.rstrip('/') + '/'
            copied.attributes.update(copy.deepcopy(attributes or {}))
            if name is not None:
                copied.attributes['name'] = name
            return self.describe(copied, new_path + copied.get_name())

        # ---------------- ассеты
        @tool('asset_export',
              "Export a script or an object as a shareable asset file (.kasset, JSON). A script asset includes the "
              "libraries it loads via world.require. An object asset includes its whole subtree and every script "
              "it needs. Give the file to someone else and they load it with asset_import.",
              {'kind': S("What to export.", enum=['script', 'object']),
               'target': S("Script name/identity, or object reference (use 'prefab:/Name' for a prefab)."),
               'path': S("Output file path, e.g. 'assets/shopkeeper.kasset'."),
               'description': S("What the asset does and how to use it."), 'author': S("Author name.")},
              ['kind', 'target', 'path'])
        def asset_export(kind, target, path, description='', author=''):
            self.require_world()
            if kind == 'script':
                asset = assets.export_script(self.world, self.find_script(target), description, author)
            elif kind == 'object':
                asset = assets.export_object(self.world, self.find_object(target)[0], description, author)
            else:
                raise ToolError("kind must be 'script' or 'object'")
            written = assets.write_asset(asset, Path(path).expanduser())
            return {'file': str(written), **assets.describe_asset(asset)}

        @tool('asset_inspect', "Look inside an asset file or URL without importing it.",
              {'source': S("Path to a .kasset file or an http(s) URL.")}, ['source'])
        def asset_inspect(source):
            try:
                return assets.describe_asset(assets.read_asset(source))
            except (OSError, ValueError) as error:
                raise ToolError(f"Cannot read asset: {error}")

        @tool('asset_import',
              "Load an asset (from a file or URL) into the open world. Scripts get added to the script list; an "
              "object asset becomes a prefab by default, or is placed into the scene when 'parent' is given. "
              "Assets contain code that will run on the game server: inspect assets from untrusted sources first.",
              {'source': S("Path to a .kasset file or an http(s) URL."),
               'parent': S("Place the object under this scene object instead of creating a prefab. " + OBJECT_REF),
               'on_conflict': S("If a script with the same name but different code exists: keep the existing one, "
                                "replace its code, or import under a new name.",
                                enum=['keep', 'replace', 'rename'])},
              ['source'], mutates=True)
        def asset_import(source, parent=None, on_conflict='keep'):
            self.require_world()
            try:
                asset = assets.read_asset(source)
            except (OSError, ValueError) as error:
                raise ToolError(f"Cannot read asset: {error}")
            target = self.find_object(parent)[0] if parent else None
            return assets.import_asset(self.world, asset, parent=target, on_conflict=on_conflict)

        @tool('asset_list', "List asset files in a directory.",
              {'directory': S("Directory to scan (default 'assets').")})
        def asset_list(directory='assets'):
            found = []
            for file in sorted(Path(directory).expanduser().glob('**/*' + assets.ASSET_EXTENSION)):
                try:
                    found.append({'file': str(file), **assets.describe_asset(assets.read_asset(file))})
                except (OSError, ValueError) as error:
                    found.append({'file': str(file), 'error': str(error)})
            return found

        # ---------------- запуск и проверка игры
        @tool('server_start',
              "Start the game server on the open world so it can be played and tested. The running game changes "
              "the world file (objects move, attributes change); server_stop decides whether to keep that.")
        def server_start():
            self.require_world()
            self.world.save_filename(self.world.filename)
            self.runner.start(self.world.filename)
            return self.runner.status(self.world)

        @tool('server_stop', "Stop the game server.",
              {'keep_changes': B("true: load the state the game left behind (default false: restore the world as it "
                                 "was before the start).")})
        def server_stop(keep_changes=False):
            self.require_world()
            self.sessions.close_all()
            logs = self.runner.stop()
            if keep_changes:
                self.world.load_filename(self.world.filename)
            else:
                # игра при выходе перезаписала файл - возвращаем состояние редактора
                self.world.save_filename(self.world.filename)
            if self.on_change:
                self.on_change()
            return {'stopped': True, 'kept_changes': keep_changes, 'last_logs': logs}

        @tool('server_status', "Is the game server running, on which addresses.")
        def server_status():
            self.require_world()
            return self.runner.status(self.world)

        @tool('server_logs', "Server output: startup messages, script errors with tracebacks, print() from scripts.",
              {'tail': I("How many last lines (default 60)."), 'contains': S("Only lines containing this text.")})
        def server_logs(tail=60, contains=None):
            return self.runner.logs(tail, contains)

        @tool('play_connect', "Connect to the running game as a player (like opening the web client). Returns a "
                              "session id and what the game sent on connect.",
              {'wait': N("Seconds to wait for the first messages (default 1).")})
        def play_connect(wait=1.0):
            self.require_world()
            if not self.runner.running():
                raise ToolError("The server is not running. Call server_start first.")
            host = 'localhost' if self.world.host in ('0.0.0.0', '') else self.world.host
            return self.sessions.connect(f"ws://{host}:{self.world.port_wss}", wait)

        @tool('play_send', "Send a line of player input in a play session and return what the game answers.",
              {'session': S("Session id from play_connect."), 'text': S("What the player types."),
               'wait': N("Seconds to wait for the answer (default 0.6)."),
               'raw': B("Return messages with color tags instead of plain text.")},
              ['session', 'text'])
        def play_send(session, text, wait=0.6, raw=False):
            return self.sessions.send(session, text, wait, raw)

        @tool('play_read', "Read messages that arrived in a play session since the last read.",
              {'session': S("Session id."), 'wait': N("Seconds to wait before reading (default 0)."),
               'raw': B("Keep color tags.")}, ['session'])
        def play_read(session, wait=0.0, raw=False):
            return self.sessions.read(session, wait, raw)

        @tool('play_disconnect', "Close a play session.", {'session': S("Session id.")}, ['session'])
        def play_disconnect(session):
            return self.sessions.close(session)

    # -- завершение работы
    def shutdown(self):
        self.sessions.close_all()
        if self.runner.running():
            self.runner.stop()
            if self.opened:
                self.world.save_filename(self.world.filename)
