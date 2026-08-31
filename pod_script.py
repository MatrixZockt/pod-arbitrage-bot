#!/usr/bin/env python3
"""
pod_autonomous_money_machine_v3.py
=================================================================
Fixed Autonomous POD Pipeline:
- Generates pure flat graphic art (no room mockups)
- Smart Google Trends keyword mapping
- Multi-product & multi-size psychological pricing (.99)
=================================================================
"""

import base64
import datetime
import json
import os
import random
import re
import sys
import time
import urllib.parse
import xml.etree.ElementTree as ET

import requests

PRINTIFY_BASE_URL = "https://api.printify.com/v1"
GOOGLE_TRENDS_RSS = "https://trends.google.com/trending/rss?geo=US"

# FIXED: Strict flat graphic art prompt (removes room/interior scene generation)
PROMPT_TEMPLATE = (
    "minimalist contemporary abstract graphic art print, {keyword}, "
    "clean composition, rich tactile texture, elegant neutral and earth tone color palette, "
    "full bleed surface pattern, high resolution vector aesthetic"
)

DECOR_TAGS = [
    "wall art",
    "home decor",
    "art print",
    "minimalist aesthetic",
    "abstract art",
    "modern wall decor"
]

TARGET_BLUEPRINTS = [1226, 920, 617]

margin_env = os.environ.get("INTRO_MARGIN_PERCENT")
INTRO_MARGIN_PERCENT = float(margin_env) if margin_env and margin_env.strip() else 120.0

REQUEST_TIMEOUT = 30
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"


def log(step: str, message: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{step}] {message}")


