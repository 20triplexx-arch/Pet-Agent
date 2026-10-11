"""Original synthetic label fixtures; no real product, logo or copied packaging."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    directory = Path(__file__).resolve().parents[2] / "frontend/tests/fixtures"
    directory.mkdir(exist_ok=True)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = ImageFont.truetype(str(font_path), 38)
    lines = ["宠伴测试标签 / SAMPLE LABEL", "完整宠物食品  成年猫", "净含量: 1.5 kg", "代谢能: 418.4 kJ/100g", "粗蛋白 >= 32.5%", "粗脂肪 >= 12.0%", "水分 <= 10.0%", "测试配方，非真实商品"]
    image = Image.new("RGB", (1100, 640), "white")
    draw = ImageDraw.Draw(image)
    for i, text in enumerate(lines):
        draw.text((50, 35 + i*70), text, font=font, fill="black")
    image.save(directory / "label-zh-en.png")
    image.rotate(180).save(directory / "label-rotated.png")
    print("Original Chinese/English and rotated OCR fixtures created")


if __name__ == "__main__":
    main()
