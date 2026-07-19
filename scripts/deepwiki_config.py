#!/usr/bin/env python3
"""Build an Ollama-first runtime config from the current upstream config."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def configure_generator(path: Path, model: str) -> None:
    config = load_json(path)
    providers = config.setdefault("providers", {})
    ollama = providers.setdefault("ollama", {})
    models = ollama.setdefault("models", {})

    config["default_provider"] = "ollama"
    ollama["default_model"] = model
    ollama["supportsCustomModel"] = True
    models.setdefault(
        model,
        {
            "options": {
                "temperature": 0.7,
                "top_p": 0.8,
                "num_ctx": 32000,
            }
        },
    )
    write_json(path, config)


def configure_embedder(path: Path, model: str) -> None:
    config = load_json(path)
    ollama = config.setdefault("embedder_ollama", {})
    ollama["client_class"] = "OllamaClient"
    ollama.setdefault("model_kwargs", {})["model"] = model
    write_json(path, config)


def render(source: Path, output: Path, model: str, embed_model: str) -> None:
    if not source.is_dir():
        raise SystemExit(f"Config source does not exist: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="config-", dir=output.parent))
    try:
        for item in source.iterdir():
            if item.is_file():
                shutil.copy2(item, temporary / item.name)

        configure_generator(temporary / "generator.json", model)
        configure_embedder(temporary / "embedder.json", embed_model)

        previous = output.with_name(f"{output.name}.previous")
        if previous.exists():
            shutil.rmtree(previous)
        if output.exists():
            os.replace(output, previous)
        os.replace(temporary, output)
        if previous.exists():
            shutil.rmtree(previous)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--embed-model", required=True)
    args = parser.parse_args()
    render(args.source, args.output, args.model, args.embed_model)


if __name__ == "__main__":
    main()
