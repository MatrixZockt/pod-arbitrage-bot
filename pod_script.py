#!/usr/bin/env python3
"""
pod_optimized_pipeline.py
=================================================================
Fully Optimized High-Margin POD Pipeline:
- Viral 2026 Organic Modern / Earthy Trend Ingestion
- SEO-Optimized Buyer-Intent Product Titles & Tags
- Psychological Pricing Engine (Ending in .99)
- Multi-Size Variant Tiering & Multi-Product Expansion
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

import requests

PRINTIFY_BASE_URL = "https://api.printify.com/v1"

VIRAL_TREND_CONCEPTS = [
    "organic modern terracotta arch and minimalist line art",
    "moody moss green botanical abstract forms",
    "warm sand and clay textured contemporary minimalism",
    "japonandi style minimalist branch and circle",
    "soft neutral bauhaus geometric shapes and warm beige tones"
]

PROMPT_TEMPLATE = (
    "{keyword}, modern contemporary fine art print, "
    "organic modern aesthetic, warm earth tones, tactile feel, "
    "clean composition, full bleed graphic, high resolution, sharp focus"
)

DECOR_TAGS = [
    "wall art",
    "home decor",
    "art print",
    "minimalist aesthetic",
    "interior styling",
    "organic modern",
    "neutral wall art"
]

# High-AOV product categories: Canvas (1226), Framed Posters (920), Desk Mats (617)
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


def fetch_decor_concept() -> str:
    concept = random.choice(VIRAL_TREND_CONCEPTS)
    log("TREND", f"Selected high-intent viral trend concept: '{concept}'")
    return concept


def generate_canvas_image(keyword: str) -> bytes:
    prompt = PROMPT_TEMPLATE.format(keyword=keyword)
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=900&nologo=true"
    
    log("IMAGE_GEN", "Requesting master fine-art asset generation...")
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 2000:
                log("IMAGE_GEN", f"Master asset rendered successfully ({len(resp.content)} bytes).")
                return resp.content
        except Exception as exc:
            log("IMAGE_GEN", f"Attempt {attempt} failed: {exc}")
        time.sleep(5)
    
    log("IMAGE_GEN", "ERROR: Image generation failed.")
    sys.exit(1)


def upload_image_to_printify(api_key: str, image_bytes: bytes, file_name: str) -> str:
    url = f"{PRINTIFY_BASE_URL}/uploads/images.json"
    payload = {"file_name": file_name, "contents": base64.b64encode(image_bytes).decode("utf-8")}
    
    log("PRINTIFY_UPLOAD", f"Uploading master asset to Printify library...")
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
            chosen_variants = variants_list[:4] # Tier up to 4 standard sizes
            return provider_id, chosen_variants
    except Exception:
        pass
    return None, []


def calculate_psychological_price(base_cost_cents: int) -> int:
    """Applies target margin and adjusts price to end in psychological .99 threshold."""
    raw_retail = base_cost_cents * (1 + INTRO_MARGIN_PERCENT / 100)
    dollars = raw_retail / 100.0
    # Round to nearest whole tier and subtract 1 cent to create X.99 pricing
    rounded_base = round(dollars)
    if rounded_base < 10:
        rounded_base = 15  # Minimum safety floor
    psychological_price_cents = (rounded_base * 100) - 1
    return int(psychological_price_cents)


def create_product_for_blueprint(api_key: str, shop_id: str, image_id: str, keyword: str, blueprint_id: int) -> str:
    provider_id, variants_list = resolve_blueprint_config(api_key, blueprint_id)
    if not provider_id or not variants_list:
        log("PRODUCT", f"Skipping blueprint {blueprint_id} (unavailable on current API scope).")
        return None

    # SEO Product Title mapping based on blueprint category
    bp_labels = {1226: "Gallery Wrapped Canvas", 920: "Framed Fine Art Print", 617: "Minimalist Desk Mat"}
    product_type_name = bp_labels.get(blueprint_id, "Home Decor Art Print")
    seo_title = f"{keyword.title()} | {product_type_name} | Organic Modern Wall Art"

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
        "description": f"Elevate your interior styling with this museum-quality {product_type_name.lower()} featuring {keyword}. Crafted with rich tactile texture and fade-resistant print technology.",
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "tags": keyword.split() + DECOR_TAGS,
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
    log("PRODUCT", f"Successfully created optimized SEO product ID {product_id} for blueprint {blueprint_id}")
    return product_id


def publish_product(api_key: str, shop_id: str, product_id: str) -> None:
    if DRY_RUN:
        return
    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products/{product_id}/publish.json"
    payload = {"title": True, "description": True, "images": True, "variants": True, "tags": True}
    requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)


def main() -> None:
    log("PIPELINE", f"=== Starting Fully Optimized Multi-Product Pipeline (DRY_RUN={DRY_RUN}) ===")
    api_key = get_required_env("PRINTIFY_API_KEY")
    shop_id = get_required_env("STORE_ID")

    keyword = fetch_decor_concept()
    image_bytes = generate_canvas_image(keyword)
    image_id = upload_image_to_printify(api_key, image_bytes, f"optimized_asset_{int(time.time())}.png")
    
    created_products = []
    for bp_id in TARGET_BLUEPRINTS:
        prod_id = create_product_for_blueprint(api_key, shop_id, image_id, keyword, bp_id)
        if prod_id:
            publish_product(api_key, shop_id, prod_id)
            created_products.append(prod_id)

    log("PIPELINE", f"=== Fully Optimized Execution Complete. Created {len(created_products)} high-conversion items. ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log("PIPELINE", f"FATAL UNHANDLED ERROR: {e}")
        sys.exit(1)
