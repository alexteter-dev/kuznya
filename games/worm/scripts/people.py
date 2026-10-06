"""people: what a resident is and how one decides what to do next.

Every resident runs think() once per tick. Order of concerns: stay alive, do the task at the head of the
queue, eat, do cape work, sleep, do the job, and only then relax.
"""
U = world.require('util')
city = world.require('city')
economy = world.require('economy')
tasks = world.require('tasks')
combat = world.require('combat')
capes = world.require('capes')
names = world.require('names')
speech = world.require('speech')

ARMED = {'police officer': (8, 2), 'PRT officer': (9, 3), 'ABB enforcer': (7, 1), 'Empire enforcer': (7, 1),
         'mercenary': (10, 3), 'dealer': (5, 0), 'guard': (7, 2), 'bouncer': (6, 1), 'pit fighter': (7, 1)}
PATROLS = {
    'police officer': ['Downtown', 'Lord Street', 'Docks Residential Fringe', 'Boardwalk', 'Lord Street Market',
                       'Docks', 'The Towers', "Captain's Hill"],
    'PRT officer': ['Downtown', 'PRT HQ', 'Lord Street', 'Boardwalk', 'Downtown'],
}
BARS = ["Somer's Rock", 'Palanquin', "Fugly Bob's"]
CASINOS = ['Ruby Dreams Casino', 'ABB Gambling Den', 'Empire Fighting Pits']
OUTDOORS = ['Boardwalk', 'Beach', 'Lord Street Market', 'Hillside Mall', 'Weymouth Shopping Center',
            'Central Library']
MONEY = {'unemployed': 15, 'student': 15, 'executive': 600, 'mayor': 400, 'doctor': 200, 'lawyer': 250}


def normalize(person):
    """Fill in everything a resident needs. Safe to call on a half-described character."""
    a = person.attributes
    a['kind'] = a.get('kind') if a.get('kind') in ('npc', 'player') else 'npc'
    a.setdefault('sex', U.pick('mf'))
    a.setdefault('age', U.rng.randrange(19, 60))
    a.setdefault('job', 'unemployed')
    a.setdefault('work', '')
    a.setdefault('home', 'Docks Tenements')
    a.setdefault('maxhp', 30)
    a.setdefault('hp', a['maxhp'])
    a.setdefault('hunger', U.rng.randrange(5, 40))
    a.setdefault('energy', U.rng.randrange(70, 100))
    a.setdefault('money', MONEY.get(a['job'], 60) * U.rng.uniform(0.5, 1.5))
    a.setdefault('inv', {})
    a.setdefault('tasks', [])
    a.setdefault('friends', [])
    a.setdefault('state', 'idle')
    a.setdefault('skills', {a['job']: round(U.rng.uniform(0.7, 1.0), 2)})
    a.setdefault('unpaid', 0)
    a.setdefault('mood', 50)
    a.setdefault('clothes_age', U.rng.randrange(0, 25))
    a.setdefault('traits', {})
    for trait in ('brave', 'greed', 'kind', 'violent', 'social'):
        a['traits'].setdefault(trait, round(U.rng.betavariate(2, 2), 2))
    a['ready'] = True
    city.PEOPLE[person.identity] = person
    return person


def spawn(job, work, home, **extra):
    """A generated resident, created from the Citizen prefab."""
    person = world.do_get_prefab_by_name('Citizen').instance()
    name, sex = names.person(extra.get('sex'))
    person.attributes.update({'name': name, 'sex': sex, 'job': job, 'work': work, 'home': home})
    person.attributes.update(extra)
    city.LOC[home].adopt(person)
    normalize(person)
    return person


def awake(person):
    a = person.attributes
    return a.get('state') != 'sleep' and not a.get('ko') and not a.get('jail')


def job_label(person):
    """The job a stranger would guess. A hero out of costume just works for the PRT."""
    job = person.attributes.get('job', '')
    return {'hero': 'PRT employee', 'gang boss': 'businessman', 'pit boss': 'promoter'}.get(job, job)


def describe(person):
    """What you see when you look at someone."""
    a = person.attributes
    cape = a.get('cape')
    if cape and cape.get('costume'):
        look = cape.get('look', 'a parahuman in costume')
        return f"{city.tag(person)} <gray>({look if len(look) < 60 else look[:57] + '...'})</>"
    extra = job_label(person)
    if a.get('state') == 'sleep':
        extra += ', asleep'
    if a.get('ko'):
        extra += ', unconscious'
    if a.get('hp', 1) < a.get('maxhp', 1) * 0.5:
        extra += ', hurt'
    return f"{city.tag(person)} <gray>({extra})</>"


