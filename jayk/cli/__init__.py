"""
Base CLI entry point and basic driver definitions.
"""

import os.path as path
import asyncio
import logging
import sys
from copy import deepcopy

from ..util import LogMixin
from .module import HelpModule, jayk_chatbot_factory
from .config import *
from .util import FileListener


log = logging.getLogger(__name__)


class JaykDriver(LogMixin):
    """
    A driver class for the Jayk bot framework CLI.
    This takes a loaded configuration, and spins up a set of bots corrseponding to it.
    """
    def __init__(self, config: JaykConfig):
        """
        Creates a new driver with the specified configuration.
        :param config: the configuration to create this driver from.
        """
        super().__init__("{}.JaykDriver".format(__name__))
        self.config = config
        self.bots = {}  # A list of bots, keyed by running servers
        self.loop = asyncio.get_event_loop()
        self.__running = False
        self.__config_listener = FileListener(config.config_path, self.__config_changed)
        for server in self.config.servers:
            self.initialize_bot(server)

    @property
    def running(self):
        """
        Gets whether the driver is running or not.
        """
        return self.__running

    def __config_changed(self):
        """
        Event that is fired whenever the configuration is changed for this driver.
        """
        # TODO : Locking
        new_config = deepcopy(self.config)
        new_config.reload()
        self.update_config(new_config)

    def update_config(self, new_config):
        """
        Program logic for updating the configuration of this server.
        """
        self.info("Updating server configurations")

        new_servers = set(new_config.servers.keys())
        old_servers = set(self.config.servers.keys())

        self.config = new_config
        to_add = new_servers - old_servers
        to_remove = old_servers - new_servers
        to_update = old_servers & new_servers
        for remove in to_remove:
            self.info("Closing connection to %s", remove)
            bot = self.bots.pop(remove)
            # TODO : on_close callbacks, and *then* call the close() function
            bot.close()
        for add in to_add:
            self.info("Adding bot for %s", add)
            self.initialize_bot(add)
            if self.running:
                self.info("Driver is currently running; initializing bot connection")
                self.bot_connect(add)
        for update in to_update:
            self.info("Updating bot for %s", update)
            self.bots[update].update_config(self.config.servers[update])

    def initialize_bot(self, server: str):
        """
        Sets up a bot to connect to a server, short of actually connecting.
        """
        assert server not in self.bots
        # TODO : add help module with customizable !help command
        #help_module = HelpModule(rooms=set())
        server_config = self.config.servers[server]
        connect_info = server_config.connect_info
        self.bots[server] = jayk_chatbot_factory(connect_info, config=server_config)

    def bot_connect(self, server: str):
        """
        Initializes a connection with a bot. The driver must be running for this to be allowed.
        """
        assert self.running
        self.info("Making connection for %s", server)
        bot = self.bots[server]
        try:
            coro = self.loop.create_connection(lambda: bot, bot.connect_info.server,
                                               bot.connect_info.port)
            self.loop.run_until_complete(coro)
        except Exception as ex:
            self.error("Could not connect to %s: %s", server, ex)

    def run_forever(self):
        """
        Starts the bot driver running... forever.
        """
        assert not self.running
        self.__running = True
        for server_name in self.bots:
            self.bot_connect(server_name)

        self.__config_listener.start()
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            self.info("ctrl-C caught; exiting")
            self.loop.stop()
            self.info("Stopping config file watcher")
            self.__config_listener.stop()
            self.__config_listener.join()
        self.loop.close()


def exit_critical(*args, **kwargs):
    """
    Emits a critical log message, and exits the program.
    """
    log.critical(*args, **kwargs)
    log.critical("exiting")
    sys.exit(1)


def jayk():
    """
    Main program entry point. Invoked by running `jayk` on the command line.
    """
    logging.basicConfig(level=logging.DEBUG)
    # Parse the configuration
    try:
        config = JaykConfig()
    except FileNotFoundError as ex:
        exit_critical("Could not find any of the expected config "
                      "files in the current directory: %s", ex)
    except JaykConfigError as ex:
        exit_critical("%s", ex)
    except Exception as ex:
        exit_critical("Unexpected error parsing config file: %s", ex)

    try:
        driver = JaykDriver(config)
        driver.run_forever()
    except Exception as ex:
        logging.exception('Unexpected error')
        exit_critical("Unexpected error was caught: %s", ex)


# TODO
# * code hot loading
# * nickserv handling
# * ssl support
# * new CLI class that handles things
# * better async code now that I know how to do it
# * async file watching (instead of current hackneyed multi-process watching)
