from ..util import LogMixin
from .module import *
from .config import *
from .util import *

import os.path as path
import asyncio
import logging
import sys


log = logging.getLogger(__name__)


class JaykDriver(LogMixin):
    """
    A driver class for the Jayk bot framework CLI.
    This takes a loaded configuration, and spins up a set of bots corrseponding to it.
    """
    def __init__(self, config: JaykConfig):
        super().__init__("{}.JaykDriver".format(__name__))
        self.config = config
        self.bots = {}  # A list of bots, keyed by running servers
        for server in self.config.servers:
            self.initialize_bot(server)

    def sync_bot_config(self, server):
        """
        Ensures a bot's configuration matches the given server's configuration
        """
        if server not in self.config.servers:
            # Server has been removed; close the connection and remove the bot
            assert server in self.bots, "Server scheduled to be removed, but was not present in the list of bots"
            bot = self.bots.pop(server)
            bot.close()
        elif server in self.bots:
            # Already connected with this server, so update its config
            bot.update_config(self.config.servers[server])
        else:
            # No registered bot with this name; create a new one
            self.initialize_bot(server)

    def initialize_bot(self, server: str):
        """
        Sets up a bot to connect to a server, short of actually connecting.
        """
        assert server not in self.bots
        help_module = HelpModule(rooms=set())
        server_config = self.config.servers[server]
        connect_info = server_config.connect_info
        self.bots[server] = jayk_chatbot_factory(connect_info, config=server_config)

    def run_forever(self):
        loop = asyncio.get_event_loop()
        for server_name, bot in self.bots.items():
            self.info("Making connection for %s", server_name)
            try:
                coro = loop.create_connection(lambda: bot, bot.connect_info.server, bot.connect_info.port)
                loop.run_until_complete(coro)
            except Exception as ex:
                self.error("Could not connect to %s: %s", server_name, ex)
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            self.info("ctrl-C caught; exiting")
            loop.stop()
        loop.close()


def exit_critical(*args, **kwargs):
    """
    Emits a critical log message, and exits the program.
    """
    log.critical(*args, **kwargs)
    log.critical("exiting")
    sys.exit(1)


def jayk():
    logging.basicConfig(level=logging.DEBUG)
    # Parse the configuration
    try:
        config = JaykConfig()
    except FileNotFoundError as ex:
        exit_critical("Could not find any of the expected config files in the current directory: %s", ex)
    except JaykConfigError as ex:
        exit_critical("%s", ex)
    #except Exception as ex:
    #    exit_critical("Error parsing config file: %s", ex)

    #try:
    driver = JaykDriver(config)
    driver.run_forever()
    #except Exception as ex:
    #    exit_critical("Unexpected error was caught: %s", ex)


# TODO
# * code hot loading
# * auto config loading
# * nickserv handling
# * ssl support
# * new CLI class that handles things
