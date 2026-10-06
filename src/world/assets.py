"""
Ассеты: переносимые скрипты и объекты.
Ассет - обычный JSON-файл (.kasset), который можно передать другому человеку
и загрузить в его проект. Ассет объекта несет с собой все нужные ему скрипты.
"""

# -- импорт библиотек
import gzip
import json
import re
import secrets
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .loader import ObjectFile, PrefabFile, ScriptFile

# -- константы
ASSET_FORMAT = 'kuznya-asset'
ASSET_VERSION = 1
ASSET_EXTENSION = '.kasset'
REQUIRE_PATTERN = re.compile(r"""world\.require\(\s*(['"])(.+?)\1\s*\)""")


# -- вспомогательные функции
def _required_names(code):
    return [match.group(2) for match in REQUIRE_PATTERN.finditer(code)]


def _collect_scripts(world, scripts):
    """Скрипты вместе с библиотеками, которые они подключают через world.require"""
    collected = []
    missing = []
    queue = [script for script in scripts if script is not None]
    while queue:
        script = queue.pop(0)
        if script in collected:
            continue
        collected.append(script)
        for name in _required_names(script.code):
            dependency = world.do_get_script_by_name(name)
            if dependency is None:
                if name not in missing:
                    missing.append(name)
            elif dependency not in collected:
                queue.append(dependency)
    return collected, missing


def _tree_scripts(obj):
    found = [script for script in obj.scripts if script is not None]
    for child in obj.children:
        found += _tree_scripts(child)
    return found


def _asset(kind, name, description, author, scripts, missing, obj=None):
    return {
        'format': ASSET_FORMAT,
        'version': ASSET_VERSION,
        'kind': kind,
        'name': name,
        'description': description,
        'author': author,
        'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'requires': missing,
        'scripts': [script.save() for script in scripts],
        'object': obj.save() if obj is not None else None,
    }


# -- экспорт
def export_script(world, script, description='', author=''):
    scripts, missing = _collect_scripts(world, [script])
    return _asset('script', script.name, description, author, scripts, missing)


def export_object(world, obj, description='', author=''):
    scripts, missing = _collect_scripts(world, _tree_scripts(obj))
    return _asset('object', obj.get_name(), description, author, scripts, missing, obj)


def write_asset(asset, path):
    path = Path(path)
    if path.suffix == '':
        path = path.with_suffix(ASSET_EXTENSION)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='UTF-8') as file:
        json.dump(asset, file, ensure_ascii=False, indent=1)
    return path


# -- импорт
def read_asset(source):
    """Чтение ассета из файла или по ссылке http(s)"""
    source = str(source)
    if source.startswith('http://') or source.startswith('https://'):
        with urllib.request.urlopen(source, timeout=30) as response:
            raw = response.read()
    else:
        raw = Path(source).read_bytes()
    if raw[:2] == b'\x1f\x8b':
        raw = gzip.decompress(raw)
    asset = json.loads(raw.decode('UTF-8'))

    if not isinstance(asset, dict) or asset.get('format') != ASSET_FORMAT:
        raise ValueError('Это не ассет Кузни')
    if asset.get('version', 0) > ASSET_VERSION:
        raise ValueError(f"Ассет создан в более новой версии формата: {asset.get('version')}")
    if asset.get('kind') not in ('script', 'object'):
        raise ValueError(f"Неизвестный тип ассета: {asset.get('kind')}")
    return asset


def describe_asset(asset):
    def count(node):
        return 1 + sum(count(child) for child in node['children'])

    return {
        'kind': asset['kind'],
        'name': asset.get('name', ''),
        'description': asset.get('description', ''),
        'author': asset.get('author', ''),
        'created': asset.get('created', ''),
        'requires': asset.get('requires', []),
        'scripts': [{'name': script['name'], 'lines': script['code'].count('\n') + 1} for script in asset['scripts']],
        'objects': count(asset['object']) if asset.get('object') else 0,
    }


def _renew_identities(node):
    node['identity'] = secrets.token_urlsafe(16)
    for child in node['children']:
        _renew_identities(child)


def import_asset(world, asset, parent=None, as_prefab=True, on_conflict='keep'):
    """
    Загрузка ассета в мир. Все идентификаторы выдаются заново, поэтому один ассет можно загружать много раз.
    on_conflict - что делать, если скрипт с таким именем уже есть, а код отличается:
    'keep' - оставить существующий, 'replace' - заменить код, 'rename' - загрузить под новым именем.
    Возвращает отчет: какие скрипты добавлены, какой объект создан.
    """
    if on_conflict not in ('keep', 'replace', 'rename'):
        raise ValueError("on_conflict: 'keep', 'replace' или 'rename'")

    report = {'scripts_added': [], 'scripts_reused': [], 'scripts_replaced': [], 'conflicts': [], 'object': None,
              'missing': []}
    identities = {}

    for saved in asset['scripts']:
        existing = world.do_get_script_by_name(saved['name'])
        if existing is not None and existing.code == saved['code']:
            identities[saved['identity']] = existing.identity
            report['scripts_reused'].append(existing.name)
            continue
        if existing is not None and on_conflict == 'keep':
            identities[saved['identity']] = existing.identity
            report['conflicts'].append(existing.name)
            continue
        if existing is not None and on_conflict == 'replace':
            existing.code = saved['code']
            identities[saved['identity']] = existing.identity
            report['scripts_replaced'].append(existing.name)
            continue

        name = saved['name']
        number = 2
        while world.do_get_script_by_name(name) is not None:
            name = f"{saved['name']} ({number})"
            number += 1
        script = ScriptFile(code=saved['code'], name=name)
        world.scripts.append(script)
        identities[saved['identity']] = script.identity
        report['scripts_added'].append(name)

    for name in asset.get('requires', []):
        if world.do_get_script_by_name(name) is None:
            report['missing'].append(name)

    if asset.get('object'):
        saved = json.loads(json.dumps(asset['object']))

        def remap(node):
            node['scripts'] = [identities[i] for i in node['scripts'] if i in identities]
            for child in node['children']:
                remap(child)

        remap(saved)
        _renew_identities(saved)

        if parent is None and as_prefab:
            obj = PrefabFile().load(saved, world)
            world.prefabs.append(obj)
        else:
            target = parent if parent is not None else world.root_object
            obj = type(target)().load(saved, world)
            target.children.append(obj)
        report['object'] = {'identity': obj.identity, 'name': obj.get_name(),
                            'prefab': isinstance(obj, PrefabFile)}

    return report
