"""ImageUtils 单元测试."""

from PIL import Image

from app.utils.image_utils import ImageUtils


class TestImageUtils:
    def test_calculate_theme_color(self, tmp_path):
        img_path = tmp_path / "red.png"
        img = Image.new("RGB", (200, 200), color=(255, 0, 0))
        img.save(img_path)
        color = ImageUtils.calculate_theme_color(str(img_path))
        assert color == "#ff0000"

    def test_calculate_theme_color_non_primary(self, tmp_path):
        img_path = tmp_path / "blue.png"
        img = Image.new("RGB", (200, 200), color=(0, 0, 255))
        for x in range(50):
            for y in range(50):
                img.putpixel((x, y), (255, 0, 0))
        img.save(img_path)
        color = ImageUtils.calculate_theme_color(str(img_path))
        assert color == "#0000ff"
