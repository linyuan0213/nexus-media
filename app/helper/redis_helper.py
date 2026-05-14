class RedisHelper:
    @staticmethod
    def is_valid():
        """
        判断redis是否有效
        不再强制依赖Redis，缓存系统会自动回退到内存缓存
        """
        return False
