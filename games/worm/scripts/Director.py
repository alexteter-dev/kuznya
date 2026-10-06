"""Director: attached to the Simulation object. Starts the city and beats the clock."""
sim = world.require('sim')


def beat():
    # re-arm first: one bad tick must not stop time
    self.schedule(beat, self.attributes.get('tick_seconds', 2.0))
    sim.step()


@world.on_event('on_start')
def start():
    sim.start()
    self.schedule(beat, self.attributes.get('tick_seconds', 2.0))
