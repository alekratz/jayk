"""Common structures among bot strategies"""


class ConnectInfo(object):
    """
    Base connection info for a bot to connect. This is encouraged to be overridden for each new bot
    strategy implemented, although it is not required.
    """
    def __init__(self, server: str, port: int):
        """
        Creates a new ConnectInfo with the specified server and port.

        :param server: the server to connect to.
        :param port: the port to connect to the server on.
        """
        self.server = server
        self.port = port


def connect_info_factory(info_type: str, **kwargs):
    """
    Creates a specific ConnectInfo based on the type of connection we are looking for. Any
    additional kwargs specified are passed on to the appropriate ConnectInfo constructor.

    :param info_type: the connection info type to make. For example, 'irc'.
    :param kwargs: any additional keyword arguments to pass to the constructor.
    """
    # add more connectinfo as necessary
    from .irc import ConnectInfo as IRCConnectInfo
    if info_type.lower() == "irc":
        return IRCConnectInfo(**kwargs)
    else:
        raise ValueError("Unknown ConnectInfo type: {}".format(info_type))


class NoMoreNicksError(Exception):
    """
    An error that gets raised when all nickname options for this bot have been exhausted by the
    server.
    """
    def __init__(self, connect_info: ConnectInfo):
        """
        Creates a new instance of this error with the connection info that was used to connect to
        this server.

        :param connect_info: the connection info to build this error from.
        """
        super().__init__("No more available nicknames for {}:{}", connect_info.server,
                         connect_info.port)
