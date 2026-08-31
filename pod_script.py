#!/usr/bin/env python3
"""
pod_script.py
=================================================================
Autonomous, zero-cost Print-on-Demand (POD) arbitrage pipeline.

Pipeline stages:
    1. Zero-token trend ingestion (Google Trends RSS -> Reddit JSON fallback)
    2. Deterministic prompt construction (hardcoded template, no LLM tokens)
    3. Image generation via a configurable image-gen API
    4. Printify API v1 integration: upload image -> create product -> publish
    5. Verbose, timestamped logging at every step

Run manually:
    python pod_script.py

Run in CI:
    Triggered daily by .github/workflows/run.yml

Required environment variables (see README.md for how to set these
as GitHub Secrets):
    PRINTIFY_API_KEY   - Printify personal access token
    STORE_ID           - Printify shop/store ID (numeric string)
    IMAGE_GEN_API_KEY  - API key for the image generation provider

Optional environment variables:
    PRINTIFY_BLUEPRINT_ID       - Printify blueprint (product) ID. Default: 384 (t-shirt)
    PRINTIFY_PRINT_PROVIDER_ID  - Printify print provider ID. Default: 1
    PRINTIFY_VARIANT_IDS        - Comma separated variant IDs. Default: "17887"
    INTRO_MARGIN_PERCENT        - Intro markup over cost, as a percent. Default: 15
=================================================================
"""

import base64
import datetime
import json
import os
import random
import sys
import time

import feedparser
import requests

# -----------------------------------------------------------------
# CONFIG / CONSTANTS
# -----------------------------------------------------------------

# Free, no-auth Google Trends "daily trends" RSS feed (US market).
GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss?geo=US"

# Public, no-auth Reddit JSON endpoint used as a fallback trend source.
REDDIT_FALLBACK_URL = "https://www.reddit.com/r/popular/top.json?limit=10&t=day"

# Printify API base
PRINTIFY_BASE_URL = "https://api.printify.com/v1"

# Deterministic prompt template. {keyword} is injected at runtime.
# Kept intentionally simple/hardcoded so no LLM reasoning tokens are spent.
PROMPT_TEMPLATE = (
    "minimalist vector sticker design of {keyword}, "
    "bold flat colors, thick black outline, die-cut sticker style, "
    "centered composition, white background, no text, no watermark, "
    "high contrast, clean simple shapes, trending on artstation"
)

# Evergreen tags appended to every product regardless of trend, to catch
# broad, always-on search traffic in addition to the trend-specific tag.
EVERGREEN_TAGS = [
    "sticker",
    "gift idea",
    "trendy design",
    "funny gift",
    "aesthetic",
    "cute sticker",
]

# Printify catalog defaults. Override via env vars if your store uses a
# different blueprint/provider/variant. These defaults target a standard
# die-cut sticker blueprint; adjust to match your actual Printify catalog.
DEFAULT_BLUEPRINT_ID = int(os.environ.get("PRINTIFY_BLUEPRINT_ID", "384"))
DEFAULT_PRINT_PROVIDER_ID = int(os.environ.get("PRINTIFY_PRINT_PROVIDER_ID", "1"))
DEFAULT_VARIANT_IDS = [
    int(v) for v in os.environ.get("PRINTIFY_VARIANT_IDS", "17887").split(",")
]

# Low introductory margin (%) applied over provider cost for early
# conversion testing. E.g. 15 means retail = cost * 1.15
INTRO_MARGIN_PERCENT = float(os.environ.get("INTRO_MARGIN_PERCENT", "15"))

REQUEST_TIMEOUT = 30  # seconds, applied to all outbound HTTP calls


# -----------------------------------------------------------------
# LOGGING HELPER
# -----------------------------------------------------------------

def log(step: str, message: str) -> None:
    """Timestamped, structured print() logging for GitHub Actions console."""
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] [{step}] {message}")


# -----------------------------------------------------------------
# ENVIRONMENT / SECRETS
# -----------------------------------------------------------------

