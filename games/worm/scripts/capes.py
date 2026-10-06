"""capes: heroes, villains, gangs, the law - and the dated events of spring 2011.

Capes are ordinary residents with a power and a second life. Out of costume they hold jobs and buy bread;
on duty they patrol, answer incidents, run gang operations. Nothing here decides who wins.
"""
U = world.require('util')
city = world.require('city')
economy = world.require('economy')
combat = world.require('combat')
powers = world.require('powers')
speech = world.require('speech')
people = world.require('people')
tasks = world.require('tasks')

GANG_HQ = {
    'ABB': ('ABB Gambling Den', 'ABB enforcer'),
    'Empire 88': ('Empire Fighting Pits', 'Empire enforcer'),
    'Merchants': ("Merchants' Hideout", 'dealer'),
    'Coil': ("Coil's Underground Base", 'mercenary'),
}
TURF = {
    'ABB': ['Docks', 'Shipping Container Blocks', 'Docks Tenements', 'North Ferry Station'],
    'Empire 88': ['Downtown', 'Lord Street', 'The Towers'],
    'Merchants': ['Trainyard', 'Boat Graveyard', 'Storage Facility'],
}
PROTECTION = {
    'ABB': ['Fishing Pier', 'Cargo Pier', 'Docks Machine Shop', 'Lord Street Market', 'Dockworkers Association'],
    'Empire 88': ['Lord Street Bakery', 'Hillside Mall', 'Weymouth Shopping Center', 'Boardwalk Boutiques'],
    'Merchants': ['Boat Graveyard'],
}
RIVALS = {
    'ABB': ['Empire 88', 'Merchants', 'Undersiders'],
    'Empire 88': ['ABB', 'Merchants'],
    'Merchants': ['ABB'],
    'Undersiders': ['ABB'],
}
BEATS = {
    'Protectorate': ['Boardwalk', 'Docks', 'Lord Street', 'Downtown', 'Lord Street Market', 'Docks Residential Fringe'],
    'Wards': ['Downtown', 'Lord Street', 'Boardwalk', 'Arcadia High', 'Hillside Mall'],
    'New Wave': ['The Towers', 'Downtown', "Captain's Hill", 'Boardwalk'],
    'Independent': ['Docks', 'Docks Residential Fringe', 'Trainyard', 'Lord Street'],
}
ROB_TARGETS = ['Ruby Dreams Casino', 'Hillside Mall', 'Weymouth Shopping Center', 'Boardwalk Boutiques',
               'Brockton Bay Central Bank', 'Medhall Building']
LEVIATHAN_PATH = ['Beach', 'Boardwalk', 'Docks', 'Cargo Pier', 'Docks', 'Lord Street', 'Lord Street Market',
                  'Lord Street', 'Downtown', 'Brockton Bay Central Bank', 'Downtown', 'Docks Residential Fringe',
                  'Docks', 'Boardwalk', 'Beach']


# -- duty
def on_duty(person, hour):
    cape = person.attributes.get('cape')
    if not cape or cape.get('passive') or not person.attributes.get('power'):
        return False
    return U.in_hours(hour, *cape.get('duty', [21, 2]))


def suit_up(person, on=True):
    cape = person.attributes['cape']
    if bool(cape.get('costume')) == on:
        return
    loc = city.loc_of(person)
    cape['costume'] = on
    if loc is not None and 'street' not in loc.attributes.get('tags', []) and city.players():
        watchers = [p for p in city.people_in(loc) if p.connection is not None]
        if watchers and len(city.people_in(loc)) <= 4:
            # changing in front of someone gives the game away
            for watcher in watchers:
                watcher.attributes.setdefault('known', {})[person.identity] = True
                watcher.send(f"<magenta>You see {person.attributes['name']} pull on a mask: {cape['name']}.</>" if on
                             else f"<magenta>{cape['name']} takes off the mask. It is {person.attributes['name']}.</>")


