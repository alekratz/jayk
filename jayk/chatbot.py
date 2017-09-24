from abc import ABCMeta, abstractmethod
import asyncio
import re
from typing import *
from . import common
from . import util
from . import irc


class ChatbotModule(metaclass=ABCMeta):
    def __init__(self, rooms: Set[str]):
        """
        Initializes a chatbot module.
        :param rooms: the list of rooms this bot is active in.
        """
        self.rooms = rooms

    def on_message(self, client: 'Chatbot', room: str, sender: str, message: str):
        """
        Called when a channel message is received.
        :param room: the room the message was sent to. If this is a private message, this is set to None.
        :param sender: the name of the sender of this message. Self-messages are ignored.
        :param message: the message content.
        """

    def on_join_room(self, room: str):
        """
        Called when the bot enters a room.
        :param room: the room that was joined.
        """


class Chatbot(metaclass=ABCMeta):
    def __init__(self, connect_info: common.ConnectInfo, modules: Collection[ChatbotModule]):
        self.connect_info = connect_info
        self.modules = modules
        self.rooms = set.union(*[set(m.rooms) for m in modules])

    def on_message(self, room: str, sender: str, message: str):
        for mod in self.modules:
            if room in mod.rooms:
                mod.on_message(self, room, sender, message)

    def on_join_room(self, room: str):
        for mod in self.modules:
            if room in mod.rooms:
                mod.on_join_room(self, room)

    @abstractmethod
    def send_message(self, room: str, msg: str):
        pass

    @abstractmethod
    def on_connect(self):
        pass

    def run_forever(self, catch_ctrl_c=True):
        loop = asyncio.get_event_loop()
        coro = loop.create_connection(lambda: self, self.connect_info.server, self.connect_info.port)
        loop.run_until_complete(coro)
        if catch_ctrl_c:
            try:
                loop.run_forever()
            except KeyboardInterrupt as e:
                print("ctrl-C caught, exiting")
                loop.stop()
        else:
            loop.run_forever()
        loop.close()


class IRCChatbot(Chatbot, irc.ClientProtocol):
    """
    Chatbot adapter for the IRC protocol. The chatbot handles:
        * connecting
        * server authentication
        * nickname management
    """
    def __init__(self, connect_info: irc.ConnectInfo, modules: Collection[ChatbotModule]):
        """
        Initializes the IRC chat bot.
        :param connect_info: the connection information to use
        """
        Chatbot.__init__(self, connect_info, modules)
        irc.ClientProtocol.__init__(self, connect_info)
        self.connect_info = connect_info
        self.__nick_rotation = iter(self.connect_info.nicks)
        self.__nick = None

    def on_connect(self):
        if self.connect_info.server_pass:
            self._send_command("PASS", self.connect_info.server_pass)
        self._send_command("USER", self.connect_info.user, '0', '*', 'Chatbot')
        self.__try_next_nick()

    def send_message(self, target: str, msg: str):
        self._send_command('PRIVMSG', target, ":{}".format(msg))

    def _handle_irc_message(self, message: irc.Message):
        """
        Handles an IRC message.
        """
        if message.command == 'RPL_MYINFO':
            for ch in self.rooms:
                self._send_command("JOIN", ch)
        elif message.command in irc.response.NICK_ERRORS:
            self.__try_next_nick()
        elif message.command == 'PING':
            if len(msg.params) == 0:
                # NOTE: throw an error?
                self.error('invalid IRC PING message received: %s', msg)
                return
            msg = message.params[0]
            if msg[0] != ':':
                msg = ':' + msg
            self._send_command('PONG', msg)
        elif message.command == 'PRIVMSG':
            if not message.user or message.user.nick == self.nick:
                return
            room = message.params[0]
            msg = message.params[1]
            self.on_message(room, message.user, msg)

    def connection_made(self, transport):
        """
        Hooks into the IRC client protocol's connection_made and calls some events after the superclass's method is
        called.
        :param transport: the transport that is passed along to the superclass
        """
        super().connection_made(transport)
        self.on_connect()

    def data_received(self, data):
        """
        Hooks into the IRC client protocol's data_received and calls some events after the superclass's method is
        called.
        :param data: the data received. This is passed on to _handle_irc_message, and then on_message.
        """
        super().data_received(data)
        lines = data.decode().split("\r\n")
        for line in filter(len, lines):
            try:
                message = irc.Message.parse(str(line))
            except ValueError as e:
                self.error("%s", e)
            else:
                self._handle_irc_message(message)

    def __try_next_nick(self):
        try:
            self.__nick = next(self.__nick_rotation)
            self._send_command("NICK", self.__nick)
        except StopIteration:
            raise NoMoreNicksError(self.connect_info)

    @property
    def nick(self):
        return self.__nick
