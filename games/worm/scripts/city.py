"""city: the map, the clock, who is where, movement, messages and the news feed."""
import datetime

U = world.require('util')

TICK_MINUTES = 10
START = datetime.datetime(2011, 4, 10, 0, 0)   # Sunday; the serial opens the following week

LOC = {}       # name -> location object
PEOPLE = {}    # identity -> person object (residents and connected players)
NEXT = {}      # (from, to) -> name of the next location on the shortest path
DIST = {}      # (from, to) -> number of moves
state = {}     # persistent simulation state: the Simulation object's attributes


def director():
    return world.do_get_object_by_name('Simulation')


def init():
    """Index the world. Called on every server start."""
    global state
    state = director().attributes
    state.setdefault('t', 6 * 60)
    state.setdefault('news', [])
    state.setdefault('orders', [])
    state.setdefault('incidents', [])
    state.setdefault('stats', {})
    LOC.clear()
    PEOPLE.clear()
    for obj in world.get_objects():
        kind = obj.attributes.get('kind')
        if kind == 'location':
            LOC[obj.attributes['name']] = obj
    for loc in LOC.values():
        for child in loc.children:
            if child.attributes.get('kind') in ('npc', 'player') and child.attributes.get('ready'):
                PEOPLE[child.identity] = child
    # exits are stored one way in places; make them all two-way
    for loc in LOC.values():
        for name in loc.attributes.get('exits', []):
            other = LOC[name].attributes.setdefault('exits', [])
            if loc.attributes['name'] not in other:
                other.append(loc.attributes['name'])
    for origin in LOC:
        DIST[(origin, origin)] = 0
        frontier = [origin]
        while frontier:
            following = []
            for name in frontier:
                for exit_name in LOC[name].attributes.get('exits', []):
                    if (origin, exit_name) not in DIST:
                        DIST[(origin, exit_name)] = DIST[(origin, name)] + 1
                        # the first step toward exit_name is the first step toward name, or the exit itself
                        NEXT[(origin, exit_name)] = NEXT.get((origin, name), exit_name)
                        following.append(exit_name)
            frontier = following


# -- clock
def now():
    return state['t']


def hour():
    return (state['t'] // 60) % 24


def minute():
    return state['t'] % 60


def day():
    return state['t'] // 1440


def stamp(t=None):
    moment = START + datetime.timedelta(minutes=state['t'] if t is None else t)
    return moment.strftime('%a %b %d, %H:%M')


def is_night():
    return U.in_hours(hour(), 21, 6)


# -- people and places
def loc_of(person):
    parent = person.parent
    return parent if parent is not None and parent.attributes.get('kind') == 'location' else None


def where(person):
    loc = loc_of(person)
    return loc.attributes['name'] if loc else None


def people_in(loc):
    return [child for child in loc.children
            if child.alive and child.attributes.get('kind') in ('npc', 'player') and child.attributes.get('ready')]


def players():
    return [p for p in PEOPLE.values() if p.attributes.get('kind') == 'player' and p.connection is not None]


def dname(person):
    """The name others see: a costume hides the person wearing it."""
    a = person.attributes
    cape = a.get('cape')
    if cape and cape.get('costume'):
        return cape['name']
    return a['name']


def tag(person):
    a = person.attributes
    cape = a.get('cape')
    if cape and cape.get('costume'):
        colour = {'hero': 'cyan', 'villain': 'red'}.get(cape.get('align'), 'magenta')
        return f"<{colour}>{cape['name']}</>"
    if a.get('kind') == 'player':
        return f"<green>{a['name']}</>"
    return a['name']


def tell_room(loc, text, exclude=()):
    if loc is None:
        return
    for child in loc.children:
        if child.connection is not None and child not in exclude:
            child.send(text)


def tell(person, text):
    if person.connection is not None:
        person.send(text)


def distance(origin, destination):
    return DIST.get((origin, destination), 99)


def move(person, destination, quiet=False):
    """Put a person into another location, telling both rooms."""
    source = loc_of(person)
    target = LOC[destination]
    if source is target:
        return
    a = person.attributes
    # crowds are background: announce only what a player would notice
    notable = a.get('kind') == 'player' or (a.get('cape') or {}).get('costume')
    if not quiet and source is not None and (notable or noticed(source)):
        tell_room(source, f"<gray>{tag(person)} leaves for {destination}.</>", exclude=(person,))
    target.adopt(person)
    if not quiet and (notable or noticed(target)):
        origin = source.attributes['name'] if source is not None else 'somewhere'
        tell_room(target, f"<gray>{tag(person)} arrives from {origin}.</>", exclude=(person,))
    person.trigger('moved')


def noticed(loc):
    """Is this a place where one more ordinary person coming or going stands out?"""
    return 'street' not in loc.attributes.get('tags', []) and len(loc.children) <= 6


def step_toward(person, destination):
    """One move along the shortest path. True when the person is already there."""
    here = where(person)
    if here == destination:
        return True
    if here is None:
        move(person, destination, quiet=True)
        return True
    following = NEXT.get((here, destination))
    if following is None:
        return True
    move(person, following)
    return following == destination


def route(origin, destination):
    path = []
    here = origin
    while here != destination and (here, destination) in NEXT:
        here = NEXT[(here, destination)]
        path.append(here)
    return path


# -- news: word of mouth plus the Parahumans Online boards
def post(text, kind='city', loud=False):
    news = state['news']
    news.append({'t': state['t'], 'text': text, 'kind': kind})
    del news[:-80]
    if loud:
        for player in players():
            player.send(f"<gold>[PHO]</> {text}")


def count(key, amount=1):
    state['stats'][key] = state['stats'].get(key, 0) + amount