def think(person, hour):
    """Cape business for this tick. True if it used the tick."""
    a = person.attributes
    cape = a['cape']
    if not on_duty(person, hour):
        if cape.get('costume') and not a['tasks']:
            suit_up(person, False)
        return False
    suit_up(person, True)
    a['state'] = 'idle'
    loc = city.loc_of(person)
    if cape['align'] == 'hero':
        for other in city.people_in(loc):
            oa = other.attributes
            if other is not person and oa.get('wanted', 0) > 0 and combat.can_fight(other) \
                    and not combat.hidden(other) and not combat.is_law(other):
                speech.say(person, other, 'arrest')
                combat.attack(person, other, 'arrest')
                return True
        beat = cape.get('beat') or BEATS['Independent']
        a['beat_wait'] = a.get('beat_wait', 0) + 1
        if a['beat_wait'] >= 3:
            a['beat_wait'] = 0
            a['beat'] = (a.get('beat', U.rng.randrange(len(beat))) + 1) % len(beat)
        city.step_toward(person, beat[a.get('beat', 0) % len(beat)])
        return True
    if cape['align'] == 'villain':
        base = cape.get('base') or a['home']
        if not a.get('faction') or a['faction'] not in GANG_HQ:
            # loners work for themselves
            if U.chance(0.002) and not a['tasks']:
                tasks.add(person, {'type': 'rob', 'loc': U.pick(ROB_TARGETS), 'ttl': 40})
                return True
        city.step_toward(person, base if base in city.LOC else a['home'])
        return True
    return False


def gang_time(person, hour):
    """Rank-and-file gang members prowl their turf at night."""
    a = person.attributes
    turf = TURF.get(a.get('faction'))
    if not turf or a.get('cape') or not U.in_hours(hour, 21, 3) or a['energy'] < 30:
        return False
    a['state'] = 'idle'
    a['beat_wait'] = a.get('beat_wait', 0) + 1
    if a['beat_wait'] >= 4:
        a['beat_wait'] = 0
        a['beat'] = U.rng.randrange(len(turf))
    spot = turf[a.get('beat', 0) % len(turf)]
    if not city.step_toward(person, spot):
        return True
    loc = city.loc_of(person)
    present = city.people_in(loc)
    if U.chance(0.08) and not any(combat.is_law(p) for p in present):
        marks = [p for p in present if p is not person and not p.attributes.get('faction') and people.awake(p)
                 and p.attributes.get('money', 0) > 20 and 'fight' not in p.attributes
                 and not combat.hidden(p) and not (p.attributes.get('cape') or {}).get('costume')
                 and not p.attributes.get('threat')]
        if marks:
            mug(person, U.pick(marks))
    return True


# -- street crime
def mug(mugger, victim):
    va = victim.attributes
    ma = mugger.attributes
    speech.say(mugger, victim, 'mug')
    city.count('muggings')
    if va.get('kind') == 'player':
        va['threat'] = {'by': mugger.identity, 'until': city.now() + 20}
        victim.send("<red>You are being robbed.</> <gray>Type</> <cyan>pay</><gray>,</> <cyan>attack</> <gray>or</> <cyan>flee</><gray>. Quickly.</>")
        combat.maybe_trigger(victim, 'hunted')
        return
    if va['traits']['brave'] < 0.65 or va.get('power') is None and U.chance(0.5):
        speech.say(victim, mugger, 'mug_pay')
        taken = va['money'] * 0.5
        va['money'] -= taken
        ma['money'] += taken
        ma['wanted'] = max(ma.get('wanted', 0), 40)
        if U.chance(0.3):
            incident(city.where(victim), mugger, 'mug', False)
        combat.maybe_trigger(victim, 'hunted')
    else:
        speech.say(victim, mugger, 'mug_fight')
        combat.attack(mugger, victim, 'mug')


def protection_target(faction):
    places = [city.LOC[name] for name in PROTECTION.get(faction, []) if name in city.LOC]
    U.rng.shuffle(places)
    for loc in places:
        staff = economy.staff(loc)
        if staff:
            return U.pick(staff)
    return None


def collect(enforcer, target, gang):
    work = city.LOC.get(target.attributes.get('work'))
    b = economy.biz(work) if work is not None else None
    speech.say(enforcer, target, 'collect')
    if b is None:
        return
    if target.attributes['traits']['brave'] > 0.85 and U.chance(0.3):
        speech.say(target, enforcer, 'collect_refuse')
        combat.attack(enforcer, target, 'assault')
        return
    speech.say(target, enforcer, 'collect_pay')
    taken = U.clamp(b['cash'] * 0.1, 0, 150)
    b['cash'] -= taken
    hq = economy.biz(city.LOC[GANG_HQ[gang][0]])
    hq['cash'] += taken
    city.count('extorted', taken)


def recruit_target(recruiter):
    pool = [p for p in city.PEOPLE.values() if p.attributes.get('kind') == 'npc'
            and p.attributes.get('job') == 'unemployed' and not p.attributes.get('faction')
            and not p.attributes.get('cape') and p.attributes.get('age', 30) >= 16]
    return U.pick(pool) if pool else None


