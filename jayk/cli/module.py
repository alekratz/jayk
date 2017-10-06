from ..chatbot import JaykMeta, jayk_command
from typing import *


class HelpModule(metaclass=JaykMeta):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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

