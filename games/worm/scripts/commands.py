"""commands: everything a player can type."""
import hashlib
import json
import secrets

U = world.require('util')
city = world.require('city')
economy = world.require('economy')
people = world.require('people')
combat = world.require('combat')
capes = world.require('capes')
powers = world.require('powers')
tasks = world.require('tasks')
speech = world.require('speech')

START = 'Brockton Bay Bus Station'
HELP = """<gold>Getting around</>   look (l) · go <place or number> · where <place> · map · time
<gold>People</>           who · examine <name> · talk <name> · say <text> · give <name> <amount|item>
<gold>Living</>           status · inv · eat [item] · buy [n] <item> · sell [n] <item> · prices · market · rest
<gold>Work</>             jobs · apply · work · stop · quit · tasks · accept
<gold>Trouble</>          attack <name> · flee · pay · steal <item> · call · join <group>
<gold>Powers</>           power · power <ability> [target or place]
<gold>The city</>         news · help"""
INTRO = """<gold>BROCKTON BAY</> <gray>- April 2011</>
An unofficial fan game set in the world of <cyan>Worm</> by Wildbow.

You are nobody in particular. You got off a bus in a dying port city run by gangs and guarded by people
in costumes. Everyone here has a job, somewhere to be and someone to talk to; the bread costs what it
costs because of who showed up for work this morning. Find a job. Eat. Stay off the Docks after dark.
<gray>They say powers come to people on the worst day of their lives.</>
"""


def hud(player):
    a = player.attributes
    if a.get('stage') != 'play':
        return
    power = a.get('power')
    player.send('@@hud ' + json.dumps({
        'name': a['name'], 'hp': int(a['hp']), 'maxhp': int(a['maxhp']), 'hunger': int(a['hunger']),
        'money': int(a['money']), 'time': city.stamp(), 'place': city.where(player) or '',
        'job': a.get('job', ''), 'power': powers.label(power) if power else '',
        'fight': 'fight' in a, 'night': city.is_night(),
    }))


# -- arriving
def connected(player):
    a = player.attributes
    if a.get('stage') == 'play':
        player.send(f"<green>Welcome back, {a['name']}.</>")
        look(player)
        hud(player)
        return
    a['stage'] = 'name'
    player.send(INTRO)
    player.send("<gold>What is your name?</> <gray>(new name to arrive in the city, your old name to return)</>")


def limbo():
    return world.do_get_object_by_name('Offline Players')


def digest(password, salt):
    return hashlib.sha256((salt + password).encode('utf-8')).hexdigest()


def login(player, text):
    a = player.attributes
    text = text.strip()
    if a['stage'] == 'name':
        name = ' '.join(word.capitalize() for word in text.split())[:24]
        if len(name) < 2 or not all(ch.isalpha() or ch in " '-" for ch in name):
            player.send("<gray>Letters only, two or more.</>")
            return
        online = [p for p in city.players() if p.attributes.get('name') == name and p is not player]
        taken = [p for p in city.PEOPLE.values() if p.attributes.get('name') == name
                 and p.attributes.get('kind') == 'npc']
        if online or taken:
            player.send("<gray>Someone by that name is already in the city. Another?</>")
            return
        a['name'] = name
        stored = [c for c in limbo().children if c.attributes.get('name') == name]
        a['stage'] = 'password' if stored else 'newpass'
        player.send("<gold>Password?</>" if stored else
                    f"<gold>{name}.</> Choose a password so you can come back to this life later:")
        return
    if a['stage'] == 'newpass':
        if len(text) < 3:
            player.send("<gray>A little longer.</>")
            return
        a['salt'] = secrets.token_hex(8)
        a['pw'] = digest(text, a['salt'])
        arrive(player)
        return
    if a['stage'] == 'password':
        stored = [c for c in limbo().children if c.attributes.get('name') == a['name']]
        if not stored or digest(text, stored[0].attributes.get('salt', '')) != stored[0].attributes.get('pw'):
            a['stage'] = 'name'
            player.send("<red>That is not it.</> <gray>What is your name?</>")
            return
        character = stored[0]
        place = character.attributes.get('last_place', START)
        city.LOC[place if place in city.LOC else START].adopt(character)
        city.PEOPLE[character.identity] = character
        a['stage'] = 'gone'
        player.transfer_user_connection_to(character)
        player.die()


def arrive(player):
    a = player.attributes
    a.update({'kind': 'player', 'stage': 'play', 'job': 'unemployed', 'work': '', 'home': 'Docks Tenements',
              'money': 60, 'inv': {'bread': 2}, 'hunger': 30, 'age': 20, 'rep': 0})
    city.LOC[START].adopt(player)
    people.normalize(player)
    city.post(f"A newcomer got off the bus: {a['name']}.", 'city')
    player.send(f"\n<green>You step off the bus with {U.cash(a['money'])}, two loaves of bread and nowhere to be.</> "
                "<gray>Type</> <cyan>help</><gray>.</>\n")
    look(player)
    hud(player)