def recruit(recruiter, target, gang):
    ta = target.attributes
    speech.say(recruiter, target, 'recruit')
    keen = ta['traits']['greed'] + ta['traits']['violent']
    if ta['hunger'] > 60 or ta['money'] < 10 or keen > 1.1:
        speech.say(target, recruiter, 'recruit_yes')
        join_gang(target, gang)
        city.post(f"{ta['name']} is running with the {gang} now.", 'gang')
    else:
        speech.say(target, recruiter, 'recruit_no')


def join_gang(person, gang):
    place, job = GANG_HQ[gang]
    loc = city.LOC[place]
    b = economy.biz(loc)
    filled = sum(1 for p in economy.staff(loc) if p.attributes.get('job') == job)
    b['slots'][job] = max(b['slots'].get(job, 0), filled + 1)
    economy.hire(loc, person, job)
    person.attributes['faction'] = gang
    person.attributes['skills'][job] = 0.8


# -- the law
def incident(place, culprit, why, powered):
    """Someone saw something. Whoever is nearest and able gets sent."""
    ca = culprit.attributes
    if combat.is_law(culprit) or ca.get('endbringer'):
        return
    recent = city.state['incidents']
    recent[:] = [i for i in recent if city.now() - i['t'] < 60]
    if any(i['who'] == culprit.identity for i in recent):
        return
    recent.append({'t': city.now(), 'loc': place, 'who': culprit.identity, 'why': why})
    city.count('incidents')
    if powered and why not in ('rob', 'theft', 'reported'):
        victim = city.PEOPLE.get((ca.get('fight') or {}).get('target', ''))
        versus = f" against {city.dname(victim)}" if victim is not None else ''
        city.post(f"Cape fight at {place}: {city.dname(culprit)}{versus}.", 'cape', loud=True)
    hour = city.hour()
    pool = []
    for person in city.PEOPLE.values():
        a = person.attributes
        if a.get('kind') != 'npc' or not people.awake(person) or 'fight' in a or a.get('away'):
            continue
        if any(t['type'] == 'respond' for t in a['tasks']):
            continue
        cape = a.get('cape')
        if cape and cape.get('align') == 'hero' and a.get('power') and not cape.get('passive'):
            if powered or on_duty(person, hour):
                pool.append((city.distance(city.where(person), place), person))
        elif a.get('job') == 'PRT officer' and powered and people.on_shift(person, hour):
            pool.append((city.distance(city.where(person), place) + 1, person))
        elif a.get('job') == 'police officer' and not powered and people.on_shift(person, hour):
            pool.append((city.distance(city.where(person), place), person))
    pool.sort(key=lambda entry: entry[0])
    for distance, person in pool[:2]:
        if person.attributes.get('cape'):
            suit_up(person, True)
        tasks.add(person, {'type': 'respond', 'loc': place, 'who': culprit.identity, 'ttl': 30}, front=True)


def do_respond(person, task):
    a = person.attributes
    culprit = city.PEOPLE.get(task['who'])
    if culprit is None or not culprit.alive:
        tasks.done(person)
        return False
    ca = culprit.attributes
    if ca.get('jail') or ca.get('wanted', 0) <= 0:
        tasks.done(person)
        return False
    a['state'] = 'idle'
    here = city.where(person)
    there = city.where(culprit)
    goal = there if there is not None and city.distance(here, there) <= 2 else task['loc']
    if here != goal:
        city.step_toward(person, goal)
        return True
    if there == here and not combat.hidden(culprit):
        if ca.get('ko'):
            arrest(culprit, person)
        elif combat.can_fight(culprit):
            speech.say(person, culprit, 'arrest')
            combat.attack(person, culprit, 'arrest')
        return True
    task['ttl'] -= 4
    return True


def arrest(person, by):
    a = person.attributes
    cape = a.get('cape')
    combat.end(person)
    a.pop('ko', None)
    a['hp'] = max(a['hp'], 5)
    a['wanted'] = 0
    a['tasks'] = []
    a['jail'] = 24 if a.get('kind') == 'player' else U.rng.randrange(144, 432)
    if cape and cape.get('align') == 'villain' and a.get('faction'):
        a['jail'] = U.rng.randrange(36, 144)      # villains with friends outside do not stay long
    a['state'] = 'idle'
    loc = city.loc_of(person)
    city.tell_room(loc, f"<cyan>{city.tag(by)} takes {city.tag(person)} into custody.</>", exclude=(person,))
    city.count('arrests')
    if cape and cape.get('costume'):
        city.post(f"{cape['name']} was taken into custody by {city.dname(by)}.", 'cape', loud=True)
    else:
        city.post(f"{a['name']} was arrested at {city.where(person)}.", 'crime')
    city.move(person, 'PRT Holding Cells', quiet=True)
    if a.get('kind') == 'player':
        person.send("<red>You are under arrest.</> <gray>You sit in a holding cell and wait.</>")
        a['rep'] = a.get('rep', 0) - 5


