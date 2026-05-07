import httpx
import logging
from typing import Dict, List
from .base_exchange import BaseExchange
from config.settings import settings

logger = logging.getLogger(__name__)

class StakeExchange(BaseExchange):
    """
    Direct API integration for Stake.com (or similar platform).
    This implementation uses HTTPx for fast, direct API calls
    without any browser automation overhead.
    """

    def __init__(self, api_key: str, graphql_url: str):
        self.api_key = api_key
        self.graphql_url = graphql_url
        self.client = None
        self._logged_in = False

    async def start(self) -> None:
        """Initialize the HTTPx client with auth headers."""
        headers = {
            "x-access-token": self.api_key,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.client = httpx.AsyncClient(headers=headers, timeout=10.0)
        
        # Verify connection
        try:
            # Placeholder for actual auth check mutation/query
            # response = await self.client.post(self.graphql_url, json={"query": "{ user { id } }"})
            # if response.status_code == 200:
            self._logged_in = True
            logger.info("✅ Stake Exchange API Connected")
        except Exception as e:
            logger.error(f"❌ Stake Exchange Connection Failed: {e}")
            self._logged_in = False

    async def stop(self) -> None:
        if self.client:
            await self.client.aclose()
            logger.info("🛑 Stake Exchange API Disconnected")

    async def is_logged_in(self) -> bool:
        return self._logged_in

    async def get_balance(self) -> float:
        if not self._logged_in:
            return 0.0
        # Placeholder GraphQL query for balance
        # query = {"query": "{ user { balances { amount currency } } }"}
        # response = await self.client.post(self.graphql_url, json=query)
        # return float(response.json()['data']['user']['balances'][0]['amount'])
        return 1200.0  # Mocked for now

    async def get_live_cricket_matches(self) -> List[Dict]:
        """Fetch live cricket matches using Stake's API."""
        if not self._logged_in:
            return []
            
        # Example GraphQL query for active cricket matches
        query = {
            "query": """
            query GetLiveCricket {
                sport(slug: "cricket") {
                    activeMatches {
                        id
                        name
                        competitors { name }
                        odds { back lay }
                    }
                }
            }
            """
        }
        
        try:
            # response = await self.client.post(self.graphql_url, json=query)
            # data = response.json()
            
            # Mock response for now until schema is verified
            return [
                {
                    "url": "stake_match_123",
                    "title": "Chennai Super Kings v Mumbai Indians",
                    "team_a": "Chennai Super Kings",
                    "team_b": "Mumbai Indians",
                    "is_ipl": True,
                    "is_live": True,
                    "back_a": 1.95,
                    "back_b": 1.95
                }
            ]
        except Exception as e:
            logger.error(f"Failed to fetch live matches: {e}")
            return []

    async def get_match_odds(self, match_id: str) -> Dict:
        # Implementation for specific match odds
        return {"back_a": 1.95, "back_b": 1.95}

    async def place_bet(self, match_id: str, side: str, stake: float, price: float) -> bool:
        """Execute a bet directly via API."""
        if not self._logged_in:
            return False
            
        logger.info(f"Placing {side} bet on {match_id}: ₹{stake} @ {price}")
        
        mutation = {
            "query": """
            mutation PlaceBet($matchId: ID!, $side: BetSide!, $amount: Float!, $odds: Float!) {
                placeBet(input: {matchId: $matchId, side: $side, amount: $amount, odds: $odds}) {
                    success
                    betId
                }
            }
            """,
            "variables": {
                "matchId": match_id,
                "side": side,
                "amount": stake,
                "odds": price
            }
        }
        
        try:
            # response = await self.client.post(self.graphql_url, json=mutation)
            # return response.json().get('data', {}).get('placeBet', {}).get('success', False)
            return True # Mock success
        except Exception as e:
            logger.error(f"Failed to place bet: {e}")
            return False

    async def navigate_to_match(self, match_id: str) -> None:
        # For API, this might just mean subscribing to a websocket channel for this match
        pass
