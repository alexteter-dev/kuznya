"""util: small helpers shared by every game script."""
import random

rng = random.Random()


def seed(value):
    rng.seed(value)


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def chance(probability):
    return rng.random() < probability


def pick(items):
    items = list(items)
    return items[rng.randrange(len(items))] if items else None


def wpick(weighted):
    """weighted: list of (item, weight)"""
    total = sum(weight for item, weight in weighted)
    roll = rng.random() * total
    for item, weight in weighted:
        roll -= weight
        if roll <= 0:
            return item
    return weighted[-1][0]


def cash(amount):
    return f'${int(round(amount))}'


def in_hours(hour, start, end):
    """Is hour inside [start, end), where the window may wrap past midnight."""
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def cap(text):
    return text[:1].upper() + text[1:]


def listing(names):
    names = list(names)
    if len(names) <= 1:
        return ''.join(names)
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def bar(value, maximum, width=10):
    filled = int(round(clamp(value / maximum if maximum else 0, 0, 1) * width))
    return '#' * filled + '-' * (width - filled)


def match(query, names):
    """Indices of names matching the query: exact, then prefix, then word prefix, then substring."""
    query = query.strip().lower()
    if not query:
        return []
    lowered = [name.lower() for name in names]
    for test in (lambda n: n == query,
                 lambda n: n.startswith(query),
                 lambda n: any(word.startswith(query) for word in n.replace('(', ' ').split()),
                 lambda n: query in n):
        found = [index for index, name in enumerate(lowered) if test(name)]
        if found:
            return found
    return []
