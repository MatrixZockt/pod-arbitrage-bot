# Printify catalog defaults with safe fallback for empty env vars
def _get_env_int(var_name: str, default: int) -> int:
    val = os.environ.get(var_name)
    return int(val) if val and val.strip() else default

DEFAULT_BLUEPRINT_ID = _get_env_int("PRINTIFY_BLUEPRINT_ID", 384)
DEFAULT_PRINT_PROVIDER_ID = _get_env_int("PRINTIFY_PRINT_PROVIDER_ID", 1)

variant_env = os.environ.get("PRINTIFY_VARIANT_IDS")
DEFAULT_VARIANT_IDS = [int(v) for v in variant_env.split(",")] if variant_env and variant_env.strip() else [17887]

margin_env = os.environ.get("INTRO_MARGIN_PERCENT")
INTRO_MARGIN_PERCENT = float(margin_env) if margin_env and margin_env.strip() else 15.0
