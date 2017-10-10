from ..util import LogMixin
import inotify.adapters
import inotify.constants
from threading import Thread
import importlib.util
import multiprocessing as mp
import queue
import time


class FileProcess(mp.Process):

    def __init__(self, listen_path, queue):
        super().__init__()
        self.listen_path = listen_path if listen_path is bytes else listen_path.encode('ascii')
        self.queue = queue
        self.notify = inotify.adapters.Inotify()

    def run(self):
        self.notify.add_watch(self.listen_path)
        # TODO : abstract away the inotify parts, and use a directory watcher instead
        while True:
            try:
                for event in self.notify.event_gen():
                    if not event: continue
                    (_, type_names, _, _) = event
                    if 'IN_IGNORED' in type_names:
                        # XXX : give it a chance to make a new file
                        # No real workaround beyond waiting for the disk to catch up
                        time.sleep(0.5)
                        self.notify.add_watch(self.listen_path)
                    self.queue.put(event)
            except Exception as ex:
                self.queue.put(ex)


class FileListener(Thread, LogMixin):
    """
    A class that watches a given path. If that file is changed, the callback is called.
    """
    def __init__(self, listen_path, callback):
        LogMixin.__init__(self, "FileListener({})".format(listen_path))
        Thread.__init__(self)
        self.callback = callback
        self.running = False
        self.queue = mp.Queue()
        self.process = FileProcess(listen_path, self.queue)

    def run(self):
        self.debug("Starting watcher")
        assert not self.running
        assert self.queue is not None, "File listener has already completed; create a new one"
        self.process.start()
        self.running = True
        ignore = {'IN_CLOSE_NOWRITE', 'IN_MOVED_TO', 'IN_OPEN', 'IN_DELETE_SELF', 'IN_MOVE_SELF'}
        while self.running:
            try:
                event = self.queue.get(True, 0.1)
                if isinstance(event, Exception):
                    # raise this event as an exception if it is one
                    raise event
                if event is None: continue
                (_, type_names, _, _) = event
                if 'IN_IGNORED' in type_names:
                    self.debug("Watched file was (re)moved; attempting to set up another watcher")
                elif not bool(ignore & set(type_names)):
                    self.debug("inotify event(s) triggered callback: %s", type_names)
                    self.callback()
            except queue.Empty: pass  # ignore empty queue exceptions. these are raised by queue.get after timing out
            except Exception as ex:
                self.exception('Unexpected error')
        self.debug("Cleaning up")
        self.remove_watch()

    def remove_watch(self):
        self.debug("Removing watcher")
        self.process.terminate()

    def stop(self):
        self.debug("Stopping")
        self.running = False
        self.remove_watch()


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