# -- death
def kill(person, cause, killer=None):
    a = person.attributes
    name = a['name']
    cape = a.get('cape')
    loc = city.loc_of(person)
    place = loc.attributes['name'] if loc else 'the city'
    by = f" by {city.dname(killer)}" if killer is not None else ''
    if cape and cape.get('costume'):
        city.post(f"{cape['name']} is dead: {cause}{by} at {place}.", 'cape', loud=True)
    else:
        city.post(f"{name} ({a.get('job', 'resident')}) died: {cause}{by} at {place}.", 'death')
    city.tell_room(loc, f"<red>{city.tag(person)} is dead.</>", exclude=(person,))
    city.count('deaths')
    city.count('deaths_' + cause.split()[0])
    if killer is not None and a.get('money', 0) > 0 and killer.attributes.get('kind') in ('npc', 'player'):
        killer.attributes['money'] = killer.attributes.get('money', 0) + a['money']
    for other_id in a.get('friends', []):
        other = city.PEOPLE.get(other_id)
        if other is not None:
            other.attributes['mood'] = U.clamp(other.attributes.get('mood', 50) - 20, 0, 100)
            if person.identity in other.attributes.get('friends', []):
                other.attributes['friends'].remove(person.identity)
    economy.leave(person)
    combat.forget(person)
    city.PEOPLE.pop(person.identity, None)
    if a.get('kind') == 'player':
        person.trigger('player_died', cause)
        return
    person.die()


# -- needs
def needs(person):
    a = person.attributes
    asleep = a['state'] == 'sleep'
    a['hunger'] = min(110, a['hunger'] + (0.3 if asleep else 0.6))
    a['energy'] = U.clamp(a['energy'] + (1.5 if asleep else -0.55), 0, 100)
    if a.get('wanted', 0) > 0:
        a['wanted'] -= 1
    if a['hunger'] >= 100:
        a['hp'] -= 0.15
        a['starving'] = a.get('starving', 0) + 1
        if a['hp'] <= 0:
            kill(person, 'starved')
            return False
        if a['starving'] % 30 == 0:
            combat.maybe_trigger(person, 'starving')
    else:
        a['starving'] = 0
        if a['hp'] < a['maxhp'] and a['hunger'] < 75:
            a['hp'] = min(a['maxhp'], a['hp'] + (0.3 if asleep else 0.08))
    return True


def eat_from_pack(person):
    a = person.attributes
    for good in ('meal', 'fish', 'bread'):
        if a['inv'].get(good, 0) >= 1:
            a['inv'][good] -= 1
            if a['inv'][good] <= 0:
                del a['inv'][good]
            a['hunger'] = max(0, a['hunger'] - economy.GOODS[good]['food'])
            return good
    return None


def eat(person):
    """True if the tick was spent on getting fed."""
    a = person.attributes
    if eat_from_pack(person):
        return True
    wanted = ['meal'] if a['money'] > 120 and U.chance(0.7) else economy.FOODS
    shop, good = economy.best_shop(person, wanted)
    if shop is not None and a['money'] >= economy.price(shop, good):
        if not city.step_toward(person, shop.attributes['name']):
            a['state'] = 'travel'
            return True
        if economy.open_now(shop):
            spare = 2 if a['money'] > economy.price(shop, good) * 6 else 1
            if economy.sell(shop, person, good, spare) > 0:
                eat_from_pack(person)
            return True
        a['state'] = 'idle'
        # the counter is unmanned: wait a little, then try somewhere else or go without
        a['wait_shop'] = a.get('wait_shop', 0) + 1
        if a['wait_shop'] < 6:
            return True
        a['wait_shop'] = 0
    if a['hunger'] > 80:
        return desperate(person)
    return False


def desperate(person):
    """No money or no food to buy. People do what people do."""
    a = person.attributes
    loc = city.loc_of(person)
    traits = a['traits']
    if traits['violent'] > 0.75 and U.chance(0.1) and loc is not None:
        victims = [p for p in city.people_in(loc) if p is not person and awake(p)
                   and p.attributes.get('money', 0) > 15 and 'fight' not in p.attributes
                   and not p.attributes.get('cape')]
        if victims:
            capes.mug(person, U.pick(victims))
            return True
    if loc is not None:
        givers = [p for p in city.people_in(loc) if p is not person and awake(p)
                  and p.attributes.get('kind') == 'npc' and p.attributes['money'] > 60
                  and p.attributes['traits']['kind'] > 0.6]
        if givers and U.chance(0.2):
            giver = U.pick(givers)
            giver.attributes['money'] -= 6
            a['money'] += 6
            speech.say(giver, person, 'charity')
            return True
    # last resort: a line off the pier
    if not city.step_toward(person, 'Fishing Pier'):
        a['state'] = 'travel'
        return True
    a['state'] = 'idle'
    if U.chance(0.12):
        a['inv']['fish'] = a['inv'].get('fish', 0) + 1
    return True


