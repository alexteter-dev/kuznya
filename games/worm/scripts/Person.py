"""Person: attached to every resident. Each one thinks for themselves, once per tick."""
people = world.require('people')


@self.on_event('tick')
def tick():
    people.think(self)
