from pathlib import Path

from PIL import Image, ImageDraw


def main() -> None:
    assets = Path(__file__).resolve().parents[1] / "assets"
    assets.mkdir(exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []

    for size in sizes:
        scale = size / 256
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        def xy(values: tuple[int, ...]) -> tuple[int, ...]:
            return tuple(round(value * scale) for value in values)

        draw.rounded_rectangle(xy((22, 22, 234, 234)), radius=round(48 * scale), fill=(36, 36, 36, 255))
        draw.ellipse(xy((78, 34, 178, 134)), fill=(255, 255, 255, 255))
        draw.rounded_rectangle(xy((94, 74, 162, 174)), radius=round(28 * scale), fill=(255, 255, 255, 255))
        draw.rounded_rectangle(xy((112, 52, 144, 160)), radius=round(16 * scale), fill=(36, 36, 36, 255))
        draw.arc(xy((72, 112, 184, 214)), start=0, end=180, fill=(255, 255, 255, 255), width=max(2, round(14 * scale)))
        draw.line(xy((128, 206, 128, 230)), fill=(255, 255, 255, 255), width=max(2, round(14 * scale)))
        draw.line(xy((96, 230, 160, 230)), fill=(255, 255, 255, 255), width=max(2, round(14 * scale)))
        images.append(image)

    images[-1].save(assets / "whisper-dictation.ico", sizes=[(size, size) for size in sizes], append_images=images[:-1])
    print(assets / "whisper-dictation.ico")


if __name__ == "__main__":
    main()
