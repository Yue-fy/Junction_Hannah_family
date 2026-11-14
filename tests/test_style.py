"""Offline tests for stoa.style (drawing-style guess from image content). Owner: R2."""

from PIL import Image, ImageDraw

from stoa.style import CLASSES, guess_style


def _plan(tmp_path, name="plan.png"):
    im = Image.new("RGB", (600, 400), "white")
    d = ImageDraw.Draw(im)
    for box in ((20, 20, 580, 380), (20, 20, 300, 200), (300, 200, 580, 380)):
        d.rectangle(box, outline="black", width=6)
    p = tmp_path / name
    im.save(p)
    return str(p)


def test_guess_style_returns_a_known_class_and_probability(tmp_path):
    s, p = guess_style(_plan(tmp_path))
    assert s in CLASSES and 0.0 <= p <= 1.0
    # an in-memory image gives the same guess as its file
    assert guess_style(Image.open(_plan(tmp_path, "b.png")))[0] == s


def test_guess_style_on_jpeg_and_grayscale(tmp_path):
    p = _plan(tmp_path, "c.png")
    Image.open(p).convert("L").save(tmp_path / "c.jpg", quality=40)
    s, q = guess_style(str(tmp_path / "c.jpg"))
    assert s in CLASSES and 0.0 <= q <= 1.0
