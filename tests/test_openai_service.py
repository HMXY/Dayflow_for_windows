import pytest
from dayflow.analysis.openai_service import OpenAIService

def test_openai_service_base_url_validation():
    # Valid URLs
    svc1 = OpenAIService(api_key="test", base_url="http://localhost:8080")
    assert svc1.base_url == "http://localhost:8080"
    
    svc2 = OpenAIService(api_key="test", base_url="https://api.openai.com/v1")
    assert svc2.base_url == "https://api.openai.com/v1"
    
    # Invalid URLs should raise ValueError
    with pytest.raises(ValueError, match="valid HTTP or HTTPS URL"):
        OpenAIService(api_key="test", base_url="ftp://localhost")
        
    with pytest.raises(ValueError, match="valid domain or IP"):
        OpenAIService(api_key="test", base_url="http://")
        
    with pytest.raises(ValueError, match="valid HTTP or HTTPS URL"):
        OpenAIService(api_key="test", base_url="not_a_url")

def test_openai_service_empty_base_url():
    # Empty or None should result in None
    svc1 = OpenAIService(api_key="test", base_url=None)
    assert svc1.base_url is None
    
    svc2 = OpenAIService(api_key="test", base_url="   ")
    assert svc2.base_url is None
