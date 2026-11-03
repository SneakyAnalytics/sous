import io

from PIL import Image

from app import config

RECIPE = {"title": "Soup", "servings": 2, "ingredients": [], "steps": []}


def png(size=(3000, 2000), mode="RGB"):
    buf = io.BytesIO()
    Image.new(mode, size, (200, 80, 40) if mode == "RGB" else (200, 80, 40, 120)).save(buf, "PNG")
    return buf.getvalue()


def test_upload_resizes_stores_and_serves_a_cover(client):
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    assert client.get(f"/recipes/{rid}").json()["cover_updated"] is None
    r = client.put(f"/recipes/{rid}/cover", content=png(), headers={"content-type": "image/png"})
    assert r.status_code == 200 and r.json()["cover_updated"]
    got = client.get(f"/recipes/{rid}/cover")
    assert got.status_code == 200 and got.headers["content-type"] == "image/webp"
    img = Image.open(io.BytesIO(got.content))
    assert max(img.size) == 1200 and img.size == (1200, 800)
    assert "immutable" in got.headers["cache-control"]


def test_transparent_png_and_phone_rotation_are_handled(client):
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    assert client.put(f"/recipes/{rid}/cover", content=png((400, 300), "RGBA")).status_code == 200
    # a landscape JPEG whose EXIF says "rotate 90 degrees" must come out portrait
    buf = io.BytesIO()
    exif = Image.Exif(); exif[0x0112] = 6
    Image.new("RGB", (800, 600), (10, 120, 10)).save(buf, "JPEG", exif=exif)
    assert client.put(f"/recipes/{rid}/cover", content=buf.getvalue()).status_code == 200
    out = Image.open(io.BytesIO(client.get(f"/recipes/{rid}/cover").content))
    assert out.size == (600, 800)
    assert not out.getexif()  # location and camera data are not kept


def test_rejects_non_images_oversize_and_unknown_recipes(client, monkeypatch):
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    assert client.put(f"/recipes/{rid}/cover", content=b"not a picture").status_code == 422
    assert client.put("/recipes/999/cover", content=png((50, 50))).status_code == 404
    from app import covers
    monkeypatch.setattr(covers, "MAX_UPLOAD_BYTES", 100)
    assert client.put(f"/recipes/{rid}/cover", content=png((300, 300))).status_code == 413
    assert client.get(f"/recipes/{rid}").json()["cover_updated"] is None  # a failed upload changes nothing


def test_remove_cover_and_deleting_the_recipe_cleans_up(client):
    rid = client.post("/recipes", json=RECIPE).json()["id"]
    client.put(f"/recipes/{rid}/cover", content=png((300, 200)))
    path = config.DATA_DIR / "images" / f"{rid}.webp"
    assert path.exists()
    assert client.delete(f"/recipes/{rid}/cover").json()["cover_updated"] is None
    assert not path.exists() and client.get(f"/recipes/{rid}/cover").status_code == 404
    client.put(f"/recipes/{rid}/cover", content=png((300, 200)))
    client.delete(f"/recipes/{rid}")
    assert not path.exists()