def left(player):
    """The connection dropped: the character waits in limbo with everything it had."""
    a = player.attributes
    if a.get('stage') != 'play':
        if a.get('stage') != 'gone':
            player.die()
        return
    combat.end(player)
    a['last_place'] = city.where(player) or START
    a.pop('threat', None)
    city.PEOPLE.pop(player.identity, None)
    limbo().adopt(player)


# -- looking
def exits_of(player, loc):
    a = player.attributes
    shown = []
    for name in loc.attributes.get('exits', []):
        target = city.LOC[name].attributes
        if target.get('hidden') and target.get('faction') != a.get('faction') \
                and name not in a.get('places', []):
            continue
        shown.append(name)
    return shown


def look(player):
    loc = city.loc_of(player)
    if loc is None:
        return
    la = loc.attributes
    turf = f" <gray>· {la['territory']} turf</>" if la.get('territory') else ''
    lines = [f"\n<gold>{la['name']}</> <gray>({la.get('district', '')})</>{turf}", la.get('desc', '')]
    b = economy.biz(loc)
    if b and b['sells']:
        if economy.open_now(loc):
            goods = ', '.join(f"{g} {U.cash(economy.price(loc, g))}" for g in b['sells'] if b['stock'].get(g, 0) >= 1)
            lines.append(f"<green>Open.</> {('For sale: ' + goods) if goods else 'The shelves are bare.'}")
        else:
            lines.append("<gray>Nobody is serving.</>")
    here = [p for p in city.people_in(loc) if p is not player and not combat.hidden(p)]
    here.sort(key=lambda p: (p.attributes.get('kind') != 'player', not (p.attributes.get('cape') or {}).get('costume')))
    if here:
        shown = [people.describe(p) for p in here[:12]]
        more = f" <gray>and {len(here) - 12} others</>" if len(here) > 12 else ''
        lines.append("Here: " + ', '.join(shown) + more)
    exits = exits_of(player, loc)
    lines.append("<gray>Exits:</> " + '  '.join(f"<cyan>{i + 1}</> {name}" for i, name in enumerate(exits)))
    player.send('\n'.join(line for line in lines if line))


def find_person(player, query, anyone=False):
    loc = city.loc_of(player)
    here = [p for p in city.people_in(loc) if p is not player and (anyone or not combat.hidden(p))]
    labels = []
    for p in here:
        labels.append(city.dname(p))
    found = U.match(query, labels)
    if not found:
        # a job title works too: "talk baker"
        found = U.match(query, [p.attributes.get('job', '') for p in here])
    if not found:
        player.send(f"<gray>Nobody like '{player.safe(query)}' here.</>")
        return None
    return here[found[0]]


# -- commands
def cmd_go(player, arg):
    a = player.attributes
    loc = city.loc_of(player)
    exits = exits_of(player, loc)
    if not arg:
        player.send("<gray>Go where?</>")
        return
    if arg.isdigit() and 1 <= int(arg) <= len(exits):
        destination = exits[int(arg) - 1]
    else:
        found = U.match(arg, exits)
        if not found:
            names = list(city.LOC)
            far = U.match(arg, names)
            if far and (city.where(player), names[far[0]]) in city.NEXT:
                destination = city.NEXT[(city.where(player), names[far[0]])]
                if destination not in exits:
                    player.send("<gray>You do not know a way there.</>")
                    return
                player.send(f"<gray>Toward {names[far[0]]}: through {destination}.</>")
            else:
                player.send("<gray>No such way out. 'look' lists the exits.</>")
                return
        else:
            destination = exits[found[0]]
    if 'fight' in a:
        player.send("<red>You are in a fight.</> <gray>'flee' to run.</>")
        return
    threat = a.pop('threat', None)
    if threat:
        mugger = city.PEOPLE.get(threat['by'])
        if mugger is not None and city.loc_of(mugger) is loc and U.chance(0.5):
            player.send("<red>You turn to leave and they grab you.</>")
            combat.attack(mugger, player, 'mug')
            return
    a['state'] = 'idle'
    city.move(player, destination)


def cmd_where(player, arg):
    names = list(city.LOC)
    found = U.match(arg, names) if arg else []
    if not found:
        player.send("<gray>No such place. 'map' lists what you know.</>")
        return
    target = names[found[0]]
    path = city.route(city.where(player), target)
    player.send(f"<gold>{target}</>: " + (' → '.join(path) if path else 'you are here.'))


def cmd_map(player, arg):
    districts = {}
    for name, loc in city.LOC.items():
        if loc.attributes.get('hidden') and name not in player.attributes.get('places', []) \
                and loc.attributes.get('faction') != player.attributes.get('faction'):
            continue
        districts.setdefault(loc.attributes.get('district', ''), []).append(name)
    lines = [f"<gold>{district}</>: {', '.join(sorted(places))}" for district, places in sorted(districts.items())]
    player.send('\n'.join(lines))


