"""commons 单元测试"""

import pytest

from app.utils.commons import retry


class TestRetry:
    def test_retry_success(self):
        call_count = 0

        @retry(ValueError, tries=3, delay=0.01)
        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary")
            return "ok"

        assert flaky() == "ok"
        assert call_count == 2

    def test_retry_exhausted_raises_original(self):
        call_count = 0

        @retry(ValueError, tries=2, delay=0.01)
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise ValueError("persistent")

        with pytest.raises(ValueError, match="persistent"):
            always_fail()
        assert call_count == 2

    def test_retry_no_retry_for_other_exception(self):
        call_count = 0

        @retry(ValueError, tries=3, delay=0.01)
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("unexpected")

        with pytest.raises(TypeError, match="unexpected"):
            raises_type_error()
        assert call_count == 1
