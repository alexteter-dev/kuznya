"""combat: fights, power abilities, getting knocked out, dying - and trigger events.

A fight is not an object. Each fighter carries a 'fight' entry naming their target; every tick each fighter
acts once. Bystanders react for themselves: run, help a friend, back their gang, call it in.
"""
U = world.require('util')
city = world.require('city')
powers = world.require('powers')
capes = world.require('capes')
speech = world.require('speech')
people = world.require('people')

ARMED = {'police officer': (8, 2), 'PRT officer': (9, 3), 'ABB enforcer': (7, 1), 'Empire enforcer': (7, 1),
         'mercenary': (10, 3), 'dealer': (5, 0), 'guard': (7, 2), 'bouncer': (6, 1), 'pit fighter': (8, 1),
         'gang boss': (8, 1), 'pit boss': (8, 1)}
LAW = {'police officer', 'PRT officer'}
COOLDOWN = {'blast': 2, 'smash': 3, 'area': 3, 'shield': 5, 'swarm': 4, 'minions': 8, 'dark': 5, 'blink': 2,
            'fly': 2, 'phase': 5, 'heal': 2, 'freeze': 4, 'insight': 4, 'copy': 99, 'null': 5, 'vanish': 8,
            'command': 6, 'aura': 4, 'morph': 6, 'craft': 0}
FIGHTERS = set()


def stats(person):
    """(attack, defence, mobility) right now."""
    a = person.attributes
    atk, dfn = ARMED.get(a.get('job'), (3, 0))
    gear = a.get('gear', {})
    atk += gear.get('atk', 0)
    dfn += gear.get('dfn', 0)
    mob = 1.0
    fight = a.get('fight') or {}
    fx = fight.get('fx', {})
    power = a.get('power')
    if power and not fx.get('null'):
        p_atk, p_dfn = power['atk'], power['dfn']
        if 'ramp' in power['passives']:
            growth = min(3.0, 1 + 0.12 * fight.get('rounds', 0))
            p_atk *= growth
            p_dfn *= growth
        if fx.get('morph'):
            p_atk *= 1.4
            p_dfn *= 1.4
        atk += p_atk
        dfn += p_dfn
        mob += power['mob']
    if fight.get('copy'):
        atk += fight['copy'][0]
        dfn += fight['copy'][1]
    if fx.get('shield'):
        dfn += fight.get('shield_val', 5)
    if fx.get('exposed'):
        dfn *= 0.5
    atk += 2 * fight.get('minions', 0)
    return atk, dfn, mob


def is_law(person):
    a = person.attributes
    cape = a.get('cape')
    return a.get('job') in LAW or bool(cape and cape.get('align') == 'hero' and cape.get('costume'))


def hidden(person):
    return person.attributes.get('hidden_until', 0) > city.now()


def can_fight(person):
    a = person.attributes
    return person.alive and not a.get('ko') and not a.get('jail') and not a.get('away')


def engage(person, target, why):
    a = person.attributes
    if 'fight' not in a:
        a['fight'] = {'target': target.identity, 'cd': {}, 'fx': {}, 'rounds': 0, 'why': why}
        if a.get('state') == 'sleep':
            a['state'] = 'idle'
    FIGHTERS.add(person.identity)


def end(person):
    person.attributes.pop('fight', None)
    FIGHTERS.discard(person.identity)


forget = end


def enemies(person):
    loc = city.loc_of(person)
    if loc is None:
        return []
    mine = person.attributes.get('fight', {}).get('target')
    return [p for p in city.people_in(loc) if p is not person and can_fight(p)
            and (p.identity == mine or p.attributes.get('fight', {}).get('target') == person.identity)]


