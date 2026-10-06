"""Business: attached to every place that makes or sells something. Prices are set here, hourly."""
economy = world.require('economy')


@self.on_event('hour')
def hour():
    economy.reprice(self)
