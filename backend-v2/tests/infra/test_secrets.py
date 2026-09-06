from zhishi.infra.secrets import store_api_key, load_api_key, delete_api_key

def test_roundtrip():
    store_api_key("unit-test-provider", "sk-abc")
    assert load_api_key("unit-test-provider") == "sk-abc"
    delete_api_key("unit-test-provider")
    assert load_api_key("unit-test-provider") is None