def attack(attacker, target, why='assault'):
    """Start (or join) a fight. Returns False if it cannot happen."""
    if attacker is target or not can_fight(attacker) or not can_fight(target):
        return False
    loc = city.loc_of(attacker)
    if loc is None or city.loc_of(target) is not loc or hidden(target):
        return False
    fresh = 'fight' not in attacker.attributes
    engage(attacker, target, why)
    attacker.attributes['fight']['target'] = target.identity
    engage(target, attacker, 'defence')
    if why != 'arrest':
        attacker.attributes['wanted'] = max(attacker.attributes.get('wanted', 0), 150)
    if fresh:
        city.tell_room(loc, f"<red>{city.tag(attacker)} attacks {city.tag(target)}!</>", exclude=(attacker, target))
        city.tell(target, f"<red>{city.tag(attacker)} attacks you!</> <gray>(attack / flee / power)</>")
        witnesses(loc, attacker, target, why)
    return True


def witnesses(loc, attacker, target, why):
    aa, ta = attacker.attributes, target.attributes
    powered = bool(aa.get('power') or ta.get('power'))
    shouted = False
    for person in city.people_in(loc):
        a = person.attributes
        if person in (attacker, target) or 'fight' in a or not people.awake(person):
            continue
        if a.get('kind') == 'player':
            continue
        faction = a.get('faction')
        if faction and faction == ta.get('faction'):
            engage(person, attacker, 'defence')
        elif faction and faction == aa.get('faction') and why in ('raid', 'rob', 'defence'):
            engage(person, target, why)
        elif is_law(person) and why != 'arrest':
            engage(person, attacker, 'arrest')
        elif why == 'arrest' and is_law(person):
            engage(person, target, 'arrest')
        elif target.identity in a.get('friends', []) and a['traits']['brave'] > 0.7:
            engage(person, attacker, 'defence')
        else:
            if not shouted and powered:
                speech.say(person, None, 'fear')
                shouted = True
            a['hang'] = {'loc': a['home'], 'until': city.now() + 90}
            exits = loc.attributes.get('exits', [])
            if exits:
                city.move(person, U.pick(exits), quiet=True)
            if powered:
                maybe_trigger(person, 'witness')
    if why != 'arrest':
        capes.incident(loc.attributes['name'], attacker, why, powered)


# -- one fighter, one tick
def tick():
    for identity in list(FIGHTERS):
        person = city.PEOPLE.get(identity)
        if person is None or 'fight' not in person.attributes:
            FIGHTERS.discard(identity)
            continue
        try:
            act(person)
        except Exception:
            end(person)
            raise


