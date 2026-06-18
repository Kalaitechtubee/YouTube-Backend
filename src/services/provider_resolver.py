from typing import List, Optional
from src.providers.base_provider import BaseProvider
from src.providers.youtube.youtube_provider import YouTubeProvider
from src.providers.instagram.instagram_provider import InstagramProvider

class ProviderResolver:
    def __init__(self, providers: Optional[List[BaseProvider]] = None):
        self._providers = providers or [
            YouTubeProvider(),
            InstagramProvider()
        ]

    def resolve(self, url: str) -> BaseProvider:
        """
        Dynamically finds the provider class that matches the URL.
        """
        for provider in self._providers:
            if provider.validate_url(url):
                return provider
        raise ValueError("Unsupported media URL. No matching provider found.")

    def register_provider(self, provider: BaseProvider):
        """Allows registering new plugins dynamically without modifying resolver core."""
        self._providers.append(provider)
