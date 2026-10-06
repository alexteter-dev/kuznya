"""economy: goods, businesses, prices, wages. Nothing here is scripted to a target: prices follow stock,
stock follows what workers actually made and haulers actually carried."""
U = world.require('util')
city = world.require('city')

GOODS = {
    'flour': {'base': 2.0},
    'bread': {'base': 5.0, 'food': 35},
    'fish': {'base': 6.0, 'food': 40},
    'meal': {'base': 9.0, 'food': 65},
    'beer': {'base': 4.0},
    'cloth': {'base': 6.0},
    'clothes': {'base': 30.0},
    'scrap': {'base': 3.0},
    'tools': {'base': 25.0},
    'medicine': {'base': 20.0},
    'drugs': {'base': 15.0},
}
FOODS = ['bread', 'fish', 'meal']
HAUL_CAPACITY = 60
HAUL_FEE = 0.5
WHOLESALE = 0.8     # shops buy from makers below the counter price; that margin is what pays shop staff
STATE_JOBS = {'student': 7, 'unemployed': 5, 'retired': 12, 'homemaker': 8}   # daily support from outside the city
RENT = {'Docks Tenements': 3, 'Trainyard': 0, "Captain's Hill": 12, 'Downtown Apartments': 8}


def biz(loc):
    return loc.attributes.get('biz')


def shops():
    return [loc for loc in city.LOC.values() if loc.attributes.get('biz')]


def init_biz(loc):
    b = loc.attributes['biz']
    b.setdefault('sells', [])
    b.setdefault('buys', [])
    b.setdefault('target', {})
    b.setdefault('stock', {})
    b.setdefault('price', {})
    b.setdefault('cost', {})
    b.setdefault('acc', {})
    b.setdefault('staff', [])
    b.setdefault('slots', {})
    b.setdefault('wage', 28)
    b.setdefault('cash', 400)
    b.setdefault('open', [8, 18])
    b.setdefault('sold', {})
    for good in set(b['sells']) | set(b['buys']):
        b['target'].setdefault(good, 40)
        b['stock'].setdefault(good, int(b['target'][good] * 0.7))
    for good in b['sells']:
        b['price'].setdefault(good, GOODS[good]['base'] * b.get('markup', 1.0))


def staff(loc):
    b = biz(loc)
    return [city.PEOPLE[i] for i in b['staff'] if i in city.PEOPLE]


def working(person):
    a = person.attributes
    return a.get('state') == 'work' and not a.get('ko') and 'fight' not in a


def open_now(loc):
    """A shop sells only while one of its people is actually behind the counter."""
    name = loc.attributes['name']
    return any(p.attributes.get('work') == name and working(p) for p in city.people_in(loc))


def price(loc, good):
    b = biz(loc)
    return round(b['price'].get(good, GOODS[good]['base']), 2)


def reprice(loc):
    """Hourly. Scarce goods get expensive, glutted goods get cheap; nobody sells below cost."""
    b = biz(loc)
    for good in b['sells']:
        base = GOODS[good]['base'] * b.get('markup', 1.0)
        target = b['target'].get(good, 40)
        stock = b['stock'].get(good, 0)
        wanted = base * (target / (stock + target * 0.1)) ** 0.7
        wanted = U.clamp(wanted, base * 0.8, base * 6)
        wanted = max(wanted, b['cost'].get(good, 0) * 1.2)
        old = b['price'].get(good, base)
        b['price'][good] = round(old + (wanted - old) * 0.35, 2)


def efficiency(loc, worker):
    a = worker.attributes
    b = biz(loc)
    value = a.get('skills', {}).get(a.get('job'), 0.3)
    if a.get('motivated'):
        value *= 1.2
    if a.get('hunger', 0) > 85:
        value *= 0.5
    if 'tools' in b['buys'] and b['stock'].get('tools', 0) < 1:
        value *= 0.6
    return value