def act(person):
    a = person.attributes
    fight = a['fight']
    fx = fight['fx']
    if not can_fight(person):
        end(person)
        return
    fight['rounds'] += 1
    power = a.get('power') or {'passives': [], 'abilities': [], 'rating': 0}

    # effects that tick
    if fx.get('dot'):
        hurt(person, fx['dot'][0], None, 'swarm')
        if 'fight' not in a:
            return
        fx['dot'][1] -= 1
        if fx['dot'][1] <= 0:
            del fx['dot']
    stunned = fx.get('stun', 0) > 0
    for key in ('stun', 'shield', 'phase', 'blind', 'morph', 'null', 'exposed', 'cover', 'thrall'):
        if fx.get(key):
            fx[key] -= 1
            if fx[key] <= 0:
                del fx[key]
    for ability in list(fight['cd']):
        fight['cd'][ability] -= 1
        if fight['cd'][ability] <= 0:
            del fight['cd'][ability]
    if 'regen' in power['passives'] and not fx.get('null'):
        a['hp'] = min(a['maxhp'], a['hp'] + power['rating'] * 0.6)
    if 'immortal' in power['passives'] and fight['rounds'] % 4 == 0 and not fx.get('null'):
        a['hp'] = a['maxhp']
    if stunned:
        city.tell(person, "<gray>You cannot move.</>")
        return

    target = city.PEOPLE.get(fight['target'])
    here = city.loc_of(person)
    if target is None or not can_fight(target) or city.loc_of(target) is not here or hidden(target):
        others = [p for p in enemies(person) if not hidden(p)]
        if not others:
            end(person)
            city.tell(person, "<gray>The fight is over.</>")
            return
        target = U.pick(others)
        fight['target'] = target.identity

    if a.get('kind') == 'player':
        intent = fight.pop('intent', None)
        if intent and intent[0] == 'flee':
            flee(person)
        elif intent and intent[0] == 'power':
            chosen = city.PEOPLE.get(intent[2]) if intent[2] else target
            if not use(person, intent[1], chosen or target):
                strike(person, target)
        else:
            strike(person, target)
        return

    # residents decide for themselves
    ratio = a['hp'] / a['maxhp']
    brave = a['traits']['brave']
    cape = a.get('cape') or {}
    nerve = (0.3 if cape.get('align') == 'villain' else 0.2) if cape.get('costume') else 0.5 - 0.35 * brave
    if a.get('fearless'):
        nerve = 0
    unarmed = a.get('job') not in ARMED and not a.get('power')
    if ratio < nerve or (unarmed and fight['why'] == 'defence' and brave < 0.65):
        if a.get('wanted') and is_law(target) and ratio < 0.3 and U.chance(0.5):
            speech.say(person, target, 'surrender')
            capes.arrest(person, target)
            return
        ready = [ab for ab in ('vanish', 'fly', 'blink', 'phase', 'dark') if ab in power['abilities']
                 and ab not in fight['cd']]
        if ready and use(person, ready[0], target):
            return
        flee(person)
        return
    if fx.get('thrall'):
        strike(person, target)
        return
    ready = [ab for ab in power['abilities'] if ab not in fight['cd']
             and ab in ('blast', 'smash', 'area', 'shield', 'swarm', 'minions', 'dark', 'phase', 'freeze',
                        'null', 'aura', 'morph', 'copy', 'heal', 'insight')]
    if 'heal' in ready and ratio > 0.6:
        ready.remove('heal')
    if 'minions' in ready and fight.get('minions', 0) > 1:
        ready.remove('minions')
    if ready and U.chance(0.65):
        if use(person, U.pick(ready), target):
            return
    strike(person, target)


def flee(person):
    a = person.attributes
    fight = a['fight']
    loc = city.loc_of(person)
    atk, dfn, mob = stats(person)
    foes = enemies(person)
    fastest = max((stats(foe)[2] for foe in foes), default=0)
    power = a.get('power') or {'passives': []}
    odds = U.clamp(0.5 + (mob - fastest) * 0.08, 0.15, 0.95)
    if 'flight' in power['passives'] or fight['fx'].get('cover') or not foes:
        odds = 1.0
    if not U.chance(odds):
        city.tell(person, "<red>You try to run, but they cut you off.</>")
        city.tell_room(loc, f"<gray>{city.tag(person)} tries to run and is cut off.</>", exclude=(person,))
        maybe_trigger(person, 'trapped')
        return False
    end(person)
    exits = loc.attributes.get('exits', [])
    home = a.get('home')
    choice = city.NEXT.get((loc.attributes['name'], home)) if home in city.LOC and U.chance(0.5) else None
    city.tell_room(loc, f"<gray>{city.tag(person)} breaks away and runs.</>", exclude=(person,))
    city.tell(person, "<green>You break away and run.</>")
    if exits:
        city.move(person, choice or U.pick(exits), quiet=True)
    return True


