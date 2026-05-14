"""刮削器 — 图片与 NFO 文件下载/保存"""

import os

from requests.exceptions import RequestException

import log
from app.core.module_config import ModuleConf
from app.utils import ExceptionUtils, RequestUtils
from app.utils.commons import retry
from app.utils.types import RmtMode


class ImageDownloader:
    """图片下载器 — 负责从 URL 下载图片并保存到本地或远程"""

    def __init__(self, temp_path: str, rmt_mode: RmtMode = None):
        self._temp_path = temp_path
        self._rmt_mode = rmt_mode

    def set_rmt_mode(self, rmt_mode: RmtMode):
        self._rmt_mode = rmt_mode

    @retry(RequestException, logger=log)
    def download(self, url, out_path, itype="", force=False):
        """下载图片并保存"""
        if not url or not out_path:
            return
        if itype:
            image_path = os.path.join(out_path, "{}.{}".format(itype, str(url).split(".")[-1]))
        else:
            image_path = out_path
        if not force and os.path.exists(image_path):
            return
        try:
            log.info(f"【Scraper】正在下载{itype}图片：{url} ...")
            r = RequestUtils().get_res(url=url, raise_exception=True)
            if r:
                if self._rmt_mode in ModuleConf.REMOTE_RMT_MODES:
                    self._save_remote(image_path, r.content)
                else:
                    with open(file=image_path, mode="wb") as img:
                        img.write(r.content)
                log.info(f"【Scraper】{itype}图片已保存：{image_path}")
            else:
                log.info(f"【Scraper】{itype}图片下载失败，请检查网络连通性")
        except RequestException as ex:
            raise RequestException from ex
        except Exception as err:
            ExceptionUtils.exception_traceback(err)

    def save_nfo(self, doc, out_file):
        """保存 NFO XML 文件"""
        log.info(f"【Scraper】正在保存NFO文件：{out_file}")
        xml_str = doc.toprettyxml(indent="  ", encoding="utf-8")
        if self._rmt_mode in ModuleConf.REMOTE_RMT_MODES:
            self._save_remote(out_file, xml_str)
        else:
            with open(out_file, "wb") as xml_file:
                xml_file.write(xml_str)
        log.info(f"【Scraper】NFO文件已保存：{out_file}")

    def _save_remote(self, out_file, content):
        """保存到远程存储（RCLONE / MINIO）"""
        from app.utils import SystemUtils

        temp_file = os.path.join(self._temp_path, out_file[1:])
        temp_file_dir = os.path.dirname(temp_file)
        if not os.path.exists(temp_file_dir):
            os.makedirs(temp_file_dir)
        with open(temp_file, "wb") as f:
            f.write(content)
        if self._rmt_mode in [RmtMode.RCLONE, RmtMode.RCLONECOPY]:
            SystemUtils.rclone_move(temp_file, out_file)
        elif self._rmt_mode in [RmtMode.MINIO, RmtMode.MINIOCOPY]:
            SystemUtils.minio_move(temp_file, out_file)
        else:
            SystemUtils.move(temp_file, out_file)
