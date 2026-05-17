"""刮削器 — 图片与 NFO 文件下载/保存"""

import io
import os

from requests.exceptions import RequestException

import log
from app.storage.backends.base import StorageBackend
from app.utils import ExceptionUtils, RequestUtils
from app.utils.commons import retry


class ImageDownloader:
    """图片下载器 — 负责从 URL 下载图片并保存到本地或远程"""

    def __init__(self, temp_path: str, dst_backend: StorageBackend | None = None):
        self._temp_path = temp_path
        self._dst_backend = dst_backend

    def set_dst_backend(self, dst_backend: StorageBackend | None):
        self._dst_backend = dst_backend

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
                if self._dst_backend:
                    self._dst_backend.write_stream(image_path, io.BytesIO(r.content), len(r.content))
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
        if self._dst_backend:
            self._dst_backend.write_stream(out_file, io.BytesIO(xml_str), len(xml_str))
        else:
            with open(out_file, "wb") as xml_file:
                xml_file.write(xml_str)
        log.info(f"【Scraper】NFO文件已保存：{out_file}")
