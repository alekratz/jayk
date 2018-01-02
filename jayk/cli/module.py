"""Jayk-specific chatbot modules, with extended configuration reloading."""
from typing import Optional

from .config import JaykConfig
from . import util
from ..chatbot import IRCChatbot, ChatbotModule
from .. import common
from .. import irc
from ..util import LogMixin


class JaykState:
    """
    Represents a chatbot's state on a server. This is contrasted with the *desired* state, which
    each server handler derives from its config. This state is per-server.

    The chatbot state holds a list of modules it has loaded, and a list of rooms it has joined.

    :param modules: the set of modules that have been loaded.
    :param rooms: the set of rooms that have been loaded.
    """
    def __init__(self, modules=None, rooms=None):
        if modules is None:
            modules = set()
        if rooms is None:
            rooms = set()
        self.modules = modules
        self.rooms = rooms

    @staticmethod
    def from_config(config):
        """
        Creates a new chatbot state from a configuration file. This is useful for determining the
        chatbot's "desired" state, versus its current state.

        :param obj: a dictionary of chatbot modules pointing to their configurations. This is the
                    equivalent of the "modules" section in the bots.yaml file for the cli
                    configuration.
        """
        modules = set()
        rooms = set()
        for module_name, module in config.items():
            if not module.enabled:
                continue
            modules |= {module_name}
            # Assume all rooms
            rooms |= set(module.rooms)
        return JaykState(modules, rooms)


