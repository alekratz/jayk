from ..util import LogMixin
from .module import *
from .config import *
from .util import *

import os.path as path
import asyncio
import logging
import sys
import importlib.util


log = logging.getLogger(__name__)


def load_module(module_name, path):
    """
    Loads a Python file as a module.
    """
    # Step 1: import
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Step 2: find the jayk bot
    for item in dir(module):
        cls = getattr(module, item)
        if isinstance(cls, JaykMeta):
            return cls
    raise JaykException("No valid module was found in {}".format(path))


class JaykDriver(LogMixin):
    """
    A driver class for the Jayk bot framework CLI.
    This takes a loaded configuration, and spins up a set of bots corrseponding to it.
    """
    def __init__(self, config: JaykConfig):
        super().__init__("{}.JaykDriver".format(__name__))
        self.config = config
        self.bots = {}  # A list of bots, keyed by running servers
        self.__module_cache = {}
        for server in self.config.servers:
            self.initialize_bot(server)

    def sync_bot_config(self, server):
        """
        Ensures a bot's configuration matches the given server's configuration
        """
        if server not in self.config.servers:
            # Server has been removed; close the connection and remove the bot
            assert server in self.bots, "Server scheduled to be removed, but was not present in the list of bots"
            bot = self.bots[server]
            self.bots.pop(server, None)
            bot.close()
        elif server in self.bots:
            # Already connected with this server, so update its config
            bot.update_module_config(self.config.servers[server].modules)
        else:
            # No registered bot with this name; create a new one
            self.initialize_bot(server)

    def initialize_bot(self, server: str):
        """
        Sets up a bot to connect to a server, short of actually connecting.
        """
        assert server not in self.bots
        help_module = HelpModule(rooms=set())
        loaded_modules = [help_module]
        server_config = self.config.servers[server]
        server_modules = server_config.modules
        for mod_name, mod in server_modules.items():
            # Pass by disabled modules
            if not mod.enabled: continue
            try:
                self.info("Loading module %s", mod_name)
                loaded_module = self.get_module(mod_name, mod.path)
            except Exception as ex:
                self.error("Could not load module %s: %s", mod_name, ex)
                self.debug("Module information: %s", mod)
            else:
                # Add the module to the list of loaded modules
                module_instance = loaded_module(**mod.params, config=mod, rooms=mod.rooms)
                loaded_modules += [module_instance]
                help_module.add_module_help(module_instance)
        connect_info = server_config.connect_info
        self.bots[server] = jayk_chatbot_factory(connect_info, modules=loaded_modules, config=server_config)

    def get_module(self, name: str, path: Optional[str]):
        """
        Gets a module, one which has either been loaded or cached based on its path.
        :param name: name of the module that is being loaded
        :param path: path for the module that is being loaded. This may be None, and the path is derived to be the name
                     parameter with `.py` tacked on to the end of it.
        """
        if path is None:
            path = name + ".py"
        if path in self.__module_cache:
            return self.__module_cache[path]
        else:
            self.debug("Importing script %s", path)
            loaded_module = load_module(name, path)
            self.__module_cache[path] = loaded_module
            return loaded_module

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


def config_changed(servers, module_setttings, file_path):
    raise NotImplementedError("TODO")


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
