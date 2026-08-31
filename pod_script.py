#!/usr/bin/env python3
"""
pod_script.py
=================================================================
Autonomous, zero-cost Print-on-Demand (POD) arbitrage pipeline.

Pipeline stages:
    1. Zero-token trend ingestion (Google Trends RSS -> Reddit JSON fallback)
    2. Deterministic prompt construction (hardcoded template, no LLM tokens)
    3. Keyless image generation via Pollinations.ai API with retry logic
    4. Printify API v1 integration: upload image -> create product -> (optional publish)
    5. Verbose, timestamped logging at every step
=================================================================
"""

import base64
import datetime
import json
import os
import random
import sys
import time
import urllib.parse

import feedparser
import requests

# -----------------------------------------------------------------
# CONFIG / CONSTANTS
# -----------------------------------------------------------------

GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo=US"
REDDIT_FALLBACK_URL = "https://www.reddit.com/r/popular/top.json?limit=10&t=day"
PRINTIFY_BASE_URL = "https://api.printify.com/v1"

PROMPT_TEMPLATE = (
    "minimalist vector sticker design of {keyword}, "
    "bold flat colors, thick black outline, die-cut sticker style, "
    "centered composition, white background, no text, no watermark, "
    "high contrast, clean simple shapes, trending on artstation"
)

EVERGREEN_TAGS = [
    "sticker",
    "gift idea",
    "trendy design",
    "funny gift",
    "aesthetic",
    "cute sticker",
]

# Hardcoded to 1268 (Vinyl Stickers) to permanently bypass any GitHub Secret overrides
DEFAULT_BLUEPRINT_ID = 1268
DEFAULT_PRINT_PROVIDER_ID = 1

variant_env = os.environ.get("PRINTIFY_VARIANT_IDS")
DEFAULT_VARIANT_IDS = [
    int(v) for v in variant_env.split(",")
] if variant_env and variant_env.strip() else []

margin_env = os.environ.get("INTRO_MARGIN_PERCENT")
INTRO_MARGIN_PERCENT = float(margin_env) if margin_env and margin_env.strip() else 15.0

REQUEST_TIMEOUT = 30

# Safe testing toggle: if true, creates the draft/product on Printify 
# but skips the public publish request entirely.
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"


# -----------------------------------------------------------------
# LOGGING HELPER
# -----------------------------------------------------------------

def log(step: str, message: str) -> None:
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{step}] {message}")


# -----------------------------------------------------------------
# ENVIRONMENT / SECRETS
# -----------------------------------------------------------------

def get_required_env(var_name: str) -> str:
    value = os.environ.get(var_name)
    if not value:
        log("ENV", f"ERROR: Missing required environment variable '{var_name}'.")
        sys.exit(1)
    return value


# -----------------------------------------------------------------
# STAGE 1: ZERO-TOKEN TREND INGESTION
# -----------------------------------------------------------------