class JaykChatbot(LogMixin):
    """
    The base chatbot that sits on a network, waiting for messages. Messages that this chatbot
    receives are multiplexed by channel and passed down to listening implementations.
    """
    __module_cache = {}

    def __init__(self, config):
        """
        Creates a new chatbot that listens on a given network.
        """
        LogMixin.__init__(self, JaykChatbot.__name__)
        self.config = util.AttrDict({'modules': {}})
        self.desired_state = None
        self.state = JaykState()
        self.update_config(config)

    def update_config(self, new_config):
        """
        This method is invoked when the module configuration for this server has changed. This
        mostly deals with modules being enabled and disabled and their parameters updated.

        :param new_config: the new configuration to update the chatbot with. This propagates down to
        all modules.
        """
        # TODO(hotload) unload/reloading of modules, maybe that will help with hot code reloading?
        # * Admin user could invoke a module reload?
        # * It's assumed that the current in-memory state goes away, so anything you need should be
        #     stored
        #   * For things like wordbot, you need a database to keep its state persistent between
        #     disconnects

        # Go through all modules, ask them to update
        assert hasattr(self, 'modules'), 'JaykChatbot does not have modules member; ' \
                                         'are you sure it derives from jayk.chatbot.Chatbot?'

        # Make sure that no disabled modules are included
        # make sure that this is an attrdict because it's how we'll be accessing it
        new_config = util.AttrDict(new_config).infect()
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

        This simply calls match_desired_modules, followed by match_desired_rooms. This should not be
        overridden.
        """
        self.match_desired_modules()
        self.match_desired_rooms()

    def match_desired_modules(self):
        """
        Called by `match_desired_state`. This is implemented by the base JaykChatbot class, but it
        can be overridden.
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
        self.warning("match_desired_rooms was not implemented; this could cause weird behavior")

    def load_module(self, name, config):
        """
        Loads a given module, caching it if not already loaded, and returning the cached version if
        it is.

        :param name: the name of the module to load.
        :param config: the configuration to load the module with.
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
        """
        Unloads a module with the given name. This simply removes the module from our contained
        modules, and calls its "on_unload()" method.

        :param name: the name of the module to unload.
        """
        self.debug("Unloading module %s", name)
        mod = self.modules.pop(name)
        mod.on_unload()

    def update_module(self, name, config):
        """
        Triggers a module with the given name to update with a new configuration.

        :param name: the name of the module to update.
        :param config: the configuration to update the module with.
        """
        self.debug("Updating module %s", name)
        mod = self.modules[name]
        mod.update_config(config)

    def get_module(self, name, path):
        """
        Gets a module for this chatbot using the given name and path. If the module has already been
        loaded, then it will return a cached version (indexed by path).

        :param name: the name of the module to retrieve.
        :param path: the to the module.
        """
        if path in JaykChatbot.__module_cache:
            self.debug("Using cached module for %s", name)
            return JaykChatbot.__module_cache[path]
        else:
            self.debug("Importing module %s (path: %s)", name, path)
            loaded_module = util.load_module(name, path)
            self.__module_cache[path] = loaded_module
            return loaded_module


class JaykIRCChatbot(JaykChatbot, IRCChatbot):
    """
    An IRC chatbot implementation, using the base JaykChatbot class. This mixes the implementations
    of jayk.module.JaykChatbot with jayk.chatbot.IRCChatbot to form a cohesive whole.
    """
    def __init__(self, config: JaykConfig = None, **kwargs):
        """
        Create a new chatbot object with the given configuration and any optional parameters for
        the IRCChatbot class.

        :param config: the configuration to use
        :param kwargs: any additional arguments to pass along to the IRCChatbot class. These kwargs
                       may include the specialized connection info for this class, or a sequence of
                       chatbot modules to install immediately upon construction.
        """
        IRCChatbot.__init__(self, **kwargs)
        JaykChatbot.__init__(self, config)

    def match_desired_rooms(self):
        """
        Tells this chatbot to attempt to join the list of rooms that are desired on this server. If
        the server's connection is not ready (e.g. we are still identifying or using Nickserv) then
        nothing will happen and the function will return.

        Otherwise, the chatbot will determine which rooms to join, and which rooms to leave, finally
        entering and exiting the desired rooms.
        """
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
        """
        This method is called when the chatbot is ready to perform actions. This implementation only
        calls `self.match_desired_state()`.
        """
        # Once the bot is ready, it should match the desired state
        self.match_desired_state()

    def _handle_irc_message(self, message: irc.Message):
        """
        Overrides the _handle_irc_message method to update the state, if necessary. This
        implementation checks to see if 'KICK', 'JOIN', or 'PART' messages were sent - if so, it
        will attempt to re-join all desired rooms.

        :param message: the message that was sent to this chatbot.
        """
        super()._handle_irc_message(message)
        if message.command.upper() in ['KICK', 'JOIN', 'PART']:
            self.match_desired_rooms()

    def on_join_room(self, room: str, who: Optional[str]):
        """
        This method is called whenever *any* user joins a room (including the chatbot itself). This
        implementation makes sure that our list of rooms that our chatbot knows about is up-to-date.

        :param room: the room that had a user join.
        :param who: the user who joined the room. If None, indicates that the user that joined was
                    the chatbot (us).
        """
        if who is None:
            self.state.rooms |= {room}
        super().on_join_room(room, who)

    def on_leave_room(self, room: str, who: Optional[str]):
        """
        This method is called whenever *any* user leaves a room (including the chatbot itself). This
        implementation makes sure that our list of rooms that our chatbot knows about is up-to-date.

        :param room: the room that had a user leave.
        :param who: the user who left the room. If None, indicates that the user that left was the
                    chatbot (us).
        """
        if who is None:
            self.state.rooms -= {room}
        super().on_leave_room(room, who)


# TODO Any more adapters here...


class JaykModule(ChatbotModule):
    """
    A cli-specific chatbot module.
    """
    def __init__(self, config, **kwargs):
        """
        Creates a new Jayk chatbot module with the specified configuration. All additional keyword
        arguments are passed on to the base `jayk.chatbot.ChatbotModule` class.

        :param config: the configuration that this module uses.
        :param kwargs: any additional keyword arguments for use in this chatbot module.
        """
        super().__init__(**kwargs)
        self.config = config

    def on_message(self, client, room, sender, message):
        """
        This method is called whenever a user message is sent (i.e. something that someone typed in
        and sent to the room).

        Since modules keep track of their own commands, this is where any command handlers are
        called (e.g. !help).

        :param client: the client that we received this message from.
        :param room: the room that this message was sent to.
        :param sender: the person who sent this message.
        :param message: the content of the entire message as a string.
        """
        parts = message.split()
        if parts:
            cmd = parts[0]
            if cmd in self.commands:
                self.commands[cmd](self, client, cmd, room, sender, message)

    def update_config(self, module_config):
        """
        Attempts to update the currently running module's configuration with a new one. Since both
        the 'rooms' and 'params' configuration values are optional, they will be set to empty sets
        and dictionaries, respectively.

        This method will call on_update_params() if it has been overridden.

        :param module_config: the module configuration to load.
        """
        self.rooms = module_config.rooms if 'rooms' in module_config else set()
        params = module_config.params if 'params' in module_config else util.AttrDict()
        self.on_update_params(params)

    def on_update_params(self, params):
        """
        Tells the module to update its params. This does not have to be implemented, although it may
        cause unexpected behavior if config reloading for this module is available. Any errors that
        occur are a failure on the part of the module implementation and not this library.

        :param params: the new params to load.
        """
        if params:
            self.warning("New params provided to module, but on_update_params() was not "
                         "implemented. New or updated params specified in the configuration file "
                         "will not be available for this module.")

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
    """
    A metaclass that provides boilerplate implementations and derivations of necessary classes to
    allow a class to act as a functional Jayk module.
    """
    def __new__(mcs, name, bases, namespace):
        """
        Implementation of class creation.

        The module is checked for the JaykModule base class - if this doesn't exist, it is added
        before anything else is attempted. Any decorated function (which uses the _jayk_commands
        attribute to denote its decoration) is given an implementation that handles that command
        being invoked by a chat room user.

        Finally, if the `on_message` method is overridden (for inspecting every message sent to the
        room/channel), AND there are decorated command methods, a *new* `on_message` wrapper method
        is created to make sure that all of the decorated commands are called when necessary while
        still passing unhandled messages to the `on_message()` override.
        """
        # Add the jaykmodule class if necessary
        if not any(map(lambda b: isinstance(b, JaykModule), bases)):
            bases += (JaykModule,)
        result = type.__new__(mcs, name, bases, dict(namespace))
        # Add command functions if necessary
        functions = [function for function in namespace.values()
                     if hasattr(function, "_jayk_commands")]
        result.commands = {}
        for function in functions:
            for cmd in function._jayk_commands:
                result.commands[cmd] = function
        # Override the on_message method if it's defined in this class to ignore all commands, only
        # if they're defined
        if result.commands and 'on_message' in namespace:
            result.__on_message_wrapped = result.on_message
            def on_message_wrapper(self, client, room, sender, msg):
                parts = msg.split(' ')
                if parts and parts[0] in self.commands:
                    cmd = parts[0]
                    self.commands[cmd](self, client, cmd, room, sender, msg)
                else:
                    self.__on_message_wrapped(client, room, sender, msg)
            result.on_message = on_message_wrapper
        return result


def jayk_command(cmd, *cmds):
    """
    A decorator which can be used on a module method to indicate that it should be called if there's
    a message starting with any of the given commands. For example:

    ```python
    class MyModule(meta=JaykMeta):
        @jayk_command("!magic", "!wizardry")
        def magic(self, client, cmd, room, sender, msg):
            # ... do some cool stuff here ...
    ```

    At least one command must be supplied, but auxiliary commands may be supplied as well.

    Note that any class this decorator appears in MUST use the `JaykMeta` metaclass.

    :param cmd: the command that this function should react to.
    :param cmds: any other commands that this function should react to.
    """
    def wrapper(function):
        function._jayk_commands = [cmd] + list(cmds)
        return function
    return wrapper


def jayk_chatbot_factory(connect_info: common.ConnectInfo, **kwargs):
    """
    Creates a CLI chatbot based on the type of connect info passed.

    :param connect_info: connection info for this Jayk chatbot. This is how the protocol (e.g. IRC,
                         Slack) is determined.
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
    """
    A basic help module that displays all available modules for use. This is sort of a special
    module that should probably not be used for a reference implementation of modules.
    """
    def __init__(self, **kwargs):
        """
        Creates the new help module. Doesn't take any extra arguments.
        """
        super().__init__(config={}, **kwargs)
        self.help_sections = []

    @jayk_command("!help")
    def help_cmd(self, client, _cmd, _room, sender, _msg):
        """
        Handles the !help command.
        """
        # TODO : allow customizing which command triggers this because of conflicting "!help"
        # commands.
        # TODO : help section breakdown
        # parts = msg.split()
        help_lines = []

        HELP_WIDTH = 40
        # HELP_TAIL = '-' * HELP_WIDTH
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
        """
        Adds a help string for the given module. In actuality, it just adds a pointer to the module
        itself so we don't have to update module strings every time we're in the mood to
        unload/reload a module.
        """
        self.help_sections += [module]
        self.state.rooms |= set(module.rooms)
