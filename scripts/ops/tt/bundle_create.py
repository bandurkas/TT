"""Create the 16/24-pair black socks bundle as a DRAFT product (owner publishes in Seller Center). Usage inside worker:
  python -I - [--publish] < bundle_create.py   (images: /tmp/bundle_01_hero.jpg, /tmp/bundle_02_value.jpg)
Verified 10.11.2026: POST /product/202309/images/upload (multipart data+use_case) -> uri; POST /product/202309/products (save_mode AS_DRAFT)."""
import json, sys, time
from src.config.settings import settings
from src.integrations.tiktok_shop.client import FileTokenProvider, TikTokShopClient
from src.integrations.tiktok_shop.auth import TokenStore
from src.integrations.tiktok_shop.signing import compute_sign, normalise_query
PUBLISH = "--publish" in sys.argv
t = FileTokenProvider(TokenStore(f"{settings.token_store_dir}/tiktok_shop_tokens.json"), settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret)
c = TikTokShopClient(settings.tiktok_shop_app_key, settings.tiktok_shop_app_secret, t, shop_cipher=settings.tiktok_shop_shop_cipher or None)

def upload(path):
    p = "/product/202309/images/upload"
    q = normalise_query({"app_key": c.app_key, "timestamp": c.now_ms() // 1000})   # images/upload: no shop_cipher
    q["sign"] = compute_sign(c.app_secret, p, q, None)   # multipart body is not part of the signature
    r = c.http.post(c.base_url + p, params=q, headers={"x-tts-access-token": t.get_access_token()}, data={"use_case": "MAIN_IMAGE"},
                    files={"data": (path.split("/")[-1], open(path, "rb").read(), "image/jpeg")}, timeout=60)
    j = r.json(); assert j.get("code") == 0, j
    print("uploaded", path.split("/")[-1], j["data"]["uri"], j["data"]["width"], "x", j["data"]["height"]); time.sleep(1); return j["data"]["uri"]

uris = sys.argv[sys.argv.index("--uris") + 1].split(",") if "--uris" in sys.argv else [upload("/tmp/bundle_01_hero.jpg"), upload("/tmp/bundle_02_value.jpg")]
WH = "7658271036268283669"
SIZES = [("7668998138543539989", "Remaja: 36-40"), ("7702715619864217351", "Dewasa: 41-45")]
PACKS = [("16 pasang", 240000, "LM-B16"), ("24 pasang", 332000, "LM-B24")]
skus = []
for pack, price, sku in PACKS:
    for vid, vname in SIZES:
        skus.append({"seller_sku": f"{sku}-{'R' if vid.startswith('7668') else 'D'}", "price": {"amount": str(price), "currency": "IDR"},
                     "inventory": [{"warehouse_id": WH, "quantity": 50}],
                     "sales_attributes": [{"name": "Isi", "value_name": pack}, {"id": "100007", "name": "Ukuran", "value_id": vid, "value_name": vname}]})
DESC = ("<p><strong>LOMIRA KAOS KAKI HITAM – PAKET HEMAT 16 &amp; 24 PASANG</strong></p>"
        "<p><strong>Semakin banyak, semakin hemat.</strong> Stok kaos kaki untuk seminggu kerja plus cadangan dalam satu paket — tidak perlu beli lagi berbulan-bulan.</p>"
        "<p>Kaos kaki hitam LOMIRA dibuat dari <strong>85% katun</strong> dengan campuran spandeks: adem, menyerap keringat, elastis dan tidak longgar. Teknologi <strong>Air Mesh</strong> menjaga sirkulasi udara supaya kaki tidak gerah dan tidak bau.</p>"
        "<p><strong>PILIHAN PAKET</strong></p><ul><li><strong>16 pasang</strong> — cukup untuk 2 minggu tanpa cuci harian</li><li><strong>24 pasang</strong> — paling hemat per pasang, cocok untuk keluarga atau stok kantor</li></ul>"
        "<p><strong>UKURAN</strong></p><ul><li>Remaja: sepatu 36–40</li><li>Dewasa: sepatu 41–45</li></ul>"
        "<p><strong>KEUNGGULAN</strong></p><ul><li>Air Mesh — tidak gerah, cepat kering</li><li>Karet lembut &amp; elastis — pas di kaki, tidak meninggalkan bekas</li><li>Ujung &amp; tumit diperkuat — awet untuk pemakaian harian</li><li>Tahan cuci — warna hitam tetap pekat</li></ul>"
        "<p>Cocok untuk kerja, sekolah, jalan dan olahraga ringan. Unisex pria &amp; wanita.</p>")
body = {"title": "LOMIRA Kaos Kaki Hitam Paket Hemat 16 & 24 Pasang | Katun Air Mesh Unisex Pria Wanita Anti Bau",
        "description": DESC, "category_id": "841736", "category_version": "v2", "brand_id": "7046224178420188929", "main_images": [{"uri": u} for u in uris],
        "skus": skus, "package_weight": {"value": "0.5", "unit": "KILOGRAM"}, "package_dimensions": {"length": "20", "width": "15", "height": "10", "unit": "CENTIMETER"},
        "product_attributes": [{"id": "100157", "values": [{"name": "Katun"}, {"name": "Spandeks"}]}],
        "is_cod_allowed": True, "save_mode": "LISTING" if PUBLISH else "AS_DRAFT"}
r = c.request("POST", "/product/202309/products", body=body, resource="probe")
print("CREATED", json.dumps(r, ensure_ascii=False)[:800])
pid = r.get("product_id")
if pid:
    time.sleep(2); d = c.get_product(pid)
    print("READBACK", pid, d.get("status"), d.get("title")[:60], [(s.get("seller_sku"), s["price"].get("sale_price"), [a.get("value_name") for a in s.get("sales_attributes", [])], s["inventory"][0]["quantity"]) for s in d.get("skus", [])])
