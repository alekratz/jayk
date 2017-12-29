import hashlib
from jayk.cli.module import JaykMeta, jayk_command


def make_hash(h, m):
    if h not in hashlib.algorithms_available:
        return None
    return hashlib.new(h, m.encode('utf-8')).hexdigest()


class HashBot(metaclass=JaykMeta):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @jayk_command("!sha1")
    def sha1(self, client, cmd, room, sender, msg):
        msg = msg[6:]
        h = make_hash('sha1', msg)
        client.send_message(room, '{}: {}'.format(sender.nick, h))

    @jayk_command("!sha256")
    def sha256(self, client, cmd, room, sender, msg):
        msg = msg[8:]
        h = make_hash('sha256', msg)
        client.send_message(room, '{}: {}'.format(sender.nick, h))

    @jayk_command("!sha384")
    def sha384(self, client, cmd, room, sender, msg):
        msg = msg[8:]
        h = make_hash('sha384', msg)
        client.send_message(room, '{}: {}'.format(sender.nick, h))

    @jayk_command("!sha512")
    def sha512(self, client, cmd, room, sender, msg):
        msg = msg[8:]
        h = make_hash('sha512', msg)
        client.send_message(room, '{}: {}'.format(sender.nick, h))

    @jayk_command("!md4")
    def md4(self, client, cmd, room, sender, msg):
        msg = msg[5:]
        h = make_hash('md4', msg)
        client.send_message(room, '{}: {}'.format(sender.nick, h))

    @jayk_command("!md5")
    def md5(self, client, cmd, room, sender, msg):
        msg = msg[5:]
        h = make_hash('md5', msg)
        client.send_message(room, '{}: {}'.format(sender.nick, h))

    @jayk_command("!hash")
    def do_hash(self, client, cmd, room, sender, msg):
        parts = msg.split(None, 2)[1:]
        if len(parts) == 0:
            return
        elif len(parts) == 1:
            parts += ['']
        algo, string = parts
        h = make_hash(algo, string)
        if h is None:
            client.send_message(room, '{}: hash algorithm not available'.format(sender.nick))
        else:
            client.send_message(room, '{}: {}'.format(sender.nick, h))

    @jayk_command("!hashes")
    def hashes(self, client, cmd, room, sender, msg):
        algos = set(map(str.lower(), hashlib.algorithms_available))
        client.send_message(room, 'Available hash algorithms: {}'.format(' '.join(algos)))

    @staticmethod
    def author(): return 'intercal'

    @staticmethod
    def about(): return '!hash algo message ... | !sha1 message ... | !sha256 message ...'

    @staticmethod
    def name(): return 'HashBot'

