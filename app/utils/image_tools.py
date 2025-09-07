from PIL import Image, ImageDraw


def _sample_background_color(img: Image.Image) -> tuple[int, int, int]:
    """Sample the probable background color from image corners (RGB)."""
    img_rgb = img.convert('RGB')
    w, h = img_rgb.size
    corners = [
        img_rgb.getpixel((0, 0)),
        img_rgb.getpixel((w - 1, 0)),
        img_rgb.getpixel((0, h - 1)),
        img_rgb.getpixel((w - 1, h - 1)),
    ]
    r = sum(c[0] for c in corners) // 4
    g = sum(c[1] for c in corners) // 4
    b = sum(c[2] for c in corners) // 4
    return (r, g, b)


def _color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> int:
    """Cheap color distance (Manhattan) to avoid extra deps."""
    return abs(c1[0] - c2[0]) + abs(c1[1] - c2[1]) + abs(c1[2] - c2[2])


def remove_background_simple(img: Image.Image, tolerance: int = 60) -> Image.Image:
    """Replace near-background (sampled from corners) with transparency.

    This is a simple heuristic that works well for logos on solid backgrounds.
    """
    bg = _sample_background_color(img)
    im = img.convert('RGBA')
    w, h = im.size
    pixels = im.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if _color_distance((r, g, b), bg) <= tolerance:
                pixels[x, y] = (r, g, b, 0)
    return im


def circle_crop(img: Image.Image, padding: int = 0) -> Image.Image:
    """Circle-crop an image to a square PNG with transparent background.

    padding trims a few pixels from the edges before masking.
    """
    im = img.convert('RGBA')
    w, h = im.size
    d = min(w, h) - max(padding * 2, 0)
    if d <= 0:
        d = min(w, h)
    left = (w - d) // 2
    top = (h - d) // 2
    right = left + d
    bottom = top + d
    im = im.crop((left, top, right, bottom))

    mask = Image.new('L', (d, d), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, d, d), fill=255)

    out = Image.new('RGBA', (d, d), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


def process_logo_image(file_storage, remove_bg: bool = True, circle: bool = True) -> Image.Image:
    """Open an uploaded image file and apply background removal and circle crop."""
    img = Image.open(file_storage.stream)
    if remove_bg:
        img = remove_background_simple(img)
    if circle:
        img = circle_crop(img, padding=2)
    return img