def strike(person, target, mult=1.0, pierce=False, label='hits'):
    a, ta = person.attributes, target.attributes
    atk, dfn, mob = stats(person)
    t_atk, t_dfn, t_mob = stats(target)
    power = a.get('power') or {'passives': []}
    t_power = ta.get('power') or {'passives': [], 'rating': 0}
    t_fx = ta.get('fight', {}).get('fx', {})
    loc = city.loc_of(person)
    for swing in range(2 if 'fast' in power['passives'] else 1):
        if 'fight' not in ta and not can_fight(target):
            return
        odds = U.clamp(0.8 + (mob - t_mob) * 0.04, 0.25, 0.97)
        if a.get('fight', {}).get('fx', {}).get('blind'):
            odds *= 0.5
        if 'precog' in t_power['passives']:
            odds *= 0.7
        missed = t_fx.get('phase') or not U.chance(odds) or ('clones' in t_power['passives'] and U.chance(0.5))
        if missed:
            city.tell(person, f"<gray>You miss {city.tag(target)}.</>")
            city.tell(target, f"<gray>{city.tag(person)} misses you.</>")
            continue
        damage = U.rng.uniform(0.6, 1.2) * atk * mult - t_dfn * (0.25 if pierce else 0.5)
        if 'tough' in t_power['passives'] and damage < t_power['rating']:
            damage = 0.5
        damage = max(1.0, damage)
        city.tell(person, f"You {label[:-1] if label.endswith('s') else label} {city.tag(target)} for <gold>{damage:.0f}</>.")
        city.tell_room(loc, f"<gray>{city.tag(person)} {label} {city.tag(target)}.</>", exclude=(person, target))
        hurt(target, damage, person, 'beaten')


def hurt(person, damage, source, context):
    a = person.attributes
    fight = a.get('fight')
    if fight and fight.get('minions', 0) > 0 and U.chance(0.5):
        fight['minions'] -= 1
        damage *= 0.3
    a['hp'] -= damage
    if source is not None:
        city.tell(person, f"<red>{city.tag(source)} hurts you for {damage:.0f}.</> <gray>({max(a['hp'], 0):.0f}/{a['maxhp']:.0f})</>")
    elif context == 'swarm':
        city.tell(person, f"<red>The swarm tears at you for {damage:.0f}.</> <gray>({max(a['hp'], 0):.0f}/{a['maxhp']:.0f})</>")
    if a['hp'] <= 0:
        down(person, source, context)
    elif a['hp'] < a['maxhp'] * 0.3:
        foes = len(enemies(person))
        maybe_trigger(person, 'outnumbered' if foes >= 2 else context if context in powers.D.TRIGGER_CLASSES else 'beaten')


def down(person, by, context='beaten'):
    a = person.attributes
    fight = a.get('fight') or {}
    power = a.get('power') or {'passives': []}
    loc = city.loc_of(person)
    if 'reroll' in power['passives'] and not fight.get('rerolled') and fight:
        fight['rerolled'] = True
        a['hp'] = a['maxhp'] * 0.7
        city.tell_room(loc, f"<magenta>{city.tag(person)} should be down - and is somehow standing, unhurt, as if that had never happened.</>")
        return
    if not a.get('power') and maybe_trigger(person, context if context in powers.D.TRIGGER_CLASSES else 'beaten', last=True):
        return
    why = (by.attributes.get('fight') or {}).get('why') if by is not None else None
    odds = 0.0
    if by is not None and not is_law(by) and why != 'arrest':
        ba = by.attributes
        cape = ba.get('cape')
        lethal = cape.get('lethal') if cape else ba['traits']['violent'] > 0.7
        odds = 0.25 if lethal else 0.03
        if a.get('cape'):
            odds *= 0.3      # the unwritten rules: capes mostly do not kill capes, and nobody wants that heat
    if by is not None and by.attributes.get('endbringer'):
        odds = 0.2 if a.get('power') else 0.45
    if by is None and context == 'disaster':
        odds = 0.35
    if a.get('kind') == 'player':
        odds = 0.0
    if U.chance(odds):
        people.kill(person, 'killed', by)
        return
    knock_out(person, by)