def cmd_who(player, arg):
    online = city.players()
    player.send("<gold>In the city:</> " + ', '.join(f"{p.attributes['name']} ({city.where(p)})" for p in online)
                + f"\n<gray>{len(city.PEOPLE) - len(online)} residents.</>")


def cmd_time(player, arg):
    player.send(f"<gold>{city.stamp()}</> <gray>· day {city.day() + 1}</>")


def cmd_examine(player, arg):
    target = find_person(player, arg) if arg else None
    if target is None:
        return
    ta = target.attributes
    lines = [people.describe(target)]
    if ta.get('desc') and not (ta.get('cape') or {}).get('costume'):
        lines.append(ta['desc'])
    ratio = ta['hp'] / ta['maxhp']
    lines.append("<gray>" + ("Unhurt." if ratio > 0.9 else "Bruised." if ratio > 0.6 else "Badly hurt." if ratio > 0.3
                             else "Barely standing.") + "</>")
    if player.attributes.get('known', {}).get(target.identity) and ta.get('cape'):
        lines.append(f"<magenta>You know that {ta['name']} is {ta['cape']['name']}.</>")
    player.send('\n'.join(lines))


def cmd_say(player, arg):
    if not arg:
        return
    loc = city.loc_of(player)
    city.tell_room(loc, f"{city.tag(player)} says: <cyan>\"{player.safe(arg)}\"</>")


def cmd_talk(player, arg):
    target = find_person(player, arg) if arg else None
    if target is None:
        return
    a, ta = player.attributes, target.attributes
    if not people.awake(target):
        player.send("<gray>They are in no state to talk.</>")
        return
    # a parcel for this person?
    for quest in list(a.get('quests', [])):
        if quest['type'] == 'parcel' and quest['to'] == target.identity:
            a['quests'].remove(quest)
            a['money'] += quest['reward']
            a['rep'] = a.get('rep', 0) + 1
            a['inv'].pop('parcel', None)
            speech.say(target, player, 'thanks')
            player.send(f"<gold>Parcel delivered: +{U.cash(quest['reward'])}.</>")
            if target.identity not in a['friends']:
                a['friends'].append(target.identity)
            return
    cape = ta.get('cape') or {}
    if cape.get('costume'):
        text = {'hero': "Stay safe, citizen. If you see trouble, 'call' it in.",
                'villain': "You have about three seconds to stop looking at me."}.get(cape.get('align'), "...")
    else:
        bits = [f"I'm {ta['name'].split()[0]}. {U.cap(people.job_label(target) or 'unemployed')}"
                + (f" at {ta['work']}." if ta.get('work') else ".")]
        if ta['tasks']:
            bits.append(f"Can't stop long - I need to {tasks.describe(ta['tasks'][0])}.")
        if ta.get('unpaid', 0) >= 1:
            bits.append("Haven't been paid properly in days.")
        if ta['hunger'] > 70:
            bits.append("I haven't eaten today.")
        report = economy.market_report()
        dear = [g for g in economy.FOODS if g in report and report[g]['price'] > report[g]['base'] * 1.6]
        if dear:
            bits.append(f"And have you seen the price of {dear[0]}?")
        elif U.chance(0.5):
            bits.append(speech.news_item())
        text = ' '.join(bits)
    player.send(f"{city.tag(target)} says: <cyan>\"{text}\"</>")


def cmd_status(player, arg):
    a = player.attributes
    lines = [f"<gold>{a['name']}</> <gray>· {a.get('job', 'unemployed')}"
             + (f" at {a['work']}" if a.get('work') else '') + (f" · {a['faction']}" if a.get('faction') else '') + "</>",
             f"Health  [{U.bar(a['hp'], a['maxhp'])}] {a['hp']:.0f}/{a['maxhp']:.0f}",
             f"Hunger  [{U.bar(a['hunger'], 100)}] " + ('starving' if a['hunger'] >= 100 else 'hungry' if a['hunger'] > 60 else 'fine'),
             f"Money   {U.cash(a['money'])}   Home: {a['home']}"]
    atk, dfn, mob = combat.stats(player)
    lines.append(f"<gray>Attack {atk:.0f} · Defence {dfn:.0f} · Mobility {mob:.0f} · Reputation {a.get('rep', 0)}</>")
    if a.get('wanted', 0) > 0:
        lines.append("<red>The law is looking for you.</>")
    if a.get('power'):
        lines.append("Power: " + powers.label(a['power']) + " <gray>('power' for details)</>")
    player.send('\n'.join(lines))


def cmd_inv(player, arg):
    inv = player.attributes['inv']
    player.send("<gold>You carry:</> " + (', '.join(f"{n} {g}" for g, n in inv.items()) or 'nothing')
                + f" <gray>· {U.cash(player.attributes['money'])}</>")


def cmd_eat(player, arg):
    a = player.attributes
    choices = [g for g in economy.FOODS if a['inv'].get(g, 0) >= 1]
    if arg:
        choices = [g for g in choices if g.startswith(arg)]
    if not choices:
        player.send("<gray>You have nothing to eat.</>")
        return
    good = choices[0]
    a['inv'][good] -= 1
    if a['inv'][good] <= 0:
        del a['inv'][good]
    a['hunger'] = max(0, a['hunger'] - economy.GOODS[good]['food'])
    player.send(f"You eat the {good}.")