def get_required_env(var_name: str) -> str:
    """
    Safely read a required secret from the environment.
    Never hardcode credentials in source -- always pulled at runtime.
    """
    value = os.environ.get(var_name)
    if not value:
        log("ENV", f"ERROR: Missing required environment variable '{var_name}'.")
        log("ENV", "Set it as a GitHub Secret and map it in run.yml, or export it locally.")
        sys.exit(1)
    return value


# -----------------------------------------------------------------
# STAGE 1: ZERO-TOKEN TREND INGESTION
# -----------------------------------------------------------------

def fetch_trending_keyword() -> str:
    """
    Pull a live trending keyword using only free, non-LLM sources.
    Primary source: Google Trends RSS feed (via feedparser).
    Fallback source: Reddit public JSON endpoint (via requests).
    """
    log("TREND", f"Fetching Google Trends RSS: {GOOGLE_TRENDS_RSS_URL}")
    try:
        feed = feedparser.parse(GOOGLE_TRENDS_RSS_URL)
        if feed.entries:
            candidates = [entry.title.strip() for entry in feed.entries if entry.get("title")]
            if candidates:
                # Pick from the top few entries to keep some variety day to day
                # while still favoring the strongest trends.
                keyword = random.choice(candidates[: min(5, len(candidates))])
                log("TREND", f"Google Trends returned {len(candidates)} entries.")
                log("TREND", f"Selected trending keyword: '{keyword}'")
                return keyword
        log("TREND", "Google Trends RSS returned no usable entries. Falling back to Reddit.")
    except Exception as exc:
        log("TREND", f"Google Trends RSS fetch failed: {exc}. Falling back to Reddit.")

    # --- Fallback: Reddit public JSON endpoint ---
    try:
        headers = {"User-Agent": "pod-arbitrage-bot/1.0"}
        log("TREND", f"Fetching Reddit fallback: {REDDIT_FALLBACK_URL}")
        resp = requests.get(REDDIT_FALLBACK_URL, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        posts = data.get("data", {}).get("children", [])
        titles = [p["data"]["title"].strip() for p in posts if p.get("data", {}).get("title")]
        if not titles:
            raise ValueError("No titles found in Reddit response.")
        keyword = random.choice(titles[: min(5, len(titles))])
        # Reddit titles can be long sentences; trim to a short phrase suitable
        # for an image prompt / product tag.
        keyword = " ".join(keyword.split()[:6])
        log("TREND", f"Reddit fallback selected keyword: '{keyword}'")
        return keyword
    except Exception as exc:
        log("TREND", f"ERROR: Reddit fallback also failed: {exc}")
        log("TREND", "No trend source available. Aborting run.")
        sys.exit(1)


# -----------------------------------------------------------------
# STAGE 2: DETERMINISTIC PROMPT MAPPING
# -----------------------------------------------------------------

def build_prompt(keyword: str) -> str:
    """Inject the trend keyword into the hardcoded prompt template."""
    prompt = PROMPT_TEMPLATE.format(keyword=keyword)
    log("PROMPT", f"Constructed image prompt: {prompt}")
    return prompt


# -----------------------------------------------------------------
# STAGE 3: IMAGE GENERATION
# -----------------------------------------------------------------

def generate_image(prompt: str, image_gen_api_key: str) -> bytes:
    """
    Generate an image from the prompt using a text-to-image API.

    This implementation targets the Stability AI "stable-image/generate/core"
    REST endpoint since it accepts a simple API-key bearer token and returns
    raw image bytes in one call. Swap the URL/payload/headers here if you use
    a different provider (e.g. OpenAI Images, Ideogram, Replicate) -- the
    rest of the pipeline only depends on this function returning PNG bytes.
    """
    url = "https://api.stability.ai/v2beta/stable-image/generate/core"
    headers = {
        "Authorization": f"Bearer {image_gen_api_key}",
        "Accept": "image/*",
    }
    files = {"none": ""}  # Stability's multipart API requires a files payload
    data = {
        "prompt": prompt,
        "output_format": "png",
        "aspect_ratio": "1:1",
    }

    log("IMAGE_GEN", f"Requesting image generation from: {url}")
    log("IMAGE_GEN", f"Payload: {json.dumps(data)}")

    try:
        resp = requests.post(
            url, headers=headers, files=files, data=data, timeout=60
        )
        resp.raise_for_status()
        image_bytes = resp.content
        log("IMAGE_GEN", f"Image generated successfully ({len(image_bytes)} bytes).")
        return image_bytes
    except requests.exceptions.HTTPError as exc:
        log("IMAGE_GEN", f"ERROR: Image generation HTTP error: {exc}")
        log("IMAGE_GEN", f"Response body: {resp.text[:500]}")
        sys.exit(1)
    except Exception as exc:
        log("IMAGE_GEN", f"ERROR: Image generation failed: {exc}")
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
    """
    Upload image bytes to Printify's media library.
    Printify's upload endpoint accepts base64-encoded file contents.
    Returns the Printify image ID to be referenced in the product payload.
    """
    url = f"{PRINTIFY_BASE_URL}/uploads/images.json"
    b64_contents = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "file_name": file_name,
        "contents": b64_contents,
    }

    log("PRINTIFY_UPLOAD", f"Uploading image to Printify: {url}")
    log("PRINTIFY_UPLOAD", f"file_name={file_name}, size={len(image_bytes)} bytes")

    resp = requests.post(
        url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT
    )
    if resp.status_code not in (200, 201):
        log("PRINTIFY_UPLOAD", f"ERROR: Upload failed [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)

    image_id = resp.json().get("id")
    log("PRINTIFY_UPLOAD", f"Upload success. Printify image_id={image_id}")
    return image_id


def fetch_variant_cost(api_key: str, shop_id: str, blueprint_id: int,
                        print_provider_id: int, variant_ids: list) -> int:
    """
    Fetch base cost (in cents) for the chosen variants from Printify's
    catalog, so the intro margin can be applied on top of real cost
    rather than a guessed number.
    """
    url = (
        f"{PRINTIFY_BASE_URL}/catalog/blueprints/{blueprint_id}"
        f"/print_providers/{print_provider_id}/variants.json"
    )
    log("PRINTIFY_COST", f"Fetching variant cost data: {url}")
    try:
        resp = requests.get(url, headers=printify_headers(api_key), timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        variants = resp.json().get("variants", [])
        costs = [v.get("cost", 0) for v in variants if v.get("id") in variant_ids]
        if not costs:
            log("PRINTIFY_COST", "WARNING: No matching variant cost found, defaulting to 1000 (=$10.00).")
            return 1000
        avg_cost = int(sum(costs) / len(costs))
        log("PRINTIFY_COST", f"Base cost for selected variants: {avg_cost} cents.")
        return avg_cost
    except Exception as exc:
        log("PRINTIFY_COST", f"WARNING: Could not fetch cost ({exc}). Defaulting to 1000 (=$10.00).")
        return 1000


def create_product(api_key: str, shop_id: str, image_id: str, keyword: str,
                    blueprint_id: int, print_provider_id: int, variant_ids: list) -> str:
    """
    Create a Printify product listing using the uploaded image, tagged
    with the trend keyword plus evergreen search terms, priced with a
    low introductory margin over real provider cost.
    """
    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products.json"

    base_cost_cents = fetch_variant_cost(
        api_key, shop_id, blueprint_id, print_provider_id, variant_ids
    )
    retail_price_cents = int(round(base_cost_cents * (1 + INTRO_MARGIN_PERCENT / 100)))

    tags = [keyword.lower()] + EVERGREEN_TAGS
    title = f"{keyword.title()} - Minimalist Vector Sticker"
    description = (
        f"A minimalist vector-style sticker inspired by '{keyword}'. "
        f"Bold flat colors, clean die-cut design. Perfect gift or laptop/water "
        f"bottle decoration. Auto-generated and listed as part of a daily "
        f"trend-testing pipeline; introductory pricing while we gather demand data."
    )

    payload = {
        "title": title,
        "description": description,
        "blueprint_id": blueprint_id,
        "print_provider_id": print_provider_id,
        "tags": tags,
        "variants": [
            {
                "id": vid,
                "price": retail_price_cents,
                "is_enabled": True,
            }
            for vid in variant_ids
        ],
        "print_areas": [
            {
                "variant_ids": variant_ids,
                "placeholders": [
                    {
                        "position": "front",
                        "images": [
                            {
                                "id": image_id,
                                "x": 0.5,
                                "y": 0.5,
                                "scale": 1,
                                "angle": 0,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    log("PRINTIFY_PRODUCT", f"Creating product listing at: {url}")
    log("PRINTIFY_PRODUCT", f"Title: {title}")
    log("PRINTIFY_PRODUCT", f"Tags: {tags}")
    log("PRINTIFY_PRODUCT", f"Base cost: {base_cost_cents}c -> Retail price: {retail_price_cents}c "
                             f"(margin={INTRO_MARGIN_PERCENT}%)")
    log("PRINTIFY_PRODUCT", f"Payload: {json.dumps(payload)}")

    resp = requests.post(
        url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT
    )
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PRODUCT", f"ERROR: Product creation failed [{resp.status_code}]: {resp.text[:800]}")
        sys.exit(1)

    product_id = resp.json().get("id")
    log("PRINTIFY_PRODUCT", f"Product created successfully. product_id={product_id}")
    return product_id


def publish_product(api_key: str, shop_id: str, product_id: str) -> None:
    """
    Publish the product so it becomes visible/orderable in the connected
    sales channel (e.g. Etsy, Shopify, or Printify's own storefront).
    """
    url = f"{PRINTIFY_BASE_URL}/shops/{shop_id}/products/{product_id}/publish.json"
    payload = {
        "title": True,
        "description": True,
        "images": True,
        "variants": True,
        "tags": True,
        "keyFeatures": True,
        "shipping_template": True,
    }

    log("PRINTIFY_PUBLISH", f"Publishing product {product_id} at: {url}")

    resp = requests.post(
        url, headers=printify_headers(api_key), json=payload, timeout=REQUEST_TIMEOUT
    )
    if resp.status_code not in (200, 201):
        log("PRINTIFY_PUBLISH", f"ERROR: Publish failed [{resp.status_code}]: {resp.text[:500]}")
        sys.exit(1)

    log("PRINTIFY_PUBLISH", f"Product {product_id} published successfully.")


# -----------------------------------------------------------------
# MAIN PIPELINE
# -----------------------------------------------------------------

def main() -> None:
    log("PIPELINE", "=== Starting daily POD arbitrage run ===")

    # --- Load credentials safely from environment ---
    printify_api_key = get_required_env("PRINTIFY_API_KEY")
    shop_id = get_required_env("STORE_ID")
    image_gen_api_key = get_required_env("IMAGE_GEN_API_KEY")

    # --- Stage 1: Trend ingestion ---
    keyword = fetch_trending_keyword()

    # --- Stage 2: Prompt construction ---
    prompt = build_prompt(keyword)

    # --- Stage 3: Image generation ---
    image_bytes = generate_image(prompt, image_gen_api_key)
    file_name = f"{keyword.lower().replace(' ', '_')}_{int(time.time())}.png"

    # --- Stage 4: Printify integration ---
    image_id = upload_image_to_printify(printify_api_key, image_bytes, file_name)
    product_id = create_product(
        printify_api_key,
        shop_id,
        image_id,
        keyword,
        DEFAULT_BLUEPRINT_ID,
        DEFAULT_PRINT_PROVIDER_ID,
        DEFAULT_VARIANT_IDS,
    )
    publish_product(printify_api_key, shop_id, product_id)

    log("PIPELINE", f"=== Run complete. Keyword='{keyword}', product_id={product_id} ===")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as unexpected_error:
        log("PIPELINE", f"FATAL UNHANDLED ERROR: {unexpected_error}")
        sys.exit(1)
