from abc import ABCMeta, abstractmethod


class _IMessageClient(metaclass=ABCMeta):
    schema = None

    def __init__(self, config: dict):
        self._config = config
        self.read_config()

    def read_config(self):
        pass

    def setup(self):
        pass

    def stop(self):
        pass

    @classmethod
    def match(cls, ctype):
        return ctype == cls.schema if cls.schema else False

    @abstractmethod
    def send_msg(self, title, text="", image="", url="", user_id="") -> tuple[bool, str]:
        pass

    @abstractmethod
    def send_list_msg(self, medias: list, user_id="", title="", **kwargs) -> tuple[bool, str]:
        pass
