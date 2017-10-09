from ..chatbot import IRCChatbot, ChatbotModule
from .config import JaykConfig
from .. import common
from .. import irc

from typing import *
from copy import deepcopy


class JaykState:
    """
    Represents a chatbot's state on a server. This is contrasted with the *desired* state, which each server handler
    derives from its config. This state is per-server.

    The chatbot state holds a list of modules it has loaded, and a list of rooms it has joined.
    """
    def __init__(self, modules, rooms):
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
            modules |= {module_name}
            # Assume all rooms
            rooms |= set(module.rooms)
        return JaykState(modules, rooms)


class JaykChatbot:
    def __init__(self, config: JaykConfig, desired_state: JaykState):
        self.config = config
        self.desired_state = JaykState.from_config(self.config.modules)
        self.state = JaykState(deepcopy(self.desired_state.modules), set())

    def update_module_config(self, new_config: JaykConfig):
        """
        This method is invoked when the module configuration for this server has changed. This mostly deals with modules
        being enabled and disabled and their parameters updated.
        """
        # TODO(hotload) unload/reloading of modules, maybe that will help with hot code reloading?
        # * Admin user could invoke a module reload?
        # * It's assumed that the current in-memory state goes away, so anything you need should be stored
        #   * For things like wordbot, you need a database to keep its state persistent between disconnects
        raise NotImplementedError("TODO")
        # Go through all modules, ask them to update
        assert hasattr(self, 'modules'), 'JaykChatbot does not have modules member; are you sure it derives from jayk.chatbot.Chatbot?'

    def match_desired_state(self):
        raise NotImplementedError('This should be implemented by the chatbot adapter')


class JaykIRCChatbot(JaykChatbot, IRCChatbot):
    def __init__(self, config: JaykConfig=None, desired_state: JaykState=None, **kwargs):
        JaykChatbot.__init__(self, config, desired_state)
        IRCChatbot.__init__(self, **kwargs)

    def match_desired_state(self):
        # Only match the desired state when we're ready
        if not self.ready:
            self.info("Not ready to sync current state with desired state")
            return
        self.info("Syncing current state with desired state")
        # Sync modules
        if self.state.modules != self.desired_state.modules:
            self.debug("Syncing modules")
            # TODO(hotload) Module unloading/reloading
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

    def on_ready(self):
        # Once the bot is ready, it should match the desired state
        self.match_desired_state()

    def _handle_irc_message(self, msg: irc.Message):
        """
        Overrides the _handle_irc_message method to update the state, if necessary
        """
        super()._handle_irc_message(msg)
        if msg.command.upper() in ['KICK', 'JOIN', 'PART', 'NICK']:
            self.match_desired_state()


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
        raise NotImplementedError("TODO")

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

