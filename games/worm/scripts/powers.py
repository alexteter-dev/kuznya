"""powers: procedural parahuman powers and trigger events."""
U = world.require('util')
D = world.require('powerdata')
W = world.require('wikipowers')
city = world.require('city')

CLASSES = ['Mover', 'Shaker', 'Brute', 'Breaker', 'Master', 'Tinker', 'Blaster', 'Thinker', 'Striker', 'Changer',
           'Trump', 'Stranger']


def scale(power, rating, weights):
    """Turn a rating and archetype weights into combat numbers."""
    atk, dfn, mob, hp = weights
    power['atk'] = round(rating * atk * 2.0, 1)
    power['dfn'] = round(rating * dfn * 1.3, 1)
    power['mob'] = round(rating * mob, 1)
    power['hp'] = int(rating * hp * 8)
    return power


def tier(rating):
    if rating <= 2:
        return 'trash'
    if rating <= 4:
        return 'low'
    if rating <= 6:
        return 'mid'
    if rating <= 8:
        return 'high'
    return 'overpowered'


def kit_for(cls):
    return U.pick([entry for entry in D.ARCHETYPES if entry[0] == cls])


def generate(context='beaten', where=None):
    """A brand-new power. The kind of danger steers the classification, as in the source material."""
    cls = U.wpick(D.TRIGGER_CLASSES.get(context, D.TRIGGER_CLASSES['beaten']))
    if U.chance(0.25):
        cls = U.pick(CLASSES)
    rating = U.wpick(D.RATING_WEIGHTS)
    archetype = kit_for(cls)
    theme, how, names = U.pick(D.THEMES)

    power = {
        'cls': cls,
        'rating': rating,
        'theme': theme,
        'abilities': list(archetype[2]),
        'passives': list(archetype[3]),
        'desc': archetype[5].format(theme=theme, theme_how=how),
        'cape_names': names,
        'origin': context,
    }

    # A third of new powers echo one documented on the wiki: same classification, same flavour of effect.
    examples = [e for e in W.EXAMPLES if e['cls'] == cls]
    if examples and U.chance(0.35):
        example = U.pick(examples)
        power['rating'] = rating = U.clamp(example['rating'] + U.pick([-2, -1, -1, 0, 0, 1]), 1, 12)
        power['desc'] = f"{example['summary']} (PRT analysts note the resemblance to {example['cape']}.)"
        power['echo'] = example['cape']

    scale(power, rating, archetype[4])
    power['tier'] = tier(rating)

    if rating <= 2:
        power['drawback'] = U.pick(D.JOKES)
        power['abilities'] = power['abilities'][:1]
        power['passives'] = []
    else:
        power['drawback'] = U.pick(D.DRAWBACKS)
    if rating >= 9:
        # the monsters get a second trick from a neighbouring classification
        extra = kit_for(U.pick(CLASSES))
        for ability in extra[2][:1]:
            if ability not in power['abilities']:
                power['abilities'].append(ability)
        power['sub'] = extra[0]
        power['passives'] = list(dict.fromkeys(power['passives'] + ['tough']))
    return power


def canon(cape, classes, text):
    """Power of a canon cape from the research data: classification and rating as listed on the wiki."""
    cls = classes[0]['cls'] if classes else 'Brute'
    rating = max((c['rating'] for c in classes), default=4)
    if cape in D.CANON:
        abilities, passives, weights = D.CANON[cape]
    else:
        archetype = kit_for(cls)
        abilities, passives, weights = archetype[2], archetype[3], archetype[4]
    power = {
        'cls': cls,
        'rating': rating,
        'theme': '',
        'abilities': list(abilities),
        'passives': list(passives),
        'desc': text,
        'drawback': '',
        'origin': 'canon',
        'classes': ', '.join(f"{c['cls']} {c['rating']}" for c in classes),
    }
    scale(power, rating, weights)
    power['tier'] = tier(rating)
    return power


def label(power):
    classes = power.get('classes') or f"{power['cls']} {power['rating']}" + (f"/{power['sub']}" if power.get('sub') else '')
    return classes


def sheet(power):
    lines = [f"<gold>{label(power)}</> <gray>({power['tier']})</>", power['desc']]
    if power.get('drawback'):
        lines.append(f"<gray>{power['drawback']}</>")
    for ability in power['abilities']:
        lines.append(f"  <cyan>power {ability}</> - {D.ABILITIES[ability]}")
    for passive in power['passives']:
        lines.append(f"  <gray>passive:</> {D.PASSIVES[passive]}")
    return '\n'.join(lines)


def cape_name(power):
    pool = power.get('cape_names') or ['Nameless']
    taken = {p.attributes.get('cape', {}).get('name') for p in city.PEOPLE.values()}
    free = [name for name in pool if name not in taken]
    return U.pick(free) if free else f"{U.pick(pool)} {U.rng.randrange(2, 99)}"


def grant(person, context):
    """A trigger event: the person gains a power on the worst day of their life."""
    a = person.attributes
    power = generate(context, city.where(person))
    a['power'] = power
    a['maxhp'] = a.get('maxhp', 30) + power['hp']
    a['hp'] = max(a['hp'], a['maxhp'] * 0.6)
    a['triggered'] = city.now()
    return power