def amount_and_item(arg):
    parts = arg.split()
    if parts and parts[0].isdigit():
        return max(1, int(parts[0])), ' '.join(parts[1:])
    return 1, arg


def shop_here(player, need_open=True):
    loc = city.loc_of(player)
    b = economy.biz(loc)
    if not b or not (b['sells'] or b['buys']):
        player.send("<gray>Nothing is bought or sold here.</>")
        return None, None
    if need_open and not economy.open_now(loc):
        player.send("<gray>Nobody is serving.</>")
        return None, None
    return loc, b


def cmd_prices(player, arg):
    loc, b = shop_here(player, need_open=False)
    if loc is None:
        return
    lines = [f"<gold>{loc.attributes['name']}</>" + ('' if economy.open_now(loc) else ' <gray>(nobody serving)</>')]
    for good in b['sells']:
        lines.append(f"  {good:<9} {U.cash(economy.price(loc, good)):>5}   <gray>{int(b['stock'].get(good, 0))} in stock</>")
    for good in b['buys']:
        lines.append(f"  <gray>buys {good} at {U.cash(economy.buy_price(loc, good))}</>")
    player.send('\n'.join(lines))


def cmd_market(player, arg):
    report = economy.market_report()
    lines = ["<gold>City prices</> <gray>(average · usual · total stock)</>"]
    for good, info in report.items():
        ratio = info['price'] / info['base']
        colour = 'red' if ratio > 1.6 else 'green' if ratio < 0.85 else 'gray'
        lines.append(f"  {good:<9} <{colour}>{U.cash(info['price']):>5}</>  <gray>{U.cash(info['base']):>5}  {info['stock']:>5}</>")
    player.send('\n'.join(lines))


def cmd_buy(player, arg):
    loc, b = shop_here(player)
    if loc is None:
        return
    quantity, item = amount_and_item(arg)
    found = U.match(item, b['sells']) if item else []
    if not found:
        player.send("<gray>They do not sell that. 'prices' shows what they have.</>")
        return
    good = b['sells'][found[0]]
    got = economy.sell(loc, player, good, quantity)
    if got:
        player.send(f"You buy {got} {good} for {U.cash(got * economy.price(loc, good))}.")
    else:
        player.send("<gray>Out of stock, or you cannot afford it.</>")


def cmd_sell(player, arg):
    loc, b = shop_here(player)
    if loc is None:
        return
    quantity, item = amount_and_item(arg)
    inv = list(player.attributes['inv'])
    found = U.match(item, inv) if item else []
    if not found:
        player.send("<gray>You do not have that.</>")
        return
    sold, earned = economy.buy(loc, player, inv[found[0]], quantity)
    player.send(f"You sell {sold} {inv[found[0]]} for {U.cash(earned)}." if sold else "<gray>They are not buying that.</>")


def cmd_give(player, arg):
    parts = arg.rsplit(' ', 1)
    if len(parts) < 2:
        player.send("<gray>give <name> <amount or item></>")
        return
    target = find_person(player, parts[0])
    if target is None:
        return
    a, ta = player.attributes, target.attributes
    if parts[1].isdigit():
        amount = min(int(parts[1]), int(a['money']))
        a['money'] -= amount
        ta['money'] += amount
        player.send(f"You give {city.tag(target)} {U.cash(amount)}.")
        if amount >= 5 and ta.get('kind') == 'npc':
            speech.say(target, player, 'thanks')
            a['rep'] = a.get('rep', 0) + 1
    else:
        found = U.match(parts[1], list(a['inv']))
        if not found:
            player.send("<gray>You do not have that.</>")
            return
        good = list(a['inv'])[found[0]]
        a['inv'][good] -= 1
        if a['inv'][good] <= 0:
            del a['inv'][good]
        ta['inv'][good] = ta['inv'].get(good, 0) + 1
        player.send(f"You give {city.tag(target)} one {good}.")
        target.send(f"{city.tag(player)} gives you one {good}.")
        if ta.get('kind') == 'npc' and good in economy.FOODS:
            speech.say(target, player, 'thanks')
            a['rep'] = a.get('rep', 0) + 1


def cmd_rest(player, arg):
    player.attributes['state'] = 'rest'
    player.send("<gray>You find somewhere to sit and let time pass. Anything you type gets you up again.</>")


def cmd_jobs(player, arg):
    openings = economy.vacancies()
    if not openings:
        player.send("<gray>Nobody is hiring. Somebody will be, the way this city goes.</>")
        return
    lines = ["<gold>Hiring</> <gray>(go there and 'apply')</>"]
    for loc, job, count in sorted(openings, key=lambda v: city.distance(city.where(player), v[0].attributes['name'])):
        b = economy.biz(loc)
        lines.append(f"  {job:<16} {loc.attributes['name']:<28} <gray>{U.cash(b['wage'])}/day · hours {b['open'][0]}-{b['open'][1]}</>")
    player.send('\n'.join(lines[:16]))


