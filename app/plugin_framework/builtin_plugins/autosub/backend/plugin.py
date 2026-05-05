# -*- coding: utf-8 -*-
"""
AutoSub Plugin v2
使用whisper自动生成视频文件字幕
"""
import copy
import os
import re
import subprocess
import tempfile
import time
import traceback
from datetime import timedelta

import iso639
import psutil
import srt
from lxml import etree

from app.helper import FfmpegHelper
from app.helper.openai_helper import OpenAiHelper
from app.plugin_framework.context import PluginContext
from app.utils import SystemUtils
from config import RMT_MEDIAEXT


class AutoSubPlugin:
    """AI字幕自动生成插件"""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx
        self._running = False
        self._end_token = ['.', '!', '?', '。', '！', '？', '。"', '！"', '？"', '."', '!"', '?"']
        self._noisy_token = [('(', ')'), ('[', ']'), ('{', '}'), ('【', '】'), ('♪', '♪'), ('♫', '♫'), ('♪♪', '♪♪')]

    def _get_config(self):
        return self.ctx.get_config() or {}

    def on_enable(self):
        self.ctx.info("AI字幕自动生成插件已启用")

    def on_disable(self):
        self.ctx.info("AI字幕自动生成插件已禁用")

    def on_hook(self, event, data):
        if event == "plugin.config_changed":
            if data.get("plugin_id") == self.ctx.plugin_id:
                config = self._get_config()
                if config.get("run_now"):
                    self.ctx.set_config("run_now", False)
                    self.run()

    def run(self):
        """立即运行字幕生成"""
        if self._running:
            self.ctx.warn("上一次任务还未完成，不进行处理")
            return

        config = self._get_config()
        path_list_raw = config.get("path_list", "")
        file_size = config.get("file_size")
        whisper_main = config.get("whisper_main")
        whisper_model = config.get("whisper_model")
        translate_zh = config.get("translate_zh", False)
        translate_only = config.get("translate_only", False)
        additional_args = config.get("additional_args", "-t 4 -p 1")
        send_notify = config.get("send_notify", False)
        asr_engine = config.get("asr_engine", "whisper.cpp")
        faster_whisper_model = config.get("faster_whisper_model", "base")
        faster_whisper_model_path = config.get("faster_whisper_model_path")

        path_list = list(set([p.strip() for p in path_list_raw.split('\n') if p.strip()]))

        if not path_list or not file_size:
            self.ctx.warn("配置信息不完整，不进行处理")
            return

        try:
            file_size = int(file_size)
        except (ValueError, TypeError):
            self.ctx.warn("文件大小不是数字，不进行处理")
            return

        if not translate_only and not self._check_asr(asr_engine, whisper_main, whisper_model, faster_whisper_model_path, faster_whisper_model, additional_args):
            return

        try:
            self._running = True
            success_count = skip_count = fail_count = process_count = 0
            for path in path_list:
                self.ctx.info(f"开始处理目录：{path} ...")
                if not os.path.exists(path):
                    self.ctx.warn(f"目录不存在，不进行处理")
                    continue
                if not os.path.isdir(path):
                    self.ctx.warn(f"目录不是文件夹，不进行处理")
                    continue
                if not os.path.isabs(path):
                    self.ctx.warn(f"目录不是绝对路径，不进行处理")
                    continue
                s, sk, f, p = self._process_folder(path, file_size, whisper_main, whisper_model, translate_zh, translate_only, additional_args, send_notify, asr_engine, faster_whisper_model, faster_whisper_model_path)
                success_count += s
                skip_count += sk
                fail_count += f
                process_count += p
        except Exception as e:
            self.ctx.error(f"处理异常: {e}")
        finally:
            self.ctx.info(f"处理完成: 成功{success_count} / 跳过{skip_count} / 失败{fail_count} / 共{process_count}")
            self._running = False

    def _check_asr(self, asr_engine, whisper_main, whisper_model, faster_whisper_model_path, faster_whisper_model, additional_args):
        if asr_engine == 'whisper.cpp':
            if not whisper_main or not whisper_model:
                self.ctx.warn("配置信息不完整，不进行处理")
                return False
            if not os.path.exists(whisper_main):
                self.ctx.warn("whisper.cpp主程序不存在，不进行处理")
                return False
            if not os.path.exists(whisper_model):
                self.ctx.warn("whisper.cpp模型文件不存在，不进行处理")
                return False
            if additional_args and re.search(r'[;|&]', additional_args):
                self.ctx.warn("扩展参数包含异常字符，不进行处理")
                return False
        elif asr_engine == 'faster-whisper':
            if not faster_whisper_model_path or not faster_whisper_model:
                self.ctx.warn("配置信息不完整，不进行处理")
                return False
            if not os.path.exists(faster_whisper_model_path):
                self.ctx.warn("faster-whisper模型文件夹不存在，不进行处理")
                return False
            try:
                from faster_whisper import WhisperModel, download_model
            except ImportError:
                self.ctx.warn("faster-whisper 未安装，不进行处理")
                return False
        else:
            self.ctx.warn("未配置asr引擎，不进行处理")
            return False
        return True

    def _process_folder(self, path, file_size, whisper_main, whisper_model, translate_zh, translate_only, additional_args, send_notify, asr_engine, faster_whisper_model, faster_whisper_model_path):
        success_count = skip_count = fail_count = process_count = 0
        for video_file in self._get_library_files(path):
            if not video_file:
                continue
            if os.path.getsize(video_file) < file_size * 1024 * 1024:
                continue

            process_count += 1
            start_time = time.time()
            file_path, file_ext = os.path.splitext(video_file)
            file_name = os.path.basename(video_file)

            try:
                self.ctx.info(f"开始处理文件：{video_file} ...")
                if self._target_subtitle_exists(video_file, translate_zh):
                    self.ctx.warn(f"字幕文件已经存在，不进行处理")
                    skip_count += 1
                    continue

                if send_notify:
                    self.ctx.notify(title="自动字幕生成", text=f" 媒体: {file_name}\n 开始处理文件 ... ")

                ret, lang = self._generate_subtitle(video_file, file_path, translate_only, whisper_main, whisper_model, additional_args, asr_engine, faster_whisper_model, faster_whisper_model_path)
                if not ret:
                    message = f" 媒体: {file_name}\n "
                    if translate_only:
                        message += "内嵌\u0026外挂字幕不存在，不进行翻译"
                        skip_count += 1
                    else:
                        message += "生成字幕失败，跳过后续处理"
                        fail_count += 1
                    if send_notify:
                        self.ctx.notify(title="自动字幕生成", text=message)
                    continue

                if translate_zh:
                    self.ctx.info(f"开始翻译字幕为中文 ...")
                    if send_notify:
                        self.ctx.notify(title="自动字幕生成", text=f" 媒体: {file_name}\n 开始翻译字幕为中文 ... ")
                    self._translate_zh_subtitle(lang, f"{file_path}.{lang}.srt", f"{file_path}.zh.srt")
                    self.ctx.info(f"翻译字幕完成：{file_name}.zh.srt")

                end_time = time.time()
                message = f" 媒体: {file_name}\n 处理完成\n 字幕原始语言: {lang}\n "
                if translate_zh:
                    message += f"字幕翻译语言: zh\n "
                message += f"耗时：{round(end_time - start_time, 2)}秒"
                self.ctx.info(f"自动字幕生成 处理完成：{message}")
                if send_notify:
                    self.ctx.notify(title="自动字幕生成", text=message)
                success_count += 1
            except Exception as e:
                self.ctx.error(f"自动字幕生成 处理异常：{e}")
                end_time = time.time()
                message = f" 媒体: {file_name}\n 处理失败\n 耗时：{round(end_time - start_time, 2)}秒"
                if send_notify:
                    self.ctx.notify(title="自动字幕生成", text=message)
                traceback.print_exc()
                fail_count += 1
        return success_count, skip_count, fail_count, process_count

    def _do_speech_recognition(self, audio_lang, audio_file, whisper_main, whisper_model, additional_args, asr_engine, faster_whisper_model, faster_whisper_model_path):
        lang = audio_lang
        if asr_engine == 'whisper.cpp':
            command = [whisper_main] + additional_args.split()
            command += ['-l', lang, '-m', whisper_model, '-osrt', '-of', audio_file, audio_file]
            ret = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if ret.returncode == 0:
                if lang == 'auto':
                    output = ret.stdout.decode('utf-8') if ret.stdout else ""
                    lang = re.search(r"auto-detected language: (\w+)", output)
                    if lang and lang.group(1):
                        lang = lang.group(1)
                    else:
                        lang = "en"
                return True, lang
        elif asr_engine == 'faster-whisper':
            try:
                from faster_whisper import WhisperModel, download_model
                cache_dir = os.path.join(faster_whisper_model_path, "cache")
                if not os.path.exists(cache_dir):
                    os.mkdir(cache_dir)
                os.environ["HUGGINGFACE_HUB_CACHE"] = cache_dir
                model = WhisperModel(download_model(faster_whisper_model),
                                     device="cpu", compute_type="int8", cpu_threads=psutil.cpu_count(logical=False))
                segments, info = model.transcribe(audio_file,
                                                  language=lang if lang != 'auto' else None,
                                                  word_timestamps=True,
                                                  temperature=0,
                                                  beam_size=5)
                if lang == 'auto':
                    lang = info.language

                subs = []
                if lang in ['en', 'eng']:
                    idx = 0
                    for segment in segments:
                        for word in segment.words:
                            idx += 1
                            subs.append(srt.Subtitle(index=idx,
                                                     start=timedelta(seconds=word.start),
                                                     end=timedelta(seconds=word.end),
                                                     content=word.word))
                    subs = self._merge_srt(subs)
                else:
                    for i, segment in enumerate(segments):
                        subs.append(srt.Subtitle(index=i,
                                                 start=timedelta(seconds=segment.start),
                                                 end=timedelta(seconds=segment.end),
                                                 content=segment.text))

                self._save_srt(f"{audio_file}.srt", subs)
                return True, lang
            except ImportError:
                self.ctx.warn("faster-whisper 未安装，不进行处理")
                return False, None
            except Exception as e:
                traceback.print_exc()
                self.ctx.error(f"faster-whisper 处理异常：{e}")
                return False, None
        return False, None

    def _generate_subtitle(self, video_file, subtitle_file, only_extract, whisper_main, whisper_model, additional_args, asr_engine, faster_whisper_model, faster_whisper_model_path):
        video_meta = FfmpegHelper().get_video_metadata(video_file)
        if not video_meta:
            self.ctx.error("获取视频文件元数据失败，跳过后续处理")
            return False, None

        ret, audio_index, audio_lang = self._get_video_prefer_audio(video_meta)
        if not ret:
            return False, None

        if not iso639.find(audio_lang) or not iso639.to_iso639_1(audio_lang):
            self.ctx.info("未知语言音轨")
            audio_lang = 'auto'

        expert_subtitle_langs = ['en', 'eng'] if audio_lang == 'auto' else [audio_lang, iso639.to_iso639_1(audio_lang)]
        self.ctx.info(f"使用 {expert_subtitle_langs} 匹配已有外挂字幕文件 ...")

        exist, lang = self._external_subtitle_exists(video_file, expert_subtitle_langs)
        if exist:
            self.ctx.info(f"外挂字幕文件已经存在，字幕语言 {lang}")
            return True, iso639.to_iso639_1(lang)

        self.ctx.info(f"外挂字幕文件不存在，使用 {expert_subtitle_langs} 匹配内嵌字幕文件 ...")
        ret, subtitle_index, subtitle_lang, subtitle_count = self._get_video_prefer_subtitle(video_meta, expert_subtitle_langs)
        if ret and (audio_lang == subtitle_lang or subtitle_count == 1):
            if audio_lang == subtitle_lang:
                self.ctx.info("内嵌音轨和字幕语言一致，直接提取字幕 ...")
            elif subtitle_count == 1:
                self.ctx.info("内嵌音轨和字幕语言不一致，但只有一个字幕，直接提取字幕 ...")

            audio_lang = iso639.to_iso639_1(subtitle_lang) if (iso639.find(subtitle_lang) and iso639.to_iso639_1(subtitle_lang)) else 'und'
            FfmpegHelper().extract_subtitle_from_video(video_file, f"{subtitle_file}.{audio_lang}.srt", subtitle_index)
            self.ctx.info(f"提取字幕完成：{subtitle_file}.{audio_lang}.srt")
            return True, audio_lang

        if audio_lang != 'auto':
            audio_lang = iso639.to_iso639_1(audio_lang)

        if only_extract:
            self.ctx.info("未开启语音识别，且无已有字幕文件，跳过后续处理")
            return False, None

        # 清理异常退出的临时文件
        tempdir = tempfile.gettempdir()
        for file in os.listdir(tempdir):
            if file.startswith('autosub-'):
                os.remove(os.path.join(tempdir, file))

        with tempfile.NamedTemporaryFile(prefix='autosub-', suffix='.wav', delete=True) as audio_file:
            self.ctx.info(f"提取音频：{audio_file.name} ...")
            FfmpegHelper().extract_wav_from_video(video_file, audio_file.name, audio_index)
            self.ctx.info(f"提取音频完成：{audio_file.name}")

            self.ctx.info(f"开始生成字幕, 语言 {audio_lang} ...")
            ret, lang = self._do_speech_recognition(audio_lang, audio_file.name, whisper_main, whisper_model, additional_args, asr_engine, faster_whisper_model, faster_whisper_model_path)
            if ret:
                self.ctx.info(f"生成字幕成功，原始语言：{lang}")
                SystemUtils.copy(f"{audio_file.name}.srt", f"{subtitle_file}.{lang}.srt")
                self.ctx.info(f"复制字幕文件：{subtitle_file}.{lang}.srt")
                os.remove(f"{audio_file.name}.srt")
                return ret, lang
            else:
                self.ctx.error("生成字幕失败")
                return False, None

    @staticmethod
    def _get_library_files(in_path, exclude_path=None):
        if not os.path.isdir(in_path):
            yield in_path
            return
        for root, dirs, files in os.walk(in_path):
            if exclude_path and any(os.path.abspath(root).startswith(os.path.abspath(path)) for path in exclude_path.split(",")):
                continue
            for file in files:
                cur_path = os.path.join(root, file)
                if os.path.splitext(file)[-1].lower() in RMT_MEDIAEXT:
                    yield cur_path

    @staticmethod
    def _load_srt(file_path):
        with open(file_path, 'r', encoding="utf8") as f:
            srt_text = f.read()
        return list(srt.parse(srt_text))

    @staticmethod
    def _save_srt(file_path, srt_data):
        with open(file_path, 'w', encoding="utf8") as f:
            f.write(srt.compose(srt_data))

    def _get_video_prefer_audio(self, video_meta, prefer_lang=None):
        if type(prefer_lang) == str and prefer_lang:
            prefer_lang = [prefer_lang]

        audio_lang = None
        audio_index = None
        audio_stream = filter(lambda x: x.get('codec_type') == 'audio', video_meta.get('streams', []))
        for index, stream in enumerate(audio_stream):
            if not audio_index:
                audio_index = index
                audio_lang = stream.get('tags', {}).get('language', 'und')
            if stream.get('disposition', {}).get('default'):
                audio_index = index
                audio_lang = stream.get('tags', {}).get('language', 'und')
            if prefer_lang and stream.get('tags', {}).get('language') in prefer_lang:
                audio_index = index
                audio_lang = stream.get('tags', {}).get('language', 'und')
                break

        if audio_index is None:
            self.ctx.warn("没有音轨，不进行处理")
            return False, None, None

        self.ctx.info(f"选中音轨信息：{audio_index}, {audio_lang}")
        return True, audio_index, audio_lang

    def _get_video_prefer_subtitle(self, video_meta, prefer_lang=None):
        image_based_subtitle_codecs = (
            'dvd_subtitle',
            'dvb_subtitle',
            'hdmv_pgs_subtitle',
        )

        if type(prefer_lang) == str and prefer_lang:
            prefer_lang = [prefer_lang]

        subtitle_lang = None
        subtitle_index = None
        subtitle_count = 0
        subtitle_stream = filter(lambda x: x.get('codec_type') == 'subtitle', video_meta.get('streams', []))
        for index, stream in enumerate(subtitle_stream):
            if stream.get('disposition', {}).get('forced'):
                continue
            if 'width' in stream or stream.get('codec_name') in image_based_subtitle_codecs:
                continue
            if not subtitle_index:
                subtitle_index = index
                subtitle_lang = stream.get('tags', {}).get('language')
            if stream.get('disposition', {}).get('default'):
                subtitle_index = index
                subtitle_lang = stream.get('tags', {}).get('language')
            if prefer_lang and stream.get('tags', {}).get('language') in prefer_lang:
                subtitle_index = index
                subtitle_lang = stream.get('tags', {}).get('language')
            subtitle_count += 1

        if subtitle_index is None:
            self.ctx.debug("没有内嵌字幕")
            return False, None, None, None

        self.ctx.debug(f"命中内嵌字幕信息：{subtitle_index}, {subtitle_lang}")
        return True, subtitle_index, subtitle_lang, subtitle_count

    def _is_noisy_subtitle(self, content):
        for token in self._noisy_token:
            if content.startswith(token[0]) and content.endswith(token[1]):
                return True
        return False

    def _merge_srt(self, subtitle_data):
        subtitle_data = copy.deepcopy(subtitle_data)
        merged_subtitle = []
        sentence_end = True

        for index, item in enumerate(subtitle_data):
            content = item.content.replace('\n', ' ').strip()
            parse = etree.HTML(content)
            if parse is not None:
                content = parse.xpath('string(.)')
            if content == '':
                continue
            item.content = content

            if self._is_noisy_subtitle(content):
                merged_subtitle.append(item)
                sentence_end = True
                continue

            if not merged_subtitle or sentence_end:
                merged_subtitle.append(item)
            elif not sentence_end:
                merged_subtitle[-1].content = f"{merged_subtitle[-1].content} {content}"
                merged_subtitle[-1].end = item.end

            if content.endswith(tuple(self._end_token)):
                sentence_end = True
            elif len(merged_subtitle[-1].content) > 350:
                sentence_end = True
            else:
                sentence_end = False

        return merged_subtitle

    def _do_translate_with_retry(self, text, retry=3):
        ret, result = OpenAiHelper().translate_to_zh(text)
        for i in range(retry):
            if ret and result:
                break
            if result and "Rate limit reached" in result:
                self.ctx.info("OpenAI Api Rate limit reached, sleep 60s ...")
                time.sleep(60)
            else:
                self.ctx.warn(f"翻译失败，重试第{i + 1}次")
            ret, result = OpenAiHelper().translate_to_zh(text)

        if not ret or not result:
            return None
        return result

    def _translate_zh_subtitle(self, source_lang, source_subtitle, dest_subtitle):
        srt_data = self._load_srt(source_subtitle)
        if source_lang in ['en', 'eng']:
            self.ctx.info("开始合并字幕语句 ...")
            merged_data = self._merge_srt(srt_data)
            self.ctx.info(f"合并字幕语句完成，合并前字幕数量：{len(srt_data)}, 合并后字幕数量：{len(merged_data)}")
            srt_data = merged_data

        batch = []
        max_batch_tokens = 1000
        for srt_item in srt_data:
            if not srt_item.content:
                continue
            if self._is_noisy_subtitle(srt_item.content):
                continue

            batch.append(srt_item)
            batch_tokens = sum([len(x.content) for x in batch])
            if batch_tokens < max_batch_tokens and srt_item != srt_data[-1]:
                continue

            batch_content = '\n'.join([x.content for x in batch])
            result = self._do_translate_with_retry(batch_content)
            if not result:
                batch = []
                continue

            translated = result.split('\n')
            if len(translated) != len(batch):
                self.ctx.info(f"翻译结果数量不匹配，翻译结果数量：{len(translated)}, 需要翻译数量：{len(batch)}, 退化为单条翻译 ...")
                for index, item in enumerate(batch):
                    result = self._do_translate_with_retry(item.content)
                    if not result:
                        continue
                    item.content = result + '\n' + item.content
            else:
                self.ctx.debug(f"翻译结果数量匹配，翻译结果数量：{len(translated)}")
                for index, item in enumerate(batch):
                    item.content = translated[index].strip() + '\n' + item.content

            batch = []

        self._save_srt(dest_subtitle, srt_data)

    @staticmethod
    def _external_subtitle_exists(video_file, prefer_langs=None):
        video_dir, video_name = os.path.split(video_file)
        video_name, video_ext = os.path.splitext(video_name)

        if type(prefer_langs) == str and prefer_langs:
            prefer_langs = [prefer_langs]

        for subtitle_lang in prefer_langs or []:
            dest_subtitle = os.path.join(video_dir, f"{video_name}.{subtitle_lang}.srt")
            if os.path.exists(dest_subtitle):
                return True, subtitle_lang

        return False, None

    def _target_subtitle_exists(self, video_file, translate_zh):
        if translate_zh:
            prefer_langs = ['zh', 'chi']
        else:
            prefer_langs = ['en', 'eng']

        exist, lang = self._external_subtitle_exists(video_file, prefer_langs)
        if exist:
            return True

        video_meta = FfmpegHelper().get_video_metadata(video_file)
        if not video_meta:
            return False
        ret, subtitle_index, subtitle_lang, _ = self._get_video_prefer_subtitle(video_meta, prefer_lang=prefer_langs)
        if ret and subtitle_lang in prefer_langs:
            return True

        return False
