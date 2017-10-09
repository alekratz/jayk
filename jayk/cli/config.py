from .util import AttrDict
from ..common import connect_info_factory
import os.path as path
import logging


__all__ = ["JaykConfigError", "JaykConfig"]


log = logging.getLogger(__name__)


def module_defaults(module_config):
    """
    Applies default settings to modules if they aren't present in the given configuration
    """
    defaults = {
            'rooms': [],
            'params': {},
            'enabled': True,
            'path': None,
            }
    for k, v in defaults.items():
        if k not in module_config:
            module_config[k] = v
    return module_config


class JaykConfigError(Exception):
    def __init__(self, msg):
        super().__init__(msg)


class JaykConfig:
    """
    A configuration for the Jayk bot framework CLI.
    """
    def __init__(self):
        """
        Figures out which configuration file we want to load, gets its contents, and loads it in to memory.
        """
        # Set up the initial class members
        self.config_path = None         # configuration path
        self.servers = {}               # list of servers by server configuration
        self.__config_hash = None       # hash of current server configuration

        # Discover and parse the configuration
        self.reload()

    @staticmethod
    def __make_hash(config):
        """
        Helper function that makes a hash of the given configuration.
        """
        import json, hashlib
        config_str = json.dumps(config)
        h = hashlib.sha256(config_str.encode('ascii'))
        return h.hexdigest()

    def reload(self):
        """
        Discovers the config location, and parses it into an object that makes sense.
        """
        config = AttrDict(self.discover()).infect()

        # Check if any changes actually need to be made
        server_config = config.servers
        # Take the hash of the JSON configuration string and use that for comparisons
        config_hash = JaykConfig.__make_hash(server_config)
        if self.__config_hash != config_hash:
            self.__config_hash = config_hash
            # Update the config since it's been changed
            self.update(server_config)

    def discover(self):
        """
        Searches around for a config file that we can use in the current directory.
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
        self.config_path = config_path
        return configs[config_path](contents)

    def update(self, config):
        """
        Makes sense of the passed configuration object, and ensures that the configuration is both consistent and sane.
        """
        # Get server connect info
        self.servers.clear()
        for server in config:
            server_type = server.type
            self.servers[server.server] = AttrDict({
                'connect_info': connect_info_factory(server_type, **server),
                'modules': {n: module_defaults(m) for n, m in server.modules.items()} if 'modules' in server else {},
                }).infect()

