from jayk.cli.module import JaykMeta, jayk_command
import random
import time


# Global bot data
fortunes = [
        'Reply hazy, try again',
        'Excellent Luck',
        'Good Luck',
        'Average Luck',
        'Bad Luck',
        'Good news will come to you by mail',
        '´_ゝ`',
        'ﾀ━━━━━━(ﾟ∀ﾟ)━━━━━━ !!!!',
        'You will meet a dark handsome stranger',
        'Better not tell you now',
        'Outlook good',
        'Very Bad Luck',
        'Godly Luck',
]


class Magic8(metaclass=JaykMeta):
    def __init__(self, timeout=300, **kwargs):
        super().__init__(**kwargs)
        self.timeouts = {}
        self.timeout = timeout

    def on_update_params(self, params):
        if 'timeout' in params:
            new_timeout = params['timeout']
            diff = new_timeout - self.timeout
            self.timeouts = {k: v + diff for k, v in self.timeouts.items()}
            self.timeout = new_timeout

    @jayk_command("!8ball", "!fortune")
    def magic8(self, client, cmd, channel, sender, msg):
        user = sender.username
        if user in self.timeouts and self.timeouts[user] > time.time():
            return
        fortune = "{}: Your fortune: {}".format(sender.nick, random.choice(fortunes))
        client.send_message(channel, fortune)
        self.timeouts[user] = time.time() + self.timeout

    @staticmethod
    def author(): return 'intercal'

    @staticmethod
    def about(): return 'Gives you a random fortune.'

    @staticmethod
    def name(): return 'Magic 8 ball'

