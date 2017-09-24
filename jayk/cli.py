from .chatbot import IRCChatbot, ChatbotModule
from .irc import ConnectInfo
import logging
from typing import *
import random
import time


fortunes = [
        'Your fortune: Reply hazy, try again',
        'Your fortune: Excellent Luck',
        'Your fortune: Good Luck',
        'Your fortune: Average Luck',
        'Your fortune: Bad Luck',
        'Your fortune: Good news will come to you by mail',
        'Your fortune: ´_ゝ`',
        'Your fortune: ﾀ━━━━━━(ﾟ∀ﾟ)━━━━━━ !!!!',
        'Your fortune: You will meet a dark handsome stranger',
        'Your fortune: Better not tell you now',
        'Your fortune: Outlook good',
        'Your fortune: Very Bad Luck',
        'Your fortune: Godly Luck',
]


class Magic8(ChatbotModule):
    def __init__(self, channels: Collection[str], timeout: int=300):
        super().__init__(channels)
        self.timeout = timeout
        self.timeouts = {}

    def on_message(self, client, channel, sender, msg):
        global fortunes
        parts = msg.split()
        cmd = parts[0] if len(parts) > 0 else None
        if cmd == '!8ball':
            user = sender.username
            if user in self.timeouts and self.timeouts[user] > time.time():
                return
            fortune = "{}: {}".format(sender.nick, random.choice(fortunes))
            client.send_message(channel, fortune)
            self.timeouts[user] = time.time() + self.timeout


def jayk():
    logging.basicConfig(level=logging.DEBUG)
    cinfo = ConnectInfo(
            server="irc.bonerjamz.us",
            port=6667,
            nicks=['magic8bot', 'magic8bot_'],
            user='botman')

    bot = IRCChatbot(cinfo, modules=[Magic8(['#idleville'])])
    bot.run_forever()