def release(person):
    a = person.attributes
    a.pop('jail', None)
    cape = a.get('cape')
    if cape and cape.get('align') == 'villain':
        city.post(f"{cape['name']} is back on the street. The PRT is not saying how.", 'cape', loud=True)
    city.move(person, 'Downtown', quiet=True)
    city.tell(person, "<green>They let you go.</> <gray>You walk out onto the street Downtown.</>")


# -- new capes
def new_cape(person):
    """A resident who just triggered decides what to do with it."""
    a = person.attributes
    traits = a['traits']
    power = a['power']
    good = traits['kind'] + traits['brave']
    bad = traits['greed'] + traits['violent']
    faction = a.get('faction')
    if faction in GANG_HQ:
        align = 'villain'
    else:
        align = 'hero' if good >= bad else 'villain'
        faction = ('Wards' if a['age'] < 18 else 'Protectorate') if align == 'hero' and U.chance(0.5) \
            else 'Independent'
        a['faction'] = faction if faction != 'Independent' or align == 'hero' else ''
    a['cape'] = {
        'name': powers.cape_name(power),
        'align': align,
        'lethal': traits['violent'] > 0.7,
        'costume': False,
        'duty': [18, 23] if align == 'hero' else [21, 2],
        'beat': BEATS.get(faction, BEATS['Independent']),
        'base': a['home'],
        'look': f"a new {power['cls'].lower()} in a homemade costume",
        'new': True,
    }


def setup_cape(person):
    """Fill in duty hours and beats for a canon cape at world start."""
    a = person.attributes
    cape = a['cape']
    faction = a.get('faction', '')
    cape.setdefault('costume', False)
    if cape['align'] == 'hero':
        default = {'Protectorate': [9, 21] if U.chance(0.5) else [14, 2], 'Wards': [16, 21],
                   'New Wave': [17, 23]}.get(faction, [21, 1])
        cape.setdefault('duty', default)
        cape.setdefault('beat', BEATS.get(faction, BEATS['Independent']))
    else:
        cape.setdefault('duty', [21, 3])
        cape.setdefault('base', GANG_HQ[faction][0] if faction in GANG_HQ else a['home'])
    if a.get('power', {}).get('passives') and 'ramp' in a['power']['passives']:
        a['fearless'] = True


# -- gang operations
def members(gang, capes_only=False):
    found = []
    for person in city.PEOPLE.values():
        a = person.attributes
        if a.get('faction') == gang and a.get('kind') == 'npc' and not a.get('jail') and not a.get('ko') \
                and not a.get('away') and (not capes_only or (a.get('cape') and not a['cape'].get('passive'))):
            found.append(person)
    return found


def send(gang, kind, place, count=3, foe=None):
    """Put an operation at the head of the queue for a gang's capes and a few of its soldiers."""
    crew = members(gang, capes_only=True)
    soldiers = [p for p in members(gang) if not p.attributes.get('cape')]
    U.rng.shuffle(soldiers)
    for person in crew + soldiers[:count]:
        if person.attributes.get('cape'):
            suit_up(person, True)
        if person.attributes['state'] == 'sleep':
            person.attributes['state'] = 'idle'
        task = {'type': kind, 'loc': place, 'ttl': 36, 'gang': gang}
        if foe:
            task['foe'] = foe
        tasks.add(person, task, front=True)
    return len(crew) + min(count, len(soldiers))


def nightly():
    """21:00. Each gang decides whether tonight is a night for trouble."""
    if city.state.get('truce', 0) > city.now():
        return
    for gang, odds in (('ABB', 0.2), ('Empire 88', 0.15), ('Merchants', 0.08)):
        if U.chance(odds) and members(gang, capes_only=True):
            rival = U.pick(RIVALS[gang])
            place = U.pick(TURF.get(rival, ['Docks']))
            send(gang, 'raid', place)
            city.count('raids')
    if U.chance(0.12) and members('Undersiders'):
        send('Undersiders', 'rob', U.pick(ROB_TARGETS[:4]), 0)


