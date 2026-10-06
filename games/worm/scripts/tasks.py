"""tasks: every resident carries a queue of things to do, and the one at the head is done first.

A task is a plain dict so it is saved with the world. Residents get a new one every morning out of their
job and their relationships: talk to the boss, ask for work, collect protection money, carry a parcel.
Some of those tasks are aimed at players.
"""
U = world.require('util')
city = world.require('city')
economy = world.require('economy')
combat = world.require('combat')
capes = world.require('capes')
speech = world.require('speech')

BOSS_JOBS = {'executive', 'mayor', 'PRT director', 'principal', 'union rep', 'gang boss', 'pit boss', 'owner'}


def add(person, task, front=False):
    queue = person.attributes['tasks']
    task.setdefault('ttl', 40)
    if front:
        queue.insert(0, task)
    else:
        queue.append(task)


def done(person):
    queue = person.attributes['tasks']
    if queue:
        queue.pop(0)


def describe(task):
    """One line for players who look into someone's head (Thinkers) or at their own list."""
    kind = task['type']
    target = city.PEOPLE.get(task.get('to', ''))
    who = city.dname(target) if target is not None else 'someone'
    if kind == 'talk':
        return {'job': f"ask {who} for work", 'order': f"give {who} the day's instructions",
                'report': f"report to {who}", 'gossip': f"catch up with {who}",
                'collect': f"collect protection money from {who}", 'recruit': f"recruit {who}",
                'allowance': f"give {who} lunch money"}.get(task['topic'], f"talk to {who}")
    if kind == 'deliver':
        return "deliver goods"
    if kind == 'buy':
        return f"buy {task['good']}"
    if kind == 'respond':
        return f"respond to trouble at {task['loc']}"
    if kind == 'raid':
        return f"hit {task['loc']}"
    if kind == 'rob':
        return f"rob {task['loc']}"
    if kind == 'goto':
        return f"go to {task['loc']}"
    return kind


# -- morning: where the day's first task comes from
def morning(person):
    a = person.attributes
    if len(a['tasks']) >= 2 or a.get('cape', {}).get('passive'):
        return
    job = a['job']
    work = city.LOC.get(a['work'])
    b = economy.biz(work) if work is not None else None

    for player in city.players():
        if player_errand(person, player):
            return

    if job == 'unemployed' and not a.get('cape'):
        openings = economy.vacancies()
        if openings:
            loc, opening, count = min(openings, key=lambda v: city.distance(city.where(person), v[0].attributes['name'])
                                      + U.rng.random() * 3)
            people = economy.staff(loc)
            if people:
                add(person, {'type': 'talk', 'to': U.pick(people).identity, 'topic': 'job',
                             'loc': loc.attributes['name'], 'job': opening})
            else:
                add(person, {'type': 'goto', 'loc': loc.attributes['name'], 'act': 'apply', 'job': opening})
            return
    if b is not None and b.get('faction') and job.endswith('enforcer') and U.chance(0.5):
        target = capes.protection_target(b['faction'])
        if target is not None:
            add(person, {'type': 'talk', 'to': target.identity, 'topic': 'collect', 'gang': b['faction']})
            return
    if b is not None and b.get('faction') in ('ABB', 'Empire 88', 'Merchants') and U.chance(0.04):
        target = capes.recruit_target(person)
        if target is not None:
            add(person, {'type': 'talk', 'to': target.identity, 'topic': 'recruit', 'gang': b['faction']})
            return
    if b is not None:
        people = [p for p in economy.staff(work) if p is not person]
        boss = city.PEOPLE.get(b.get('owner') or '')
        if (job in BOSS_JOBS or b.get('owner') == person.identity) and people:
            add(person, {'type': 'talk', 'to': U.pick(people).identity, 'topic': 'order'})
            return
        if boss is not None and boss is not person and U.chance(0.3):
            add(person, {'type': 'talk', 'to': boss.identity, 'topic': 'report'})
            return
    for child_id in a.get('children', []):
        if child_id in city.PEOPLE and a['money'] > 30:
            add(person, {'type': 'talk', 'to': child_id, 'topic': 'allowance'})
            return
    if a.get('clothes_age', 0) > (14 if a['money'] > 200 else 30) and a['money'] > 70:
        a['clothes_age'] = 0
        add(person, {'type': 'buy', 'good': 'clothes'})
        return
    friends = [f for f in a['friends'] if f in city.PEOPLE]
    if friends:
        add(person, {'type': 'talk', 'to': U.pick(friends), 'topic': 'gossip'})