def fetch_trending_keyword() -> str:
    log("TREND", f"Fetching Google Trends RSS: {GOOGLE_TRENDS_RSS_URL}")
    try:
        feed = feedparser.parse(GOOGLE_TRENDS_RSS_URL)
        if feed.entries:
            candidates = [entry.title.strip() for entry in feed.entries if entry.get("title")]
            if candidates:
                keyword = random.choice(candidates[: min(5, len(candidates))])
                log("TREND", f"Google Trends selected keyword: '{keyword}'")
                return keyword
    except Exception as exc:
        log("TREND", f"Google Trends RSS fetch failed: {exc}. Falling back to Reddit.")

    try:
        headers = {"User-Agent": "pod-arbitrage-bot/1.0"}
        log("TREND", f"Fetching Reddit fallback: {REDDIT_FALLBACK_URL}")
        resp = requests.get(REDDIT_FALLBACK_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        titles = [p["data"]["title"].strip() for p in posts if p.get("data", {}).get("title")]
        keyword = random.choice(titles[: min(5, len(titles))])
        keyword = " ".join(keyword.split()[:6])
        log("TREND", f"Reddit fallback selected keyword: '{keyword}'")
        return keyword
    except Exception as exc:
        log("TREND", f"ERROR: Trend ingestion failed: {exc}")
        sys.exit(1)


# -----------------------------------------------------------------
# STAGE 2: DETERMINISTIC PROMPT MAPPING
# -----------------------------------------------------------------

def build_prompt(keyword: str) -> str:
    prompt = PROMPT_TEMPLATE.format(keyword=keyword)
    log("PROMPT", f"Constructed image prompt: {prompt}")
    return prompt


# -----------------------------------------------------------------
# STAGE 3: IMAGE GENERATION (POLLINATIONS.AI)
# -----------------------------------------------------------------

def generate_image(prompt: str) -> bytes:
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
    
    log("IMAGE_GEN", f"Requesting image generation from Pollinations.ai endpoint...")

    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200 and len(resp.content) > 1000:
                log("IMAGE_GEN", f"Image generated successfully ({len(resp.content)} bytes).")
                return resp.content
            else:
                log("IMAGE_GEN", f"Attempt {attempt} received status {resp.status_code}. Retrying...")
        except Exception as exc:
            log("IMAGE_GEN", f"Attempt {attempt} failed with error: {exc}. Retrying...")
        
        if attempt < max_retries:
            time.sleep(10)

    log("IMAGE_GEN", "ERROR: Image generation failed after all retry attempts.")
    sys.exit(1)


# -----------------------------------------------------------------
# STAGE 4: PRINTIFY INTEGRATION
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

    log("PRINTIFY_UPLOAD", f"Uploading image to Printify: {url}")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_UPLOAD", f"ERROR: Upload failed [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)

    image_id = resp.json().get("id")
    log("PRINTIFY_UPLOAD", f"Upload success. Printify image_id={image_id}")
    return image_id


def fetch_valid_variants(api_key: str, blueprint_id: int, print_provider_id: int, requested_ids: list) -> tuple:
    url = f"{PRINTIFY_BASE_URL}/catalog/blueprints/{blueprint_id}/print_providers/{print_provider_id}/variants.json"
    log("PRINTIFY_VARIANTS", f"Fetching valid variants from catalog: {url}")
    try:
        resp = requests.get(url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        variants_list = data.get("variants", [])
        
        if not variants_list:
            log("PRINTIFY_VARIANTS", "ERROR: No variants found in catalog response.")
            sys.exit(1)

        available_ids = [v.get("id") for v in variants_list if v.get("id")]
        
        if requested_ids:
            valid_requested = [vid for vid in requested_ids if vid in available_ids]
            if valid_requested:
                costs = [v.get("cost", 1000) for v in variants_list if v.get("id") in valid_requested]
                avg_cost = int(sum(costs) / len(costs)) if costs else 1000
                return valid_requested, avg_cost

        first_variant = variants_list[0]
        chosen_id = first_variant.get("id")
        chosen_cost = first_variant.get("cost", 1000)
        log("PRINTIFY_VARIANTS", f"Auto-selected valid variant ID: {chosen_id} with cost {chosen_cost} cents.")
        return [chosen_id], chosen_cost

    except Exception as exc:
        log("PRINTIFY_VARIANTS", f"ERROR: Failed to fetch blueprint variants: {exc}")
        sys.exit(1)


def create_product(api_key: str, shop_id: str, image_id: str, keyword: str,
                    blueprint_id: int, print_provider_id: int, user_variant_ids: list) -> str:
    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products.json"

    variant_ids, base_cost_cents = fetch_valid_variants(api_key, blueprint_id, print_provider_id, user_variant_ids)
    retail_price_cents = int(round(base_cost_cents * (1 + INTRO_MARGIN_PERCENT / 100)))

    tags = [keyword.lower()] + EVERGREEN_TAGS
    title = f"{keyword.title()} - Minimalist Vector Sticker [DRY-RUN]"
    description = f"Backtest item for keyword: {keyword}."

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
                "images": [{"id": image_id, "x": 0.5, "y": 0.5, "scale": 1, "angle": 0}]
            }]
        }],
    }

    log("PRINTIFY_PRODUCT", f"Creating product listing at: {url}")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PRODUCT", f"ERROR: Product creation failed [{resp.status_code}]: {resp.text[:800]}")
        sys.exit(1)

    product_id = resp.json().get("id")
    log("PRINTIFY_PRODUCT", f"Product successfully generated. product_id={product_id}")
    return product_id


def publish_product(api_key: str, shop_id: str, product_id: str) -> None:
    if DRY_RUN:
        log("PRINTIFY_PUBLISH", "DRY_RUN is enabled. Skipping public marketplace publish step safely.")
        return

    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products/{product_id}/publish.json"
    payload = {"title": True, "description": True, "images": True, "variants": True, "tags": True}

    log("PRINTIFY_PUBLISH", f"Publishing product {product_id} at: {url}")
    resp = requests.post(url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT)
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PUBLISH", f"ERROR: Publish failed [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)
    log("PRINTIFY_PUBLISH", f"Product {product_id} published successfully.")


# -----------------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------------

def main() -> None:
    log("PIPELINE", f"=== Starting POD backtest run (DRY_RUN={DRY_RUN}) ===")

    printify_api_key = get_required_env("PRINTIFY_API_KEY")
    shop_id = get_required_env("STORE_ID")

    keyword = fetch_trending_keyword()
    prompt = build_prompt(keyword)
    image_bytes = generate_image(prompt)
    file_name = f"{keyword.lower().replace(' ', '_')}_{int(time.time())}.png"

    image_id = upload_image_to_printify(printify_api_key, image_bytes, file_name)
    product_id = create_product(
        printify_api_key, shop_id, image_id, keyword,
        DEFAULT_BLUEPRINT_ID, DEFAULT_PRINT_PROVIDER_ID, DEFAULT_VARIANT_IDS
    )
    publish_product(printify_api_key, shop_id, product_id)

    log("PIPELINE", f"=== Backtest complete successfully. Keyword='{keyword}', product_id={product_id} ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as unexpected_error:
        log("PIPELINE", f"FATAL UNHANDLED ERROR: {unexpected_error}")
        sys.exit(1)
