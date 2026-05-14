class NumberUtils:
    @staticmethod
    def max_ele(a, b):
        """
        返回非空最大值
        """
        if not a:
            return b
        if not b:
            return a
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
        KB = 1024
        MB = KB * KB
        GB = MB * KB
        TB = GB * KB
        try:
            if isinstance(byte_num, str):
                byte_num = int(byte_num)
            if byte_num > TB:
                result = f"{round(byte_num / TB, 2)} TB"
            elif byte_num > GB:
                result = f"{round(byte_num / GB, 2)} GB"
            elif byte_num > MB:
                result = f"{round(byte_num / MB, 2)} MB"
            elif byte_num > KB:
                result = f"{round(byte_num / KB, 2)} KB"
            else:
                result = f"{byte_num} B"
            return result
        except Exception as e:
            print(e.args)
            return byte_num
