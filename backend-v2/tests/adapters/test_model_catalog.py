import httpx
import pytest

from zhishi.adapters.model_catalog import (
    CatalogError,
    ModelCatalogRequest,
    catalog_url,
    discover_models,
)


def body(**kwargs):
    return ModelCatalogRequest(base_url='https://models.example/v1', api_key='test-private-token', **kwargs)


@pytest.mark.parametrize(('provider','url','expected'), [
    ('openai_compat','https://example.test/','https://example.test/v1/models'),
    ('openai_responses','https://example.test/api/v1/','https://example.test/api/v1/models'),
    ('anthropic','https://example.test/','https://example.test/v1/models'),
    ('anthropic','https://example.test/proxy','https://example.test/proxy/v1/models'),
    ('anthropic','https://example.test/v1','https://example.test/v1/models'),
    ('openai_compat','http://127.0.0.1:1234/v1','http://127.0.0.1:1234/v1/models'),
])
def test_endpoint_resolution(provider,url,expected):
    assert catalog_url(url,provider) == expected


@pytest.mark.parametrize('url', ['file:///tmp/x','https://user:password@example.test/v1',
    'https://example.test/v1?key=secret','https://example.test/v1#fragment',
    'https://example.test/v1/responses','https://example.test/v1/chat/completions',
    'https://example.test:99999/v1','https://example.test:0/v1','https://example.test\\evil/v1'])
def test_bad_base_url_rejected(url):
    with pytest.raises(CatalogError):
        catalog_url(url,'openai_compat')


@pytest.mark.parametrize('provider',['openai_compat','openai_responses','anthropic'])
def test_catalog_dedup_sort_and_headers(provider):
    def serve(request):
        assert request.method == 'GET' and str(request.url) == 'https://models.example/v1/models'
        if provider == 'anthropic':
            assert request.headers['x-api-key'] == 'test-private-token'
            assert request.headers['anthropic-version'] == '2023-06-01'
            assert 'Authorization' not in request.headers
        else:
            assert request.headers['Authorization'] == 'Bearer test-private-token'
        return httpx.Response(200,json={'data':[{'id':'z-model'},None,{'id':''},{'id':'a-model','display_name':'A'},{'id':'z-model'}]})
    result = discover_models(body(provider_kind=provider),transport=httpx.MockTransport(serve))
    assert [m.id for m in result.models] == ['a-model','z-model']
    assert result.models[0].name == 'A' and not result.truncated
    assert 'test-private-token' not in repr(body())


def test_pagination_uses_same_endpoint_and_bounds_pages():
    calls=[]
    def serve(request):
        calls.append(request)
        assert request.url.host == 'models.example'
        return httpx.Response(200,json={'data':[{'id':f'model-{len(calls)}'}], 'has_more':True,
                                       'last_id':f'cursor-{len(calls)}', 'next':'https://other.example/steal'})
    result=discover_models(body(provider_kind='anthropic'),transport=httpx.MockTransport(serve))
    assert len(calls)==3 and result.truncated
    assert calls[1].url.params['after_id'] == 'cursor-1'


@pytest.mark.parametrize('status',[302,401,403,404,405,429,500])
def test_upstream_errors_do_not_echo_keys_or_follow_redirects(status):
    calls=[]
    def serve(request):
        calls.append(request)
        return httpx.Response(status,text='echo test-private-token',headers={'Location':'https://other.example'})
    with pytest.raises(CatalogError) as error:
        discover_models(body(),transport=httpx.MockTransport(serve))
    assert 'test-private-token' not in str(error.value) and len(calls)==1


@pytest.mark.parametrize('payload',[b'<html>sign in</html>',b'{"models":[]}',b'[]',b'X'*(1024*1024+1)],ids=['html','wrong-shape','array','over-limit'])
def test_malformed_and_oversized_payload(payload):
    with pytest.raises(CatalogError):
        discover_models(body(),transport=httpx.MockTransport(lambda _: httpx.Response(200,content=payload)))


def test_timeouts_have_safe_message():
    def serve(request):
        raise httpx.ReadTimeout('echo test-private-token',request=request)
    with pytest.raises(CatalogError) as error:
        discover_models(body(),transport=httpx.MockTransport(serve))
    assert error.value.status == 504 and 'test-private-token' not in str(error.value)


def test_empty_catalog_and_unauthenticated_local_endpoint():
    def serve(request):
        assert 'Authorization' not in request.headers
        return httpx.Response(200,json={'data':[]})
    result=discover_models(ModelCatalogRequest(base_url='http://127.0.0.1:1234/v1'),transport=httpx.MockTransport(serve))
    assert result.models == [] and not result.truncated
