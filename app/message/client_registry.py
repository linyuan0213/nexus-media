from app.message.registry import get_all_clients, get_client_class
from app.message.registry import register as _register


class ClientRegistry:
    @classmethod
    def register(cls, client_cls):
        _register(client_cls)

    @classmethod
    def build(cls, ctype, conf):
        client_cls = get_client_class(ctype)
        if client_cls:
            return client_cls(conf)
        return None

    @classmethod
    def get_all_schemas(cls):
        return [cls.schema for cls in get_all_clients() if hasattr(cls, "schema") and cls.schema]
