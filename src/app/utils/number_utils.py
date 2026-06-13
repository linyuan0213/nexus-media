import log


class NumberUtils:
    @staticmethod
    def max_ele(a, b):
        """
        返回非空最大值
        """
        if not a:
            return int(b) if b else 0
        if not b:
            return int(a)
        return max(int(a), int(b))

    @staticmethod
    def get_size_gb(size):
        """
        将字节转换为GB
        """
        if not size:
            return 0.0
        return float(size) / 1024 / 1024 / 1024

    @staticmethod
    def format_byte_repr(byte_num):
        """
        size转换
        :param byte_num: 单位Byte
        :return:
        """
        _kb = 1024
        _mb = _kb * _kb
        _gb = _mb * _kb
        _tb = _gb * _kb
        try:
            if isinstance(byte_num, str):
                byte_num = int(byte_num)
            if byte_num > _tb:
                result = f"{round(byte_num / _tb, 2)} TB"
            elif byte_num > _gb:
                result = f"{round(byte_num / _gb, 2)} GB"
            elif byte_num > _mb:
                result = f"{round(byte_num / _mb, 2)} MB"
            elif byte_num > _kb:
                result = f"{round(byte_num / _kb, 2)} KB"
            else:
                result = f"{byte_num} B"
            return result
        except Exception as e:
            log.warn(f"[NumberUtils]格式化字节失败: {e.args}")
            return byte_num