def knock_out(person, by):
    a = person.attributes
    loc = city.loc_of(person)
    a['hp'] = 1
    a['ko'] = U.rng.randrange(12, 30)
    end(person)
    city.tell_room(loc, f"<red>{city.tag(person)} goes down.</>", exclude=(person,))
    if by is not None:
        ba = by.attributes
        if is_law(by) and (a.get('wanted', 0) > 0 or (a.get('cape') or {}).get('align') == 'villain'):
            capes.arrest(person, by)
        elif ba.get('wanted', 0) > 0 and not is_law(by) and a.get('money', 0) > 0 and not a.get('cape'):
            taken = a['money'] * 0.6
            a['money'] -= taken
            ba['money'] = ba.get('money', 0) + taken
            city.tell(by, f"<gold>You take {U.cash(taken)} off {city.tag(person)}.</>")
    if a.get('kind') == 'player':
        person.trigger('knocked_out')


# -- power abilities. Returns True if the ability was used.
def use(person, ability, target=None):
    a = person.attributes
    power = a.get('power')
    if not power or ability not in power['abilities']:
        return False
    fight = a.get('fight')
    if fight is None or ability in fight['cd'] or fight['fx'].get('null'):
        return False
    rating = power['rating']
    loc = city.loc_of(person)
    foes = enemies(person)
    me = city.tag(person)
    fight['cd'][ability] = COOLDOWN.get(ability, 3)

    def show(text):
        city.tell_room(loc, f"<magenta>{text}</>")

    if ability == 'blast':
        show(f"{me} lets loose at {city.tag(target)}.")
        strike(person, target, 1.7, True, 'blasts')
    elif ability == 'smash':
        show(f"{me} winds up and hits {city.tag(target)} with everything.")
        strike(person, target, 2.2, False, 'smashes')
    elif ability == 'area':
        show(f"{me}'s power tears through the whole place.")
        for foe in foes:
            strike(person, foe, 1.0, False, 'hits')
        for bystander in city.people_in(loc):
            if bystander is not person and bystander not in foes and 'fight' not in bystander.attributes \
                    and U.chance(0.08):
                hurt(bystander, 5 + rating, None, 'disaster')
    elif ability == 'shield':
        show(f"{me} throws up a defence.")
        fight['fx']['shield'] = 3
        fight['shield_val'] = rating * 2.5
    elif ability == 'swarm':
        show(f"A swarm boils out of every crack and descends on {me}'s enemies.")
        for foe in foes:
            ffx = foe.attributes.get('fight', {}).get('fx')
            if ffx is not None:
                ffx['dot'] = [rating * 1.3, 3]
                ffx['blind'] = 3
    elif ability == 'minions':
        fight['minions'] = 2 + rating // 2
        show(f"{me} is no longer alone: {fight['minions']} minions close in.")
    elif ability == 'dark':
        show(f"{me} drowns the place in darkness.")
        for foe in foes:
            ffx = foe.attributes.get('fight', {}).get('fx')
            if ffx is not None:
                ffx['blind'] = 3
        for friend in city.people_in(loc):
            if friend.attributes.get('faction') and friend.attributes.get('faction') == a.get('faction') \
                    and 'fight' in friend.attributes:
                friend.attributes['fight']['fx']['cover'] = 3
        fight['fx']['cover'] = 3
    elif ability in ('blink', 'fly'):
        fight['fx']['cover'] = 1
        show(f"{me} is suddenly somewhere else.")
        flee(person)
    elif ability == 'phase':
        show(f"{me} becomes something that blows pass straight through.")
        fight['fx']['phase'] = 2
    elif ability == 'heal':
        patient = target if target is not None and target not in foes else person
        if patient in foes or patient is None:
            patient = person
        pa = patient.attributes
        pa['hp'] = min(pa['maxhp'], pa['hp'] + rating * 6)
        show(f"{me} mends {city.tag(patient)}'s wounds.")
    elif ability == 'freeze':
        t_fx = target.attributes.get('fight', {}).get('fx')
        if t_fx is None:
            return False
        strong = (target.attributes.get('power') or {}).get('rating', 0) >= 9
        t_fx['stun'] = 1 if strong else 2
        show(f"{me} locks {city.tag(target)} in place.")
    elif ability == 'insight':
        t_fx = target.attributes.get('fight', {}).get('fx')
        if t_fx is None:
            return False
        t_fx['exposed'] = 3
        show(f"{me} reads {city.tag(target)} like a page and finds the weak point.")
    elif ability == 'copy':
        best = None
        for other in city.people_in(loc):
            other_power = other.attributes.get('power')
            if other is not person and other_power and (best is None or other_power['rating'] > best['rating']):
                best = other_power
        if best is None:
            del fight['cd'][ability]
            return False
        fight['copy'] = (best['atk'] * 0.8, best['dfn'] * 0.8)
        show(f"{me} takes on a borrowed power.")
    elif ability == 'null':
        t_fx = target.attributes.get('fight', {}).get('fx')
        if t_fx is None:
            return False
        t_fx['null'] = 3
        show(f"{city.tag(target)}'s power gutters out around {me}.")
    elif ability == 'vanish':
        show(f"{me} is gone. Nobody is quite sure when they left.")
        a['hidden_until'] = city.now() + 60
        end(person)
    elif ability == 'command':
        ta = target.attributes
        if ta.get('power') or ta.get('kind') == 'player' or 'fight' not in ta:
            del fight['cd'][ability]
            return False
        others = [foe for foe in foes if foe is not target]
        if others:
            ta['fight']['target'] = U.pick(others).identity
            ta['fight']['fx']['thrall'] = 4
            show(f"{city.tag(target)} jerks like a puppet and turns on their own side.")
        else:
            ta['fight']['fx']['stun'] = 2
            show(f"{city.tag(target)} locks up, fighting their own body.")
    elif ability == 'aura':
        show(f"A wave of dread rolls out from {me}.")
        for foe in foes:
            fa = foe.attributes
            foe_rating = (fa.get('power') or {}).get('rating', 0)
            if fa.get('kind') == 'npc' and fa['traits']['brave'] < 0.7 and foe_rating < rating and 'fight' in fa:
                fa['fight']['fx']['cover'] = 1
                flee(foe)
    elif ability == 'morph':
        show(f"{me}'s body flows into something bigger and worse.")
        fight['fx']['morph'] = 4
    else:
        del fight['cd'][ability]
        return False
    return True