def cmd_apply(player, arg):
    loc = city.loc_of(player)
    openings = [v for v in economy.vacancies() if v[0] is loc]
    if not openings:
        player.send("<gray>There is no opening here. 'jobs' lists who is hiring.</>")
        return
    job = openings[0][1]
    economy.hire(loc, player, job)
    player.attributes['shift'] = 0
    b = economy.biz(loc)
    player.send(f"<green>You are taken on as a {job} at {loc.attributes['name']}.</> "
                f"<gray>{U.cash(b['wage'])} a day for a full shift, paid at 18:00. Come here during opening hours "
                f"({b['open'][0]}-{b['open'][1]}) and type 'work'. You start unskilled.</>")


def cmd_work(player, arg):
    a = player.attributes
    if not a.get('work'):
        player.send("<gray>You have no job. 'jobs' lists who is hiring.</>")
        return
    if city.where(player) != a['work']:
        player.send(f"<gray>Your job is at {a['work']}.</>")
        return
    b = economy.biz(city.loc_of(player))
    if not U.in_hours(city.hour(), *b['open']):
        player.send(f"<gray>Closed. Hours are {b['open'][0]}-{b['open'][1]}.</>")
        return
    a['state'] = 'work'
    player.send("<green>You get to work.</> <gray>'stop' when you have had enough.</>")


def cmd_stop(player, arg):
    player.attributes['state'] = 'idle'
    player.send("<gray>You stop.</>")


def cmd_quit(player, arg):
    if not player.attributes.get('work'):
        player.send("<gray>You have no job to quit.</>")
        return
    economy.leave(player)
    player.send("You quit.")


def cmd_tasks(player, arg):
    a = player.attributes
    a['offers'] = [o for o in a.get('offers', []) if o['until'] > city.now()]
    lines = []
    for quest in a.get('quests', []):
        target = city.PEOPLE.get(quest['to'])
        place = city.where(target) if target is not None else 'nowhere - they are gone'
        lines.append(f"  Take the parcel to <cyan>{quest['to_name']}</> <gray>(now at {place})</> for {U.cash(quest['reward'])}: 'talk' to them.")
    for offer in a['offers']:
        lines.append(f"  <gray>Offer from {offer['from_name']}: a parcel for {offer['to_name']}, {U.cash(offer['reward'])}. 'accept'.</>")
    for invite in a.get('invites', []):
        lines.append(f"  <gray>You could 'join {invite}'.</>")
    if a.get('work'):
        lines.append(f"  <gray>Your job: {a['job']} at {a['work']}.</>")
    player.send("<gold>Things to do</>\n" + ('\n'.join(lines) if lines else "  <gray>Nothing. Nobody needs you. 'jobs'?</>"))


def cmd_accept(player, arg):
    a = player.attributes
    offers = [o for o in a.get('offers', []) if o['until'] > city.now()]
    if not offers:
        player.send("<gray>Nobody has offered you anything.</>")
        return
    offer = offers[0]
    a['offers'].remove(offer)
    a.setdefault('quests', []).append(offer)
    a['inv']['parcel'] = a['inv'].get('parcel', 0) + 1
    player.send(f"<green>You take the parcel for {offer['to_name']}.</> <gray>'tasks' shows where they are.</>")


def cmd_attack(player, arg):
    a = player.attributes
    threat = a.pop('threat', None)
    target = find_person(player, arg) if arg else city.PEOPLE.get((threat or {}).get('by', ''))
    if target is None:
        if not arg:
            player.send("<gray>Attack whom?</>")
        return
    if not combat.attack(player, target, 'defence' if threat else 'assault'):
        player.send("<gray>You cannot fight them right now.</>")
        return
    player.send(f"<red>You go for {city.tag(target)}.</>")
    if not threat and target.attributes.get('kind') == 'npc' and not target.attributes.get('wanted'):
        a['rep'] = a.get('rep', 0) - 3


def cmd_flee(player, arg):
    a = player.attributes
    if 'fight' in a:
        a['fight']['intent'] = ('flee',)
        player.send("<gray>You look for a way out...</>")
    elif a.get('threat'):
        exits = exits_of(player, city.loc_of(player))
        cmd_go(player, U.pick(exits))
    else:
        player.send("<gray>Nothing to run from.</>")


def cmd_pay(player, arg):
    a = player.attributes
    threat = a.pop('threat', None)
    mugger = city.PEOPLE.get((threat or {}).get('by', ''))
    if mugger is None:
        player.send("<gray>Nobody is demanding anything.</>")
        return
    taken = a['money'] * 0.5
    a['money'] -= taken
    mugger.attributes['money'] += taken
    player.send(f"<red>You hand over {U.cash(taken)}.</> They shove you aside and walk off.")


