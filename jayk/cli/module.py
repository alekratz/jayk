from .config import JaykConfig
from . import util
from ..chatbot import IRCChatbot, ChatbotModule
from .. import common
from .. import irc
from ..util import LogMixin

from typing import *
from copy import deepcopy


class JaykState:
    """
    Represents a chatbot's state on a server. This is contrasted with the *desired* state, which each server handler
    derives from its config. This state is per-server.

    The chatbot state holds a list of modules it has loaded, and a list of rooms it has joined.
    """
    def __init__(self, modules=set(), rooms=set()):
        self.modules = modules
        self.rooms = rooms

    @staticmethod
    def from_config(config):
        """
        Creates a new chatbot state from a configuration file. This is useful for determining the chatbot's "desired"
        state, versus its current state.
        :param obj: a dictionary of chatbot modules pointing to their configurations. This is the equivalent of the
                    "modules" section in the bots.yaml file for the cli configuration.
        """
        modules = set()
        rooms = set()
        for module_name, module in config.items():
            if not module.enabled: continue
            modules |= {module_name}
            # Assume all rooms
            rooms |= set(module.rooms)
        return JaykState(modules, rooms)


class JaykChatbot(LogMixin):
    __module_cache = {}

    def __init__(self, config):
        self.config = util.AttrDict({'modules': {}})
        self.desired_state = None
        self.state = JaykState()
        self.update_config(config)

    def update_config(self, new_config):
        """
        This method is invoked when the module configuration for this server has changed. This mostly deals with modules
        being enabled and disabled and their parameters updated.
        """
        # TODO(hotload) unload/reloading of modules, maybe that will help with hot code reloading?
        # * Admin user could invoke a module reload?
        # * It's assumed that the current in-memory state goes away, so anything you need should be stored
        #   * For things like wordbot, you need a database to keep its state persistent between disconnects
        # Go through all modules, ask them to update
        assert hasattr(self, 'modules'), 'JaykChatbot does not have modules member; are you sure it derives from jayk.chatbot.Chatbot?'

        # Make sure that no disabled modules are included
        new_config = util.AttrDict(new_config).infect()  # make sure that this is an attrdict because it's how we'll be accessing it
        new_config.modules = util.AttrDict({
                name: mod for name, mod in new_config.modules.items() if mod.enabled
            })

        # Create the new desired state, and get it to match
        self.config = new_config
        self.desired_state = JaykState.from_config(self.config.modules)
        self.match_desired_state()

    def match_desired_state(self):
        """
        Attempts to match the current state with the desired state.

        This simply calls match_desired_modules, followed by match_desired_rooms. This should not be overridden.
        """
        self.match_desired_modules()
        self.match_desired_rooms()

    def match_desired_modules(self):
        """
        Called by `match_desired_state`. This is implemented by the base JaykChatbot class, but it can be overridden.
        """
        self.debug("Matching desired modules")
        old_modules = set(self.state.modules)
        new_modules = set(self.config.modules.keys())

        to_add = new_modules - old_modules
        to_remove = old_modules - new_modules
        to_update = new_modules & old_modules

        for remove in to_remove:
            self.unload_module(remove)
        for add in to_add:
            self.load_module(add, self.config.modules[add])
        for update in to_update:
            self.update_module(update, self.config.modules[update])
        self.state.modules = set(self.modules.keys())

    def match_desired_rooms(self):
        """
        Called by `match_desired_state`. This should be implemented by the overriding adapter.
        """
        self.warning("match_desired_rooms was not implemented; this could cause some weird behavior.")

    def load_module(self, name, config):
        """
        Loads a given module, caching it if not already loaded, and returning the cached version if it is.
        """
        if not config.enabled:
            return
        self.debug("Loading module %s", name)
        path = config.path
        if not path:
            path = name + '.py'
        loaded_module = self.get_module(name, path)
        module_instance = loaded_module(**config.params, config=config, rooms=config.rooms)
        self.modules[name] = module_instance

    def unload_module(self, name):
        self.debug("Unloading module %s", name)
        mod = self.modules.pop(name)
        mod.on_unload()

    def update_module(self, name, config):
        self.debug("Updating module %s", name)
        mod = self.modules[name]
        mod.update_config(config)

    def get_module(self, name, path):
        if path in JaykChatbot.__module_cache:
            self.debug("Using cached module for %s", name)
            return JaykChatbot.__module_cache[path]
        else:
            self.debug("Importing module %s (path: %s)", name, path)
            loaded_module = util.load_module(name, path)
            self.__module_cache[path] = loaded_module
            return loaded_module


