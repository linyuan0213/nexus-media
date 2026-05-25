import traceback

import log


class ExceptionUtils:
    @classmethod
    def exception_traceback(cls, e):
        msg = f"Exception: {str(e)}\nCallstack:\n{traceback.format_exc()}"
        log.error(msg)
