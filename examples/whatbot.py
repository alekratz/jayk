from jayk.cli.module import JaykMeta
import string

def message_is_what(message):
    message = message.strip(string.punctuation+string.whitespace).lower()
    return message == "what"

class Whatbot(metaclass=JaykMeta):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_message = None # The message to shout back.
        self._last_sender = None # Used to make sure we don't shout a user's own message back to them.
    
    def on_message(self, client, room, sender, msg):
        if message_is_what(msg) and self._last_sender is not None and self._last_sender.username != sender.username:
            reply = sender.nick + ": " + self._last_message.upper()
            client.send_message(room, reply)
        else:
            self._last_message = msg
            self._last_sender = sender
    
    @staticmethod
    def author():
        return "Maxpm"
    
    @staticmethod
    def about():
        return "If someone says \"what\" and nothing else, the last message is helpfully shouted at them."
    
    @staticmethod
    def name():
        return "Whatbot"
