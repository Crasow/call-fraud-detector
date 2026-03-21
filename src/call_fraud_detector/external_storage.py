from abc import ABC, abstractmethod


class ExternalStorageClient(ABC):
    @abstractmethod
    async def fetch_call(self, external_id: str) -> bytes:
        ...


class StubStorageClient(ExternalStorageClient):
    async def fetch_call(self, external_id: str) -> bytes:
        raise NotImplementedError("External storage not configured")
