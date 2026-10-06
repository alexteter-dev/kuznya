"""sim: brings the city to life and moves time forward."""
import traceback

U = world.require('util')
city = world.require('city')
economy = world.require('economy')
people = world.require('people')
combat = world.require('combat')
capes = world.require('capes')
powers = world.require('powers')
names = world.require('names')

WELL_OFF = {'executive', 'doctor', 'lawyer', 'mayor', 'professor', 'banker', 'PRT director', 'croupier'}
MIDDLE = {'teacher', 'clerk', 'office worker', 'PRT officer', 'PRT clerk', 'police officer', 'nurse', 'librarian',
          'curator', 'principal', 'hero', 'tailor', 'guard', 'bartender', 'bouncer', 'Empire enforcer',
          'pit fighter', 'pit boss', 'mercenary', 'consultant'}
SQUATTERS = {'dealer', 'scavenger'}


def home_for(job):
    if job in WELL_OFF:
        return "Captain's Hill"
    if job in MIDDLE:
        return 'Downtown Apartments'
    if job in SQUATTERS:
        return 'Trainyard'
    return U.pick(['Docks Tenements', 'Docks Residential Fringe', 'Docks Residential Fringe'])


def prepare(person):
    """Turn a character as authored in the editor into a living resident."""
    a = person.attributes
    raw = a.pop('cape_raw', None)
    if a.pop('anon', False) or not a.get('name'):
        # canon never gives this person a civilian name
        a['name'] = names.person(a.get('sex'))[0]
    if 'description' in a:
        a['desc'] = a.pop('description')
    names.used.add(a['name'])
    if a.get('home') not in city.LOC:
        a['home'] = home_for(a.get('job', 'unemployed'))
    people.normalize(person)
    if raw:
        power = powers.canon(raw['cape'], raw['classes'], raw['power'])
        a['power'] = power
        a['maxhp'] = 30 + power['hp']
        a['hp'] = a['maxhp']
        a['cape'] = {'name': raw['cape'], 'align': raw['align'], 'lethal': raw.get('lethal', False),
                     'look': raw.get('look', 'a parahuman in costume')}
        for key in ('passive', 'duty', 'beat', 'base'):
            if key in raw:
                a['cape'][key] = raw[key]
        traits = a['traits']
        if raw['align'] == 'hero':
            traits['brave'] = max(traits['brave'], 0.75)
            traits['kind'] = max(traits['kind'], 0.6)
        elif raw['align'] == 'villain':
            traits['brave'] = max(traits['brave'], 0.6)
            traits['violent'] = max(traits['violent'], 0.75 if raw.get('lethal') else 0.5)
        capes.setup_cape(person)
    return person


def register(person):
    """Put a resident on the staff list of their workplace."""
    a = person.attributes
    loc = city.LOC.get(a.get('work'))
    b = economy.biz(loc) if loc is not None else None
    if b is None:
        return
    if person.identity not in b['staff']:
        same = sum(1 for p in economy.staff(loc) if p.attributes.get('job') == a['job'])
        a.setdefault('shift', same % 2)
        b['staff'].append(person.identity)


def populate():
    """First start only: wake the authored characters and generate everyone else from the jobs that exist."""
    for loc in list(city.LOC.values()):
        for child in list(loc.children):
            if child.attributes.get('kind') == 'npc' and not child.attributes.get('ready'):
                prepare(child)
    for person in list(city.PEOPLE.values()):
        register(person)
    for loc in economy.shops():
        b = economy.biz(loc)
        place = loc.attributes['name']
        for job, slots in b['slots'].items():
            filled = sum(1 for p in economy.staff(loc) if p.attributes.get('job') == job)
            for index in range(slots - filled):
                extra = {}
                if b.get('faction'):
                    extra['faction'] = b['faction']
                    extra['traits'] = {'violent': round(U.rng.uniform(0.5, 1.0), 2)}
                    extra['home'] = {'ABB': 'Docks Tenements', 'Merchants': 'Trainyard'}.get(b['faction'], 'Downtown Apartments')
                home = extra.pop('home', None) or home_for(job)
                register(people.spawn(job, place, home, **extra))
    for index in range(14):
        people.spawn('unemployed', '', U.pick(['Docks Tenements', 'Docks Tenements', 'Trainyard']),
                     addict=U.chance(0.35), money=U.rng.randrange(5, 30))
    for school, count in (('Winslow High', 10), ('Arcadia High', 8)):
        for index in range(count):
            register(people.spawn('student', school, home_for('teacher' if school == 'Arcadia High' else 'baker'),
                                  age=U.rng.randrange(15, 18)))

    by_name = {}
    for person in city.PEOPLE.values():
        by_name[person.attributes['name']] = person
        if person.attributes.get('cape'):
            by_name[person.attributes['cape']['name']] = person
    # owners
    for loc in economy.shops():
        b = economy.biz(loc)
        owner = by_name.get(b.pop('owner_name', ''))
        if owner is not None:
            b['owner'] = owner.identity
        elif b.get('owned') and economy.staff(loc):
            b['owner'] = economy.staff(loc)[0].identity
    # families, then workmates and neighbours
    for person in city.PEOPLE.values():
        a = person.attributes
        for name in a.pop('family', []):
            other = by_name.get(name)
            if other is None or other is person:
                continue
            if other.identity not in a['friends']:
                a['friends'].append(other.identity)
            if a['age'] - other.attributes['age'] >= 18 and other.attributes['age'] < 19:
                a.setdefault('children', []).append(other.identity)
    everyone = list(city.PEOPLE.values())
    for person in everyone:
        a = person.attributes
        mates = [p for p in everyone if p is not person and a['work'] and p.attributes['work'] == a['work']]
        near = [p for p in everyone if p is not person and p.attributes['home'] == a['home']]
        for pool, count in ((mates, 2), (near, 1)):
            for other in U.rng.sample(pool, min(count, len(pool))):
                if other.identity not in a['friends'] and len(a['friends']) < 6:
                    a['friends'].append(other.identity)
    city.state['pop_target'] = len(city.PEOPLE)
    city.state['populated'] = True
    city.post("Sunday morning in Brockton Bay. The ferry still is not running.", 'city')


