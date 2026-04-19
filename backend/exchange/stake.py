"""
Stake.com Exchange Integration — GraphQL API

Stake uses a private GraphQL API at https://stake.com/_api/graphql
Auth: x-access-token header (get from browser DevTools → Network tab)

Cricket markets available:
- Match winner (pre-match + live)
- Live in-play odds during IPL matches

Setup:
1. Log into stake.com in browser
2. Open DevTools → Network tab → any request → copy x-access-token header
3. Set STAKE_ACCESS_TOKEN in Railway env vars
4. Set STAKE_CURRENCY to "inr" or "usdt" (default: usdt)

WARNING: Stake automation violates ToS. Use at your own risk.
Account ban risk is real — keep stakes reasonable and don't spam requests.
"""
import asyncio
import logging
import time
import uuid
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── GraphQL queries / mutations ───────────────────────────────────────────────

_GQL_BALANCE = """
query UserBalance {
  user {
    id
    balances {
      available { amount currency }
    }
  }
}
"""

_GQL_CRICKET_EVENTS = """
query SportEvents($slug: String!) {
  sportsEventsByFilter(
    filter: {
      sportSlug: $slug
      status: LIVE
      limit: 20
    }
  ) {
    id
    name
    status
    startTime
    sport { slug name }
    competitors {
      id
      name
      odds { id value }
    }
    markets {
      id
      name
      status
      selections {
        id
        name
        odds
        status
      }
    }
  }
}
"""

_GQL_PLACE_BET = """
mutation PlaceSportsBet(
  $selectionId: String!
  $odds: Float!
  $amount: Float!
  $currency: CurrencyEnum!
) {
  createSportsBet(
    selectionId: $selectionId
    odds: $odds
    amount: $amount
    currency: $currency
    isCashoutEnabled: true
  ) {
    id
    amount
    odds
    potentialWin
    status
    currency
    createdAt
  }
}
"""

_GQL_ACTIVE_BETS = """
query ActiveBets {
  sportsBets(
    query: { status: [ACTIVE, PENDING], limit: 20 }
  ) {
    id
    amount
    odds
    potentialWin
    status
    currency
    createdAt
    selections {
      id
      name
      status
      event { id name }
    }
  }
}
"""

_GQL_CASHOUT = """
mutation CashoutBet($betId: String!, $amount: Float!) {
  cashoutSportsBet(betId: $betId, cashoutAmount: $amount) {
    id
    status
    cashoutAmount
  }
}
"""


