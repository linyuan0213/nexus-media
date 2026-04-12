import logging
import os
import sys
import threading
import inspect
from loguru import logger

from config import Config

logging.getLogger('werkzeug').setLevel(logging.ERROR)
logging.getLogger('watchdog').setLevel(logging.INFO)

# 使用RLock支持重入，减少死锁风险
lock = threading.RLock()

_log_buffer = None


def _get_log_buffer():
    global _log_buffer
    if _log_buffer is None:
        # 延迟导入，避免循环导入
        from app.utils.log_buffer import LogBuffer
        _log_buffer = LogBuffer(maxlen=200)
    return _log_buffer


class _LogBufferProxy:
    """延迟加载 LogBuffer 的代理对象，避免顶层导入导致循环引用。"""

    def append(self, level, text):
        return _get_log_buffer().append(level, text)

    def get_logs(self, source=None, last_counter=0):
        return _get_log_buffer().get_logs(source=source, last_counter=last_counter)

    @property
    def counter(self):
        return _get_log_buffer().counter

    def __len__(self):
        return len(_get_log_buffer())

    def __iter__(self):
        return iter(_get_log_buffer())

    def __getitem__(self, index):
        return _get_log_buffer().__getitem__(index)


LOG_BUFFER = _LogBufferProxy()


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 1
        while frame.f_code.co_filename == logging.__file__ or frame.f_code.co_filename == __file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


class Logger:
    logger = None
    __instance = {}
    __config = None

    def __init__(self, module):
        self.logger = logger
        self.__config = Config()
        logtype = self.__config.get_config('log').get('type') or "console"
        loglevel = self.__config.get_config('log').get('level') or "info"
        handlers = []
        self.logger.level(loglevel.upper())
        if logtype == "server":
            logserver = self.__config.get_config('log').get('server', '').split(':')
            if logserver:
                logip = logserver[0]
                if len(logserver) > 1:
                    logport = int(logserver[1] or '514')
                else:
                    logport = 514

                handler = {
                        "sink": f"tcp://{logip}:{logport}",
                        "format": "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level:8}| {file} : {module}.{function}:{line:4} | - {message}",
                        "colorize": False
                    }
                handlers.append(handler)

        elif logtype == "file":
            # 记录日志到文件
            logpath = os.environ.get('NASTOOL_LOG') or self.__config.get_config('log').get('path') or ""
            if logpath:
                if not os.path.exists(logpath):
                    os.makedirs(logpath)

                handler = {
                        "sink": os.path.join(logpath, module + ".log"),
                        "rotation": "5 MB",
                        "format": "{time:YYYY-MM-DD HH:mm:ss.SSS} |{level:8}| {file} : {module}.{function}:{line:4} | - {message}",
                        "colorize": False,
                        "retention": "5 days"
                    }
                handlers.append(handler)
        # 记录日志到终端
        handler = {
            "sink": sys.stderr,
            "format": "{time:YYYY-MM-DD HH:mm:ss.SSS} |<lvl>{level:8}</>| {file} : {module}.{function}:{line:4} | - <lvl>{message}</>",
            "colorize": True
        }
        handlers.append(handler)
        logger.configure(handlers=handlers)
        logging.basicConfig(handlers=[InterceptHandler()], level=0)

    @staticmethod
    def get_instance(module):
        if not module:
            module = "run"
        # 双重检查锁定，减少锁竞争
        instance = Logger.__instance.get(module)
        if instance:
            return instance
        with lock:
            instance = Logger.__instance.get(module)
            if instance:
                return instance
            Logger.__instance[module] = Logger(module)
        return Logger.__instance.get(module)


def debug(text, module=None):
    frame, depth = inspect.currentframe(), 0
    while frame and (depth == 0 or frame.f_code.co_filename == __file__):
        frame = frame.f_back
        depth += 1
    LOG_BUFFER.append("DEBUG", text)
    return Logger.get_instance(module).logger.opt(depth=depth).debug(text)


def info(text, module=None):
    frame, depth = inspect.currentframe(), 0
    while frame and (depth == 0 or frame.f_code.co_filename == __file__):
        frame = frame.f_back
        depth += 1
    LOG_BUFFER.append("INFO", text)
    return Logger.get_instance(module).logger.opt(depth=depth).info(text)


def error(text, module=None):
    frame, depth = inspect.currentframe(), 0
    while frame and (depth == 0 or frame.f_code.co_filename == __file__):
        frame = frame.f_back
        depth += 1
    LOG_BUFFER.append("ERROR", text)
    return Logger.get_instance(module).logger.opt(depth=depth).error(text)


def warn(text, module=None):
    frame, depth = inspect.currentframe(), 0
    while frame and (depth == 0 or frame.f_code.co_filename == __file__):
        frame = frame.f_back
        depth += 1
    LOG_BUFFER.append("WARN", text)
    return Logger.get_instance(module).logger.opt(depth=depth).warning(text)


def console(text):
    LOG_BUFFER.append("INFO", text)
    print(text)


# 保持向后兼容的别名
LOG_QUEUE = LOG_BUFFER
LOG_INDEX = property(lambda self: len(LOG_BUFFER))
