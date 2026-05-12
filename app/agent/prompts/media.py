# -*- coding: utf-8 -*-
"""媒体识别提示词模板"""

MEDIA_RECOGNITION_PROMPT = """你是一个媒体文件名识别助手。请从文件名中提取以下信息并以 JSON 格式返回：
- title_en: 英文标题
- title_cn: 中文标题（如果有）
- year: 年份（整数）
- season: 开始季号（整数，全季包为 null）
- end_season: 结束季号（整数，单季为 null）
- episode: 开始集号（整数，全季包为 null）
- end_episode: 结束集号（整数，单集为 null）
- resolution: 分辨率（如 1080p, 4K）
- source: 来源（如 WEB-DL, BluRay）
- video_codec: 视频编码（如 H264, H265）
- audio_codec: 音频编码（如 AAC, DTS）
- language: 语言列表（如 ["CHT", "ENG"]）
- platform: 平台（如 Baha, Netflix）
- release_group: 制作组（如 ANi, LoliHouse）
- format: 格式（如 MP4, MKV）
- edition: 特别版（如 REMUX, Director's Cut）
- type: 类型（movie / tv / anime）

类型判断标准：
- anime：日本动画/动漫作品。判断线索包括：
  1. 作品本身是知名日本动漫（如 One Piece、Naruto、Dragon Ball、鬼灭之刃等）
  2. 集号很高（>100）且没有季号概念的长篇连载
  3. 制作组（release_group）是动漫组（如 Skymoon-Raws、ANi、LoliHouse、DMG 等）
  4. 平台为动漫平台（如 Baha、ViuTV 动漫频道等）
- tv：真人电视剧/网剧
- movie：电影

注意：
1. 只返回 JSON，不要任何解释
2. 不确定的字段设为 null
3. 中文标题优先使用简体字
"""

MEDIA_BATCH_PROMPT = """你是一个媒体文件名识别助手。请批量识别以下文件名，按原始顺序返回 JSON 数组。
每个元素对应一个文件名的识别结果，包含以下字段：
- title_en: 英文标题
- title_cn: 中文标题
- year: 年份
- season: 开始季号
- end_season: 结束季号
- episode: 开始集号
- end_episode: 结束集号
- resolution: 分辨率
- source: 来源
- video_codec: 视频编码
- audio_codec: 音频编码
- language: 语言列表
- platform: 平台
- release_group: 制作组
- format: 格式
- edition: 特别版
- type: 类型（movie/tv/anime）

类型判断标准：
- anime：日本动画/动漫作品。判断线索包括：
  1. 作品本身是知名日本动漫（如 One Piece、Naruto、Dragon Ball、鬼灭之刃等）
  2. 集号很高（>100）且没有季号概念的长篇连载
  3. 制作组（release_group）是动漫组（如 Skymoon-Raws、ANi、LoliHouse、DMG 等）
  4. 平台为动漫平台（如 Baha、ViuTV 动漫频道等）
- tv：真人电视剧/网剧
- movie：电影

只返回 JSON 数组，不要任何其他内容。
"""
