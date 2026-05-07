import abc
from typing import Dict, List, Optional

class BaseExchange(abc.ABC):
    """
    Abstract Base Class for Betting Exchanges.
    Any exchange (Stake, Betfair, RoyalBook, etc.) must implement this interface
    to be compatible with the Cricket Trading Intelligence System.
    """

    @abc.abstractmethod
    async def start(self) -> None:
        """Initialize the exchange connection/session."""
        pass

    @abc.abstractmethod
    async def stop(self) -> None:
        """Close the exchange connection/session cleanly."""
        pass

    @abc.abstractmethod
    async def is_logged_in(self) -> bool:
        """Check if the current session is authenticated."""
        pass

    @abc.abstractmethod
    async def get_balance(self) -> float:
        """Get the current available balance."""
        pass

    @abc.abstractmethod
    async def get_live_cricket_matches(self) -> List[Dict]:
        """
        Fetch all live cricket matches.
        Should return a list of dicts with:
        {
            "url": "unique_match_identifier_or_url",
            "title": "Team A v Team B",
            "team_a": "Team A",
            "team_b": "Team B",
            "is_ipl": bool,
            "is_live": bool,
            "back_a": float,
            "back_b": float
        }
        """
        pass

    @abc.abstractmethod
    async def get_match_odds(self, match_id: str) -> Dict:
        """
        Get detailed odds for a specific match.
        """
        pass

    @abc.abstractmethod
    async def place_bet(self, match_id: str, side: str, stake: float, price: float) -> bool:
        """
        Place a bet on the exchange.
        side: 'BACK' or 'LAY'
        Returns True if successful, False otherwise.
        """
        pass

    @abc.abstractmethod
    async def navigate_to_match(self, match_id: str) -> None:
        """
        Navigate or subscribe to a specific match for live updates.
        """
        pass
