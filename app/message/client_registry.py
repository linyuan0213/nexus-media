import importlib


class ClientRegistry:
    _registry = {}
    _clients_loaded = False

    _MODULES = [
        "wechat",
        "telegram",
        "bark",
        "chanify",
        "gotify",
        "iyuu",
        "ntfy",
        "pushdeer",
        "pushplus",
        "serverchan",
        "slack",
        "synologychat",
        "webhook",
    ]

    @classmethod
    def register(cls, client_cls):
        cls._registry[client_cls.schema] = client_cls

    @classmethod
    def build(cls, ctype, conf):
        cls._ensure_loaded()
        client_cls = cls._registry.get(ctype)
        if client_cls:
            return client_cls(conf)
        return None

    @classmethod
    def _ensure_loaded(cls):
        if cls._clients_loaded:
            return
        for mod in cls._MODULES:
            try:
                importlib.import_module(f"app.message.client.{mod}")
            except ImportError:
                pass
        cls._clients_loaded = True
