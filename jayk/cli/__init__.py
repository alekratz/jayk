from ..chatbot import chatbot_factory, JaykMeta, ChatbotState
from ..common import connect_info_factory
from .module import HelpModule
import asyncio
import logging
import os.path as path
import sys
import importlib.util


log = logging.getLogger(__name__)


def load_module(module_name, path=None):
    """
    Loads a Python file as a module.
    """
    # Step 1: import
    if path is None:
        path = module_name + ".py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Step 2: find the jayk bot
    for item in dir(module):
        cls = getattr(module, item)
        if isinstance(cls, JaykMeta):
            return cls
    return None


def exit_critical(*args, **kwargs):
    """
    Emits a critical log message, and exits the program.
    """
    log.critical(*args, **kwargs)
    sys.exit(1)


def parse_config():
    """
    Parses the configuration based on the current files in the directory.
    """
    import json
    configs = {'bots.json': json.loads}
    try:
        import yaml
        configs['bots.yaml'] = configs['bots.yml'] = yaml.load
    except:
        log.debug("could not import YAML; skipping searching for bots.yaml and bots.yml")
    config_path = None
    for f in configs:
        log.debug("looking for %s", f)
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

    log.debug("Configuration successful")
    log.debug("Servers: %s", servers)
    log.debug("Modules: %s", module_settings)

    # Load modules
    log.debug("Loading modules")
    for server_name in servers:
        help_module = HelpModule(rooms=set())
        server_modules = servers[server_name]['modules'] = [help_module]
        for module_name in module_settings:
            module = module_settings[module_name]
            if server_name in module['servers'] and module['enabled']:
                # Load the module
                log.info("Loading module %s for server %s", module_name, server_name)
                path = module['path'] if 'path' in module else None
                loaded_module = load_module(module_name, path)
                # Construct the bot module
                module_params = module['params'] if 'params' in module else {}
                module_instance = loaded_module(**module_params, rooms=module['servers'][server_name])
                server_modules += [module_instance]
                # Add the help topics for the loaded module, and add the rooms to the help module
                help_module.add_module_help(module_instance)
                help_module.rooms |= set(module['servers'][server_name])
    # Make connections to servers
    loop = asyncio.get_event_loop()
    for server_name in servers:
        log.info("Connecting to %s", server_name)
        # Create the module configuration info
        connect_info = servers[server_name]['connect_info']
        # Create the desired state
        desired_state = ChatbotState.from_config(config['modules'], server_name)
        modules = servers[server_name]['modules']
        chatbot = chatbot_factory(connect_info, modules, desired_state)
        coro = loop.create_connection(lambda: chatbot, connect_info.server, connect_info.port)
        loop.run_until_complete(coro)
    log.info("Running forever")
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        self.info("ctrl-C caught, exiting")
        loop.stop()
    loop.close()


# TODO
# * code hot loading
# * auto config loading
# * nickserv handling
# * ssl support
# * new CLI class that handles things
