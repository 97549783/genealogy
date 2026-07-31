"""Проверки подготовки запросов без загрузки настоящей модели."""

import numpy as np

from core.semantic import query_encoder


def test_e5_queries_are_cleaned_and_limited() -> None:
    values = query_encoder.prepare_queries([" а ", "", "б", "в", "г", "д", "е"], "multilingual-e5")
    assert values == ["query: а", "query: б", "query: в", "query: г", "query: д"]


def test_encoding_uses_lazy_fake_encoder(monkeypatch) -> None:
    class FakeEncoder:
        def encode(self, values, normalize_embeddings):
            assert values == ["query: запрос"]
            assert normalize_embeddings is True
            return [[3.0, 4.0]]

    monkeypatch.setattr(query_encoder, "load_query_encoder", lambda model_name, device: FakeEncoder())
    result = query_encoder.encode_queries(["запрос"], "e5", True, "cpu")
    assert result.dtype == np.float32
    assert np.array_equal(result, [[3.0, 4.0]])


def test_combined_query_is_normalized() -> None:
    result = query_encoder.combine_query_vectors(np.array([[2, 0], [0, 2]], dtype=np.float32))
    assert np.allclose(result, [2 ** -0.5, 2 ** -0.5])
