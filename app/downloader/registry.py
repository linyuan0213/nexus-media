from typing import TypeVar

T = TypeVar("T", bound=type)
_registry: dict[str, type] = {}


def register(cls: T) -> T:
    if not hasattr(cls, "client_id") or not cls.client_id:
        raise ValueError(f"下载器类 {cls.__name__} 必须定义 client_id")
    _registry[cls.client_id] = cls
    return cls


def get_client_class(client_id: str) -> type | None:
    return _registry.get(client_id)


def get_all_clients() -> list[type]:
    return list(_registry.values())
