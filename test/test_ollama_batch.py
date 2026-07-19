from adalflow.core.types import Document

from api.ollama_patch import OllamaDocumentProcessor


class FakeResponse:
    def __init__(self, embeddings):
        self._embeddings = embeddings

    def raise_for_status(self):
        return None

    def json(self):
        return {"embeddings": self._embeddings}


def test_ollama_embeddings_use_native_batches(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        embeddings = [
            [float(len(text)), float(index)]
            for index, text in enumerate(json["input"])
        ]
        return FakeResponse(embeddings)

    monkeypatch.setattr("api.ollama_patch.requests.post", fake_post)
    processor = OllamaDocumentProcessor(
        embedder=None,
        model_name="embed-model",
        batch_size=2,
        ollama_host="http://ollama.example:11434",
    )

    result = processor(
        [
            Document(text="one"),
            Document(text="two"),
            Document(text="three"),
        ]
    )

    assert len(result) == 3
    assert len(calls) == 2
    assert calls[0][0] == "http://ollama.example:11434/api/embed"
    assert calls[0][1] == {
        "model": "embed-model",
        "input": ["one", "two"],
    }
    assert calls[1][1]["input"] == ["three"]
    assert all(len(document.vector) == 2 for document in result)
