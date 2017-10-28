from jayk.cli.module import JaykMeta, jayk_command
import random
import re
import time


dice_re = re.compile("([1-9][0-9]*)[dD]([1-9][0-9]*)")


def roll(sides, count):
    return [random.randint(1, sides) for _ in range(count)]


class RTD(metaclass=JaykMeta):

    def __init__(self, max_sides=10**6, max_dice=20, timeout=5, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_sides = max_sides
        self.max_dice = max_dice
        self.timeout = timeout
        self.timeouts = {}

    @jayk_command("!rtd")
    def rtd(self, client, cmd, room, sender, msg):
        global dice_re
        user_time = self.timeouts.get(sender.username, 0.0)
        if user_time > time.time():
            return
        parts = msg.split()
        if len(parts) != 2:
            return
        match = dice_re.match(parts[1])
        if not match:
            return
        g = match.groups()
        count = int(g[0])
        sides = int(g[1])
        if count > self.max_dice or sides > self.max_sides:
            return
        result = roll(sides, count)
        total = sum(result)
        sum_str = ' + '.join(map(str, result))
        out_str = '{}: ({}d{}) {} = {}'.format(sender.nick, count, sides, sum_str, total)
        client.send_message(room, out_str)
        self.timeouts[sender.username] = time.time() + self.timeout

    @staticmethod
    def author(): return 'intercal'

    @staticmethod
    def about(): return 'Use !rtd XdY to roll Y sided dice X times'

    @staticmethod
    def name(): return 'RTD'

