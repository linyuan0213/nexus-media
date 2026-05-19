from dataclasses import dataclass, field

from app.schemas.download import TorrentStatus


@dataclass
class RemoveStrategy:
    filter_tags: list[str] = field(default_factory=list)
    filter_status: list[TorrentStatus] = field(default_factory=list)
    ratio: float | None = None
    seeding_time: float | None = None
    size_range: tuple[int, int] | None = None
    upload_avs: float | None = None
    savepath_key: str | None = None
    tracker_key: str | None = None
    samedata: bool = False

    @classmethod
    def from_dict(cls, config: dict) -> "RemoveStrategy":
        size = config.get("size")
        size_range = None
        if size and isinstance(size, list) and len(size) >= 2:
            minsize = size[0] * 1024 * 1024 * 1024
            maxsize = size[-1] * 1024 * 1024 * 1024
            size_range = (minsize, maxsize)

        filter_tags = config.get("filter_tags") or []
        if isinstance(filter_tags, str):
            filter_tags = [filter_tags]

        filter_status = config.get("filter_status") or []
        if filter_status and not isinstance(filter_status, list):
            filter_status = [filter_status]

        return cls(
            filter_tags=filter_tags,
            filter_status=filter_status,
            ratio=config.get("ratio"),
            seeding_time=config.get("seeding_time"),
            size_range=size_range,
            upload_avs=config.get("upload_avs"),
            savepath_key=config.get("savepath_key"),
            tracker_key=config.get("tracker_key"),
            samedata=bool(config.get("samedata")),
        )
