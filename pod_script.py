#!/usr/bin/env python3
"""
pod_autonomous_money_machine_v3.py
=================================================================
Deterministic Clean Art Pipeline:
- Uses stable curated design parameters instead of broken RSS text
- Forces lifestyle room mockup to primary thumbnail position 0
- Front-loaded high-intent SEO titles and 13 unique Etsy tags
=================================================================
"""

import base64
import datetime
import os
import random
import sys
import time
import urllib.parse
import requests

PRINTIFY_BASE_URL = "https://api.printify.com/v1"

# STABLE CURATED DESIGN PROMPTS (Bypasses broken RSS string inputs)
CURATED_ART_CONCEPTS = [
    "minimalist organic arch composition, neutral beige and terracotta earth tones, textured plaster background, modern contemporary wall art",
    "scandinavian botanical line art, sage green and soft cream color block, clean aesthetic, abstract nature study",
    "japandi style minimalist geometric balance, warm sand and charcoal strokes, wabi-sabi texture, premium art print",
    "abstract mid-century modern shapes, muted olive green and clay color palette, soft brush stroke details"
]

OPTIMIZED_ETSY_TAGS = [
    "Minimalist wall art",
    "Neutral abstract print",
    "Japandi decor",
    "Large canvas print",
    "Sage green aesthetic",
    "Modern home decor",
    "Cozy living room art",
    "Earth tone artwork",
    "Scandi wall decor",
    "Abstract canvas art",
    "Housewarming gift",
    "Minimal art print",
    "Bestseller wall decor"
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


def generate_canvas_image() -> bytes:
    concept = random.choice(CURATED_ART_CONCEPTS)
    encoded_prompt = urllib.parse.quote(concept)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=1600&nologo=true"
    
    log("IMAGE_GEN", f"Requesting clean art generation for concept: {concept[:40]}...")
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 5000:
                log("IMAGE_GEN", f"Asset rendered successfully ({len(resp.content)} bytes).")
                return resp.content
        except Exception as exc:
            log("IMAGE_GEN", f"Attempt {attempt} failed: {exc}")
        time.sleep(5)
    
    log("IMAGE_GEN", "ERROR: Image generation failed.")
    sys.exit(1)


def upload_image_to_printify(api_key: str, image_bytes: bytes) -> str:
    url = f"{PRINTIFY_BASE_URL}/uploads/images.json"
    payload = {"file_name": f"art_print_{int(time.time())}.png", "contents": base64.b64encode(image_bytes).decode("utf-8")}
    
    log("PRINTIFY_UPLOAD", "Uploading asset to Printify library...")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_UPLOAD", f"ERROR [{resp.status_code}]: {resp.text[:300]}")
        sys.exit(1)
    
    image_id = resp.json().get("id")
    log("PRINTIFY_UPLOAD", f"Upload success. image_id={image_id}")
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


def create_product_for_blueprint(api_key: str, shop_id: str, image_id: str, blueprint_id: int) -> str:
    provider_id, variants_list = resolve_blueprint_config(api_key, blueprint_id)
    if not provider_id or not variants_list:
        log("PRODUCT", f"Skipping blueprint {blueprint_id}.")
        return None

    bp_labels = {1226: "Gallery Canvas", 920: "Framed Fine Art", 617: "Minimalist Desk Mat"}
    product_type_name = bp_labels.get(blueprint_id, "Art Print")
    
    seo_title = f"Minimalist Wall Art, {product_type_name}, Neutral Earth Tone Canvas Print"

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
        "description": f"Curated museum-quality {product_type_name.lower()} featuring contemporary graphic art aesthetics.",
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "tags": OPTIMIZED_ETSY_TAGS,
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
        log("PRODUCT", f"Failed to create product for blueprint {blueprint_id}: {resp.text[:200]}")
        return None

    product_data = resp.json()
    product_id = product_data.get("id")
    
    # FORCE LIFESTYLE MOCKUP TO INDEX 0 (Thumbnail position)
    product_images = product_data.get("images", [])
    if product_images and len(product_images) > 1:
        lifestyle_idx = next((i for i, img in enumerate(product_images) if img.get("position") != "front"), None)
        if lifestyle_idx is not None and lifestyle_idx != 0:
            img_to_front = product_images.pop(lifestyle_idx)
            product_images.insert(0, img_to_front)
            update_url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products/{product_id}.json"
            requests.put(update_url, headers=printify_headers(api_key), json={"images": product_images}, timeout=REQUEST_TIMEOUT)
            log("PRODUCT", f"Forced lifestyle mockup to primary thumbnail for product {product_id}")

    log("PRODUCT", f"Registered product ID {product_id} for blueprint {blueprint_id}")
    return product_id


def publish_product(api_key: str, shop_id: str, product_id: str) -> None:
    if DRY_RUN:
        return
    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products/{product_id}/publish.json"
    payload = {"title": True, "description": True, "images": True, "variants": True, "tags": True}
    requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)


def main() -> None:
    log("PIPELINE", f"=== Starting Clean Art Pipeline (DRY_RUN={DRY_RUN}) ===")
    api_key = get_required_env("PRINTIFY_API_KEY")
    shop_id = get_required_env("STORE_ID")

    image_bytes = generate_canvas_image()
    image_id = upload_image_to_printify(api_key, image_bytes)
    
    created_products = []
    for bp_id in TARGET_BLUEPRINTS:
        prod_id = create_product_for_blueprint(api_key, shop_id, image_id, bp_id)
        if prod_id:
            publish_product(api_key, shop_id, prod_id)
            created_products.append(prod_id)

    log("PIPELINE", f"=== Complete. Published {len(created_products)} clean art items. ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log("PIPELINE", f"FATAL ERROR: {e}")
        sys.exit(1)
