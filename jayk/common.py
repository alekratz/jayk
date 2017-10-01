# common.py
# Common structures among bot strategies


class ConnectInfo(object):
    def __init__(self, server: str, port: int):
        self.server = server
        self.port = port


def connect_info_factory(info_type: str, **kwargs):
    # TODO : add more connectinfo as necessary
    from .irc import ConnectInfo as IRCConnectInfo
    if info_type.lower() == "irc":
        return IRCConnectInfo(**kwargs)
    else:
        raise ValueError("Unknown ConnectInfo type: {}".format(info_type))


class NoMoreNicksError(Exception):
    def __init__(self, connect_info: ConnectInfo):
        super().__init__("No more available nicknames for {}:{}", connect_info.server, connect_info.port)