def produce(loc, worker):
    """One worker, one tick of work."""
    b = biz(loc)
    kind = b.get('type')
    amount = b.get('rate', 0) * efficiency(loc, worker) / 6.0   # rate is per hour, six ticks an hour
    if amount <= 0:
        return
    if kind == 'import':
        # unload whatever the pier is shortest of
        good = min(b['makes'], key=lambda g: b['stock'].get(g, 0) / b['target'].get(g, 40))
        inputs = {}
    elif kind == 'make':
        good = b['output']
        inputs = b.get('inputs', {})
    else:
        return
    if b['stock'].get(good, 0) >= b['target'].get(good, 40) * 2:
        return
    b['acc'][good] = b['acc'].get(good, 0) + amount
    whole = int(b['acc'][good])
    if whole <= 0:
        return
    for needed, per_unit in inputs.items():
        whole = min(whole, int(b['stock'].get(needed, 0) // per_unit))
    if whole <= 0:
        b['acc'][good] = min(b['acc'][good], 1.0)
        return
    for needed, per_unit in inputs.items():
        b['stock'][needed] -= whole * per_unit
    b['acc'][good] -= whole
    b['stock'][good] = b['stock'].get(good, 0) + whole * b.get('yield', 1)
    city.count('made_' + good, whole * b.get('yield', 1))


def sell(loc, buyer, good, quantity):
    """A person buys from a shop. Returns how many units changed hands."""
    b = biz(loc)
    a = buyer.attributes
    unit = price(loc, good)
    quantity = min(quantity, int(b['stock'].get(good, 0)), int(a['money'] // unit) if unit > 0 else quantity)
    if quantity <= 0:
        return 0
    total = unit * quantity
    a['money'] -= total
    # part of an importer's takings leaves the city to pay for the cargo
    b['cash'] += total * (1 - b.get('outflow', 0))
    b['stock'][good] -= quantity
    a['inv'][good] = a['inv'].get(good, 0) + quantity
    b['sold'][good] = b['sold'].get(good, 0) + quantity
    return quantity


def buy_price(loc, good):
    return round(price(loc, good) * 0.55, 2) if good in biz(loc)['sells'] else round(GOODS[good]['base'] * 0.5, 2)


def buy(loc, seller, good, quantity):
    """A shop buys from a person (scavengers selling scrap, players selling loot)."""
    b = biz(loc)
    a = seller.attributes
    if good not in b['buys'] and good not in b['sells']:
        return 0, 0
    room = int(b['target'].get(good, 40) * 2 - b['stock'].get(good, 0))
    unit = buy_price(loc, good)
    quantity = min(quantity, a['inv'].get(good, 0), max(room, 0), int(max(b['cash'], 0) // unit) if unit else quantity)
    if quantity <= 0:
        return 0, 0
    a['inv'][good] -= quantity
    if a['inv'][good] <= 0:
        del a['inv'][good]
    a['money'] += unit * quantity
    b['cash'] -= unit * quantity
    b['stock'][good] = b['stock'].get(good, 0) + quantity
    return quantity, unit * quantity


def best_shop(person, goods, need_open=True):
    """Where to go for any of these goods: cheap, stocked, and not across the whole city."""
    here = city.where(person)
    best = None
    for loc in shops():
        b = biz(loc)
        if b.get('wholesale') or b.get('faction'):
            continue
        if need_open and not (open_now(loc) or U.in_hours(city.hour(), *b['open'])):
            continue
        for good in goods:
            if good in b['sells'] and b['stock'].get(good, 0) >= 1:
                value = GOODS[good].get('food', 30)
                score = price(loc, good) / value * (1 + 0.08 * city.distance(here, loc.attributes['name']))
                if best is None or score < best[0]:
                    best = (score, loc, good)
    return (best[1], best[2]) if best else (None, None)


def supplier(good, exclude):
    best = None
    for loc in shops():
        b = biz(loc)
        if loc.attributes['name'] == exclude:
            continue
        if b.get('output') == good or good in b.get('makes', []):
            stock = b['stock'].get(good, 0)
            if stock >= 5 and (best is None or stock > best[0]):
                best = (stock, loc)
    return best[1] if best else None


def restock():
    """Hourly: businesses short of something they need put an order on the haulers' board."""
    orders = city.state['orders']
    orders[:] = [o for o in orders if o.get('taken') or city.now() - o['t'] < 12 * 60]
    for loc in shops():
        b = biz(loc)
        name = loc.attributes['name']
        for good in b['buys']:
            target = b['target'].get(good, 40)
            stock = b['stock'].get(good, 0)
            pending = sum(o['qty'] for o in orders if o['dst'] == name and o['good'] == good)
            if stock + pending >= target * 0.8:
                continue
            source = supplier(good, name)
            if source is None:
                continue
            quantity = int(min(HAUL_CAPACITY, target * 1.2 - stock - pending))
            if quantity >= 3:
                city.state['order_id'] = city.state.get('order_id', 0) + 1
                orders.append({'id': city.state['order_id'], 'good': good, 'qty': quantity, 'dst': name,
                               'src': source.attributes['name'], 't': city.now(), 'taken': None})


def take_order(hauler):
    """The most urgent order on the board: whoever is closest to running out goes first."""
    best = None
    for order in city.state['orders']:
        if order.get('taken'):
            continue
        b = biz(city.LOC[order['dst']])
        urgency = b['stock'].get(order['good'], 0) / max(b['target'].get(order['good'], 40), 1)
        if best is None or urgency < best[0]:
            best = (urgency, order)
    if best is None:
        return None
    best[1]['taken'] = hauler.identity
    return best[1]


def drop_order(order_id):
    city.state['orders'][:] = [o for o in city.state['orders'] if o['id'] != order_id]


def load(order, hauler):
    source = city.LOC[order['src']]
    b = biz(source)
    quantity = int(min(order['qty'], b['stock'].get(order['good'], 0), HAUL_CAPACITY))
    if quantity <= 0:
        return 0
    b['stock'][order['good']] -= quantity
    inv = hauler.attributes['inv']
    inv[order['good']] = inv.get(order['good'], 0) + quantity
    order['loaded'] = quantity
    order['unit'] = round((price(source, order['good']) if order['good'] in b['sells']
                           else GOODS[order['good']]['base']) * WHOLESALE, 2)
    return quantity


def unload(order, hauler):
    """Goods arrive: the buyer pays the maker and the haulers' union."""
    source = biz(city.LOC[order['src']])
    target = biz(city.LOC[order['dst']])
    inv = hauler.attributes['inv']
    quantity = min(order.get('loaded', 0), inv.get(order['good'], 0))
    if quantity > 0:
        inv[order['good']] -= quantity
        if inv[order['good']] <= 0:
            del inv[order['good']]
        payment = order['unit'] * quantity
        fee = HAUL_FEE * quantity
        target['stock'][order['good']] = target['stock'].get(order['good'], 0) + quantity
        target['cash'] -= payment + fee
        source['cash'] += payment * (1 - source.get('outflow', 0))
        union = biz(city.LOC[hauler.attributes['work']]) if hauler.attributes.get('work') in city.LOC else None
        if union is not None:
            union['cash'] += fee
        old = target['cost'].get(order['good'], order['unit'])
        target['cost'][order['good']] = round(old * 0.5 + (order['unit'] + HAUL_FEE) * 0.5, 2)
        city.count('hauled', quantity)
    drop_order(order['id'])
    return quantity


# -- jobs
def vacancies():
    found = []
    for loc in shops():
        b = biz(loc)
        if b.get('faction'):
            continue
        people = staff(loc)
        for job, slots in b['slots'].items():
            filled = sum(1 for p in people if p.attributes.get('job') == job)
            if filled < slots:
                found.append((loc, job, slots - filled))
    return found


def hire(loc, person, job):
    a = person.attributes
    leave(person)
    b = biz(loc)
    a['job'] = job
    a['work'] = loc.attributes['name']
    a['unpaid'] = 0
    a.setdefault('skills', {}).setdefault(job, 0.3)
    people = staff(loc)
    a['shift'] = sum(1 for p in people if p.attributes.get('job') == job) % 2
    if person.identity not in b['staff']:
        b['staff'].append(person.identity)
    if not b.get('owner') and b.get('owned'):
        b['owner'] = person.identity


def leave(person):
    a = person.attributes
    work = a.get('work')
    if work in city.LOC and biz(city.LOC[work]):
        b = biz(city.LOC[work])
        if person.identity in b['staff']:
            b['staff'].remove(person.identity)
        if b.get('owner') == person.identity:
            b['owner'] = ''
    a['work'] = ''
    a['job'] = 'unemployed'


def shift_hours(person):
    """(start, end) of this person's working hours, or None."""
    a = person.attributes
    work = a.get('work')
    if work not in city.LOC:
        return None
    b = biz(city.LOC[work])
    if not b:
        return None
    start, end = b['open']
    length = (end - start) % 24 or 24
    if length <= 10:
        return start, end
    half = length // 2 + 1
    if a.get('shift', 0) == 0:
        return start, (start + half) % 24
    return (end - half) % 24, end


def payday():
    """18:00. Wages come out of the till; if the till is empty, people go unpaid."""
    for loc in shops():
        b = biz(loc)
        b['cash'] += b.get('income', 0)
        people = staff(loc)
        if not people:
            continue
        wage = b['wage']
        funded = b.get('funded') == 'state'
        share = wage if funded else U.clamp(b['cash'] / len(people), 0, wage)
        for person in people:
            a = person.attributes
            paid = share
            if a.get('kind') == 'player':
                paid = share * U.clamp(a.get('worked', 0) / 36.0, 0, 1)
                a['worked'] = 0
                if paid > 0:
                    person.send(f"<gold>Payday:</> {U.cash(paid)} from {loc.attributes['name']}.")
            a['money'] += paid
            if not funded:
                b['cash'] -= paid
            a['unpaid'] = 0 if paid >= wage * 0.5 or a.get('kind') == 'player' else a.get('unpaid', 0) + 1
        owner = city.PEOPLE.get(b.get('owner') or '')
        reserve = wage * len(people) * 4 + 300
        if b['cash'] > reserve and not funded:
            profit = (b['cash'] - reserve) * 0.3
            b['cash'] -= profit
            if owner is not None:
                owner.attributes['money'] += profit
            else:
                # nobody owns the place: a good season is shared out as a bonus
                for person in people:
                    person.attributes['money'] += profit / len(people)
    for person in city.PEOPLE.values():
        a = person.attributes
        if a.get('job') in STATE_JOBS and a.get('kind') == 'npc':
            a['money'] += STATE_JOBS[a['job']]


def rent():
    for person in city.PEOPLE.values():
        a = person.attributes
        due = RENT.get(a.get('home'), 6)
        # bills, taxes and money sent to family elsewhere: savings do not pile up forever
        due += max(0, a['money'] - 200) * 0.05
        a['money'] = max(0, a['money'] - due)


def daily():
    for loc in shops():
        b = biz(loc)
        if 'tools' in b['buys'] and staff(loc):
            # tools wear out with use
            b['stock']['tools'] = max(0, b['stock'].get('tools', 0) - max(1, len(staff(loc)) // 4))
        b['sold'] = {}
    for person in list(city.PEOPLE.values()):
        a = person.attributes
        job = a.get('job')
        if a.get('work') and a.get('worked_today'):
            skills = a.setdefault('skills', {})
            skills[job] = round(min(1.0, skills.get(job, 0.3) + 0.04), 2)
        a['worked_yesterday'] = bool(a.get('worked_today'))
        a['worked_today'] = False
        a['motivated'] = False
        a['clothes_age'] = a.get('clothes_age', 0) + 1
        if a.get('unpaid', 0) >= 3 and a.get('kind') == 'npc' and not a.get('cape'):
            city.post(f"{a['name']} walked out of {a['work']} after three days without pay.")
            leave(person)


def market_report():
    """Average price and total stock of each good across the city's shops."""
    report = {}
    for good in GOODS:
        prices = []
        stock = 0
        for loc in shops():
            b = biz(loc)
            if good in b['sells'] and not b.get('faction'):
                stock += b['stock'].get(good, 0)
                prices.append(price(loc, good))
        if prices:
            report[good] = {'price': round(sum(prices) / len(prices), 2), 'stock': int(stock),
                            'base': GOODS[good]['base']}
    return report


def money_supply():
    people = sum(p.attributes.get('money', 0) for p in city.PEOPLE.values())
    business = sum(biz(loc)['cash'] for loc in shops())
    return people, business
