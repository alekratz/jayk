"""Common utilities among the CLI to use."""
from threading import Thread
import importlib.util
import multiprocessing as mp
from queue import Empty as EmptyQueue
import time
import inotify.adapters
import inotify.constants
from ..util import LogMixin


class FileProcess(mp.Process):
    """
    A single, dedicated process which watches a file.
    """
    def __init__(self, listen_path, queue):
        """
        Creates a new file watcher process object with the given listen path and IPC queue.

        :param listen_path: the path to watch.
        :param queue: the queue to use for sending and receiving messages across processes.
        """
        super().__init__()
        self.listen_path = listen_path if listen_path is bytes else listen_path.encode('ascii')
        self.queue = queue
        self.notify = inotify.adapters.Inotify()

    def run(self):
        """
        Behavior implementation of this process.
        """
        self.notify.add_watch(self.listen_path)
        # TODO : abstract away the inotify parts, and use a directory watcher instead
        while True:
            try:
                for event in self.notify.event_gen():
                    if not event:
                        continue
                    (_, type_names, _, _) = event
                    if 'IN_IGNORED' in type_names:
                        # XXX : give it a chance to make a new file
                        # No real workaround beyond waiting for the disk to catch up
                        time.sleep(1.0)
                        self.notify.add_watch(self.listen_path)
                    self.queue.put(event)
            except Exception as ex:
                self.queue.put(ex)


class FileListener(Thread, LogMixin):
    """
    A class that watches a given path for modification. If that file is changed, the callback is
    called.
    """
    def __init__(self, listen_path, callback):
        """
        Creates a new FileListener over the given path, and a callback for what to do when the file
        is modified.

        :param listen_path: the path to listen for modifications.
        :param callback: the method to call when the file is modified.
        """
        LogMixin.__init__(self, "FileListener({})".format(listen_path))
        Thread.__init__(self)
        self.callback = callback
        self.running = False
        self.queue = mp.Queue()
        self.process = FileProcess(listen_path, self.queue)

    def run(self):
        """
        Starts the watcher for this path in another thread.
        """
        self.debug("Starting watcher")
        assert not self.running
        assert self.queue is not None, "File listener has already completed; create a new one"
        self.process.start()
        self.running = True
        ignore = {'IN_CLOSE_NOWRITE', 'IN_MOVED_TO', 'IN_OPEN', 'IN_DELETE_SELF', 'IN_MOVE_SELF',
                  'IN_ACCESS'}
        while self.running:
            try:
                event = self.queue.get(True, 0.1)
                if isinstance(event, Exception):
                    # raise this event as an exception if it is one
                    raise event
                if event is None:
                    continue
                (_, type_names, _, _) = event
                if 'IN_IGNORED' in type_names:
                    self.debug("Watched file was (re)moved; attempting to set up another watcher")
                elif not bool(ignore & set(type_names)):
                    self.debug("inotify event(s) triggered callback: %s", type_names)
                    self.callback()
            except EmptyQueue:
                # ignore empty queue exceptions. these are raised by queue.get after timing out
                pass
            except Exception:
                self.exception('Unexpected error')
        self.debug("Cleaning up")
        self.remove_watch()

    def remove_watch(self):
        """
        Stops our watcher process.
        """
        self.debug("Removing watcher")
        self.process.terminate()

    def stop(self):
        """
        Stops this thread from watching.
        """
        self.debug("Stopping")
        self.running = False
        self.remove_watch()


class AttrDict(dict):
    """
    Dict that sets dictionary values to attributes. Useful for configurations representations.
    """
    def __init__(self, *args, **kwargs):
        """
        Creates a new AttrDict object in the style of the built-in dict() function.
        """
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
        """
        Runs `AttrDict.infect` on every item in the provided if they are dicts and
        `AttrDict.infect_list` on every item in the provided list if they are lists themselves.
        """
        return [AttrDict(v).infect() if isinstance(v, dict) else
                self.infect_list(v) if isinstance(v, list) else v
                for v in seq]


class JaykException(Exception):
    """
    A general exception that gets raised by the Jayk library.
    """


def load_module(module_name, path):
    """
    Loads a Python file as a module.

    :param module_name: the name of the module.
    :param path: the path to the module.
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
