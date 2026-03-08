import importlib
import traceback

from . import CONFIG

APIS = CONFIG["apis"]
SERVICES = []

for service in CONFIG["services"]:
    try:
        service_module = importlib.import_module(
            f"butlarr.services.{service['type'].lower()}"
        )
        ServiceConstructor = getattr(service_module, service["type"])
    except Exception as e:
        traceback.print_exc()
        raise RuntimeError(
            f"Could not load service of type '{service.get('type')}': {e}\n"
            f"Make sure the type matches an existing module in butlarr/services/ "
            f"(e.g. 'Radarr', 'Sonarr')."
        ) from e

    api_config = APIS[service["api"]]
    args = {
        "commands": service["commands"],
        "api_host": api_config["api_host"],
        "api_key": api_config["api_key"],
    }

    SERVICES.append(ServiceConstructor(**args))
