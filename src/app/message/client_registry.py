from app.message.registry import get_all_clients, get_client_class
from app.message.registry import register as _register
from app.services.apikey_service import APIKeyService


class ClientRegistry:
    @classmethod
    def register(cls, client_cls):
        _register(client_cls)

    @classmethod
    def build(cls, ctype, conf, apikey_service: APIKeyService | None = None):
        client_cls = get_client_class(ctype)
        if client_cls:
            return client_cls(conf, apikey_service)
        return None

    @classmethod
    def get_all_schemas(cls):
        return [cls.schema for cls in get_all_clients() if hasattr(cls, "schema") and cls.schema]
