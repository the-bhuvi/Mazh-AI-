from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseWeatherProvider(ABC):
    @abstractmethod
    async def get_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Fetches weather data containing current, hourly (48h), and daily (7d) metrics.
        Returns normalized dictionary with raw weather elements.
        """
        pass
