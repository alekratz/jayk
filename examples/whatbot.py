from jayk.cli.module import JaykMeta
import string

def message_is_what(message):
    message = message.strip(string.punctuation+string.whitespace).lower()
    return message == "what"

class Whatbot(metaclass=JaykMeta):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_message = None
        self._last_sender = None
    
    def on_message(self, client, room, sender, msg):
        if message_is_what(msg) and self._message_to_repeat is not None:
            reply = sender.nick + ": " + self._message_to_repeat.upper()
            client.send_message(room, reply)
        else:
            self._message_to_repeat = msg
