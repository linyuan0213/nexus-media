"""Debug Chinese brackets title"""

import os
import sys
from unittest.mock import MagicMock

from app.media.parser.video import parse_video_title
from app.utils.tokens import Tokens

sys.modules["log"] = MagicMock()

os.environ["NEXUS_MEDIA_CONFIG"] = "/home/linyuan/python/config/config.yaml"

title = "【关于我转生变成史莱姆这档事 Tensei Shitara Slime Datta Ken 】【12】【GB】【1080P】"

print("=" * 70)
print("测试标题:")
print(title)
print("=" * 70)

# Tokens
tokens = Tokens(title)
print("\nTokens:")
for i, token in enumerate(tokens._tokens):
    print(f"  [{i:2d}] '{token}'")

# Parse
info = parse_video_title(title)
print("\n解析结果:")
print(f"  cn_name: {info.cn_name}")
print(f"  en_name: {info.en_name}")
print(f"  type: {info.type}")
print(f"  season: {info.begin_season}")
print(f"  episode: {info.begin_episode}")
print(f"  end_episode: {info.end_episode}")
print(f"  year: {info.year}")
print(f"  resource_type: {info.resource_type}")
print(f"  resource_pix: {info.resource_pix}")
