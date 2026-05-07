"""
Execution Engine — Places trades (simulated or real).

Supports:
- SimulatedExchange: Virtual bankroll, paper trading (default)
- BetfairExchange: Real execution via Betfair API (optional)
- BrowserExchange: Selenium-based automation (optional)

All exchanges implement the same interface.
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """Result of a trade execution attempt"""
    success: bool
    order_id: str = ""
    filled_odds: float = 0.0
    filled_stake: float = 0.0
    message: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    exchange: str = "unknown"
    slippage: float = 0.0


class BaseExchange(ABC):
    """Interface all exchanges must implement"""

    @abstractmethod
    async def place_back(self, match_id: str, team: str, odds: float, stake: float) -> OrderResult:
        """Place a back bet on a team"""
        ...

    @abstractmethod
    async def place_lay(self, match_id: str, team: str, odds: float, stake: float) -> OrderResult:
        """Place a lay bet against a team"""
        ...

    @abstractmethod
    async def get_current_odds(self, match_id: str) -> dict:
        """Get current market odds"""
        ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel a pending order"""
        ...

    @abstractmethod
    def get_balance(self) -> float:
        """Get current account balance"""
        ...


class SimulatedExchange(BaseExchange):
    """
    Paper trading exchange — simulates fills at current odds.
    
    Perfect for testing strategies without real money.
    Adds realistic slippage simulation.
    """

    def __init__(self, initial_balance: float = 10000.0, slippage_pct: float = 0.5):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.slippage_pct = slippage_pct / 100
        self._order_counter = 0
        self._orders: List[OrderResult] = []
        self._current_odds: dict = {}

    async def place_back(self, match_id: str, team: str, odds: float, stake: float) -> OrderResult:
        """Simulate a back bet"""
        if stake > self.balance:
            return OrderResult(
                success=False,
                message=f"Insufficient balance: ₹{self.balance:.2f} < ₹{stake:.2f}",
                exchange="simulated",
            )

        # Apply slippage (odds get slightly worse)
        slippage = odds * self.slippage_pct
        filled_odds = round(odds - slippage, 2)

        self.balance -= stake
        self._order_counter += 1
        order_id = f"SIM-BACK-{self._order_counter:05d}"

        result = OrderResult(
            success=True,
            order_id=order_id,
            filled_odds=filled_odds,
            filled_stake=stake,
            message=f"BACK {team} @ {filled_odds} ₹{stake}",
            exchange="simulated",
            slippage=slippage,
        )
        self._orders.append(result)

        logger.info(f"📝 SIM BACK: {team} @ {filled_odds} (req {odds}) ₹{stake}")
        return result

    async def place_lay(self, match_id: str, team: str, odds: float, stake: float) -> OrderResult:
        """Simulate a lay bet"""
        liability = stake * (odds - 1)
        if liability > self.balance:
            return OrderResult(
                success=False,
                message=f"Insufficient balance for lay liability: ₹{liability:.2f}",
                exchange="simulated",
            )

        # Apply slippage (odds get slightly worse for lay)
        slippage = odds * self.slippage_pct
        filled_odds = round(odds + slippage, 2)

        self.balance -= liability
        self._order_counter += 1
        order_id = f"SIM-LAY-{self._order_counter:05d}"

        result = OrderResult(
            success=True,
            order_id=order_id,
            filled_odds=filled_odds,
            filled_stake=stake,
            message=f"LAY {team} @ {filled_odds} ₹{stake}",
            exchange="simulated",
            slippage=slippage,
        )
        self._orders.append(result)

        logger.info(f"📝 SIM LAY: {team} @ {filled_odds} (req {odds}) ₹{stake}")
        return result

    async def get_current_odds(self, match_id: str) -> dict:
        return self._current_odds.get(match_id, {"team_a_odds": 1.85, "team_b_odds": 2.10})

    async def cancel_order(self, order_id: str) -> bool:
        logger.info(f"📝 SIM CANCEL: {order_id}")
        return True

    def get_balance(self) -> float:
        return self.balance

    def credit(self, amount: float):
        """Credit winnings back to balance"""
        self.balance += amount
        logger.info(f"💵 SIM CREDIT: ₹{amount:.2f} | Balance: ₹{self.balance:.2f}")

    def set_odds(self, match_id: str, odds_a: float, odds_b: float):
        """Update simulated market odds"""
        self._current_odds[match_id] = {"team_a_odds": odds_a, "team_b_odds": odds_b}

    def get_stats(self) -> dict:
        return {
            "exchange": "simulated",
            "balance": round(self.balance, 2),
            "initial_balance": self.initial_balance,
            "pnl": round(self.balance - self.initial_balance, 2),
            "total_orders": self._order_counter,
            "recent_orders": [
                {"id": o.order_id, "odds": o.filled_odds, "stake": o.filled_stake,
                 "message": o.message, "time": o.timestamp}
                for o in self._orders[-10:]
            ],
        }


class BetfairExchange(BaseExchange):
    """
    Betfair API integration.
    
    To use:
    1. Get Betfair API app key: https://developer.betfair.com
    2. Set BETFAIR_APP_KEY, BETFAIR_USERNAME, BETFAIR_PASSWORD in .env
    """

    def __init__(self, app_key: str = "", username: str = "", password: str = ""):
        self.app_key = app_key
        self.username = username
        self.password = password
        self._session_token = None
        self._balance = 0.0

        if not all([app_key, username, password]):
            logger.warning("Betfair credentials not fully configured")

    async def _login(self):
        """Authenticate with Betfair"""
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://identitysso.betfair.com/api/certlogin",
                    headers={"X-Application": self.app_key},
                    data={"username": self.username, "password": self.password},
                )
                data = resp.json()
                if data.get("loginStatus") == "SUCCESS":
                    self._session_token = data["sessionToken"]
                    logger.info("✅ Betfair login successful")
                else:
                    logger.error(f"Betfair login failed: {data}")
        except Exception as e:
            logger.error(f"Betfair login error: {e}")

    async def _api_call(self, endpoint: str, params: dict) -> dict:
        """Make Betfair API call"""
        if not self._session_token:
            await self._login()

        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.betfair.com/exchange/betting/rest/v1.0/{endpoint}/",
                headers={
                    "X-Application": self.app_key,
                    "X-Authentication": self._session_token,
                    "Content-Type": "application/json",
                },
                json={"filter": params},
            )
            return resp.json()

    async def place_back(self, match_id: str, team: str, odds: float, stake: float) -> OrderResult:
        logger.info(f"🔴 BETFAIR BACK: {team} @ {odds} ₹{stake} (NOT IMPLEMENTED)")
        return OrderResult(success=False, message="Betfair back not yet implemented", exchange="betfair")

    async def place_lay(self, match_id: str, team: str, odds: float, stake: float) -> OrderResult:
        logger.info(f"🔴 BETFAIR LAY: {team} @ {odds} ₹{stake} (NOT IMPLEMENTED)")
        return OrderResult(success=False, message="Betfair lay not yet implemented", exchange="betfair")

    async def get_current_odds(self, match_id: str) -> dict:
        return {}

    async def cancel_order(self, order_id: str) -> bool:
        return False

    def get_balance(self) -> float:
        return self._balance





def create_exchange(exchange_type: str = "simulated", exchange_instance=None, **kwargs) -> BaseExchange:
    """Factory for creating exchanges"""
    if exchange_type == "stake" and exchange_instance:
        return exchange_instance
    if exchange_type == "betfair":
        return BetfairExchange(**kwargs)
    return SimulatedExchange(**kwargs)
