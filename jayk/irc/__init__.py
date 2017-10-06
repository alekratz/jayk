import re
import asyncio
import functools
from abc import ABCMeta, abstractmethod
from typing import *
from ..util import LogMixin
from .. import common
from . import response


__all__ = ["ConnectInfo", "ClientProtocol", "Message", "response"]


class User:
    def __init__(self, nick, username, host):
        self.nick = nick
        self.username = username
        self.host = host

    RE = re.compile("(?P<nick>[^!]+)!(?P<user>[^@]+)@(?P<host>.+)")

    @staticmethod
    def parse(s: str):
        match = User.RE.match(s)
        if not match:
            raise ValueError("Invalid user pattern")
        nick = match.group('nick')
        username = match.group('user')
        host = match.group('host')
        return User(nick, username, host)


class ConnectInfo(common.ConnectInfo):
    """
    IRC-specific connect info.
    """
    def __init__(self, server: str, nicks: Sequence[str], user: str,
                 port: Optional[int]=None, server_pass: Optional[str]=None, ssl: Optional[bool]=None):
        """
        Creates a new ConnectInfo object for IRC connections.
        :param server: IRC the server to connect to.
        :param nicks: the list of nicknames to attempt to use. There must be at least one nickname in this list.
        :param user: the username to use on the IRC server.
        :param port: the port to connect to the IRC server on. Optional. Default is 6667.
        :param server_pass: the password used to connect to the IRC server. Optional. Default is None.
        :param ssl: whether or not to use SSL to connect to the IRC server. Optional. Default is True if port is 6697,
                    otherwise False.
        """
        if len(nicks) == 0:
            raise ValueError("number of nicks specified in ConnectInfo must contain at least one nick")
        # default port 6667
        if port is None:
            port = 6667
        super().__init__(server, port)
        self.nicks = nicks
        self.user = user
        self.server_pass = server_pass
        if ssl is None:
            self.ssl = (port == 6697)
        else:
            self.ssl = ssl


class Message(object):
    """
    An IRC message with an optional prefix, a command, and optional parameters.
    """
    def __init__(self, prefix: Optional[str], command: str, params: Sequence[str]):
        """
        Creates an IRC message. This constructor does no validation of parameters beforehand.
        :param prefix: the prefix for the message.
        :param command: the command to pass, as a string.
        :param params: the parameters to pass.
        """
        self.prefix = prefix
        try:
            self.user = User.parse(self.prefix)
        except:
            self.user = None
        self.command = command
        self.params = params

    def __str__(self):
        """
        Formats the IRC message for sending, excluding CRLF.
        :return:
        """
        message = ''
        if self.prefix:
            message += ':{} '.format(self.prefix)
        message += self.command.upper()
        if self.params:
            message += " {}".format(' '.join(self.params))
        return message

    MESSAGE_RE = re.compile(
        '^(:(?P<prefix>[^ ]+) )?(?P<command>[a-zA-Z]+|[0-9]{3})(?P<params>( [^: \r\n]+)*)(?P<trailing> :[^\r\n]+)?$',
        re.MULTILINE)
    @staticmethod
    def parse(line: str):
        """
        Parses an IRC message.
        :param line: the message to parse
        :raises ValueError: if the line is malformed.
        :return: the parsed message
        """
        match = Message.MESSAGE_RE.match(line)
        if not match:
            raise ValueError("invalid IRC message: {}".format(line))
        prefix = match.group('prefix')
        command = match.group('command')
        try:
            command = response.CODE_TO_NAME[int(command)]
        except: pass
        params = list(filter(len, match.group('params').split(' ')))
        trailing = match.group('trailing')
        if trailing:
            params += [trailing[2:]]
        return Message(prefix, command, params)


class ClientProtocol(asyncio.Protocol, LogMixin, metaclass=ABCMeta):
    """
    The IRC asyncio protocol implementation.
    """
    def __init__(self, connect_info: ConnectInfo):
        """
        Creates a new IRC client protocol object, using the given connection info.
        """
        self.connect_info = connect_info
        self.transport = None
        LogMixin.__init__(self, "{}@{}".format(connect_info.user, connect_info.server))

    def connection_made(self, transport):
        assert self.transport is None, "transport must be unset after disconnection"
        self.info("connected")
        self.transport = transport

    def data_received(self, data):
        for line in filter(len, data.decode().split('\r\n')):
            self.debug("%s", line)

    def connection_lost(self, exc):
        # exc is either an exception or None
        # see: https://docs.python.org/3/library/asyncio-protocol.html#asyncio.BaseProtocol.connection_lost
        self.info("connection lost")
        self.transport = None
        # TODO : auto-reconnect module

    def _make_message(self, command: str, *params: str):
        """
        Constructs an IRC message from a command and its params.
        """
        return Message(prefix=None, command=command, params=params)

    def _send_message(self, msg: Message):
        """
        Sends a message to the IRC server.
        :param msg: the message structured to send.
        """
        # use a variable here because otherwise it gets calculated twice; in the log and when it's used
        msg_str = str(msg)
        self.debug("%s", msg_str)
        self.transport.write("{}\r\n".format(msg_str).encode())

    def _send_command(self, command: str, *params: str):
        """
        Constructs an IRC message from a command and its params, and sends it.
        :param command: the command to construct
        :param params: any parameters the command expects
        """
        self._send_message(self._make_message(command, *params))

    def _schedule_command(self, timeout, command: str, *params: str):
        """
        Schedules a command to be sent in a given number of seconds.

        """
        loop = asyncio.get_event_loop()
        send_command = functools.partial(self._send_command, command, *params)
        loop.call_later(timeout, send_command)
        # TODO : store the callback from loop.call_later() somewhere, so we can cancel messages or whatever
