"""
Runs the Brockton Bay simulation without a server, as fast as it will go, and prints what happened.
The world file is not modified.

    python games/worm/simulate.py --days 14
    python games/worm/simulate.py --days 14 --kill baker --on 4     # the bakers die on day 4: watch bread
    python games/worm/simulate.py --days 3 --leviathan 1
"""
import argparse
import io
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / 'interpreter' / 'src'))
from utils.game import World  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=10)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--kill', help='job whose holders all die')
    parser.add_argument('--on', type=int, default=3, help='day on which --kill happens')
    parser.add_argument('--leviathan', type=int, help='day on which Leviathan arrives (default: canon day 35)')
    parser.add_argument('--quiet-events', action='store_true', help='no dated events')
    parser.add_argument('--news', action='store_true', help='print the news feed at the end')
    args = parser.parse_args()

    world = World().load_filename(HERE / 'brockton_bay.wrld')
    world.require('util').seed(args.seed)
    world.start()
    sim, city, economy, people, capes = (world.require(name) for name in ('sim', 'city', 'economy', 'people', 'capes'))
    city.state['autosave'] = False
    if args.quiet_events:
        capes.EVENTS[:] = []
    if args.leviathan is not None:
        capes.EVENTS[:] = [e for e in capes.EVENTS if e[2] != 'leviathan'] + [(args.leviathan, 6, 'leviathan')]

    print(f"{'day':>3} {'pop':>4} {'bread':>6} {'fish':>6} {'meal':>6} {'stock b/f/m':>13} {'hungry':>6} "
          f"{'jobless':>7} {'cash':>7} {'tills':>7} {'dead':>4} {'fights':>6} {'capes':>5}")
    started = time.time()
    errors = 0
    for day in range(args.days):
        if args.kill and day == args.on:
            victims = [p for p in list(city.PEOPLE.values()) if p.attributes.get('job') == args.kill]
            for victim in victims:
                people.kill(victim, 'killed in an accident')
            print(f"    -- every {args.kill} in the city is dead ({len(victims)}) --")
        for tick in range(144):
            try:
                sim.step()
            except Exception:
                errors += 1
                if errors <= 3:
                    import traceback
                    traceback.print_exc()
        report = economy.market_report()
        residents = [p for p in city.PEOPLE.values() if p.attributes.get('kind') == 'npc']
        held, tills = economy.money_supply()
        stats = city.state['stats']
        stock = '/'.join(str(report[g]['stock']) for g in ('bread', 'fish', 'meal'))
        print(f"{city.day():>3} {len(residents):>4} {report['bread']['price']:>6.2f} {report['fish']['price']:>6.2f} "
              f"{report['meal']['price']:>6.2f} {stock:>13} "
              f"{sum(1 for p in residents if p.attributes['hunger'] > 85):>6} "
              f"{sum(1 for p in residents if p.attributes['job'] == 'unemployed'):>7} {held:>7.0f} {tills:>7.0f} "
              f"{stats.get('deaths', 0):>4} {stats.get('incidents', 0):>6} "
              f"{sum(1 for p in residents if p.attributes.get('power')):>5}")
    errors += city.state['stats'].get('errors', 0)
    print(f"\n{args.days} days in {time.time() - started:.1f}s, script errors: {errors}")
    print('stats:', {k: (round(v) if isinstance(v, float) else v) for k, v in sorted(city.state['stats'].items())})
    if args.news:
        for item in city.state['news'][-40:]:
            print(' ', city.stamp(item['t']), '|', item['text'])

    # the world must still be saveable after any amount of play
    import gzip
    import json
    json.dumps(world.root_object.save())
    return errors


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.exit(1 if main() else 0)
