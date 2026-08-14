#!/usr/bin/env python3

from pathlib import Path

import yaml

CONFIG_FILE = Path("config/assessors.yaml")
ENV_FILE = Path(".env")
ENV_TEMPLATE = Path("env.template")


def create_env_from_template():
    if not ENV_TEMPLATE.exists():
        raise FileNotFoundError(f"{ENV_TEMPLATE} does not exist")

    output = []

    print(f"{ENV_FILE} does not exist.")
    print("Review values from env.template (press Enter to accept the default):\n")

    for line in ENV_TEMPLATE.read_text().splitlines():
        stripped = line.strip()

        # Preserve comments and blank lines
        if not stripped or stripped.startswith("#") or "=" not in line:
            output.append(line)
            continue

        key, default = line.split("=", 1)

        value = input(f"{key} [{default}]: ").strip()

        output.append(f"{key}={value or default}")

    ENV_FILE.write_text("\n".join(output) + "\n")

    print(f"\nCreated {ENV_FILE}")


# Create .env interactively if it doesn't exist

if not ENV_FILE.exists():
    create_env_from_template()


# Load assessor configuration

with CONFIG_FILE.open() as f:
    config = yaml.safe_load(f)

assessors = config["assessors"]

versions = {
    "FUJI_VERSION": str(assessors["fuji"]["version"]),
    "FAIR_CORE_TESTS_VERSION": str(assessors["fair_champion"]["version"]),
    "FAIR_CHAMPION_VERSION": str(assessors["fair_champion"]["service_version"]),
}


# Update existing .env

lines = ENV_FILE.read_text().splitlines()

updated = set()
output = []

for line in lines:
    key = line.split("=", 1)[0].strip()

    if key in versions:
        output.append(f"{key}={versions[key]}")
        updated.add(key)
    else:
        output.append(line)


# Append versions missing from .env

for key, value in versions.items():
    if key not in updated:
        output.append(f"{key}={value}")

ENV_FILE.write_text("\n".join(output) + "\n")

print(f"Updated assessor versions in {ENV_FILE}")