def get_required_env(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        log("ENV", f"ERROR: Missing required environment variable '{var_name}'.")
        sys.exit(1)
    return value


def printify_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def fetch_smart_trend_concept() -> tuple:
    log("TREND", "Parsing live consumer interest for graphic art adaptation...")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(GOOGLE_TRENDS_RSS, headers=headers, timeout=15)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            titles = [elem.text for elem in root.findall(".//item/title") if elem.text]
            if titles:
                raw_trend = random.choice(titles[: min(15, len(titles))])
                clean_keyword = re.sub(r'[^\w\s]', '', raw_trend).strip().lower()
                
                art_styles = [
                    f"terracotta arch and abstract clay shapes inspired by {clean_keyword}",
                    f"moody moss green organic color block study capturing {clean_keyword}",
                    f"warm sand and minimalist geometric balance reflecting {clean_keyword}",
                    f"japandi style minimalist line art structure for {clean_keyword}"
                ]
                translated_concept = random.choice(art_styles)
                log("TREND", f"Successfully translated trend into graphic art concept.")
                return "smart_trend", translated_concept
    except Exception as exc:
        log("TREND", f"Feed warning: {exc}. Engaging evergreen vector.")

    evergreens = [
        "terracotta arch and textured clay abstract shapes",
        "moody moss green atmospheric minimalist color field",
        "warm sand and clay contemporary geometric balance"
    ]
    return "evergreen_viral", random.choice(evergreens)


def generate_canvas_image(keyword: str) -> bytes:
    prompt = PROMPT_TEMPLATE.format(keyword=keyword)
    encoded_prompt = urllib.parse.quote(prompt)
    # Using square/vertical dimensions optimized for print ratios
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=1600&nologo=true"
    
    log("IMAGE_GEN", "Requesting flat graphic art asset generation...")
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 5000:
                log("IMAGE_GEN", f"Graphic asset rendered successfully ({len(resp.content)} bytes).")
                return resp.content
        except Exception as exc:
            log("IMAGE_GEN", f"Attempt {attempt} failed: {exc}")
        time.sleep(5)
    
    log("IMAGE_GEN", "ERROR: Image generation failed.")
    sys.exit(1)


def upload_image_to_printify(api_key: str, image_bytes: bytes, file_name: str) -> str:
    url = f"{PRINTIFY_BASE_URL}/uploads/images.json"
    payload = {"file_name": file_name, "contents": base64.b64encode(image_bytes).decode("utf-8")}
    
    log("PRINTIFY_UPLOAD", "Uploading graphic asset to Printify library...")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_UPLOAD", f"ERROR [{resp.status_code}]: {resp.text[:300]}")
        sys.exit(1)
    
    image_id = resp.json().get("id")
    log("PRINTIFY_UPLOAD", f"Upload success. Printify image_id={image_id}")
    return image_id


def resolve_blueprint_config(api_key: str, blueprint_id: int) -> tuple:
    providers_url = f"{PRINTIFY_BASE_URL}/catalog/blueprints/{blueprint_id}/print_providers.json"
    try:
        resp = requests.get(providers_url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            return None, []
        providers = resp.json()
        if not providers:
            return None, []
        
        provider_id = providers[0].get("id")
        variants_url = f"{PRINTIFY_BASE_URL}/catalog/blueprints/{blueprint_id}/print_providers/{provider_id}/variants.json"
        v_resp = requests.get(variants_url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
        if v_resp.status_code != 200:
            return None, []
        
        variants_list = v_resp.json().get("variants", [])
        if variants_list:
            return provider_id, variants_list[:4]
    except Exception:
        pass
    return None, []


def calculate_psychological_price(base_cost_cents: int) -> int:
    raw_retail = base_cost_cents * (1 + INTRO_MARGIN_PERCENT / 100)
    dollars = raw_retail / 100.0
    rounded_base = round(dollars)
    if rounded_base < 10:
        rounded_base = 15
    return int((rounded_base * 100) - 1)


def create_product_for_blueprint(api_key: str, shop_id: str, image_id: str, trend_source: str, keyword: str, blueprint_id: int) -> str:
    provider_id, variants_list = resolve_blueprint_config(api_key, blueprint_id)
    if not provider_id or not variants_list:
        log("PRODUCT", f"Skipping blueprint {blueprint_id} (unavailable on current API scope).")
        return None

    bp_labels = {1226: "Gallery Wrapped Canvas", 920: "Framed Fine Art Print", 617: "Minimalist Desk Mat"}
    product_type_name = bp_labels.get(blueprint_id, "Home Decor Art Print")
    
    seo_title = f"Organic Modern {product_type_name} | Minimalist Contemporary Wall Art"

    variant_payloads = []
    variant_ids = []
    for v in variants_list:
        vid = v.get("id")
        base_cost = v.get("cost", 1500)
        retail_price = calculate_psychological_price(base_cost)
        variant_ids.append(vid)
        variant_payloads.append({
            "id": vid,
            "price": retail_price,
            "is_enabled": True
        })

    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products.json"
    payload = {
        "title": seo_title,
        "description": f"Curated museum-quality {product_type_name.lower()} featuring contemporary graphic art aesthetics. Designed to fill modern interior spaces with texture and visual depth.",
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "tags": DECOR_TAGS,
        "variants": variant_payloads,
        "print_areas": [{
            "variant_ids": variant_ids,
            "placeholders": [{
                "position": "front",
                "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]
            }]
        }],
    }

    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRODUCT", f"Warning: Failed to create product for blueprint {blueprint_id}: {resp.text[:200]}")
        return None

    product_id = resp.json().get("id")
    log("PRODUCT", f"Successfully registered product ID {product_id} for blueprint {blueprint_id}")
    return product_id


def publish_product(api_key: str, shop_id: str, product_id: str) -> None:
    if DRY_RUN:
        return
    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products/{product_id}/publish.json"
    payload = {"title": True, "description": True, "images": True, "variants": True, "tags": True}
    requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)


def main() -> None:
    log("PIPELINE", f"=== Starting Graphic Art Pipeline (DRY_RUN={DRY_RUN}) ===")
    api_key = get_required_env("PRINTIFY_API_KEY")
    shop_id = get_required_env("STORE_ID")

    trend_source, keyword = fetch_smart_trend_concept()
    image_bytes = generate_canvas_image(keyword)
    image_id = upload_image_to_printify(api_key, image_bytes, f"graphic_art_{int(time.time())}.png")
    
    created_products = []
    for bp_id in TARGET_BLUEPRINTS:
        prod_id = create_product_for_blueprint(api_key, shop_id, image_id, trend_source, keyword, bp_id)
        if prod_id:
            publish_product(api_key, shop_id, prod_id)
            created_products.append(prod_id)

    log("PIPELINE", f"=== Execution Complete. Published {len(created_products)} graphic art items. ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log("PIPELINE", f"FATAL UNHANDLED ERROR: {e}")
        sys.exit(1)