def do_raid(person, task):
    a = person.attributes
    if not city.step_toward(person, task['loc']):
        a['state'] = 'travel'
        return True
    a['state'] = 'idle'
    loc = city.loc_of(person)
    foes = RIVALS.get(a.get('faction'), [])
    targets = [p for p in city.people_in(loc) if p is not person and combat.can_fight(p) and not combat.hidden(p)
               and (p.attributes.get('faction') in foes or (task.get('foe') and p.attributes.get('faction') == task['foe'])
                    or (p.attributes.get('wanted', 0) > 0 and task.get('foe') == 'wanted'))]
    if targets:
        combat.attack(person, U.pick(targets), 'arrest' if task.get('foe') else 'raid')
    return True


def do_rob(person, task):
    a = person.attributes
    if a.get('cape'):
        suit_up(person, True)
    if not city.step_toward(person, task['loc']):
        a['state'] = 'travel'
        return True
    loc = city.loc_of(person)
    b = economy.biz(loc)
    if b is not None and b['cash'] > 50:
        taken = b['cash'] * 0.25
        b['cash'] -= taken
        a['money'] += taken
        a['wanted'] = max(a.get('wanted', 0), 120)
        city.tell_room(loc, f"<red>{city.tag(person)} is robbing the place!</>")
        city.post(f"{city.dname(person)} hit {task['loc']} and got away with {U.cash(taken)}.", 'crime',
                  loud=bool(a.get('cape')))
        city.count('robberies')
        incident(task['loc'], person, 'rob', bool(a.get('power')))
    tasks.done(person)
    # and away, before anyone in a costume shows up
    base = (a.get('cape') or {}).get('base') or a['home']
    tasks.add(person, {'type': 'goto', 'loc': base if base in city.LOC else a['home'], 'stay': 12, 'ttl': 40},
              front=True)
    return True


# -- dated events, April-May 2011. They set things in motion; the simulation decides how they end.
def by_cape(name):
    for person in city.PEOPLE.values():
        if (person.attributes.get('cape') or {}).get('name') == name:
            return person
    return None


def event_lung(day):
    lung = by_cape('Lung')
    if lung is None or lung.attributes.get('jail'):
        return
    city.post("Word on the Docks: Lung is gathering his people tonight, and he is in a mood.", 'gang', loud=True)
    lung.attributes['wanted'] = 300
    send('ABB', 'goto', 'Docks', 5)
    for person in members('ABB'):
        if person.attributes['tasks'] and person.attributes['tasks'][0]['type'] == 'goto':
            person.attributes['tasks'][0]['stay'] = 24
    skitter = by_cape('Skitter')
    if skitter is not None:
        suit_up(skitter, True)
        tasks.add(skitter, {'type': 'respond', 'loc': 'Docks', 'who': lung.identity, 'ttl': 40}, front=True)
    city.state['pending'] = city.state.get('pending', []) + [[city.now() + 60, 'undersiders_docks']]


def event_undersiders_docks(day):
    send('Undersiders', 'raid', 'Docks', 0)


def event_bank(day):
    city.post("Alarms at Brockton Bay Central Bank.", 'crime', loud=True)
    send('Undersiders', 'rob', 'Brockton Bay Central Bank', 0)


def event_arrivals(day):
    world.require('sim').arrivals()


def event_bombing(day):
    bakuda = by_cape('Bakuda')
    if bakuda is None or bakuda.attributes.get('jail') or not 5 <= day <= 21:
        return
    place = U.pick(['Lord Street Market', 'Boardwalk', 'Downtown', 'Lord Street', 'Weymouth Shopping Center',
                    'Winslow High', 'Docks Residential Fringe', 'Cargo Pier', 'Lord Street Bakery'])
    loc = city.LOC[place]
    city.tell_room(loc, "<red>The world goes white. Then the sound arrives.</>")
    city.post(f"A bomb went off at {place}. The ABB's tinker is claiming it.", 'crime', loud=True)
    city.count('bombings')
    bakuda.attributes['wanted'] = 400
    for person in list(city.people_in(loc)):
        if U.chance(0.2) and person.alive:
            combat.hurt(person, U.rng.randrange(10, 40), None, 'disaster')
    b = economy.biz(loc)
    if b:
        for good in b['stock']:
            b['stock'][good] = int(b['stock'][good] * 0.6)


