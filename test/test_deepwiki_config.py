import json
from pathlib import Path

from scripts.deepwiki_config import render


def read_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def test_render_preserves_upstream_and_selects_ollama(tmp_path):
    source = Path(__file__).parents[1] / "api" / "config"
    output = tmp_path / "config"

    render(source, output, "custom-model:latest", "custom-embed:latest")

    generator = read_json(output / "generator.json")
    ollama = generator["providers"]["ollama"]
    embedder = read_json(output / "embedder.json")

    assert generator["default_provider"] == "ollama"
    assert ollama["default_model"] == "custom-model:latest"
    assert "custom-model:latest" in ollama["models"]
    assert "google" in generator["providers"]
    assert (
        embedder["embedder_ollama"]["model_kwargs"]["model"]
        == "custom-embed:latest"
    )


def test_render_can_be_repeated_with_a_different_model(tmp_path):
    source = Path(__file__).parents[1] / "api" / "config"
    output = tmp_path / "config"

    render(source, output, "first-model", "nomic-embed-text")
    render(source, output, "second-model", "nomic-embed-text")

    generator = read_json(output / "generator.json")
    assert generator["providers"]["ollama"]["default_model"] == "second-model"
    assert not output.with_name("config.previous").exists()
