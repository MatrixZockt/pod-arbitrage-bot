#!/usr/bin/env python3
"""
pod_canvas_pipeline_v3.py
=================================================================
Resilient High-Margin POD Pipeline (Fixed Endpoints Edition).
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

# -----------------------------------------------------------------
# CONFIG / CONSTANTS
# -----------------------------------------------------------------

# Using an open, unblocked design trend rotation source instead of Reddit
DESIGN_TRENDS_URL = "https://gist.githubusercontent.com/raw/placeholder-design-terms.json" # handled via fallback list if needed
FALLBACK_CONCEPTS = [
    "botanical eucalyptus branch",
    "serene alpine mountain ridge",
    "abstract minimalist coastal horizon",
    "mid-century geometric sun and arch",
    "line art botanical wild fern"
]

PRINTIFY_BASE_URL = "https://api.printify.com/v1"

PROMPT_TEMPLATE = (
    "minimalist abstract line art and organic shapes representing {keyword}, "
    "modern contemporary fine art print, elegant neutral color palette, "
    "clean composition, full bleed graphic, high resolution, sharp focus"
)

DECOR_TAGS = [
    "wall art",
    "home decor",
    "canvas print",
    "minimalist aesthetic",
    "interior styling",
]

# Verified active canvas blueprints
ACTIVE_BLUEPRINTS = [1226, 900]

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
    log("TREND", "Selecting curated interior styling concept...")
    concept = random.choice(FALLBACK_CONCEPTS)
    log("TREND", f"Selected high-intent decor concept: '{concept}'")
    return concept


def generate_canvas_image(keyword: str) -> bytes:
    prompt = PROMPT_TEMPLATE.format(keyword=keyword)
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=900&nologo=true"
    
    log("IMAGE_GEN", "Requesting high-resolution canvas render from Pollinations.ai...")
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 2000:
                log("IMAGE_GEN", f"Canvas artwork rendered successfully ({len(resp.content)} bytes).")
                return resp.content
        except Exception as exc:
            log("IMAGE_GEN", f"Attempt {attempt} failed: {exc}")
        time.sleep(5)
    
    log("IMAGE_GEN", "ERROR: Canvas image generation failed.")
    sys.exit(1)


def upload_image_to_printify(api_key: str, image_bytes: bytes, file_name: str) -> str:
    url = f"{PRINTIFY_BASE_URL}/uploads/images.json"
    payload = {"file_name": file_name, "contents": base64.b64encode(image_bytes).decode("utf-8")}
    
    log("PRINTIFY_UPLOAD", f"Uploading high-res canvas art asset to Printify...")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_UPLOAD", f"ERROR [{resp.status_code}]: {resp.text[:300]}")
        sys.exit(1)
    
    image_id = resp.json().get("id")
    log("PRINTIFY_UPLOAD", f"Upload success. Printify image_id={image_id}")
    return image_id


def resolve_working_blueprint(api_key: str) -> tuple:
    """Iterates through active canvas blueprints to find a valid provider/variant configuration."""
    for bp_id in ACTIVE_BLUEPRINTS:
        providers_url = f"{PRINTIFY_BASE_URL}/catalog/blueprints/{bp_id}/print_providers.json"
        log("PRINTIFY_DISCOVERY", f"Checking print providers for canvas blueprint {bp_id}...")
        try:
            resp = requests.get(providers_url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            providers = resp.json()
            if not providers:
                continue
            
            provider_id = providers[0].get("id")
            variants_url = f"{PRINTIFY_BASE_URL}/catalog/blueprints/{bp_id}/print_providers/{provider_id}/variants.json"
            v_resp = requests.get(variants_url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
            if v_resp.status_code != 200:
                continue
            
            variants_list = v_resp.json().get("variants", [])
            if variants_list:
                chosen = variants_list[:1]
                variant_ids = [v.get("id") for v in chosen]
                base_cost = chosen[0].get("cost", 2000)
                log("PRINTIFY_DISCOVERY", f"Successfully resolved Blueprint ID {bp_id} with Provider {provider_id}")
                return bp_id, provider_id, variant_ids, base_cost
        except Exception as exc:
            log("PRINTIFY_DISCOVERY", f"Skipping blueprint {bp_id} due to error: {exc}")
            continue

    log("PRINTIFY_DISCOVERY", "ERROR: Could not resolve any active print provider/blueprint configuration.")
    sys.exit(1)


def create_canvas_product(api_key: str, shop_id: str, image_id: str, keyword: str) -> str:
    blueprint_id, provider_id, variant_ids, base_cost = resolve_working_blueprint(api_key)
    retail_price = int(round(base_cost * (1 + INTRO_MARGIN_PERCENT / 100)))

    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products.json"
    payload = {
        "title": f"{keyword.title()} Premium Gallery Wrapped Canvas",
        "description": f"Museum-quality art print featuring {keyword}.",
        "blueprint_id": blueprint_id,
        "print_provider_id": provider_id,
        "tags": [keyword] + DECOR_TAGS,
        "variants": [{"id": vid, "price": retail_price, "is_enabled": True} for vid in variant_ids],
        "print_areas": [{
            "variant_ids": variant_ids,
            "placeholders": [{
                "position": "front",
                "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]
            }]
        }],
    }

    log("PRINTIFY_PRODUCT", f"Submitting high-margin canvas payload to shop endpoint...")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PRODUCT", f"ERROR [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)

    product_id = resp.json().get("id")
    log("PRINTIFY_PRODUCT", f"High-AOV canvas product successfully registered. product_id={product_id}")
    return product_id


def publish_product(api_key: str, shop_id: str, product_id: str) -> None:
    if DRY_RUN:
        log("PRINTIFY_PUBLISH", "DRY_RUN is active. Skipping marketplace synchronization safely.")
        return

    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products/{product_id}/publish.json"
    payload = {"title": True, "description": True, "images": True, "variants": True, "tags": True}

    log("PRINTIFY_PUBLISH", f"Publishing high-margin canvas {product_id}...")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PUBLISH", f"ERROR [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)
    log("PRINTIFY_PUBLISH", f"Canvas product {product_id} successfully published.")


def main() -> None:
    log("PIPELINE", f"=== Starting High-Margin Canvas Pipeline Execution (DRY_RUN={DRY_RUN}) ===")
    api_key = get_required_env("PRINTIFY_API_KEY")
    shop_id = get_required_env("STORE_ID")

    keyword = fetch_decor_concept()
    image_bytes = generate_canvas_image(keyword)
    image_id = upload_image_to_printify(api_key, image_bytes, f"canvas_{int(time.time())}.png")
    
    product_id = create_canvas_product(api_key, shop_id, image_id, keyword)
    publish_product(api_key, shop_id, product_id)
    log("PIPELINE", f"=== High-Margin Pipeline Execution Completed. product_id={product_id} ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        log("PIPELINE", f"FATAL UNHANDLED ERROR: {e}")
        sys.exit(1)
