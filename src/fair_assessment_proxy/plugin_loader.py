import importlib
from pathlib import Path
from typing import Any

import yaml

from fair_assessment_proxy.plugins.base import AssessorPlugin


class PluginLoadError(Exception):
    pass


def load_yaml_config(path: str = "config/assessors.yaml") -> dict[str, Any]:
    config_path = Path(path)

    if not config_path.exists():
        raise PluginLoadError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    if not config or "assessors" not in config:
        raise PluginLoadError("Missing top-level 'assessors' key")

    return config["assessors"]


def import_class(dotted_path: str):
    module_name, class_name = dotted_path.rsplit(".", 1)

    module = importlib.import_module(module_name)

    return getattr(module, class_name)


def load_assessor_plugins(
    config_path: str = "config/assessors.yaml",
) -> dict[str, AssessorPlugin]:
    configs = load_yaml_config(config_path)
    plugins: dict[str, AssessorPlugin] = {}

    for assessor_id, assessor_config in configs.items():
        if not assessor_config.get("enabled", False):
            continue

        class_path = assessor_config.get("class")

        if not class_path:
            raise PluginLoadError(
                f"Assessor '{assessor_id}' is missing a 'class' value"
            )

        cls = import_class(class_path)
        instance = cls(assessor_id=assessor_id, config=assessor_config)

        if not isinstance(instance, AssessorPlugin):
            raise PluginLoadError(f"{class_path} does not implement AssessorPlugin")

        plugins[assessor_id] = instance

    return plugins
