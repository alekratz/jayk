from .chatbot import CommandModule, chatbot_factory
from .common import connect_info_factory
import asyncio
import logging
import os.path as path
import sys
import importlib.util


logger = logging.getLogger(__name__)


class HelpModule(CommandModule):
    def __init__(self, **kwargs):
        super().__init__(commands={'!help'}, **kwargs)
        self.help_sections = []

    def on_command(self, client, cmd, room, sender, msg):
        parts = msg.split()
        help_lines = []

        HELP_WIDTH = 40
        HELP_TAIL = '-' * HELP_WIDTH
        for info in self.help_sections:
            # Header
            module_name = info['name']
            header_line = '- {} '.format(module_name)
            header_line += '-' * (HELP_WIDTH - len(header_line))
            # Command info
            about_line = info['about'] if 'about' in info else ''
            commands_line = "Available commands: {}".format(', '.join(info['commands']))
            help_lines += [header_line, about_line, commands_line, HELP_TAIL]
        for line in help_lines:
            client.send_message(sender.nick, line)

    def add_module_help(self, module):
        info = module.INFO
        self.help_sections += [info]


def load_module(module_name, path=None):
    if path is None:
        path = module_name + ".py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exit_critical(*args, **kwargs):
    logger.critical(*args, **kwargs)
    sys.exit(1)


def parse_config():
    import json
    configs = {'bots.json': json.loads}
    try:
        import yaml
        configs['bots.yaml'] = configs['bots.yml'] = yaml.load
    except:
        logger.debug("could not import YAML; skipping searching for bots.yaml and bots.yml")
    config_path = None
    for f in configs:
        logger.debug("looking for %s", f)
        if path.isfile(f):
            config_path = f
            break
    if config_path == None:
        raise FileNotFoundError(', '.join(configs.keys()))
    with open(config_path) as fp:
        contents = fp.read()
    return configs[config_path](contents)


def jayk():
    logging.basicConfig(level=logging.DEBUG)
    # Parse the configuration
    try:
        config = parse_config()
    except FileNotFoundError as ex:
        exit_critical("Could not find any of the expected config files in the current directory: %s", ex)
    except Exception as ex:
        exit_critical("Error parsing config file: %s", ex)

    # Get server connect info
    servers = {}
    try:
        for server in config['servers']:
            server_type = server['type']
            server.pop('type', None)
            servers[server['server']] = {'connect_info': connect_info_factory(server_type, **server)}
    except KeyError as ex:
        exit_critical("Error while parsing server config: could not find key %s", ex)
    except Exception as ex:
        exit_critical("Error while parsing server config: %s", ex)

    # Get modules
    module_settings = {}
    try:
        for module_name in config['modules']:
            module = config['modules'][module_name]
            if 'servers' not in module:
                module['servers'] = {}
                for server_name in servers:
                    module['servers'][server_name] = set(module['rooms'])
                module.pop('rooms', None)
            # set default settings
            if 'autoreload' not in module: module['autoreload'] = True
            if 'autoreconnect' not in module: module['autoreconnect'] = True
            if 'autorejoin' not in module: module['autorejoin'] = True
            if 'enabled' not in module: module['enabled'] = True
            module_settings[module_name] = module
    except KeyError as ex:
        exit_critical("Error while parsing module config: could not find key %s in module %s", ex, module_name)
    except Exception as ex:
        exit_critical("Error while parsing module config: %s", ex)

    logger.debug("Configuration successful")
    logger.debug("Servers: %s", servers)
    logger.debug("Modules: %s", module_settings)

    # Load modules
    logger.debug("Loading modules")
    for server_name in servers:
        help_module = HelpModule(rooms=set())
        server_modules = servers[server_name]['modules'] = [help_module]
        for module_name in module_settings:
            module = module_settings[module_name]
            if server_name in module['servers'] and module['enabled']:
                # Load the module
                logger.info("Loading module %s for server %s", module_name, server_name)
                path = module['path'] if 'path' in module else None
                loaded_module = load_module(module_name, path)
                # Add the help topics for the loaded module, and add the rooms to the help module
                help_module.add_module_help(loaded_module)
                help_module.rooms |= set(module['servers'][server_name])
                # Construct the bot module
                module_params = module['params'] if 'params' in module else {}
                bot_info = loaded_module.INFO
                server_modules += [bot_info['module'](rooms=module['servers'][server_name], **module_params)]
    # Make connections to servers
    loop = asyncio.get_event_loop()
    for server_name in servers:
        logger.info("Connecting to %s", server_name)
        connect_info = servers[server_name]['connect_info']
        modules = servers[server_name]['modules']
        chatbot = chatbot_factory(connect_info, modules)
        coro = loop.create_connection(lambda: chatbot, connect_info.server, connect_info.port)
        loop.run_until_complete(coro)
    logger.info("Running forever")
    loop.run_forever()


# TODO
# * code hot loading
# * auto config loading
# * nickserv handling
# * ssl support
# * new CLI class that handles things