def player_errand(person, player):
    """Residents with a reason to seek out a player. At most one seeker per player per day."""
    a = person.attributes
    pa = player.attributes
    if pa.get('sought') == city.day() or a.get('cape', {}).get('passive') or a['age'] < 16:
        return False
    topic = None
    extra = {}
    work = city.LOC.get(a['work'])
    b = economy.biz(work) if work is not None else None
    if pa.get('work') and pa['work'] == a['work'] and b and (b.get('owner') == person.identity or U.chance(0.3)):
        topic = 'boss'
    elif pa.get('power') and not pa.get('faction') and a['job'] == 'PRT officer' and pa.get('rep', 0) >= 0:
        topic = 'recruit_hero'
    elif pa.get('power') and not pa.get('faction') and a.get('cape', {}).get('name') == 'Tattletale':
        topic = 'undersiders'
    elif not pa.get('work') and a['job'] == 'union rep':
        openings = [v for v in economy.vacancies()]
        if openings:
            loc, opening, count = U.pick(openings)
            topic, extra = 'offer_job', {'place': loc.attributes['name'], 'job': opening}
    elif b and b.get('faction') and not pa.get('faction') and pa.get('money', 0) < 30 and U.chance(0.4) \
            and b['faction'] in ('ABB', 'Empire 88', 'Merchants'):
        topic, extra = 'recruit_gang', {'gang': b['faction']}
    elif a['job'] not in ('unemployed', 'student') and not a.get('faction') and a['money'] > 60 and U.chance(0.04):
        friends = [city.PEOPLE[f] for f in a['friends'] if f in city.PEOPLE]
        if friends:
            friend = U.pick(friends)
            topic = 'parcel'
            extra = {'target': friend.identity, 'reward': U.rng.randrange(12, 30)}
    if topic is None:
        return False
    pa['sought'] = city.day()
    add(person, {'type': 'talk', 'to': player.identity, 'topic': topic, 'data': extra, 'ttl': 60})
    return True


# -- doing the task at the head of the queue. Returns True when it used up the tick.
def work_on(person):
    a = person.attributes
    task = a['tasks'][0]
    task['ttl'] = task.get('ttl', 40) - 1
    if task['ttl'] <= 0:
        if task['type'] == 'deliver':
            abandon_delivery(person, task)
        done(person)
        return False
    handler = HANDLERS.get(task['type'])
    if handler is None:
        done(person)
        return False
    return handler(person, task)


def do_talk(person, task):
    a = person.attributes
    target = city.PEOPLE.get(task['to'])
    if target is None or not target.alive:
        done(person)
        return False
    ta = target.attributes
    if ta.get('kind') == 'player' and target.connection is None:
        done(person)
        return False
    if ta.get('ko') or ta.get('jail') or ta.get('away') or 'fight' in ta or ta.get('state') == 'sleep':
        return False     # not now; get on with the day and try again later
    there = city.where(target)
    if there is None:
        return False
    if city.where(person) != there:
        city.step_toward(person, there)
        a['state'] = 'travel'
        return True
    a['state'] = 'idle'
    converse(person, target, task)
    done(person)
    return True


def converse(person, target, task):
    a = person.attributes
    ta = target.attributes
    topic = task['topic']
    data = task.get('data', {})

    if ta.get('kind') == 'player':
        return converse_player(person, target, topic, data)

    if topic == 'job':
        loc = city.LOC[task['loc']]
        open_now = any(v[0] is loc and v[1] == task['job'] for v in economy.vacancies())
        speech.say(person, target, 'job_ask')
        if open_now:
            speech.say(target, person, 'job_yes')
            economy.hire(loc, person, task['job'])
            city.post(f"{a['name']} was taken on at {task['loc']}: {task['job']}.", 'jobs')
        else:
            speech.say(target, person, 'job_no')
    elif topic == 'order':
        speech.say(person, target, 'order')
        ta['motivated'] = True
    elif topic == 'report':
        speech.say(person, target, 'report')
        a['mood'] = U.clamp(a['mood'] + 3, 0, 100)
    elif topic == 'allowance':
        speech.say(person, target, 'allowance')
        gift = min(10, a['money'])
        a['money'] -= gift
        ta['money'] += gift
    elif topic == 'collect':
        capes.collect(person, target, task['gang'])
    elif topic == 'recruit':
        capes.recruit(person, target, task['gang'])
    else:
        speech.chat(person, target)
        for one, other in ((a, target), (ta, person)):
            if other.identity not in one['friends'] and len(one['friends']) < 6 and U.chance(0.3):
                one['friends'].append(other.identity)
        a['mood'] = U.clamp(a['mood'] + 4, 0, 100)


