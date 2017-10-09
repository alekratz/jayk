import inotify.adapters
import inotify.constants
from threading import Thread
import importlib.util


class FileListener(Thread):
    """
    A class that watches a given path. If that file is changed, the callback is called.
    """
    def __init__(self, listen_path, callback):
        self.listen_path = listen_path if listen_path is bytes else listen_path.encode('ascii')
        self.callback = callback
        self.running = False

    def run(self):
        assert not self.running
        self.running = True
        notify = inotify.adapters.Inotify()
        notify.add_watch(self.listen_path, inotify.constants.IN_MODIFY)
        try:
            for event in notify.event_gen():
                if event is None: continue
                self.callback()
        finally:
            self.running = False
            notify.remove_watch(self.listen_path)


class AttrDict(dict):
    """
    Dict that sets dictionary values to attributes. Useful for configurations representations.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

    def infect(self):
        """
        Attempts to convert all dictionaries in this AttrDict to AttrDicts themselves.
        """
        for k in self:
            v = self[k]
            if isinstance(v, list):
                self[k] = self.infect_list(v)
            elif isinstance(v, dict):
                self[k] = AttrDict(v)
                self[k].infect()
        return self

    def infect_list(self, seq):
        return [AttrDict(v).infect() if isinstance(v, dict) else
                self.infect_list(v) if isinstance(v, list) else v
                for v in seq]


class JaykException(Exception):
    def __init__(self, msg):
        super().__init__(msg)


def load_module(module_name, path):
    """
    Loads a Python file as a module.
    """
    from .module import JaykMeta
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
