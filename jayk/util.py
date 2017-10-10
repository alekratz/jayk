import logging
import logging.config


class LogMixin:
    """
    A logging mixin class, which provides methods for writing log messages.
    """
    def __init__(self, logger_name: str):
        self.__logger = logging.getLogger(logger_name)

    def critical(self, message, *args, **kwargs):
        self.__logger.critical(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self.__logger.error(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self.__logger.warning(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self.__logger.info(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self.__logger.debug(message, *args, **kwargs)

    def exception(self, message, *args, **kwargs):
        self.__logger.exception(message, *args, **kwargs)
