from ledgerquant.models.budget import reservation
from tests.unit.test_openai_provider import profile


def test_cache_write_rate_and_utf8_bytes_are_reserved_conservatively():
    request = {"input": "æøå" * 100}
    ordinary = profile(input_usd_per_million=10, output_usd_per_million=50)
    caching = ordinary.model_copy(update={"cache_write_usd_per_million": 12.5})
    tokens, ordinary_money = reservation(ordinary, request)
    same_tokens, cache_money = reservation(caching, request)
    assert same_tokens == tokens
    assert tokens > 4096 + 512 + 600
    assert cache_money > ordinary_money
