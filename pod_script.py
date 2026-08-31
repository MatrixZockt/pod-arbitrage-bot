#!/usr/bin/env python3
"""
pod_canvas_pipeline.py
=================================================================
High-Margin Automated POD Pipeline (Canvas Wall Art Edition).

Pipeline stages:
    1. Sentiment & Decor Trend Ingestion (Home & Living focus)
    2. High-Resolution Minimalist Vector / Line-Art Prompt Mapping
    3. Keyless High-Res Image Generation via Pollinations.ai API
    4. Printify API v1 Integration: Stretched Gallery Canvas Blueprint (#383)
    5. Automatic High-AOV Retail Calculation & Multi-Variant Payload Generation
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

import feedparser
import requests

# -----------------------------------------------------------------
# CONFIG / CONSTANTS
# -----------------------------------------------------------------

GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo=US"
REDDIT_FALLBACK_URL = "https://www.reddit.com/r/CozyPlaces/top.json?limit=10&t=day"
PRINTIFY_BASE_URL = "https://api.printify.com/v1"

# Optimized for high-end home decor canvas prints (clean lines, safe framing layout)
PROMPT_TEMPLATE = (
    "minimalist botanical line art and abstract watercolor elements representing {keyword}, "
    "nordic interior design style, elegant neutral color palette, "
    "high-end gallery wall art aesthetic, clean composition, "
    "isolated on a solid warm off-white background, high resolution, sharp focus"
)

DECOR_TAGS = [
    "wall art",
    "home decor",
    "canvas print",
    "minimalist aesthetic",
    "interior styling",
    "gift for home",
]

DEFAULT_BLUEPRINT_ID = 383  # Stretched Canvas, Multiple Sizes

variant_env = os.environ.get("PRINTIFY_VARIANT_IDS")
DEFAULT_VARIANT_IDS = [
    int(v) for v in variant_env.split(",")
] if variant_env and variant_env.strip() else []

# High-margin baseline: targeting 100%+ markup to ensure $25+ net profit per unit
margin_env = os.environ.get("INTRO_MARGIN_PERCENT")
INTRO_MARGIN_PERCENT = float(margin_env) if margin_env and margin_env.strip() else 120.0

REQUEST_TIMEOUT = 30
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"


# -----------------------------------------------------------------
# LOGGING HELPER
# -----------------------------------------------------------------

def log(step: str, message: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{step}] {message}")


def get_required_env(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        log("ENV", f"ERROR: Missing required environment variable '{var_name}'.")
        sys.exit(1)
    return value


# -----------------------------------------------------------------
# STAGE 1: TREND & DECOR CONCEPT INGESTION
# -----------------------------------------------------------------

def sanitize_keyword(raw_keyword: str) -> str:
    clean = re.sub(r'[^\w\s]', '', raw_keyword)
    clean = " ".join(clean.split())
    return clean.lower()


def fetch_decor_concept() -> str:
    log("TREND", f"Fetching interior styling trends from Reddit CozyPlaces/Lifestyle feeds...")
    try:
        headers = {"User-Agent": "pod-canvas-bot/1.0"}
        resp = requests.get(REDDIT_FALLBACK_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        titles = [p["data"]["title"].strip() for p in posts if p.get("data", {}).get("title")]
        if titles:
            raw_keyword = random.choice(titles[: min(5, len(titles))])
            raw_keyword = " ".join(raw_keyword.split()[:3])  # Keep core subject clean
            keyword = sanitize_keyword(raw_keyword)
            log("TREND", f"Selected high-intent decor concept: '{keyword}'")
            return keyword
    except Exception as exc:
        log("TREND", f"Community feed fallback failed: {exc}. Using evergreen aesthetic default.")
    
    fallback = random.choice(["serene mountain landscape", "botanical eucalyptus branch", "abstract coastal horizon", "mid century geometric warmth"])
    log("TREND", f"Using curated evergreen decor concept: '{fallback}'")
    return fallback


# -----------------------------------------------------------------
# STAGE 2 & 3: HIGH-RES GENERATION
# -----------------------------------------------------------------

def build_prompt(keyword: str) -> str:
    prompt = PROMPT_TEMPLATE.format(keyword=keyword)
    log("PROMPT", f"Constructed fine-art canvas prompt: {prompt}")
    return prompt


def generate_canvas_image(prompt: str) -> bytes:
    encoded_prompt = urllib.parse.quote(prompt)
    # Requesting a wider 4:3 canvas aspect ratio resolution suitable for wall art
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1200&height=900&nologo=true"
    
    log("IMAGE_GEN", f"Requesting high-resolution canvas render from Pollinations.ai...")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=90)
            if resp.status_code == 200 and len(resp.content) > 2000:
                log("IMAGE_GEN", f"Canvas artwork rendered successfully ({len(resp.content)} bytes).")
                return resp.content
            else:
                log("IMAGE_GEN", f"Attempt {attempt} received status {resp.status_code}. Retrying...")
        except Exception as exc:
            log("IMAGE_GEN", f"Attempt {attempt} failed with error: {exc}. Retrying...")
        
        if attempt < max_retries:
            time.sleep(10)

    log("IMAGE_GEN", "ERROR: Canvas image generation failed after all retry attempts.")
    sys.exit(1)


# -----------------------------------------------------------------
# STAGE 4 & 5: PRINTIFY API INTEGRATION (CANVAS BLUEPRINT)
# -----------------------------------------------------------------

def printify_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def upload_image_to_printify(api_key: str, image_bytes: bytes, file_name: str) -> str:
    url = f"{PRINTIFY_BASE_URL}/uploads/images.json"
    b64_contents = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "file_name": file_name,
        "contents": b64_contents,
    }

    log("PRINTIFY_UPLOAD", f"Uploading high-res canvas art asset to Printify: {url}")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_UPLOAD", f"ERROR: Upload failed [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)

    image_id = resp.json().get("id")
    log("PRINTIFY_UPLOAD", f"Upload success. Printify image_id={image_id}")
    return image_id


def resolve_blueprint_and_variants(api_key: str, blueprint_id: int, requested_ids: list) -> tuple:
    providers_url = f"{PRINTIFY_BASE_URL}/catalog/blueprints/{blueprint_id}/print_providers.json"
    log("PRINTIFY_DISCOVERY", f"Querying verified print providers for canvas blueprint {blueprint_id}...")
    
    try:
        resp = requests.get(providers_url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        providers = resp.json()
        
        if not providers:
            log("PRINTIFY_DISCOVERY", f"ERROR: No print providers available for canvas blueprint ID {blueprint_id}.")
            sys.exit(1)
        
        print_provider_id = providers[0].get("id")
        log("PRINTIFY_DISCOVERY", f"Discovered optimal print_provider_id={print_provider_id}")
        
    except Exception as exc:
        log("PRINTIFY_DISCOVERY", f"ERROR: Failed to query print providers: {exc}")
        sys.exit(1)

    variants_url = f"{PRINTIFY_BASE_URL}/catalog/blueprints/{blueprint_id}/print_providers/{print_provider_id}/variants.json"
    log("PRINTIFY_VARIANTS", f"Fetching premium canvas variant schema...")
    
    try:
        resp = requests.get(variants_url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        variants_list = data.get("variants", [])
        
        if not variants_list:
            log("PRINTIFY_VARIANTS", "ERROR: Canvas catalog response contained zero variants.")
            sys.exit(1)

        available_ids = [v.get("id") for v in variants_list if v.get("id")]
        
        if requested_ids:
            valid_requested = [vid for vid in requested_ids if vid in available_ids]
            if valid_requested:
                costs = [v.get("cost", 2000) for v in variants_list if v.get("id") in valid_requested]
                avg_cost = int(sum(costs) / len(costs)) if costs else 2000
                return print_provider_id, valid_requested, avg_cost

        # Default to up to 2 standard wall sizes if none specified
        chosen_variants = variants_list[:2] if len(variants_list) >= 2 else variants_list
        chosen_ids = [v.get("id") for v in chosen_variants]
        costs = [v.get("cost", 2000) for v in chosen_variants]
        avg_cost = int(sum(costs) / len(costs)) if costs else 2000
        
        log("PRINTIFY_VARIANTS", f"Auto-selected high-AOV canvas variant IDs: {chosen_ids} (Avg Base Cost: {avg_cost} cents)")
        return print_provider_id, chosen_ids, avg_cost

    except Exception as exc:
        log("PRINTIFY_VARIANTS", f"ERROR: Failed to retrieve variant catalog: {exc}")
        sys.exit(1)


def create_canvas_product(api_key: str, shop_id: str, image_id: str, keyword: str,
                           blueprint_id: int, user_variant_ids: list) -> str:
    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products.json"

    print_provider_id, variant_ids, base_cost_cents = resolve_blueprint_and_variants(
        api_key, blueprint_id, user_variant_ids
    )
    # High-AOV pricing calculation
    retail_price_cents = int(round(base_cost_cents * (1 + INTRO_MARGIN_PERCENT / 100)))

    tags = [keyword] + DECOR_TAGS
    title = f"{keyword.title()} Premium Gallery Wrapped Canvas"
    description = (
        f"Transform your space with this museum-quality gallery wrapped canvas featuring an "
        f"exclusive minimalist interpretation of {keyword}. Printed with fade-resistant UV inks "
        f"on durable poly-cotton blend canvas, stretched professionally over kiln-dried pine wood frames."
    )

    payload = {
        "title": title,
        "description": description,
        "blueprint_id": blueprint_id,
        "print_provider_id": print_provider_id,
        "tags": tags,
        "variants": [{"id": vid, "price": retail_price_cents, "is_enabled": True} for vid in variant_ids],
        "print_areas": [{
            "variant_ids": variant_ids,
            "placeholders": [{
                "position": "front",
                "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1.0, "angle": 0}]
            }]
        }],
    }

    log("PRINTIFY_PRODUCT", f"Submitting high-margin canvas payload to shop endpoint: {url}")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PRODUCT", f"ERROR: Canvas creation rejected [{resp.status_code}]: {resp.text[:800]}")
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

    log("PRINTIFY_PUBLISH", f"Publishing high-margin canvas {product_id} at: {url}")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PUBLISH", f"ERROR: Publish failed [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)
    log("PRINTIFY_PUBLISH", f"Canvas product {product_id} successfully published.")


# -----------------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------------

def main() -> None:
    log("PIPELINE", f"=== Starting High-Margin Canvas Pipeline Execution (DRY_RUN={DRY_RUN}) ===")

    printify_api_key = get_required_env("PRINTIFY_API_KEY")
    shop_id = get_required_env("STORE_ID")

    keyword = fetch_decor_concept()
    prompt = build_prompt(keyword)
    image_bytes = generate_canvas_image(prompt)
    file_name = f"canvas_{keyword.replace(' ', '_')}_{int(time.time())}.png"

    image_id = upload_image_to_printify(printify_api_key, image_bytes, file_name)
    product_id = create_canvas_product(
        printify_api_key, shop_id, image_id, keyword,
        DEFAULT_BLUEPRINT_ID, DEFAULT_VARIANT_IDS
    )
    publish_product(printify_api_key, shop_id, product_id)

    log("PIPELINE", f"=== High-Margin Pipeline Execution Completed. Concept='{keyword}', product_id={product_id} ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as unexpected_error:
        log("PIPELINE", f"FATAL UNHANDLED ERROR: {unexpected_error}")
        sys.exit(1)