def arrivals():
    """People who were out of town come into the city on their day."""
    away = world.do_get_object_by_name('Out of Town')
    if away is None:
        return
    for person in list(away.children):
        if person.attributes.get('arrives', 0) <= city.day():
            home = person.attributes.get('home')
            city.LOC[home if home in city.LOC else 'Downtown Apartments'].adopt(person)
            prepare(person)
            register(person)
            cape = person.attributes.get('cape')
            if cape and not cape.get('passive'):
                city.post(f"New in town, or newly active: {cape['name']}.", 'cape', loud=True)


def start():
    """Every server start."""
    city.init()
    for loc in economy.shops():
        economy.init_biz(loc)
    if not city.state.get('populated'):
        populate()
    else:
        for person in city.PEOPLE.values():
            person.attributes.pop('fight', None)
            names.used.add(person.attributes['name'])
    print(f"[Brockton Bay] {len(city.LOC)} places, {len(city.PEOPLE)} residents, {city.stamp()}")


def record():
    report = economy.market_report()
    held, tills = economy.money_supply()
    residents = [p for p in city.PEOPLE.values() if p.attributes.get('kind') == 'npc']
    history = city.state.setdefault('history', [])
    history.append({
        'day': city.day(), 'pop': len(residents),
        'bread': report.get('bread', {}).get('price'), 'fish': report.get('fish', {}).get('price'),
        'meal': report.get('meal', {}).get('price'),
        'hungry': sum(1 for p in residents if p.attributes['hunger'] > 85),
        'jobless': sum(1 for p in residents if p.attributes['job'] == 'unemployed'),
        'money': int(held), 'tills': int(tills), 'deaths': city.state['stats'].get('deaths', 0),
    })
    del history[:-90]


def step():
    """One tick: ten minutes of city time."""
    state = city.state
    state['t'] += city.TICK_MINUTES
    for person in list(city.PEOPLE.values()):
        if person.alive:
            try:
                person.trigger('tick')
            except Exception as error:
                # one resident's bad moment must not freeze everyone else
                city.count('errors')
                if state['stats']['errors'] <= 20:
                    print(f"[script error] {person.attributes.get('name')}: {error}")
                    traceback.print_exc()
    try:
        combat.tick()
    except Exception as error:
        city.count('errors')
        print(f"[script error] combat: {error}")
        traceback.print_exc()
    if city.minute() != 0:
        return
    hour = city.hour()
    for loc in economy.shops():
        loc.trigger('hour')
    economy.restock()
    capes.hourly()
    if hour == 18:
        economy.payday()
    if hour == 0:
        economy.rent()
        economy.daily()
        record()
    if hour == 9:
        residents = sum(1 for p in city.PEOPLE.values() if p.attributes.get('kind') == 'npc')
        if residents < state.get('pop_target', 0) and U.chance(0.6):
            newcomer = people.spawn('unemployed', '', 'Docks Tenements', money=U.rng.randrange(20, 60))
            city.move(newcomer, 'Brockton Bay Bus Station', quiet=True)
            city.post(f"A newcomer got off the bus: {newcomer.attributes['name']}.", 'city')
    if hour == 4 and state.get('autosave', True):
        world.save_filename(world.filename)
