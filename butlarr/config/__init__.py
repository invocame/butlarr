import yaml
import os
from loguru import logger


def load_config_from_file():
    config_file = os.getenv("BUTLARR_CONFIG_FILE") or "config.yaml"
    logger.info(f'Loading config from file "{config_file}"')
    with open(config_file, "r") as f:
        return yaml.safe_load(f)


def _get_env_vars_with_prefix(prefix):
    return {k: v for k, v in os.environ.items() if k.startswith(prefix)}


def _inject_api_conf(config):
    def update_config(key, value, field, prefix, suffix):
        name = key.removeprefix(prefix).removesuffix(suffix).lower()
        if name not in config["apis"]:
            config["apis"][name] = {}
        config["apis"][name][field] = value

    options = [("api_host", "_HOST"), ("api_key", "_API_KEY")]
    for key, val in _get_env_vars_with_prefix("BUTLARR_APIS_").items():
        for field, suffix in options:
            if key.endswith(suffix):
                update_config(key, val, field, "BUTLARR_APIS_", suffix)


def _inject_service_conf(config):
    service_envs = _get_env_vars_with_prefix("BUTLARR_SERVICES_").items()
    indexes = {}
    index_carry = 0

    def check_indexes(name):
        if name not in indexes:
            nonlocal index_carry
            indexes[name] = index_carry
            index_carry += 1

    def update_config_simple(key, value, field, prefix, suffix):
        name = key.removeprefix(prefix).removesuffix(suffix).lower()
        check_indexes(name)
        while indexes[name] >= len(config["services"]):
            config["services"].append({})
        config["services"][indexes[name]][field] = value

    options = [("api", "_API"), ("type", "_TYPE"), ("name", "_NAME")]
    for key, val in service_envs:
        for field, suffix in options:
            if key.endswith(suffix):
                v = val.lower() if suffix == "_API" else val
                update_config_simple(key, v, field, "BUTLARR_SERVICES_", suffix)

    def update_config_list(key, value, field, prefix, suffix):
        (name, idx) = key.removeprefix(prefix).replace(suffix, "_").rsplit("_", 1)
        idx = int(idx)
        name = name.lower()
        check_indexes(name)
        if indexes[name] >= len(config["services"]):
            config["services"].append({})
        if field not in config["services"][indexes[name]]:
            config["services"][indexes[name]][field] = []
        conf = config["services"][indexes[name]][field]
        while len(conf) <= idx:
            conf.append([])
        conf[int(idx)] = value

    list_options = [("commands", "_COMMAND_")]
    for key, value in service_envs:
        for field, suffix in list_options:
            if suffix in key:
                update_config_list(key, value, field, "BUTLARR_SERVICES_", suffix)


def _inject_whitelist(config):
    """
    Read BUTLARR_WHITELIST_0, BUTLARR_WHITELIST_1, … and add them to the
    whitelist list as integers.
    """
    entries = _get_env_vars_with_prefix("BUTLARR_WHITELIST_")
    for val in entries.values():
        try:
            config["whitelist"].append(int(val))
        except ValueError:
            logger.warning(f"Whitelist entry '{val}' is not a valid integer ID — skipped.")


def load_config_from_env():
    logger.info("Loading config from environment variables")
    config = {
        "telegram": {
            "token": os.getenv("TELEGRAM_BOT_TOKEN"),
        },
        "whitelist": [],
        "apis": {},
        "services": [],
    }

    _inject_api_conf(config)
    _inject_service_conf(config)
    _inject_whitelist(config)

    # Clean up commands — remove empty elements
    for s in config["services"]:
        s["commands"] = list(filter(bool, s.get("commands", [])))

    return config


def load_config():
    use_env_config = os.getenv("BUTLARR_USE_ENV_CONFIG", "False").lower() in (
        "true", "1", "t",
    )
    if use_env_config:
        if config := load_config_from_env():
            logger.debug(config)
            return config

    return load_config_from_file()


CONFIG = load_config()