# -- sleep and work
def on_shift(person, hour):
    hours = economy.shift_hours(person)
    return bool(hours) and U.in_hours(hour, *hours)


def go_sleep(person):
    a = person.attributes
    if city.step_toward(person, a['home'] if a['home'] in city.LOC else 'Docks Tenements'):
        a['state'] = 'sleep'
    else:
        a['state'] = 'travel'


def do_work(person):
    a = person.attributes
    job = a['job']
    if job == 'hauler' and not any(t['type'] == 'deliver' for t in a['tasks']):
        # haulers take the next order from wherever the last one left them
        order = economy.take_order(person)
        if order is not None:
            a['state'] = 'work'
            tasks.add(person, {'type': 'deliver', 'order': order['id'], 'stage': 0, 'wait': 0}, front=True)
            return
    if not city.step_toward(person, a['work']):
        a['state'] = 'travel'
        return
    a['state'] = 'work'
    a['worked_today'] = True
    loc = city.LOC[a['work']]
    if job in ('doctor', 'nurse'):
        treat(person, loc)
    elif job in PATROLS:
        patrol(person, PATROLS[job])
    elif job == 'dealer':
        deal(person, loc)
        economy.produce(loc, person)
    else:
        economy.produce(loc, person)


def treat(doctor, loc):
    b = economy.biz(loc)
    patients = [p for p in city.people_in(loc) if p.attributes.get('work') != loc.attributes['name']
                and p.attributes['hp'] < p.attributes['maxhp'] * 0.9]
    if not patients or b['stock'].get('medicine', 0) < 1:
        return
    patient = min(patients, key=lambda p: p.attributes['hp'])
    pa = patient.attributes
    pa['hp'] = min(pa['maxhp'], pa['hp'] + (5 if doctor.attributes['job'] == 'doctor' else 3))
    if pa.get('ko'):
        pa['ko'] = max(1, pa['ko'] - 3)
    b['acc']['medicine_used'] = b['acc'].get('medicine_used', 0) + 0.12
    if b['acc']['medicine_used'] >= 1:
        b['acc']['medicine_used'] -= 1
        b['stock']['medicine'] -= 1
    fee = min(pa.get('money', 0), 1.5)
    pa['money'] -= fee
    b['cash'] += fee


def patrol(person, beat):
    a = person.attributes
    a['state'] = 'work'
    a['beat_wait'] = a.get('beat_wait', 0) + 1
    if a['beat_wait'] < 3:
        return
    a['beat_wait'] = 0
    a['beat'] = (a.get('beat', U.rng.randrange(len(beat))) + 1) % len(beat)
    city.step_toward(person, beat[a['beat']])


def deal(dealer, loc):
    """Dealers sell the gang's product to anyone hooked who wanders by."""
    b = economy.biz(loc)
    if b['stock'].get('drugs', 0) < 1:
        return
    for buyer in city.people_in(loc):
        ba = buyer.attributes
        if ba.get('addict') and ba.get('fix_day') != city.day() and ba['money'] >= economy.price(loc, 'drugs'):
            if economy.sell(loc, buyer, 'drugs', 1):
                ba['inv'].pop('drugs', None)
                ba['fix_day'] = city.day()
                ba['mood'] = U.clamp(ba['mood'] + 15, 0, 100)
                return


def hustle(person):
    """The unemployed pick through the Boat Graveyard and sell what they find."""
    a = person.attributes
    if a['inv'].get('scrap', 0) >= 6:
        if city.step_toward(person, 'Docks Machine Shop'):
            sold, earned = economy.buy(city.LOC['Docks Machine Shop'], person, 'scrap', a['inv']['scrap'])
            if not sold:
                a['inv'].pop('scrap', None)
        return
    if not city.step_toward(person, 'Boat Graveyard'):
        a['state'] = 'travel'
        return
    a['state'] = 'idle'
    if U.chance(0.18):
        a['inv']['scrap'] = a['inv'].get('scrap', 0) + 1


