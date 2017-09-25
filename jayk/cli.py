from .chatbot import IRCChatbot, command_bot
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
timeouts = {}
timeout = 300


@command_bot(rooms={'#idleville'}, commands={'!fortune', '!8ball'})
def magic8(client, cmd, channel, sender, msg):
    user = sender.username
    if user in timeouts and timeouts[user] > time.time():
        return
    fortune = "{}: {}".format(sender.nick, random.choice(fortunes))
    client.send_message(channel, fortune)
    timeouts[user] = time.time() + timeout


def jayk():
    logging.basicConfig(level=logging.DEBUG)
    cinfo = ConnectInfo(
            server="irc.bonerjamz.us",
            port=6667,
            nicks=['magic8bot', 'magic8bot_'],
            user='botman')

    bot = IRCChatbot(cinfo, modules=[
        magic8(),
    ])
    bot.run_forever()