def cmd_call(player, arg):
    loc = city.loc_of(player)
    culprits = [p for p in city.people_in(loc) if p.attributes.get('wanted', 0) > 0 and p is not player]
    threat = city.PEOPLE.get((player.attributes.get('threat') or {}).get('by', ''))
    if threat is not None:
        threat.attributes['wanted'] = max(threat.attributes.get('wanted', 0), 60)
        culprits.append(threat)
    if not culprits:
        player.send("<gray>You have nothing to report.</>")
        return
    culprit = culprits[0]
    capes.incident(loc.attributes['name'], culprit, 'reported', bool(culprit.attributes.get('power')))
    player.attributes['rep'] = player.attributes.get('rep', 0) + 1
    player.send("<cyan>You call it in. Someone is on the way - probably.</>")


def cmd_steal(player, arg):
    a = player.attributes
    loc, b = shop_here(player, need_open=False)
    if loc is None:
        return
    found = U.match(arg, b['sells']) if arg else []
    if not found or b['stock'].get(b['sells'][found[0]], 0) < 1:
        player.send("<gray>Nothing like that to take.</>")
        return
    good = b['sells'][found[0]]
    staff = [p for p in city.people_in(loc) if p.attributes.get('work') == loc.attributes['name'] and people.awake(p)]
    if combat.hidden(player) or not staff or U.chance(0.45):
        b['stock'][good] -= 1
        a['inv'][good] = a['inv'].get(good, 0) + 1
        player.send(f"You pocket one {good}. Nobody notices.")
        return
    a['wanted'] = max(a.get('wanted', 0), 60)
    a['rep'] = a.get('rep', 0) - 2
    city.tell_room(loc, f"<red>{city.tag(staff[0])} shouts: \"Thief!\"</>")
    capes.incident(loc.attributes['name'], player, 'theft', False)


def cmd_join(player, arg):
    a = player.attributes
    invites = a.get('invites', [])
    found = U.match(arg, invites) if arg else []
    if not found:
        player.send("<gray>Nobody has invited you to anything like that.</>" if arg else
                    "<gray>Invitations: " + (', '.join(invites) or 'none') + "</>")
        return
    group = invites[found[0]]
    a['invites'] = []
    a['faction'] = group
    if group in capes.GANG_HQ:
        capes.join_gang(player, group)
        a['places'] = a.get('places', []) + [capes.GANG_HQ[group][0]]
        a['rep'] = a.get('rep', 0) - 5
    elif group in ('Wards', 'Protectorate'):
        loc = city.LOC['PRT HQ']
        b = economy.biz(loc)
        b['slots']['hero'] = b['slots'].get('hero', 0) + 1
        economy.hire(loc, player, 'hero')
        a['places'] = a.get('places', []) + ['Wards Base']
        a['rep'] = a.get('rep', 0) + 5
    else:
        a['places'] = a.get('places', []) + ['Redmond Welding']
    city.post(f"{a['name']} is with the {group} now.", 'cape' if a.get('power') else 'gang')
    player.send(f"<green>You are with the {group}.</> <gray>They will not turn on you, and their enemies are yours.</>")


def cmd_news(player, arg):
    news = city.state['news'][-14:]
    lines = ["<gold>Parahumans Online · Brockton Bay</>"]
    for item in news:
        colour = {'cape': 'magenta', 'crime': 'red', 'death': 'red'}.get(item['kind'], 'gray')
        lines.append(f"  <gray>{city.stamp(item['t'])}</> <{colour}>{item['text']}</>")
    player.send('\n'.join(lines))


