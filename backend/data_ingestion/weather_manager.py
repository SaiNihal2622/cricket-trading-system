import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class WeatherManager:
    """
    Fetches live weather data for DLS predictive modeling.
    Uses OpenWeatherMap (or similar) to get probability of precipitation (PoP).
    """
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        # Common IPL stadium coordinates fallback
        self.stadiums = {
            "mumbai": {"lat": 18.9272, "lon": 72.8206},
            "chennai": {"lat": 13.0628, "lon": 80.2793},
            "bengaluru": {"lat": 12.9788, "lon": 77.5997},
            "kolkata": {"lat": 22.5646, "lon": 88.3433},
            "delhi": {"lat": 28.6378, "lon": 77.2432},
            "ahmedabad": {"lat": 23.0911, "lon": 72.5975},
        }

    async def get_stadium_weather(self, stadium_name: str) -> Optional[dict]:
        """
        Returns { 'rain_prob': float, 'humidity': float, 'conditions': str }
        """
        if not self.api_key:
            # Mock data for demonstration without key
            return {"rain_prob": 0.15, "humidity": 65.0, "conditions": "Clear"}

        stadium_key = next((k for k in self.stadiums.keys() if k in stadium_name.lower()), "mumbai")
        coords = self.stadiums[stadium_key]

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                url = f"https://api.openweathermap.org/data/2.5/weather?lat={coords['lat']}&lon={coords['lon']}&appid={self.api_key}"
                # For demo, if we hit 401 we just return mock
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "rain_prob": data.get("rain", {}).get("1h", 0) / 10.0, # rough heuristic
                        "humidity": data.get("main", {}).get("humidity", 50),
                        "conditions": data.get("weather", [{}])[0].get("main", "Clear")
                    }
                else:
                    return {"rain_prob": 0.0, "humidity": 60.0, "conditions": "Clear"}
        except Exception as e:
            logger.warning(f"Weather API failed: {e}")
            return {"rain_prob": 0.0, "humidity": 55.0, "conditions": "Unknown"}
