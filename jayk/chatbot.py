from abc import ABCMeta, abstractmethod
import asyncio
import re
from typing import *
from copy import deepcopy
from . import common
from . import util
from . import irc


class ChatbotState:
    """
    Represents a chatbot's state on a server. This is contrasted with the *desired* state, which each server handler
    derives from its config. This state is per-server.

    The chatbot state holds a list of modules it has loaded, and a list of rooms it has joined.
    """
    def __init__(self, modules, rooms):
        self.modules = modules
        self.rooms = rooms

    @staticmethod
    def from_config(config, for_server=None):
        """
        Creates a new chatbot state from a configuration file. This is useful for determining the chatbot's "desired"
        state, versus its current state.
        :param obj: a dictionary of chatbot modules pointing to their configurations. This is the equivalent of the
                    "modules" section in the bots.yaml file for the cli configuration.
        :param for_server: the server that this state concerns. If not specified, it assumes all servers.
        """
        modules = set()
        rooms = set()
        for module_name in config:
            module = config[module_name]
            modules |= {module_name}
            if 'servers' in module:
                # All servers
                if for_server is None:
                    rooms |= set.union(*[module['servers'][r] for r in module['servers']])
                # This server
                else:
                    rooms |= set(module['servers'][for_server])
            elif 'rooms' in module:
                # Assume all rooms
                rooms |= set(modules['rooms'])
        return ChatbotState(modules, rooms)


class ChatbotModule(util.LogMixin):
    def __init__(self, rooms: Set[str]):
        """
        Initializes a chatbot module.
        :param rooms: the list of rooms this bot is active in.
        """
        super().__init__(__name__)
        self.rooms = rooms

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


class JaykModule(ChatbotModule):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_message(self, client, room, sender, msg):
        parts = msg.split()
        if parts:
            cmd = parts[0]
            if cmd in self.commands:
                self.commands[cmd](self, client, cmd, room, sender, msg)
    # Module metadata methods
    @staticmethod
    def author():
        """
        Gets the name of the author for this module
        """
        return ''

    @staticmethod
    def name():
        """
        Gets the name of this module
        """
        return ''

    @staticmethod
    def about():
        """
        Gets a basic description of this module
        """
        return ''


class JaykMeta(type):
    def __new__(metacls, name, bases, namespace, **kwargs):
        # Add the jaykmodule class if necessary
        if not any(map(lambda b: isinstance(b, JaykModule), bases)):
            bases += (JaykModule,)
        result = type.__new__(metacls, name, bases, dict(namespace))
        functions = [function for function in namespace.values() if hasattr(function, "_jayk_commands")]
        result.commands = { }
        for function in functions:
            for cmd in function._jayk_commands:
                result.commands[cmd] = function
        return result


def jayk_command(cmd, *cmds):
    def wrapper(function):
        function._jayk_commands = [cmd] + list(cmds)
        return function
    return wrapper


class Chatbot(metaclass=ABCMeta):
    """
    A chatbot abstraction, which provides a number of methods that the chatbot can use to interact with the users in
    some generic chatroom or protocol.
    """
    def __init__(self, connect_info: common.ConnectInfo, modules: Sequence[ChatbotModule], desired_state: ChatbotState):
        self.connect_info = connect_info
        self.modules = modules
        self.desired_state = desired_state
        self.state = ChatbotState(deepcopy(desired_state.modules), set())
        self.rooms = set.union(*[set(m.rooms) for m in modules])

    @abstractmethod
    def match_desired_state(self):
        """
        Makes the chatbot protocol match the current state to the desired state.
        """

    def on_message(self, room: str, sender, message: str):
        for mod in self.modules:
            if room in mod.rooms:
                mod.on_message(self, room, sender, message)

    def on_join_room(self, room: str, who: Optional[str]):
        for mod in self.modules:
            if room in mod.rooms:
                mod.on_join_room(self, room, who)

    def on_leave_room(self, room: str, who: Optional[str]):
        for mod in self.modules:
            if room in mod.rooms:
                mod.on_leave_room(self, room, who)

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
    def __init__(self, connect_info: irc.ConnectInfo, modules: Sequence[ChatbotModule], desired_state):
        """
        Initializes the IRC chat bot.
        :param connect_info: the connection information to use
        """
        Chatbot.__init__(self, connect_info, modules, desired_state)
        irc.ClientProtocol.__init__(self, connect_info)
        self.connect_info = connect_info
        self.__nick_rotation = iter(self.connect_info.nicks)
        self.__nick = None
        self.__ready = False

    def match_desired_state(self):
        # Only match the desired state when we're ready
        if not self.__ready:
            self.info("Not ready to sync current state with desired state")
            return
        self.info("Syncing current state with desired state")
        # Sync modules
        if self.state.modules != self.desired_state.modules:
            self.debug("Syncing modules")
            # TODO : Module unloading/reloading
            self.warning("Current state of modules does not match desired state! This has not yet been implemented.")
            self.warning("Things may get weird.")
        else:
            self.debug("No modules to sync")

        # Sync rooms
        if self.state.rooms != self.desired_state.rooms:
            self.debug("Syncing rooms")
            to_leave = self.state.rooms - self.desired_state.rooms
            to_join = self.desired_state.rooms - self.state.rooms
            if to_leave:
                self.info("Leaving these rooms: %s", to_leave)
                self._send_command("PART", ",".join(to_leave))
            if to_join:
                self.info("Joining these rooms: %s", to_join)
                self._send_command("JOIN", ",".join(to_join))
        else:
            self.debug("No rooms to sync")

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
            # MYINFO command handling; we've joined successfully and we're in a room.
            self.__ready = True
            self.match_desired_state()
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
            self.match_desired_state()
        elif message.command == 'KICK':
            # TODO : consolodate differences between "who" arg in on_join_room and on_leave_room
            # Kick handling
            room = message.params[0]
            who = message.params[1]
            self.on_leave_room(room, None if who == self.nick else who)
            self.match_desired_state()
        elif message.command == 'PART':
            # TODO : consolodate differences between "who" arg in on_join_room and on_leave_room
            # Part handling
            room = message.params[0]
            who = message.user.nick
            self.on_leave_room(room, None if who == self.nick else who)
            self.match_desired_state()
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


def chatbot_factory(connect_info: common.ConnectInfo, modules, desired_state):
    if isinstance(connect_info, irc.ConnectInfo):
        return IRCChatbot(connect_info, modules, desired_state)
    else:
        raise ValueError("Unknown ConnectInfo type: {}".format(repr(connect_info)))