def cmd_power(player, arg):
    a = player.attributes
    power = a.get('power')
    if not power:
        player.send("<gray>You have no power. Be glad; you know what it costs.</>")
        return
    if not arg:
        player.send(powers.sheet(power))
        return
    parts = arg.split(' ', 1)
    found = U.match(parts[0], power['abilities'])
    if not found:
        player.send("<gray>Your power does not do that. 'power' lists what it does.</>")
        return
    ability = power['abilities'][found[0]]
    rest = parts[1].strip() if len(parts) > 1 else ''
    rating = power['rating']
    loc = city.loc_of(player)

    if 'fight' in a:
        target = find_person(player, rest) if rest else None
        if ability in a['fight']['cd']:
            player.send(f"<gray>Not yet: {a['fight']['cd'][ability]} more moments.</>")
            return
        a['fight']['intent'] = ('power', ability, target.identity if target else None)
        player.send(f"<magenta>You reach for your power: {ability}.</>")
        return

    wait = a.get('power_ready', 0) - city.now()
    if wait > 0 and ability != 'insight':
        player.send(f"<gray>You are spent. Give it {wait} minutes.</>")
        return
    if ability in ('blink', 'fly'):
        names = list(city.LOC)
        found = U.match(rest, names) if rest else []
        if not found:
            player.send("<gray>To where?</>")
            return
        target = names[found[0]]
        reach = 99 if ability == 'fly' else 1 + rating // 2
        if city.distance(city.where(player), target) > reach:
            player.send("<gray>Too far for your power.</>")
            return
        city.tell_room(loc, f"<magenta>{city.tag(player)} is suddenly gone.</>", exclude=(player,))
        city.move(player, target, quiet=True)
        a['power_ready'] = city.now() + 20
    elif ability == 'heal':
        target = find_person(player, rest) if rest else player
        if target is None:
            return
        ta = target.attributes
        healed = min(ta['maxhp'] - ta['hp'], rating * 6)
        ta['hp'] += healed
        ta.pop('ko', None) if healed > 0 else None
        player.send(f"<magenta>You mend {'yourself' if target is player else city.tag(target)}: +{healed:.0f}.</>")
        if target is not player and healed > 3:
            a['rep'] = a.get('rep', 0) + 2
        a['power_ready'] = city.now() + 30
    elif ability == 'insight':
        target = find_person(player, rest, anyone=True) if rest else None
        if target is None:
            if not rest:
                hidden = [n for n in loc.attributes.get('exits', []) if city.LOC[n].attributes.get('hidden')]
                capes_here = [p for p in city.people_in(loc) if p.attributes.get('power') and p is not player]
                a['places'] = list(set(a.get('places', []) + hidden))
                player.send("<magenta>You let the details add up.</> "
                            + (f"There is a way to {U.listing(hidden)} here that people are not meant to notice. " if hidden else '')
                            + (f"Parahumans here: {U.listing(p.attributes['name'] for p in capes_here)}." if capes_here
                               else "No parahumans here but you."))
            return
        ta = target.attributes
        a.setdefault('known', {})[target.identity] = True
        lines = [f"<magenta>You read {ta['name']}.</> {U.cap(ta.get('job', ''))}, {ta['age']}, {U.cash(ta['money'])} on them, "
                 f"health {ta['hp']:.0f}/{ta['maxhp']:.0f}."]
        if ta.get('cape'):
            lines.append(f"This is <gold>{ta['cape']['name']}</> ({ta.get('faction') or 'independent'}).")
        if ta.get('power'):
            lines.append(f"{powers.label(ta['power'])}: {ta['power']['desc']}")
        if ta['tasks']:
            lines.append(f"Right now they mean to {tasks.describe(ta['tasks'][0])}.")
        player.send('\n'.join(lines))
    elif ability == 'craft':
        inv = a['inv']
        gear = a.setdefault('gear', {'atk': 0, 'dfn': 0})
        if gear['atk'] + gear['dfn'] >= rating * 2:
            player.send("<gray>You have built everything your specialty allows.</>")
            return
        if inv.get('tools', 0) >= 1:
            inv['tools'] -= 1
        elif inv.get('scrap', 0) >= 3:
            inv['scrap'] -= 3
        else:
            player.send("<gray>You need a set of tools or three scrap to build with.</>")
            return
        for good in ('tools', 'scrap'):
            if good in inv and inv[good] <= 0:
                del inv[good]
        which = 'atk' if gear['atk'] <= gear['dfn'] else 'dfn'
        gear[which] += 2
        player.send(f"<magenta>Hours vanish. When you look up you have built something:</> +2 {'attack' if which == 'atk' else 'defence'}.")
        a['power_ready'] = city.now() + 60
    elif ability == 'vanish':
        a['hidden_until'] = city.now() + 60
        player.send("<magenta>Eyes slide off you.</> <gray>For an hour nobody will notice what you do.</>")
        a['power_ready'] = city.now() + 120
    elif ability == 'command':
        target = find_person(player, rest) if rest else None
        if target is None:
            return
        ta = target.attributes
        if ta.get('power') or ta.get('kind') != 'npc':
            player.send("<gray>Their will is not that easy to take.</>")
            return
        taken = ta['money'] * 0.4
        ta['money'] -= taken
        a['money'] += taken
        a['rep'] = a.get('rep', 0) - 3
        a['wanted'] = max(a.get('wanted', 0), 30)
        player.send(f"<magenta>{ta['name']} hands you {U.cash(taken)} with empty eyes.</>")
        a['power_ready'] = city.now() + 60
    elif ability == 'swarm':
        lines = ["<magenta>You spread your senses out through a thousand small bodies.</>"]
        for name in loc.attributes.get('exits', []):
            there = city.people_in(city.LOC[name])
            notable = [city.dname(p) for p in there if (p.attributes.get('cape') or {}).get('costume')
                       or p.attributes.get('wanted', 0) > 0]
            lines.append(f"  {name}: {len(there)} people" + (f" - {U.listing(notable)}" if notable else ''))
        player.send('\n'.join(lines))
    else:
        player.send("<gray>That only means something in a fight.</>")


