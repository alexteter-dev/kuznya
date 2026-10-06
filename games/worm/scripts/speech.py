"""speech: what residents say out loud. Players standing nearby hear it."""
U = world.require('util')
city = world.require('city')
economy = world.require('economy')

LINES = {
    'gossip': [
        "Did you hear? {news}",
        "You won't believe it. {news}",
        "People are saying: {news}",
        "Quiet week. Makes me nervous, in this city.",
        "My cousin's moving to Boston. Says there's nothing left here but gangs and rust.",
        "They keep promising to bring the ferry back. Danny Hebert's been on about it for years.",
    ],
    'price_up': [
        "{price} for {good} at {place}. {price}! Used to be half that.",
        "You seen what {good} costs now? {price} at {place}.",
        "Can't feed a family with {good} at {price}.",
    ],
    'price_gone': [
        "No {good} anywhere. Shelves are bare at {place}.",
        "I went all the way to {place} and they were out of {good}.",
    ],
    'order': ["{you}, I need you sharp today. We're behind.", "Good work yesterday, {you}. Same again.",
              "{you}, the stock won't move itself."],
    'report': ["All in hand, boss.", "We're short-handed, I'm doing two people's work.",
               "Boss, I haven't seen a full wage in days."],
    'job_ask': ["Heard you're short of hands. I can start today."],
    'job_yes': ["You're hired. Don't be late."],
    'job_no': ["Sorry. Nothing going right now."],
    'recruit': ["You look hungry. We look after our own. Think about it.",
                "There's money in it if you've got the stomach."],
    'recruit_yes': ["...Alright. I'm in."],
    'recruit_no': ["Not interested. Leave me alone."],
    'collect': ["Nice place. Be a shame if something happened. You know what's owed."],
    'collect_pay': ["Take it. Just take it and go."],
    'collect_refuse': ["Not this time. Get out of my shop."],
    'allowance': ["Here, for lunch. Don't spend it on junk."],
    'charity': ["Here. Get yourself something to eat."],
    'thanks': ["Thank you. Really."],
    'mug': ["Wallet. Now.", "Empty your pockets. Slowly."],
    'mug_pay': ["Okay, okay! Here!"],
    'mug_fight': ["Get away from me!"],
    'arrest': ["On the ground! Hands where I can see them!"],
    'surrender': ["I give up! Don't hurt me!"],
    'warn': ["Stay off the streets after dark. It's getting worse out there."],
    'fear': ["Capes! Run!", "Oh God. Go, go!"],
    'grief': ["I can't believe they're gone."],
    'welcome': ["New in town? Word of advice: learn whose street you're standing on."],
    'offer_job': ["You look like you need work. {place} is short of a {job}. Go there and 'apply'."],
    'parcel': ["Could you take this to {target} for me? Should be around {place}. There's {reward} in it for you."],
    'boss_good': ["You've been pulling your weight. Keep it up."],
    'boss_bad': ["You didn't show up yesterday. Don't make it a habit."],
    'recruit_hero': ["The PRT knows what you can do. Come to PRT HQ and 'join' - better us than a gang."],
    'undersiders': ["I know what you are. No, don't bother denying it. We could use you. Type 'join Undersiders' if you want in."],
    'recruit_gang': ["{gang} could use someone like you. Say the word: 'join {gang}'."],
}


def line(topic, **values):
    return U.pick(LINES[topic]).format(**values)


def say(speaker, listener, topic, **values):
    """One line from speaker to listener, heard by players in the room."""
    values.setdefault('you', city.dname(listener).split()[0] if listener is not None else '')
    text = line(topic, **values)
    loc = city.loc_of(speaker)
    if listener is not None and listener.connection is not None:
        listener.send(f"{city.tag(speaker)} says to you: <cyan>\"{text}\"</>")
        city.tell_room(loc, f"<gray>{city.tag(speaker)} says something to {city.tag(listener)}.</>",
                       exclude=(speaker, listener))
    else:
        target = f" to {city.tag(listener)}" if listener is not None else ''
        city.tell_room(loc, f"<gray>{city.tag(speaker)} says{target}: \"{text}\"</>", exclude=(speaker,))
    return text


def news_item():
    news = city.state['news']
    return U.pick(news[-12:])['text'] if news else 'nothing ever happens here.'


def chat(speaker, listener):
    """Idle talk. People complain about exactly what the simulation is doing to them."""
    report = economy.market_report()
    dear = [(good, info) for good, info in report.items()
            if good in economy.FOODS and info['price'] > info['base'] * 1.6]
    empty = [(good, info) for good, info in report.items() if good in economy.FOODS and info['stock'] < 5]
    place = U.pick(['Lord Street Market', 'Weymouth Shopping Center', 'Lord Street Bakery'])
    if empty and U.chance(0.5):
        good, info = U.pick(empty)
        return say(speaker, listener, 'price_gone', good=good, place=place)
    if dear and U.chance(0.6):
        good, info = U.pick(dear)
        return say(speaker, listener, 'price_up', good=good, price=U.cash(info['price']), place=place)
    return say(speaker, listener, 'gossip', news=news_item())