def event_leviathan(day):
    city.post("ENDBRINGER SIRENS. Leviathan is making landfall at Brockton Bay. Civilians to shelters. "
              "All capes: truce is in effect.", 'cape', loud=True)
    city.state['truce'] = city.now() + 24 * 60
    monster = world.do_get_prefab_by_name('Citizen').instance()
    monster.attributes.update({
        'name': 'Leviathan', 'sex': 'm', 'age': 15, 'job': 'endbringer', 'home': 'Beach', 'work': '',
        'endbringer': True, 'fearless': True, 'faction': 'Endbringer', 'maxhp': 2500, 'hp': 2500,
        'leviathan': {'step': 0, 'wait': 0, 'left': 40},
        'cape': {'name': 'Leviathan', 'align': 'endbringer', 'lethal': True, 'costume': True, 'passive': True,
                 'look': 'thirty feet of grey-green muscle with four eyes and an afterimage of water'},
        'power': {'cls': 'Brute', 'rating': 12, 'theme': 'water', 'abilities': ['area'],
                  'passives': ['regen', 'fast', 'tough'], 'atk': 55, 'dfn': 36, 'mob': 9, 'hp': 0,
                  'desc': 'An Endbringer. Hydrokinesis on a scale that sinks coastlines.', 'drawback': '',
                  'tier': 'overpowered', 'classes': 'Endbringer'},
    })
    city.LOC['Beach'].adopt(monster)
    people.normalize(monster)
    for person in list(city.PEOPLE.values()):
        a = person.attributes
        if a.get('kind') != 'npc' or person is monster or a.get('jail'):
            continue
        if a['state'] == 'sleep':
            a['state'] = 'idle'
        if a.get('cape') and a.get('power') and not a['cape'].get('passive'):
            suit_up(person, True)
            tasks.add(person, {'type': 'raid', 'loc': 'Boardwalk', 'foe': 'Endbringer', 'ttl': 90, 'levi': True},
                      front=True)
        else:
            tasks.add(person, {'type': 'goto', 'loc': 'Endbringer Shelter', 'stay': 80, 'ttl': 120}, front=True)


def leviathan_think(monster):
    a = monster.attributes
    state = a['leviathan']
    loc = city.loc_of(monster)
    place = loc.attributes['name']
    state['left'] -= 1
    if state['left'] <= 0 or a['hp'] < a['maxhp'] * 0.4:
        city.post("Leviathan is retreating into the bay. It is over. Count the dead.", 'cape', loud=True)
        city.tell_room(loc, "<cyan>A golden figure hangs in the sky. Leviathan turns and is gone into the water.</>")
        combat.end(monster)
        city.PEOPLE.pop(monster.identity, None)
        monster.die()
        return
    # a wave over everything in the open
    for person in list(city.people_in(loc)):
        if person is not monster and person.alive and not person.attributes.get('ko') and U.chance(0.25):
            combat.hurt(person, U.rng.randrange(8, 30), monster, 'disaster')
    b = economy.biz(loc)
    if b:
        for good in b['stock']:
            b['stock'][good] = int(b['stock'][good] * 0.85)
    state['wait'] += 1
    if state['wait'] >= 3:
        state['wait'] = 0
        state['step'] = (state['step'] + 1) % len(LEVIATHAN_PATH)
        combat.end(monster)
        city.move(monster, LEVIATHAN_PATH[state['step']])
        place = LEVIATHAN_PATH[state['step']]
        city.post(f"Leviathan is at {place}.", 'cape', loud=True)
    # the defenders follow it
    for person in city.PEOPLE.values():
        queue = person.attributes.get('tasks')
        if queue and queue[0].get('levi'):
            queue[0]['loc'] = place


# day, hour, handler; None for day means every day
EVENTS = [
    (0, 22, 'lung'),
    (4, 12, 'bank'),
    (5, 8, 'arrivals'),
    (8, 8, 'arrivals'),
    (None, 13, 'bombing'),
    (35, 6, 'leviathan'),
]


def hourly():
    day, hour = city.day(), city.hour()
    done = city.state.setdefault('events_done', [])
    for when, at, name in EVENTS:
        key = f"{name}:{day}"
        if (when is None or when == day) and at == hour and key not in done:
            done.append(key)
            del done[:-40]
            globals()['event_' + name](day)
    pending = city.state.get('pending', [])
    for entry in list(pending):
        if entry[0] <= city.now():
            pending.remove(entry)
            globals()['event_' + entry[1]](day)
    if hour == 21:
        nightly()