# -- free time
def leisure(person, hour):
    a = person.attributes
    hang = a.get('hang')
    if not hang or hang['until'] <= city.now():
        traits = a['traits']
        options = [(a['home'], 3)]
        if U.in_hours(hour, 17, 24):
            options += [(bar, 2.5 * traits['social']) for bar in BARS if bar != 'Palanquin' or hour >= 20]
            if a['money'] > 120:
                options += [(casino, 2 * traits['greed']) for casino in CASINOS]
        elif U.in_hours(hour, 8, 20):
            options += [(place, 1.2 * traits['social']) for place in OUTDOORS]
        if a.get('addict') and a.get('fix_day') != city.day():
            options.append(("Merchants' Hideout", 6))
        place = U.wpick(options)
        hang = a['hang'] = {'loc': place if place in city.LOC else a['home'],
                            'until': city.now() + U.rng.randrange(60, 200)}
    if not city.step_toward(person, hang['loc']):
        a['state'] = 'travel'
        return
    a['state'] = 'idle'
    enjoy(person, city.LOC[hang['loc']])


def enjoy(person, loc):
    a = person.attributes
    b = economy.biz(loc)
    if b and economy.open_now(loc):
        if 'beer' in b['sells'] and a['money'] > 30 and U.chance(0.15):
            if economy.sell(loc, person, 'beer', 1):
                a['inv'].pop('beer', None)
                a['mood'] = U.clamp(a['mood'] + 4, 0, 100)
        if b.get('type') in ('retail', 'make') and b['sells'] and a['money'] > 120 and U.chance(0.08):
            # people with money in their pocket spend it: odds and ends, a treat, something for the house
            spent = (a['money'] - 100) * 0.04
            a['money'] -= spent
            b['cash'] += spent
            a['mood'] = U.clamp(a['mood'] + 2, 0, 100)
        if b.get('type') == 'casino' and a['money'] > 40 and U.chance(0.2):
            stake = min(a['money'] * 0.1, 25)
            won = U.chance(0.4)
            a['money'] += stake if won else -stake
            b['cash'] += -stake if won else stake
            a['mood'] = U.clamp(a['mood'] + (6 if won else -3), 0, 100)
    if U.chance(0.05):
        others = [p for p in city.people_in(loc) if p is not person and awake(p) and 'fight' not in p.attributes
                  and p.attributes.get('state') in ('idle', 'work')]
        if others:
            other = U.pick(others)
            speech.chat(person, other)
            if other.attributes.get('kind') == 'npc' and U.chance(0.2) \
                    and other.identity not in a['friends'] and len(a['friends']) < 6:
                a['friends'].append(other.identity)


# -- the decision
def think(person):
    a = person.attributes
    if a.get('endbringer'):
        capes.leviathan_think(person)
        return
    if a.get('jail'):
        a['jail'] -= 1
        if a['jail'] <= 0:
            capes.release(person)
        return
    if a.get('ko'):
        a['ko'] -= 1
        if a['ko'] <= 0:
            a.pop('ko')
            a['hp'] = max(a['hp'], 4)
            a['state'] = 'idle'
        return
    if not needs(person):
        return
    if 'fight' in a:
        return
    hour = city.hour()

    if a['state'] == 'sleep':
        if a['energy'] >= 98 or a['hunger'] > 92 or (on_shift(person, hour) and a['energy'] > 40) \
                or (a.get('cape') and capes.on_duty(person, hour) and a['energy'] > 40):
            a['state'] = 'idle'
        else:
            return

    if a.get('morning') != city.day() and U.in_hours(hour, 6, 13):
        a['morning'] = city.day()
        tasks.morning(person)

    # emergencies come before anything on the list; the wounded still have to eat
    if a['hunger'] > 80 and eat(person):
        return
    if a['hp'] < a['maxhp'] * 0.45 and not a.get('cape', {}).get('costume'):
        if city.step_toward(person, 'Brockton General Hospital'):
            a['state'] = 'patient'
        return
    if a.get('state') == 'patient':
        if a['hp'] < a['maxhp'] * 0.85 and a['hunger'] < 80:
            return
        a['state'] = 'idle'

    # the task at the head of the queue is done first
    if a['tasks'] and tasks.work_on(person):
        return
    if a['hunger'] > 50 and eat(person):
        return
    if a.get('cape') and capes.think(person, hour):
        return
    if a['energy'] < 25 or (U.in_hours(hour, 23, 6) and a['energy'] < 80 and not on_shift(person, hour)):
        go_sleep(person)
        return
    if a['work'] and on_shift(person, hour):
        do_work(person)
        return
    if a['job'] == 'unemployed' and U.in_hours(hour, 9, 16) and not a.get('cape'):
        hustle(person)
        return
    if a.get('faction') and capes.gang_time(person, hour):
        return
    leisure(person, hour)