def converse_player(person, player, topic, data):
    """A resident who came looking for a player. Offers land in the player's offer list."""
    pa = player.attributes
    offers = pa.setdefault('offers', [])
    if topic == 'boss':
        speech.say(person, player, 'boss_good' if pa.get('worked_yesterday') else 'boss_bad')
        if pa.get('worked_yesterday'):
            pa['money'] += 5
            player.send("<gray>They press a five into your hand.</>")
    elif topic == 'offer_job':
        speech.say(person, player, 'offer_job', **data)
    elif topic == 'parcel':
        friend = city.PEOPLE.get(data['target'])
        if friend is None:
            return
        speech.say(person, player, 'parcel', target=friend.attributes['name'],
                   place=city.where(friend) or friend.attributes['home'], reward=U.cash(data['reward']))
        offers.append({'type': 'parcel', 'from': person.identity, 'from_name': person.attributes['name'],
                       'to': friend.identity, 'to_name': friend.attributes['name'], 'reward': data['reward'],
                       'until': city.now() + 24 * 60})
        player.send("<gray>Type</> <cyan>accept</> <gray>to take the parcel, or ignore it.</>")
    elif topic in ('recruit_hero', 'undersiders'):
        speech.say(person, player, topic)
        pa.setdefault('invites', [])
        invite = 'Wards' if topic == 'recruit_hero' and pa.get('age', 25) < 18 else \
            'Protectorate' if topic == 'recruit_hero' else 'Undersiders'
        if invite not in pa['invites']:
            pa['invites'].append(invite)
    elif topic == 'recruit_gang':
        speech.say(person, player, 'recruit_gang', **data)
        pa.setdefault('invites', [])
        if data['gang'] not in pa['invites']:
            pa['invites'].append(data['gang'])
    else:
        speech.say(person, player, 'welcome')


def abandon_delivery(person, task):
    """A hauler who gives up leaves the order on the board for someone else."""
    for order in city.state['orders']:
        if order['id'] == task['order']:
            if order.get('loaded'):
                economy.unload(order, person) if city.where(person) == order['dst'] else None
            order['taken'] = None
            order['t'] = city.now()


def do_deliver(person, task):
    a = person.attributes
    order = next((o for o in city.state['orders'] if o['id'] == task['order']), None)
    if order is None:
        done(person)
        return False
    a['state'] = 'work'
    a['worked_today'] = True
    if task['stage'] == 0:
        if city.step_toward(person, order['src']):
            if economy.load(order, person) > 0:
                task['stage'] = 1
            else:
                task['wait'] += 1
                if task['wait'] > 6:
                    economy.drop_order(order['id'])
                    done(person)
        return True
    if city.step_toward(person, order['dst']):
        economy.unload(order, person)
        done(person)
    return True


def do_buy(person, task):
    a = person.attributes
    shop, good = economy.best_shop(person, [task['good']])
    if shop is None:
        return False
    if not city.step_toward(person, shop.attributes['name']):
        a['state'] = 'travel'
        return True
    if economy.open_now(shop):
        if economy.sell(shop, person, good, 1):
            if good == 'clothes':
                a['inv'].pop('clothes', None)
            done(person)
        else:
            done(person)
    return True


def do_goto(person, task):
    a = person.attributes
    if not city.step_toward(person, task['loc']):
        a['state'] = 'travel'
        return True
    if task.get('act') == 'apply':
        loc = city.LOC[task['loc']]
        if any(v[0] is loc and v[1] == task['job'] for v in economy.vacancies()):
            economy.hire(loc, person, task['job'])
            city.post(f"{a['name']} was taken on at {task['loc']}: {task['job']}.", 'jobs')
        done(person)
        return True
    task['stay'] = task.get('stay', 0) - 1
    if task['stay'] <= 0:
        done(person)
    return True


HANDLERS = {
    'talk': do_talk,
    'deliver': do_deliver,
    'buy': do_buy,
    'goto': do_goto,
    'respond': lambda person, task: capes.do_respond(person, task),
    'raid': lambda person, task: capes.do_raid(person, task),
    'rob': lambda person, task: capes.do_rob(person, task),
}
