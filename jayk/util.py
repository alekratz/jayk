"""Common utilities used through this codebase."""


import logging
import logging.config


class LogMixin:
    """
    A logging mixin class, which provides methods for writing log messages.
    """
    def __init__(self, logger_name: str):
        """
        Creates the logger with the specified name.

        :param logger_name: the name for this logger. When in doubt, use MyType.__name__.
        """
        self.__logger = logging.getLogger(logger_name)

    def critical(self, message, *args, **kwargs):
        """
        Passes a critical logging message on to the internal logger.
        """
        self.__logger.critical(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        """
        Passes an error logging message on to the internal logger.
        """
        self.__logger.error(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        """
        Passes an warning logging message on to the internal logger.
        """
        self.__logger.warning(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        """
        Passes an info logging message on to the internal logger.
        """
        self.__logger.info(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        """
        Passes a debug logging message on to the internal logger.
        """
        self.__logger.debug(message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        """
        Passes an exception logging message on to the internal logger. This should only be called
        when in the "except" clause of an exception handler.
        """
        self.__logger.exception(message, *args, **kwargs)
