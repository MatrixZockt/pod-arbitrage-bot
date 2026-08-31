# Daily POD Arbitrage Pipeline — Setup Guide

This repo runs a fully automated, zero-LLM-token pipeline once a day:
trending keyword → image prompt → generated image → Printify product →
published listing. It's designed to run for free on GitHub Actions.

## What you need before you start

- A **Printify** account with a store already connected to a sales
  channel (Etsy, Shopify, or Printify's own storefront).
- An account with an **image generation API** provider (the script ships
  configured for Stability AI's `stable-image/generate/core` endpoint —
  swap this out in `generate_image()` if you prefer a different provider).
- A **GitHub** account.

---

## Step 1 — Create the GitHub repository

1. Go to [github.com/new](https://github.com/new).
2. Name the repository (e.g. `pod-arbitrage-bot`).
3. Set visibility to **Public** (required for unlimited free GitHub
   Actions minutes on the free tier).
4. Click **Create repository**, leaving it otherwise empty.

## Step 2 — Upload the pipeline files

Upload the following files, preserving the folder structure:

```
pod-arbitrage-bot/
├── pod_script.py
├── requirements.txt
└── .github/
    └── workflows/
        └── run.yml
```

Easiest method via the web UI:
1. Click **Add file → Upload files** on the repo home page.
2. Drag in `pod_script.py` and `requirements.txt`.
3. Commit directly to `main`.
4. Click **Add file → Create new file**, type
   `.github/workflows/run.yml` as the file name (GitHub auto-creates the
   folders), paste the workflow contents, and commit.

(Alternatively, clone the repo locally, copy the files in with `git add .`,
`git commit`, `git push`.)

## Step 3 — Get your credentials

**Printify API key**
1. Log in to Printify → click your profile icon → **My Account**.
2. Go to **Connections** → **Printify API** → **Generate token**.
3. Copy the token — this is `PRINTIFY_API_KEY`.

**Printify Store ID**
1. With the same token, call:
   `GET https://api.printify.com/v1/shops.json`
   (e.g. via a quick `curl -H "Authorization: Bearer <token>" https://api.printify.com/v1/shops.json`,
   or a tool like Postman).
2. Note the `id` field for your store — this is `STORE_ID`.

**Image generation API key**
1. Sign up with your chosen provider (Stability AI by default).
2. Generate an API key from their dashboard — this is `IMAGE_GEN_API_KEY`.

**Verify your Printify catalog IDs**
The script defaults to a sticker-style blueprint (`PRINTIFY_BLUEPRINT_ID=384`,
`PRINTIFY_PRINT_PROVIDER_ID=1`, `PRINTIFY_VARIANT_IDS=17887`). Confirm these
match a real blueprint/provider/variant combination available to your store
by calling `GET /v1/catalog/blueprints.json` and drilling into the
provider/variants endpoints. Override any mismatches using the optional
env vars described in the script header — set them as repo Secrets and
uncomment the matching lines in `run.yml`.

## Step 4 — Add GitHub Secrets

1. In your repo, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret** and add each of the following one at a
   time:
   - `PRINTIFY_API_KEY`
   - `STORE_ID`
   - `IMAGE_GEN_API_KEY`
3. (Optional) Add any of `PRINTIFY_BLUEPRINT_ID`, `PRINTIFY_PRINT_PROVIDER_ID`,
   `PRINTIFY_VARIANT_IDS`, `INTRO_MARGIN_PERCENT` if you need to override
   the script defaults.

Secrets are encrypted at rest and are never printed in logs or exposed to
forks of a public repo — this is why the script reads them only via
`os.environ.get()` at runtime rather than hardcoding anything.

## Step 5 — Verify the workflow file is recognized

1. Go to the **Actions** tab of your repository.
2. You should see a workflow named **Daily POD Arbitrage Run** listed on
   the left. If it's not there, double check the file is committed at
   exactly `.github/workflows/run.yml`.

## Step 6 — Run a manual test

1. Click into the **Daily POD Arbitrage Run** workflow.
2. Click the **Run workflow** dropdown (top right) → **Run workflow**
   button to trigger it manually via `workflow_dispatch`.
3. Refresh after a few seconds — a new run will appear.
4. Click into the run → click the `run-pipeline` job → expand the
   **Run POD arbitrage pipeline** step to watch the live logs.

## Step 7 — Read the logs to confirm success

You should see structured log lines for each stage, e.g.:

```
[2026-08-31 04:00:01 UTC] [TREND] Fetching Google Trends RSS: ...
[2026-08-31 04:00:02 UTC] [TREND] Selected trending keyword: 'example topic'
[2026-08-31 04:00:02 UTC] [PROMPT] Constructed image prompt: minimalist vector sticker design of example topic, ...
[2026-08-31 04:00:05 UTC] [IMAGE_GEN] Image generated successfully (482113 bytes).
[2026-08-31 04:00:06 UTC] [PRINTIFY_UPLOAD] Upload success. Printify image_id=...
[2026-08-31 04:00:07 UTC] [PRINTIFY_PRODUCT] Product created successfully. product_id=...
[2026-08-31 04:00:08 UTC] [PRINTIFY_PUBLISH] Product ... published successfully.
[2026-08-31 04:00:08 UTC] [PIPELINE] === Run complete. ===
```

If a step fails, the log will show the HTTP status code and response body
returned by the failing API, and the job will exit with a non-zero code
(visible as a red ✗ on the Actions tab) so failures are never silent.

## Step 8 — Let it run on schedule

Once the manual test succeeds, no further action is needed — GitHub
Actions will trigger the workflow automatically every day at **04:00 UTC**
per the `cron: "0 4 * * *"` schedule in `run.yml`.

---

## Operational notes and things to review before relying on this in production

- **Pricing model risk**: Printify's "cost" fields can change per print
  provider and don't always include shipping — check your actual margins
  in the Printify dashboard, don't rely solely on the script's calculated
  retail price.
- **API rate limits**: Both Printify and most image-gen providers rate-limit
  free/low tiers. A once-daily run is well within typical limits, but
  check your provider's docs if you increase frequency.
- **Trend keyword quality**: RSS/JSON trend feeds sometimes surface
  keywords unsuitable for merchandise (news events, sensitive topics).
  Consider adding a keyword denylist/filter before generating images if
  you plan to run this unattended for a long time.
- **Image generation cost**: unlike the trend-fetching stage, most
  image-generation APIs are paid per call (Stability AI, DALL·E, etc.),
  so "zero-cost" here refers to the trend-ingestion and orchestration
  layers, not the image-gen API usage itself. Check your provider's
  pricing.
- **This is automation tooling, not a guaranteed revenue system.** Whether
  any given listing sells depends on demand, competition, and platform
  policies — treat this as a testing/listing accelerator, not a
  guaranteed income source.
