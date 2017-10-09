from abc import ABCMeta, abstractmethod
import asyncio
import re
from typing import *
from . import common
from . import util
from . import irc


class ChatbotModule(util.LogMixin):
    """
    This is the base chatbot module. This may be overridden and plugged in to the chatbot.
    """
    def __init__(self, rooms: Set[str], **kwargs):
        """
        Initializes a chatbot module.
        :param rooms: the list of rooms this bot is active in.
        """
        super().__init__(__name__)
        self.rooms = rooms
        if kwargs:
            for k in kwargs: self.warning("Unused parameter when creating chatbot module: %s", k)

    def on_message(self, client: 'Chatbot', room: str, sender, message: str):
        """
        Called when a channel message is received.
        :param room: the room the message was sent to. If this is a private message, this is set to None.
        :param sender: the name of the sender of this message. Self-messages are ignored.
        :param message: the message content.
        """

    def on_join_room(self, client: 'Chatbot', room: str, who: Optional[str]):
        """
        Called when a user enters a room.
        :param room: the room that was joined.
        :param who: the nickname of the person who joined the room. If None, then it refers to the bot.
        """

    def on_leave_room(self, client: 'Chatbot', room: str, who: Optional[str]):
        """
        Called when a user leaves the room.
        :param room: the room that was left.
        :param who: the nickname of the person who joined the room. If None, then it refers to the bot.
        """


class Chatbot(metaclass=ABCMeta):
    """
    A chatbot abstraction, which provides a number of methods that the chatbot can use to interact with the users in
    some generic chatroom or protocol.
    """
    def __init__(self, connect_info: common.ConnectInfo, modules: Mapping[str, ChatbotModule]={}, **kwargs):
        self.connect_info = connect_info
        self.modules = modules
        # XXX : better way to log this. It's implied that MOST chatbots are going to be LogMixins, but not all of them.
        if kwargs and isinstance(self, LogMixin):
            for k in kwargs: self.warning("Unused parameter when creating chatbot: %s", k)

    def on_message(self, room: str, sender, message: str):
        for mod in self.modules.values():
            if room in mod.rooms:
                mod.on_message(self, room, sender, message)

    def on_join_room(self, room: str, who: Optional[str]):
        for mod in self.modules.values():
            if room in mod.rooms:
                mod.on_join_room(self, room, who)

    def on_leave_room(self, room: str, who: Optional[str]):
        for mod in self.modules.values():
            if room in mod.rooms:
                mod.on_leave_room(self, room, who)

    @abstractmethod
    def send_message(self, room: str, msg: str):
        """
        Sends a message to a room on the server. This is server-dependent.
        """

    def on_connect(self):
        """
        This method is invoked when the chatbot connects to its server.
        """

    @property
    def rooms(self):
        return set.union(*[set(m.rooms) for m in self.modules.values()])

    def run_forever(self, catch_ctrl_c: bool=True):
        """
        Runs this chatbot connection forever, asynchronously.
        """
        # XXX : this assumes that the chatbot is also a Protocol object. This should be fixed in the future. Maybe
        #       attach it to a protocol wrapper and derive from that? feels like overengineering...
        loop = asyncio.get_event_loop()
        coro = loop.create_connection(lambda: self, self.connect_info.server, self.connect_info.port)
        loop.run_until_complete(coro)
        if catch_ctrl_c:
            try:
                loop.run_forever()
            except KeyboardInterrupt as e:
                self.info("ctrl-C caught, exiting")
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
    def __init__(self, connect_info: irc.ConnectInfo, **kwargs):
        """
        Initializes the IRC chat bot.
        :param connect_info: the connection information to use
        """
        Chatbot.__init__(self, connect_info, **kwargs)
        irc.ClientProtocol.__init__(self, connect_info)
        self.connect_info = connect_info
        self.__nick_rotation = iter(self.connect_info.nicks)
        self.__nick = None
        self.__ready = False

    def on_connect(self):
        if self.connect_info.server_pass:
            self._send_command("PASS", self.connect_info.server_pass)
        self._send_command("USER", self.connect_info.user, '0', '*', 'Chatbot')
        self.__try_next_nick()

    def on_ready(self):
        """
        Event that is called when the IRC connection is ready to receive commands and messages. This is useful for
        setting up any necessary state for the given bot.
        """

    def send_message(self, target: str, msg: str):
        self._send_command('PRIVMSG', target, ":{}".format(msg))

    def _handle_irc_message(self, message: irc.Message):
        """
        Handles an IRC message.
        """
        if message.command == 'RPL_MYINFO':
            # MYINFO command handling; we've joined successfully and we're in a room.
            self.__ready = True
            self.on_ready()
        elif message.command in irc.response.NICK_ERRORS:
            # Invalid NICK errors handled here
            self.__try_next_nick()
        elif message.command == 'PING':
            # PING/PONG command handling
            if len(message.params) == 0:
                # NOTE: throw an error?
                self.error('invalid IRC PING message received: %s', msg)
                return
            msg = message.params[0]
            if msg[0] != ':':
                msg = ':' + msg
            self._send_command('PONG', msg)
        elif message.command == 'JOIN':
            # TODO : consolodate differences between "who" arg in on_join_room and on_leave_room
            # Join handling
            who = None if message.user.nick == self.nick else message.user
            room = message.params[0]
            self.on_join_room(room, who)
        elif message.command == 'KICK':
            # TODO : consolodate differences between "who" arg in on_join_room and on_leave_room
            # Kick handling
            room = message.params[0]
            who = message.params[1]
            self.on_leave_room(room, None if who == self.nick else who)
        elif message.command == 'PART':
            # TODO : consolodate differences between "who" arg in on_join_room and on_leave_room
            # Part handling
            room = message.params[0]
            who = message.user.nick
            self.on_leave_room(room, None if who == self.nick else who)
        elif message.command == 'NICK':
            # TODO : implement nickname change handler
            pass
        elif message.command == 'PRIVMSG':
            # PRIVMSG command handling
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

    @property
    def ready(self):
        return self.__ready


def chatbot_factory(connect_info: common.ConnectInfo, modules: Sequence[ChatbotModule]):
    """
    Creates a chatbot based on the type of connect info passed.
    """
    if isinstance(connect_info, irc.ConnectInfo):
        return IRCChatbot(connect_info, modules, desired_state)
    else:
        raise ValueError("Unknown ConnectInfo type: {}".format(repr(connect_info)))