COMMANDS = {
    'help': lambda player, arg: player.send(HELP), 'look': lambda player, arg: look(player),
    'go': cmd_go, 'where': cmd_where, 'map': cmd_map, 'who': cmd_who, 'time': cmd_time, 'examine': cmd_examine,
    'say': cmd_say, 'talk': cmd_talk, 'status': cmd_status, 'inv': cmd_inv, 'eat': cmd_eat, 'buy': cmd_buy,
    'sell': cmd_sell, 'prices': cmd_prices, 'market': cmd_market, 'give': cmd_give, 'rest': cmd_rest,
    'jobs': cmd_jobs, 'apply': cmd_apply, 'work': cmd_work, 'stop': cmd_stop, 'quit': cmd_quit,
    'tasks': cmd_tasks, 'accept': cmd_accept, 'attack': cmd_attack, 'flee': cmd_flee, 'pay': cmd_pay,
    'call': cmd_call, 'steal': cmd_steal, 'join': cmd_join, 'news': cmd_news, 'power': cmd_power,
}
ALIASES = {'l': 'look', 'x': 'examine', 'i': 'inv', 'inventory': 'inv', 'me': 'status', 'st': 'status',
           'kill': 'attack', 'hit': 'attack', 'run': 'flee', 'walk': 'go', 'move': 'go', 'list': 'prices',
           'offers': 'tasks', 'sleep': 'rest', 'wait': 'rest', '?': 'help', 'p': 'power', 'n': 'news'}


def handle(player, text):
    a = player.attributes
    text = text.strip()[:200]
    if a.get('stage') != 'play':
        if a.get('stage') in ('name', 'newpass', 'password'):
            login(player, text)
        return
    if not text:
        return
    if a.get('ko'):
        player.send("<gray>You are unconscious.</>")
        return
    if a.get('jail'):
        player.send(f"<gray>You are in a holding cell. About {a['jail'] * 10} more minutes.</>")
        return
    word, _, arg = text.partition(' ')
    word = word.lower()
    arg = arg.strip()
    if word.isdigit():
        word, arg = 'go', word
    word = ALIASES.get(word, word)
    if word not in COMMANDS:
        found = U.match(word, list(COMMANDS))
        if len(found) == 1:
            word = list(COMMANDS)[found[0]]
        else:
            # maybe it is a place: "docks" means "go docks"
            if U.match(text, exits_of(player, city.loc_of(player))):
                word, arg = 'go', text
            else:
                player.send("<gray>You are not sure how to do that. 'help' lists what you can do.</>")
                return
    if a.get('state') in ('rest', 'work') and word not in ('work', 'rest', 'status', 'inv', 'look', 'time', 'news',
                                                         'market', 'prices', 'tasks', 'help', 'who', 'eat', 'say'):
        a['state'] = 'idle'
    COMMANDS[word](player, arg)
    hud(player)


# -- the passing of time for a player
def tick(player):
    a = player.attributes
    if a.get('stage') != 'play':
        return
    if a.get('jail'):
        a['jail'] -= 1
        if a['jail'] <= 0:
            capes.release(player)
            look(player)
        hud(player)
        return
    if a.get('ko'):
        a['ko'] -= 1
        if a['ko'] <= 0:
            a.pop('ko')
            bill = a['money'] * 0.3
            a['money'] -= bill
            a['hp'] = a['maxhp'] * 0.5
            a['hunger'] = min(a['hunger'], 60)
            a['state'] = 'idle'
            city.move(player, 'Brockton General Hospital', quiet=True)
            player.send(f"\n<green>You wake up in a hospital bed.</> <gray>Someone brought you in. The bill was {U.cash(bill)}.</>")
            look(player)
        hud(player)
        return
    resting = a.get('state') == 'rest'
    a['hunger'] = min(110, a['hunger'] + (0.35 if resting else 0.5))
    if a.get('wanted', 0) > 0:
        a['wanted'] -= 1
    if a['hunger'] >= 100:
        a['hp'] -= 0.2
        a['starving'] = a.get('starving', 0) + 1
        if a['starving'] % 12 == 1:
            player.send("<red>You are starving.</>")
        if a['starving'] % 30 == 0:
            combat.maybe_trigger(player, 'starving')
        if a['hp'] <= 0:
            a['hp'] = 1
            a['ko'] = 6
            player.send("<red>You collapse from hunger.</>")
    else:
        a['starving'] = 0
        if a['hunger'] == 75:
            player.send("<gray>Your stomach growls.</>")
        if 'fight' not in a and a['hp'] < a['maxhp']:
            a['hp'] = min(a['maxhp'], a['hp'] + (0.5 if resting else 0.1))
    threat = a.get('threat')
    if threat and threat['until'] <= city.now():
        a.pop('threat')
        mugger = city.PEOPLE.get(threat['by'])
        if mugger is not None and city.loc_of(mugger) is city.loc_of(player):
            player.send("<red>You took too long.</>")
            combat.attack(mugger, player, 'mug')
    if a.get('state') == 'work':
        loc = city.loc_of(player)
        b = economy.biz(loc)
        if a.get('work') != city.where(player) or not b or not U.in_hours(city.hour(), *b['open']):
            a['state'] = 'idle'
            player.send("<gray>The working day is over.</>")
        else:
            economy.produce(loc, player)
            a['worked'] = a.get('worked', 0) + 1
            a['worked_today'] = True
    hud(player)