# -- trigger events
def maybe_trigger(person, context, last=False):
    """Danger is how powers happen. Mostly it is just danger."""
    a = person.attributes
    if a.get('power') or a.get('age', 30) < 10 or a.get('away'):
        return False
    fight = a.get('fight')
    if fight is not None:
        if fight.get('trig_' + context) and not last:
            return False
        fight['trig_' + context] = True
    if a.get('kind') == 'player':
        odds = 0.3 + 0.15 * a.get('near_misses', 0) + (0.2 if last else 0)
    else:
        odds = 0.012 if last else 0.004
    if not U.chance(odds):
        if a.get('kind') == 'player':
            a['near_misses'] = a.get('near_misses', 0) + 1
        return False
    trigger(person, context)
    return True


def trigger(person, context):
    a = person.attributes
    loc = city.loc_of(person)
    foes = enemies(person)
    power = powers.grant(person, context)
    for foe in foes:
        ffx = foe.attributes.get('fight', {}).get('fx')
        if ffx is not None:
            ffx['stun'] = 2
    a['near_misses'] = 0
    place = loc.attributes['name'] if loc else 'the city'
    city.tell_room(loc, f"<magenta>Something breaks inside {city.tag(person)}. For an instant they are somewhere else entirely - and then the air around them is wrong.</>", exclude=(person,))
    city.post(f"Unconfirmed: a new parahuman triggered at {place}. Classification guess: {power['cls']}.", 'cape', loud=True)
    city.count('triggers')
    if a.get('kind') == 'player':
        person.trigger('triggered', power)
    else:
        capes.new_cape(person)
