import pytest
from unittest.mock import AsyncMock

@pytest.fixture
def mock_settings():
    class FakeSettings:
        gemini_api_key = None
        groq_api_key = "test-key"
        gemini_flash_model = None
        gemini_embedding_model = None
        ollama_url = "http://localhost:11434"
        ollama_model = "llama3:latest"
        ollama_embedding_model = "nomic-embed-text"
        rabbitmq_url = "amqp://guest:guest@localhost/"
        redis_url = "redis://localhost"
        database_url = "postgresql://test:test@localhost/test"
        serpapi_key = "test"
        gmail_client_id = "test"
        gmail_client_secret = "test"
        gmail_redirect_uri = "http://localhost:8000/auth/gmail/callback"
        secret_key = "test-secret"
        environment = "test"
        log_level = "WARNING"
        rate_limit_capacity = 10
        rate_limit_leak_rate = 1.0
        hallucination_threshold = 4
        resume_match_threshold = 0.65
    return FakeSettings()

@pytest.fixture
def mock_redis():
    store = {}
    expiries = {}

    class FakeRedis:
        async def get(self, key):
            return store.get(key)
        async def set(self, key, value, ex=None, nx=False):
            if nx and key in store:
                return None
            store[key] = value
            return True
        async def setex(self, key, ttl, value):
            store[key] = value
        async def delete(self, key):
            store.pop(key, None)
        async def ping(self):
            return True
        def pipeline(self):
            return FakePipeline(store)

    class FakePipeline:
        def __init__(self, store):
            self._store = store
            self._cmds = []
        def get(self, key):
            self._cmds.append(('get', key))
            return self
        def set(self, key, value, ex=None):
            self._cmds.append(('set', key, value))
            return self
        async def execute(self):
            results = []
            for cmd in self._cmds:
                if cmd[0] == 'get':
                    results.append(self._store.get(cmd[1]))
                elif cmd[0] == 'set':
                    self._store[cmd[1]] = cmd[2]
                    results.append(True)
            return results

    return FakeRedis()

@pytest.fixture
def mock_queue():
    class FakeQueue:
        def __init__(self):
            self.published = []
        async def publish(self, queue_key, payload, routing_key=None):
            self.published.append({"queue": queue_key, "payload": payload})
        async def publish_to_dlq(self, queue_key, payload, reason):
            self.published.append({"queue": f"DLQ_{queue_key}", "payload": payload, "dlq": True, "reason": reason})
        async def connect(self):
            pass
        async def close(self):
            pass
        async def consume(self, queue_key, handler):
            pass
    return FakeQueue()
