"""Player: attached to the player prefab. One object per connection; it becomes the character."""
commands = world.require('commands')
powers = world.require('powers')


@self.on_event('on_connect')
def connected():
    commands.connected(self)


@self.on_event('on_message')
def message(text):
    commands.handle(self, text)


@self.on_event('on_disconnect')
def disconnected():
    commands.left(self)


@self.on_event('tick')
def tick():
    commands.tick(self)


@self.on_event('moved')
def moved():
    commands.look(self)
    commands.hud(self)


@self.on_event('knocked_out')
def knocked_out():
    self.send("<red>Everything goes dark.</>")


@self.on_event('player_died')
def died(cause):
    self.attributes['hp'] = 1
    self.attributes['ko'] = 6


@self.on_event('triggered')
def triggered(power):
    self.send("\n<magenta>It is the worst moment of your life, and in the middle of it something vast and far away "
              "turns to look at you.\nTwo shapes, spiralling through nothing. Then you forget them, and the world "
              "comes back different.</>\n\n<gold>You have triggered.</>")
    self.send(powers.sheet(power))
    self.send("<gray>Use it with 'power <ability>'. People will want things from you now.</>")
