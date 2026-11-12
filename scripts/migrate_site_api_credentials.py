"""把 CONFIG_SITE.NOTE.api_credentials 迁移到加密的正式表."""

from __future__ import annotations

import json

from app.db.repositories.site_repository import SiteRepository
from app.utils.json_utils import JsonUtils


def main() -> None:
    repo = SiteRepository()
    rows = repo.get_config_site()
    migrated = 0
    for row in rows:
        if not row.NOTE:
            continue
        try:
            note = json.loads(row.NOTE)
        except (TypeError, ValueError):
            continue
        credentials = note.pop("api_credentials", None)
        if not isinstance(credentials, dict) or not credentials:
            continue
        for profile, credential in credentials.items():
            if isinstance(credential, dict):
                repo.upsert_site_api_credentials(int(row.ID), str(profile), credential)
                migrated += 1
        repo.update_config_site_note(int(row.ID), JsonUtils.dumps(note))
    print(f"migrated_profiles={migrated}")


if __name__ == "__main__":
    main()
