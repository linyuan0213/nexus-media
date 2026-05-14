"""Debug tokenization for Slime title"""

import sys
from unittest.mock import MagicMock

sys.modules["log"] = MagicMock()

import os

os.environ["NASTOOL_CONFIG"] = "/home/linyuan/python/config/config.yaml"

from app.utils.tokens import Tokens

title = "[LoliHouse] 关于我转生变成史莱姆这档事 / Tensei Shitara Slime Datta Ken  - 72 [WebRip 1080p HEVC-10bit AAC][简繁内封字幕][END]"

print("标题:")
print(title)
print()

# 检查预处理后的 tokens
tokens = Tokens(title)
print("Tokens:")
for i, token in enumerate(tokens._tokens):
    print(f"  [{i:2d}] '{token}'")