class JaykIRCChatbot(JaykChatbot, IRCChatbot):
    def __init__(self, config: JaykConfig=None, **kwargs):
        IRCChatbot.__init__(self, **kwargs)
        JaykChatbot.__init__(self, config)

    def match_desired_rooms(self):
        # Only match the desired state when we're ready
        if not self.ready:
            self.info("Not ready to sync current state with desired state")
            return
        self.info("Syncing current rooms with desired rooms")

        # Sync rooms
        old_rooms = set(self.state.rooms)
        new_rooms = set(self.desired_state.rooms)
        self.debug("Old rooms: %s", old_rooms)
        self.debug("New rooms: %s", new_rooms)

        to_leave = old_rooms - new_rooms
        to_join = new_rooms - old_rooms
        if to_leave:
            self.info("Leaving these rooms: %s", to_leave)
            self._send_command("PART", ",".join(to_leave))
        if to_join:
            self.info("Joining these rooms: %s", to_join)
            self._send_command("JOIN", ",".join(to_join))

    def on_ready(self):
        # Once the bot is ready, it should match the desired state
        self.match_desired_state()

    def _handle_irc_message(self, msg: irc.Message):
        """
        Overrides the _handle_irc_message method to update the state, if necessary
        """
        super()._handle_irc_message(msg)
        if msg.command.upper() in ['KICK', 'JOIN', 'PART']:
            self.match_desired_rooms()

    def on_join_room(self, room: str, who: Optional[str]):
        if who is None:
            self.state.rooms |= {room}
        super().on_join_room(room, who)

    def on_leave_room(self, room: str, who: Optional[str]):
        if who is None:
            self.state.rooms -= {room}
        super().on_leave_room(room, who)


# TODO Any more adapters here...


class JaykModule(ChatbotModule):
    """
    A cli-specific chatbot module.
    """
    def __init__(self, config, **kwargs):
        super().__init__(**kwargs)
        self.config = config

    def on_message(self, client, room, sender, msg):
        parts = msg.split()
        if parts:
            cmd = parts[0]
            if cmd in self.commands:
                self.commands[cmd](self, client, cmd, room, sender, msg)

    def update_config(self, module_config):
        """
        Attempts to update the currently running module's configuration with a new one.
        """
        self.rooms = module_config.rooms if 'rooms' in module_config else set()
        params = module_config.params if 'params' in module_config else util.AttrDict()
        self.on_update_params(params)

    def on_update_params(self, params):
        """
        Tells the module to update its params. This does not have to be implemented, although it may cause unexpected
        behavior if config reloading for this module is available.
        """
        if params:
            self.warning("New params provided to module, but on_update_params() was not implemented. New or updated "
                         "params specified in the configuration file will not be available for this module.")

    def on_unload(self):
        """
        This event is called whenever the module is unloaded, via a configuration reload.
        """

    # Module metadata methods
    @staticmethod
    def author():
        """
        Gets the name of the author for this module
        """
        return 'anonymous'

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
        return 'A nondescript module.'


class JaykMeta(type):
    def __new__(metacls, name, bases, namespace, **kwargs):
        # Add the jaykmodule class if necessary
        if not any(map(lambda b: isinstance(b, JaykModule), bases)):
            bases += (JaykModule,)
        result = type.__new__(metacls, name, bases, dict(namespace))
        # Add command functions if necessary
        functions = [function for function in namespace.values() if hasattr(function, "_jayk_commands")]
        result.commands = { }
        for function in functions:
            for cmd in function._jayk_commands:
                result.commands[cmd] = function
        # Override the on_message method if it's defined in this class to ignore all commands, only if they're defined
        if len(result.commands) > 0 and 'on_message' in namespace:
            result.__on_message_wrapped = result.on_message
            def on_message_wrapper(self, client, room, sender, msg):
                parts = msg.split(' ')
                if len(parts) > 0 and parts[0] in self.commands:
                    cmd = parts[0]
                    self.commands[cmd](self, client, cmd, room, sender, msg)
                else:
                    self.__on_message_wrapped(client, room, sender, msg)
            result.on_message = on_message_wrapper
        return result


def jayk_command(cmd, *cmds):
    def wrapper(function):
        function._jayk_commands = [cmd] + list(cmds)
        return function
    return wrapper


def jayk_chatbot_factory(connect_info: common.ConnectInfo, **kwargs):
    """
    Creates a CLI chatbot based on the type of connect info passed.
    """
    if isinstance(connect_info, irc.ConnectInfo):
        return JaykIRCChatbot(connect_info=connect_info, **kwargs)
    # TODO Any more adapters here ...
    else:
        raise ValueError("Unknown ConnectInfo type: {}".format(repr(connect_info)))


################################################################################
# Base module implementations                                                  #
################################################################################


class HelpModule(metaclass=JaykMeta):
    def __init__(self, **kwargs):
        super().__init__(config={}, **kwargs)
        self.help_sections = []

    @jayk_command("!help")
    def help_cmd(self, client, cmd, room, sender, msg):
        parts = msg.split()
        help_lines = []

        HELP_WIDTH = 40
        HELP_TAIL = '-' * HELP_WIDTH
        for module in self.help_sections:
            # Header
            module_name = type(module).name()
            header_line = '- {} '.format(module_name)
            header_line += '-' * (HELP_WIDTH - len(header_line))
            # Command info
            about_line = type(module).about()
            commands_line = "Available commands: {}".format(', '.join(module.commands.keys()))
            help_lines += [header_line, about_line, commands_line]
            # TODO : room info
        for line in help_lines:
            if line:  # Don't send blank lines
                client.send_message(sender.nick, line)

    def add_module_help(self, module):
        self.help_sections += [module]
        self.rooms |= set(module.rooms)