class StakeClient:
    """
    Async Stake.com GraphQL client.

    Usage:
        client = StakeClient(access_token="your_token")
        await client.init()
        events = await client.get_cricket_events()
        bet = await client.place_bet(selection_id, odds, amount)
    """

    GQL_URL  = "https://stake.pet/_api/graphql"
    HEADERS  = {
        "Content-Type":   "application/json",
        "Accept":         "*/*",
        "Origin":         "https://stake.pet",
        "Referer":        "https://stake.pet/",
        "User-Agent":     (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "x-language":     "en",
    }
    # Minimum delay between API calls (ms) — avoid ban
    _RATE_LIMIT_MS = 1500

    def __init__(self, access_token: str, currency: str = "usdt"):
        self._token    = access_token
        self._currency = currency.lower()
        self._client: Optional[httpx.AsyncClient] = None
        self._last_call = 0.0
        self._balance: float = 0.0
        self._available = bool(access_token)

    @property
    def is_available(self) -> bool:
        return self._available

    async def init(self):
        """Initialize HTTP client and verify token works."""
        self._client = httpx.AsyncClient(
            timeout=15.0,
            headers={**self.HEADERS, "x-access-token": self._token},
            follow_redirects=True,
        )
        if self._token:
            try:
                bal = await self.get_balance()
                if bal >= 0:
                    logger.info(f"Stake.com connected — balance: {bal:.4f} {self._currency.upper()}")
                    self._available = True
                else:
                    logger.warning("Stake.com: token invalid or expired")
                    self._available = False
            except Exception as e:
                logger.warning(f"Stake.com init failed: {e}")
                self._available = False

    async def _gql(self, query: str, variables: dict = None) -> dict:
        """Execute a GraphQL query with rate limiting."""
        # Rate limit
        now = time.monotonic() * 1000
        wait = self._RATE_LIMIT_MS - (now - self._last_call)
        if wait > 0:
            await asyncio.sleep(wait / 1000)
        self._last_call = time.monotonic() * 1000

        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = await self._client.post(self.GQL_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

        if "errors" in data:
            errs = data["errors"]
            raise RuntimeError(f"Stake GQL error: {errs}")

        return data.get("data", {})

    async def get_balance(self) -> float:
        """Get available balance in configured currency."""
        try:
            data = await self._gql(_GQL_BALANCE)
            balances = data.get("user", {}).get("balances", [])
            for b in balances:
                av = b.get("available", {})
                if av.get("currency", "").lower() == self._currency:
                    self._balance = float(av.get("amount", 0))
                    return self._balance
            # If currency not found, return first balance
            if balances:
                av = balances[0].get("available", {})
                self._balance = float(av.get("amount", 0))
                return self._balance
        except Exception as e:
            logger.debug(f"Stake balance error: {e}")
        return self._balance

    async def get_cricket_events(self) -> list:
        """
        Get live cricket events with odds.
        Returns list of dicts: {id, name, markets: [{id, name, selections: [{id, name, odds}]}]}
        """
        try:
            data = await self._gql(_GQL_CRICKET_EVENTS, {"slug": "cricket"})
            events = data.get("sportsEventsByFilter", []) or []
            result = []
            for ev in events:
                markets = []
                for mkt in (ev.get("markets") or []):
                    if mkt.get("status") not in ("OPEN", "ACTIVE", None):
                        continue
                    sels = []
                    for sel in (mkt.get("selections") or []):
                        if sel.get("status") not in ("OPEN", "ACTIVE", None):
                            continue
                        sels.append({
                            "id":   sel["id"],
                            "name": sel["name"],
                            "odds": float(sel.get("odds", 0) or 0),
                        })
                    if sels:
                        markets.append({
                            "id":         mkt["id"],
                            "name":       mkt["name"],
                            "selections": sels,
                        })
                if markets:
                    result.append({
                        "id":      ev["id"],
                        "name":    ev["name"],
                        "status":  ev.get("status"),
                        "markets": markets,
                    })
            return result
        except Exception as e:
            logger.error(f"Stake get_cricket_events error: {e}")
            return []

    def find_ipl_event(self, events: list, team_a: str, team_b: str) -> Optional[dict]:
        """Find the IPL match in the events list matching our teams."""
        if not events:
            return None
        t_a = team_a.lower()
        t_b = team_b.lower()
        # Abbreviation map
        ABBR = {
            "mi": "mumbai", "csk": "chennai", "kkr": "kolkata",
            "rcb": "bangalore", "rr": "rajasthan", "dc": "delhi",
            "pbks": "punjab", "srh": "hyderabad", "gt": "gujarat",
            "lsg": "lucknow",
        }
        t_a = ABBR.get(t_a, t_a)
        t_b = ABBR.get(t_b, t_b)

        for ev in events:
            name = ev["name"].lower()
            if (t_a in name or t_b in name) and ("ipl" in name or "t20" in name or "india" in name):
                return ev
            # Looser match — just team names
            if t_a in name and t_b in name:
                return ev
        # Last resort: any live cricket
        return events[0] if events else None

    def find_selection(self, event: dict, team: str, is_lay: bool = False) -> Optional[dict]:
        """
        Find the market selection for backing/laying a team.
        Returns the selection dict with {id, name, odds}.
        Note: Stake doesn't support lay bets natively — lay = back the OTHER team.
        """
        if not event:
            return None
        team_lower = team.lower()
        ABBR = {
            "mi": "mumbai", "csk": "chennai", "kkr": "kolkata",
            "rcb": "bangalore", "rr": "rajasthan", "dc": "delhi",
            "pbks": "punjab", "srh": "hyderabad", "gt": "gujarat",
            "lsg": "lucknow",
        }
        team_lower = ABBR.get(team_lower, team_lower)

        # Look in "Match Winner" or "Winner" market first
        winner_mkt = None
        for mkt in event.get("markets", []):
            name = mkt["name"].lower()
            if "winner" in name or "match odds" in name or "1x2" in name:
                winner_mkt = mkt
                break
        mkt = winner_mkt or (event["markets"][0] if event.get("markets") else None)
        if not mkt:
            return None

        sels = mkt.get("selections", [])
        if not sels:
            return None

        # Find matching selection
        for sel in sels:
            if team_lower in sel["name"].lower():
                return sel

        # If no match found and it's a 2-selection market, pick by position
        if is_lay and len(sels) >= 2:
            # Lay = back the other team
            for sel in sels:
                if team_lower not in sel["name"].lower():
                    return sel
        return sels[0] if sels else None

    async def place_bet(
        self,
        selection_id: str,
        odds: float,
        amount: float,
    ) -> dict:
        """
        Place a sports bet on Stake.
        Returns: {success, bet_id, odds, amount, potential_win, status}
        """
        try:
            data = await self._gql(_GQL_PLACE_BET, {
                "selectionId": selection_id,
                "odds":        round(odds, 4),
                "amount":      round(amount, 8),
                "currency":    self._currency.upper(),
            })
            bet = data.get("createSportsBet", {})
            if not bet:
                return {"success": False, "error": "No bet returned"}

            logger.info(
                f"Stake bet placed: id={bet['id']} "
                f"odds={bet['odds']} amount={bet['amount']} "
                f"potential={bet['potentialWin']} status={bet['status']}"
            )
            return {
                "success":       True,
                "bet_id":        bet["id"],
                "odds":          float(bet["odds"]),
                "amount":        float(bet["amount"]),
                "potential_win": float(bet["potentialWin"]),
                "status":        bet["status"],
                "currency":      bet["currency"],
            }
        except Exception as e:
            logger.error(f"Stake place_bet error: {e}")
            return {"success": False, "error": str(e)}

    async def get_active_bets(self) -> list:
        """Get all active/pending sports bets."""
        try:
            data = await self._gql(_GQL_ACTIVE_BETS)
            return data.get("sportsBets", []) or []
        except Exception as e:
            logger.debug(f"Stake active bets error: {e}")
            return []

    async def cashout_bet(self, bet_id: str, amount: float) -> dict:
        """Cash out (partial or full) an active bet."""
        try:
            data = await self._gql(_GQL_CASHOUT, {
                "betId":  bet_id,
                "amount": round(amount, 8),
            })
            result = data.get("cashoutSportsBet", {})
            logger.info(f"Stake cashout: {result}")
            return {"success": True, **result}
        except Exception as e:
            logger.error(f"Stake cashout error: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        if self._client:
            await self._client.aclose()


# ── Exchange adapter (matches BaseExchange interface) ─────────────────────────

class StakeExchange:
    """
    Wraps StakeClient into the BaseExchange interface used by TradingAgent.

    Back bet  → back the team on Stake match winner market
    Lay bet   → back the OPPONENT on Stake (no native lay market)
    Bookset   → cashout active bet at current odds
    """

    def __init__(self, access_token: str, currency: str = "usdt"):
        self._client  = StakeClient(access_token, currency)
        self._balance = 0.0
        self._active_bets: dict = {}   # selection_id → bet_id

    async def init(self):
        await self._client.init()
        self._balance = await self._client.get_balance()

    @property
    def is_available(self) -> bool:
        return self._client.is_available

    def get_balance(self) -> float:
        return self._balance

    async def place_back(
        self,
        match_id: str,
        team: str,
        odds: float,
        stake: float,
        team_a: str = "",
        team_b: str = "",
    ) -> dict:
        """Back a team — find Stake event and place bet."""
        events = await self._client.get_cricket_events()
        event  = self._client.find_ipl_event(events, team_a or team, team_b or "")
        if not event:
            logger.warning(f"Stake: no live cricket event found for {team}")
            return {"success": False, "error": "No live cricket event on Stake"}

        sel = self._client.find_selection(event, team, is_lay=False)
        if not sel:
            logger.warning(f"Stake: no selection found for {team} in {event['name']}")
            return {"success": False, "error": f"Selection not found for {team}"}

        # Use Stake's odds (might differ from our model)
        stake_odds = sel["odds"]
        logger.info(
            f"Stake BACK {team}: our_odds={odds:.2f} stake_odds={stake_odds:.2f} "
            f"stake={stake:.4f} {self._client._currency.upper()}"
        )
        result = await self._client.place_bet(sel["id"], stake_odds, stake)
        if result.get("success"):
            self._active_bets[sel["id"]] = result["bet_id"]
            self._balance = await self._client.get_balance()
        return result

    async def place_lay(
        self,
        match_id: str,
        team: str,
        odds: float,
        stake: float,
        team_a: str = "",
        team_b: str = "",
    ) -> dict:
        """
        Stake has no lay market — lay team X = back team Y (opponent).
        """
        events = await self._client.get_cricket_events()
        event  = self._client.find_ipl_event(events, team_a or team, team_b or "")
        if not event:
            return {"success": False, "error": "No live cricket event on Stake"}

        # Find opponent selection
        sel = self._client.find_selection(event, team, is_lay=True)
        if not sel:
            return {"success": False, "error": f"Opponent selection not found"}

        stake_odds = sel["odds"]
        logger.info(
            f"Stake LAY {team} → backing {sel['name']}: "
            f"odds={stake_odds:.2f} stake={stake:.4f}"
        )
        result = await self._client.place_bet(sel["id"], stake_odds, stake)
        if result.get("success"):
            self._active_bets[sel["id"]] = result["bet_id"]
            self._balance = await self._client.get_balance()
        return result

    async def cashout_all(self, cashout_pct: float = 1.0) -> list:
        """
        Cash out all active bets. cashout_pct=1.0 = full cashout.
        Used for loss_cut and bookset.
        """
        results = []
        active = await self._client.get_active_bets()
        for bet in active:
            bet_id = bet["id"]
            amount = float(bet.get("potentialWin", 0)) * cashout_pct
            if amount > 0:
                r = await self._client.cashout_bet(bet_id, amount)
                results.append(r)
        if results:
            self._balance = await self._client.get_balance()
        return results

    async def get_current_odds(self, team_a: str, team_b: str) -> dict:
        """Get current Stake odds for a match."""
        events = await self._client.get_cricket_events()
        event  = self._client.find_ipl_event(events, team_a, team_b)
        if not event:
            return {}
        result = {}
        for mkt in event.get("markets", []):
            if "winner" in mkt["name"].lower():
                for sel in mkt.get("selections", []):
                    result[sel["name"]] = sel["odds"]
        return result

    async def close(self):
        await self._client.close()


# ── Singleton ─────────────────────────────────────────────────────────────────

_stake_instance: Optional[StakeExchange] = None


async def get_stake_exchange(access_token: str = "", currency: str = "usdt") -> Optional[StakeExchange]:
    """Get or create the Stake exchange instance."""
    global _stake_instance
    if _stake_instance is None and access_token:
        _stake_instance = StakeExchange(access_token, currency)
        await _stake_instance.init()
    return _stake_instance
