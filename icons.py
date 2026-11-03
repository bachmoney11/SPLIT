"""Ikony šampionů z Data Dragonu (ddragon.leagueoflegends.com) -> jeden sprite data/icons.json (40 px, webp)."""
import json, requests, io, base64
from PIL import Image
V = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=30).json()[0]
d = requests.get(f"https://ddragon.leagueoflegends.com/cdn/{V}/data/en_US/champion.json", timeout=30).json()["data"]
names = sorted(d, key=lambda k: d[k]["name"]); S, cols = 40, 14
sheet = Image.new("RGB", (cols * S, ((len(names) + cols - 1) // cols) * S)); idx = {}
for i, k in enumerate(names):
    im = Image.open(io.BytesIO(requests.get(f"https://ddragon.leagueoflegends.com/cdn/{V}/img/champion/{k}.png", timeout=30).content)).convert("RGB").resize((S, S))
    sheet.paste(im, ((i % cols) * S, (i // cols) * S)); idx[d[k]["name"]] = i
b = io.BytesIO(); sheet.save(b, "WEBP", quality=80)
json.dump(dict(sprite="data:image/webp;base64," + base64.b64encode(b.getvalue()).decode(), cols=cols, size=S, idx=idx, version=V), open("data/icons.json", "w"))
print(V, len(names))
