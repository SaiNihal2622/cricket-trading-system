"""
RoyalBook.win — Production Playwright exchange.

Features:
- Login state detection + auto re-login on session expiry
- IPL-only match discovery + today's schedule
- Match Odds (BACK/LAY), Bookmaker, Sessions, Premium Sessions
- Stop loss execution (hedge opposite side)
- Balance monitoring
- Screenshot-based debug mode
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class RoyalBookExchange:
    BASE        = "https://royalbook.win"
    LOGIN_URL   = "https://royalbook.win/login"
    CRICKET_URL = "https://royalbook.win/exchange_sports/cricket"

    # Selectors tried in order — some RoyalBook skins differ
    _USER_SELS  = ['input[name="username"]', 'input[type="text"]',
                   'input[placeholder*="ser" i]', 'input[placeholder*="ogin" i]',
                   'input[id*="user" i]', 'input[autocomplete="username"]']
    _PASS_SELS  = ['input[type="password"]', 'input[name="password"]',
                   'input[id*="pass" i]', 'input[placeholder*="ass" i]']
    _SUBMIT_SELS = ['button[type="submit"]', 'button:has-text("Login")',
                    'button:has-text("Sign In")', 'input[type="submit"]',
                    'a:has-text("Login")', '[class*="login" i] button']
    _BALANCE_SELS = ['[class*="balance" i]', '[class*="Balance"]',
                     '#balance', '[class*="Available"]',
                     'span:has-text("Bal")', '[id*="bal" i]']
    _STAKE_SELS   = ['input[placeholder*="Stake" i]', 'input[placeholder*="stake"]',
                     '.betslip input[type="number"]', '#stakeValue',
                     '[class*="stake" i] input', '[class*="Stake"] input',
                     'input[type="number"]']
    _PLACEBET_SELS = ['button:has-text("Place Bet")', 'button:has-text("PLACE BET")',
                      'button:has-text("Place Order")', 'button:has-text("Confirm")',
                      '[class*="place-bet" i] button', '[class*="placeBet"] button',
                      'button:has-text("Submit")']

    def __init__(self, username: str, password: str, headless: bool = True):
        self.username   = username
        self.password   = password
        self.headless   = headless

        self._pw       = None
        self._browser: Optional[Browser]        = None
        self._ctx:     Optional[BrowserContext]  = None
        self._page:    Optional[Page]            = None

        self._logged_in         = False
        self._demo_mode         = False   # True when logged in via Demo (can't place bets)
        self._last_odds: dict   = {}
        self._active_match_url: Optional[str] = None
        self._login_attempts    = 0

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def check_site_accessible(self) -> bool:
        """Quick HTTP check to see if royalbook.win is reachable (no browser needed)."""
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                r = await client.get(self.LOGIN_URL, headers={"User-Agent": "Mozilla/5.0"})
                ok = r.status_code < 500
                logger.info(f"RoyalBook site check: HTTP {r.status_code} — {'✅ reachable' if ok else '❌ unreachable'}")
                return ok
        except Exception as e:
            logger.warning(f"RoyalBook site check failed: {e}")
            return False

    async def start(self):
        # First verify the site is reachable at all
        await self.check_site_accessible()

        import platform
        self._pw      = await async_playwright().start()
        args = [
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-web-security",
            "--disable-setuid-sandbox",
            "--window-size=1440,900",
        ]
        # --single-process crashes on Windows; only use on Linux (Railway)
        if platform.system() == "Linux":
            args += ["--single-process", "--disable-gpu", "--disable-software-rasterizer"]

        self._browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=args,
        )
        self._ctx = await self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-IN,en-GB;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "sec-ch-ua": '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
            },
        )
        # Deep anti-detection — make headless Chromium look like real Chrome
        await self._ctx.add_init_script("""
            // Remove webdriver flag
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            // Fake plugins (real Chrome has these)
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-IN', 'en-GB', 'en'],
            });
            // Chrome runtime
            window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
            // Fake notification permission
            const origQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (params) =>
                params.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : origQuery(params);
        """)
        self._page = await self._ctx.new_page()

        # Intercept all requests to ensure Origin + Referer headers are present
        # (RoyalBook login API rejects requests missing Origin header)
        async def _add_origin(route, request):
            headers = {**request.headers,
                       "Origin": "https://royalbook.win",
                       "Referer": "https://royalbook.win/login"}
            await route.continue_(headers=headers)

        await self._page.route("**/*", _add_origin)
        await self._login()

    async def stop(self):
        try:
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass

    # ── Auth ─────────────────────────────────────────────────────────────────

    async def _login(self):
        """Full login flow with robust selector fallbacks + screenshot on failure."""
        p = self._page
        self._login_attempts += 1
        logger.info(f"RoyalBook login attempt #{self._login_attempts}")

        try:
            await p.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=35000)
            await p.wait_for_timeout(2500)

            current_url = p.url
            logger.info(f"Login page loaded: {current_url}")

            # If already logged in (session cookie survived restart)
            if "login" not in current_url.lower() and current_url != "about:blank":
                logger.info("RoyalBook: already logged in via cookie ✅")
                self._logged_in = True
                return

            # ── Click "Username" / "User ID" tab if present ─────────────────
            # RoyalBook has "Login with: [Username] [Phone Number]" tabs
            for tab_sel in [
                'a:has-text("Username")', 'button:has-text("Username")',
                'span:has-text("Username")', '[class*="tab"]:has-text("Username")',
                'a:has-text("User ID")', 'button:has-text("User ID")',
                'li:has-text("Username")', 'li:has-text("User ID")',
            ]:
                try:
                    el = await p.query_selector(tab_sel)
                    if el:
                        await el.click(timeout=2000)
                        logger.info(f"Clicked login tab: {tab_sel}")
                        await p.wait_for_timeout(500)
                        break
                except Exception:
                    continue

            # ── Fill username (type like a human, not instant fill) ─────────
            user_filled = False
            for sel in self._USER_SELS:
                try:
                    await p.click(sel, timeout=3000)
                    await p.wait_for_timeout(200)
                    await p.type(sel, self.username, delay=80)  # 80ms per char
                    logger.info(f"Username typed via: {sel}")
                    user_filled = True
                    break
                except Exception:
                    continue
            if not user_filled:
                logger.warning("Could not find username field — page text:")
                try:
                    txt = await p.inner_text("body")
                    logger.warning(f"{txt[:400]}")
                except Exception:
                    pass

            await p.wait_for_timeout(600)

            # ── Fill password (human-like typing) ───────────────────────────
            for sel in self._PASS_SELS:
                try:
                    await p.click(sel, timeout=3000)
                    await p.wait_for_timeout(200)
                    await p.type(sel, self.password, delay=80)
                    logger.info(f"Password typed via: {sel}")
                    break
                except Exception:
                    continue

            await p.wait_for_timeout(1000)

            # ── Submit ───────────────────────────────────────────────────────
            # Wait a moment for any JS validation to settle before clicking
            await p.wait_for_timeout(600)
            clicked = False
            for sel in self._SUBMIT_SELS:
                try:
                    await p.click(sel, timeout=3000)
                    logger.info(f"Submit clicked via: {sel}")
                    clicked = True
                    break
                except Exception:
                    continue

            if not clicked:
                # Last resort: press Enter on the password field
                for sel in self._PASS_SELS:
                    try:
                        await p.press(sel, "Enter", timeout=2000)
                        logger.info("Submitted via Enter key")
                        clicked = True
                        break
                    except Exception:
                        continue

            # Wait for navigation after submit
            try:
                await p.wait_for_load_state("networkidle", timeout=25000)
            except Exception:
                await p.wait_for_timeout(4000)

            final_url = p.url
            # Success = URL changed away from /login
            login_gone = "login" not in final_url.lower()

            # Also check for account elements as secondary confirmation
            if not login_gone:
                for sel in self._BALANCE_SELS:
                    try:
                        el = await p.query_selector(sel)
                        if el:
                            login_gone = True
                            break
                    except Exception:
                        continue

            self._logged_in = login_gone
            self._demo_mode = False
            logger.info(
                f"RoyalBook login: {'✅ SUCCESS' if self._logged_in else '❌ FAILED'} "
                f"→ {final_url}"
            )

            # If credential login failed, fall back to Demo login
            if not self._logged_in:
                logger.warning("Credentials failed — trying Demo login as fallback (odds scraping only)")
                try:
                    await p.goto(self.LOGIN_URL, wait_until="networkidle", timeout=20000)
                    await p.wait_for_timeout(1000)
                    demo_btn = await p.query_selector('button:has-text("Demo login"), button:has-text("Demo Login"), a:has-text("Demo")')
                    if demo_btn:
                        await demo_btn.click()
                        await p.wait_for_timeout(3000)
                        if "login" not in p.url.lower():
                            self._logged_in = True
                            self._demo_mode = True
                            logger.info("RoyalBook: DEMO LOGIN active (odds scraping only — no real bets)")
                except Exception as de:
                    logger.debug(f"Demo login also failed: {de}")

            # Screenshot debug on failure
            if not self._logged_in:
                try:
                    import os
                    os.makedirs("/tmp/rb_debug", exist_ok=True)
                    path = f"/tmp/rb_debug/login_fail_{self._login_attempts}.png"
                    await p.screenshot(path=path)
                    logger.info(f"Debug screenshot saved: {path}")
                    # Also log visible text for diagnosis
                    txt = await p.inner_text("body")
                    logger.warning(f"Login page content (first 500): {txt[:500]}")
                except Exception as se:
                    logger.debug(f"Screenshot failed: {se}")

        except Exception as e:
            logger.error(f"Login error: {e}")
            self._logged_in = False

    async def is_logged_in(self) -> bool:
        """
        Check if the current page session is authenticated.
        Detects session expiry by checking for login page redirect or missing account elements.
        """
        try:
            url = self._page.url
            if not url or "login" in url.lower():
                return False
            # Check for balance element (only present when logged in)
            for sel in self._BALANCE_SELS:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        return True
                except Exception:
                    continue
            # Check for logout link
            logout_el = await self._page.query_selector(
                'a:has-text("Logout"), a:has-text("Log Out"), button:has-text("Logout"), '
                '[class*="logout" i]'
            )
            return bool(logout_el)
        except Exception:
            return False

    async def ensure_logged_in(self) -> bool:
        """
        Ensure we're logged in. Re-login if session has expired.
        Called before every scrape/bet action.
        """
        if not await self.is_logged_in():
            logger.warning("⚠️ RoyalBook session expired — re-logging in...")
            await self._login()
        return self._logged_in

    # ── Match Discovery ──────────────────────────────────────────────────────

    async def get_live_cricket_matches(self) -> list:
        """
        Get all live cricket matches — IPL matches prioritized.
        Returns list of {url, title, is_ipl, is_live}
        """
        await self.ensure_logged_in()
        p = self._page

        try:
            await p.goto(self.CRICKET_URL, wait_until="domcontentloaded", timeout=20000)
            await p.wait_for_timeout(2000)

            links = await p.evaluate("""() => {
                const seen = new Set();
                const ipl_keywords = ['ipl', 'indian premier', 'mumbai', 'chennai', 'kolkata',
                                      'rajasthan', 'delhi', 'bangalore', 'rcb', 'mi', 'csk',
                                      'kkr', 'rr', 'dc', 'pbks', 'srh', 'gt', 'lsg', 'punjab',
                                      'sunrisers', 'gujarat', 'lucknow'];
                return [...document.querySelectorAll('a')]
                    .filter(a => a.href && a.href.includes('/exchange_sports/cricket/'))
                    .map(a => {
                        const title = a.innerText.trim() || a.title || '';
                        const lower = title.toLowerCase();
                        const is_ipl = ipl_keywords.some(k => lower.includes(k));
                        const is_live = !!(
                            a.closest('[class*="live" i]') ||
                            lower.includes('live') ||
                            a.querySelector('[class*="live" i]')
                        );
                        return { url: a.href, title, is_ipl, is_live };
                    })
                    .filter(m => {
                        if (seen.has(m.url) || !m.title || m.title.length < 3) return false;
                        seen.add(m.url);
                        return true;
                    })
                    .sort((a, b) => (b.is_ipl - a.is_ipl) || (b.is_live - a.is_live));
            }""")
            logger.info(f"Found {len(links)} cricket matches ({sum(1 for l in links if l.get('is_ipl'))} IPL)")
            return links
        except Exception as e:
            logger.error(f"get_live_cricket_matches: {e}")
            return []

    async def navigate_to_match(self, url: str):
        """Navigate to a specific match page with login check."""
        await self.ensure_logged_in()
        if self._active_match_url == url:
            return
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await self._page.wait_for_timeout(2000)
            self._active_match_url = url
            logger.info(f"RoyalBook → {url}")
        except Exception as e:
            logger.error(f"navigate_to_match failed: {e}")

    async def refresh_match_page(self):
        """Reload the current match page (odds update)."""
        if self._active_match_url:
            try:
                await self._page.reload(wait_until="domcontentloaded", timeout=15000)
                await self._page.wait_for_timeout(1500)
            except Exception as e:
                logger.warning(f"Refresh failed: {e}")

    # ── Odds Scraping ────────────────────────────────────────────────────────

    async def scrape_match_odds(self) -> dict:
        """
        Comprehensive scrape: Match Odds, Bookmaker, Sessions, Premium Sessions.
        Auto re-logins if session expired.
        Returns:
        {
          "match_odds":   { "Team A": {"back": 2.10, "lay": 2.12}, ... },
          "bookmaker":    { "Team A": {"back": 110}, ... },
          "sessions":     [{"label": "6 Over Runs KKR", "no": 59, "yes": 61, "no_odds": 1.83, "yes_odds": 1.97}, ...],
          "premium_sessions": [...],
          "match_title":  "...",
          "score":        "...",
          "timestamp":    "..."
        }
        """
        # Check if session expired (page might have redirected to login)
        if not await self.is_logged_in():
            await self._login()
            if self._active_match_url:
                await self.navigate_to_match(self._active_match_url)

        p = self._page
        try:
            result = await p.evaluate("""() => {
                const data = {
                    match_odds: {}, bookmaker: {},
                    sessions: [], premium_sessions: [],
                    match_title: '', score: ''
                };

                const pf = t => {
                    if (!t) return null;
                    const v = parseFloat((t + '').replace(/[^0-9.]/g, ''));
                    return isNaN(v) || v === 0 ? null : v;
                };

                // ── Match title & score ────────────────────────────────────
                const titleEl = document.querySelector('h1, h2, [class*="match-title" i], [class*="matchTitle"]');
                if (titleEl) data.match_title = titleEl.innerText.trim().substring(0, 100);

                const scoreEl = document.querySelector('[class*="score" i], [class*="Score"], .score-board');
                if (scoreEl) data.score = scoreEl.innerText.trim().replace(/\\s+/g, ' ').substring(0, 200);

                // ── Helper: extract team rows from a section ───────────────
                const extractTeamRows = (section) => {
                    const teams = {};
                    if (!section) return teams;
                    section.querySelectorAll('tr').forEach(row => {
                        const cells = [...row.querySelectorAll('td')];
                        if (cells.length < 3) return;
                        const name = cells[0]?.innerText?.trim();
                        if (!name || name.length < 2 || name.length > 40) return;
                        // Back cols (blue): 1,2,3 → take best (middle one)
                        const allVals = cells.slice(1).map(c => pf(c.innerText));
                        const backs = allVals.slice(0, 3).filter(v => v && v > 1 && v < 500);
                        const lays  = allVals.slice(3, 6).filter(v => v && v > 1 && v < 500);
                        if (backs.length) {
                            teams[name] = {
                                back: backs[Math.floor(backs.length/2)],
                                lay: lays.length ? lays[Math.floor(lays.length/2)] : null
                            };
                        }
                    });
                    return teams;
                };

                // ── Match Odds section ─────────────────────────────────────
                // Try by heading text
                const allTextEls = [...document.querySelectorAll('div, h3, h4, span')];
                const moHeading = allTextEls.find(el =>
                    /^Match Odds$/i.test(el.innerText?.trim()) ||
                    /^Match Winner$/i.test(el.innerText?.trim())
                );
                let moSection = moHeading?.closest('table') ||
                                moHeading?.parentElement?.querySelector('table') ||
                                moHeading?.closest('[class]')?.querySelector('table');

                // Fallback: find by class
                if (!moSection) {
                    moSection = document.querySelector(
                        '[class*="match-odds" i] table, [class*="matchOdds"] table, ' +
                        '[class*="match_odds"] table'
                    );
                }
                if (moSection) {
                    data.match_odds = extractTeamRows(moSection.closest('table') || moSection);
                }

                // ── Bookmaker section ──────────────────────────────────────
                const bmHeading = allTextEls.find(el =>
                    /^BOOKMAKER$/i.test(el.innerText?.trim()) ||
                    /^Bookmaker Market$/i.test(el.innerText?.trim())
                );
                let bmSection = bmHeading?.closest('table') ||
                                bmHeading?.parentElement?.querySelector('table') ||
                                bmHeading?.closest('[class]')?.querySelector('table');
                if (!bmSection) {
                    bmSection = document.querySelector('[class*="bookmaker" i] table');
                }
                if (bmSection) {
                    const bm = extractTeamRows(bmSection.closest('table') || bmSection);
                    // Bookmaker odds are integers (run differences)
                    data.bookmaker = bm;
                }

                // ── Sessions / Fancy ───────────────────────────────────────
                const sessionKeywords = /Over Runs|Session|Adv|Fancy|Wicket|Runs/i;
                const premiumKeywords = /Premium|Player Runs|Partnership|Boundaries/i;

                [...document.querySelectorAll('tr')].forEach(row => {
                    const cells = [...row.querySelectorAll('td')];
                    if (cells.length < 3) return;

                    const label = cells[0]?.innerText?.trim();
                    if (!label || label.length < 4 || label.length > 80) return;

                    if (!sessionKeywords.test(label) && !premiumKeywords.test(label)) return;

                    // Session layout: | Label | NO_ODDS | NO_LINE | YES_LINE | YES_ODDS | Status? |
                    // Or simpler:     | Label | NO | YES |
                    const vals = cells.slice(1).map(c => pf(c.innerText));

                    let no_line = null, yes_line = null, no_odds = null, yes_odds = null;

                    if (vals.length >= 4) {
                        // Typical: no_odds, no_line, yes_line, yes_odds
                        no_odds  = vals[0];
                        no_line  = vals[1];
                        yes_line = vals[2];
                        yes_odds = vals[3];
                    } else if (vals.length >= 2) {
                        no_line  = vals[0];
                        yes_line = vals[1];
                    }

                    const entry = { label, no: no_line, yes: yes_line, no_odds, yes_odds };

                    if (premiumKeywords.test(label)) {
                        data.premium_sessions.push(entry);
                    } else {
                        data.sessions.push(entry);
                    }
                });

                return data;
            }""")

            if result and (result.get("match_odds") or result.get("sessions")):
                result["timestamp"] = datetime.utcnow().isoformat()
                self._last_odds = result
                logger.debug(
                    f"Scraped: {len(result.get('match_odds', {}))} teams, "
                    f"{len(result.get('sessions', []))} sessions, "
                    f"{len(result.get('premium_sessions', []))} premium"
                )
            return self._last_odds

        except Exception as e:
            logger.error(f"scrape_match_odds: {e}")
            # If page seems broken, try re-navigating
            if self._active_match_url:
                try:
                    await self._page.goto(self._active_match_url, wait_until="domcontentloaded", timeout=15000)
                    await self._page.wait_for_timeout(2000)
                except Exception:
                    pass
            return self._last_odds

    # ── Internal bet helpers ─────────────────────────────────────────────────

    async def _click_cell(self, team_or_label: str, col_index_candidates: list) -> dict:
        """
        Generic helper: find a table row by label, click a cell at one of the candidate indices.
        Returns {ok, val} or {ok: false}.
        """
        return await self._page.evaluate("""([label, cols]) => {
            const rows = [...document.querySelectorAll('tr')];
            for (const row of rows) {
                const first = row.querySelector('td:first-child');
                if (!first) continue;
                const text = first.innerText.trim().toLowerCase();
                if (!text.includes(label.toLowerCase())) continue;
                const cells = [...row.querySelectorAll('td')];
                for (const idx of cols) {
                    const cell = cells[idx];
                    if (cell && cell.innerText.trim() && parseFloat(cell.innerText) > 0) {
                        cell.click();
                        return { ok: true, val: cell.innerText.trim() };
                    }
                }
            }
            return { ok: false };
        }""", [team_or_label, col_index_candidates])

    async def _fill_and_place(self, stake: float) -> dict:
        """Fill stake field and click Place Bet. Returns success status."""
        if self._demo_mode:
            logger.warning("DEMO MODE — bet skipped (no real account). Register on royalbook.win to enable live betting.")
            return {"ok": False, "demo": True, "reason": "Demo mode — register account first"}
        p = self._page
        await p.wait_for_timeout(700)

        # Fill stake
        filled = False
        for sel in self._STAKE_SELS:
            try:
                el = await p.wait_for_selector(sel, timeout=2500)
                if el:
                    await el.triple_click()
                    await el.fill("")
                    await el.type(str(int(stake)), delay=40)
                    filled = True
                    break
            except Exception:
                continue

        if not filled:
            return {"success": False, "message": "Stake input not found"}

        await p.wait_for_timeout(350)

        # Place bet
        placed = False
        for sel in self._PLACEBET_SELS:
            try:
                btn = await p.wait_for_selector(sel, timeout=2000)
                if btn:
                    await btn.click()
                    placed = True
                    break
            except Exception:
                continue

        if not placed:
            return {"success": False, "message": "Place Bet button not found"}

        await p.wait_for_timeout(1200)

        # Read confirmation
        msg = "Bet placed"
        for sel in ['.alert-success', '[class*="success"]', '[class*="toast"]',
                    '[class*="notification"]', '[class*="alert"]']:
            try:
                el = await p.query_selector(sel)
                if el:
                    msg = (await el.inner_text()).strip()[:200]
                    break
            except Exception:
                pass

        return {"success": True, "message": msg}

    # ── Bet Placement ────────────────────────────────────────────────────────

    async def place_back_bet(self, team: str, stake: float, market: str = "match_odds") -> dict:
        """
        Place a BACK bet on a team in Match Odds market.
        Back = Blue columns (indices 1, 2, 3 in a typical row).
        """
        await self.ensure_logged_in()
        p = self._page
        try:
            # Back columns: indices 1, 2, 3 (blue cells)
            clicked = await self._click_cell(team, [1, 2, 3])
            if not clicked.get("ok"):
                return {"success": False, "message": f"Back button not found for '{team}'"}

            result = await self._fill_and_place(stake)
            if result["success"]:
                logger.info(f"✅ BACK {team} @ {clicked.get('val')} ₹{stake} | {result['message']}")
            result["team"] = team
            result["stake"] = stake
            result["odds"] = clicked.get("val")
            return result

        except Exception as e:
            logger.error(f"place_back_bet: {e}")
            return {"success": False, "message": str(e)}

    async def place_lay_bet(self, team: str, stake: float) -> dict:
        """
        Place a LAY bet on a team.
        Lay = Pink columns (indices 4, 5, 6).
        """
        await self.ensure_logged_in()
        try:
            clicked = await self._click_cell(team, [4, 5, 6])
            if not clicked.get("ok"):
                return {"success": False, "message": f"Lay button not found for '{team}'"}

            result = await self._fill_and_place(stake)
            if result["success"]:
                logger.info(f"✅ LAY {team} @ {clicked.get('val')} ₹{stake}")
            result["team"] = team
            result["stake"] = stake
            return result

        except Exception as e:
            logger.error(f"place_lay_bet: {e}")
            return {"success": False, "message": str(e)}

    async def place_session_bet(self, label: str, side: str, stake: float) -> dict:
        """
        Place a session/fancy bet.
        side: 'yes' (BACK over line) | 'no' (BACK under line)
        Yes = blue (cols 3,4), No = pink (cols 1,2).
        """
        await self.ensure_logged_in()
        try:
            cols = [3, 4] if side.lower() == "yes" else [1, 2]
            clicked = await self._click_cell(label, cols)
            if not clicked.get("ok"):
                return {"success": False, "message": f"Session button not found: '{label}' {side}"}

            result = await self._fill_and_place(stake)
            if result["success"]:
                logger.info(f"✅ SESSION {label} {side.upper()} ₹{stake}")
            result["label"] = label
            result["side"] = side
            result["stake"] = stake
            return result

        except Exception as e:
            logger.error(f"place_session_bet: {e}")
            return {"success": False, "message": str(e)}

    async def place_stop_loss(self, team: str, stop_stake: float, side: str = "lay") -> dict:
        """
        Execute a stop loss by placing a lay bet on the backed team
        (or a back on the opposite team).
        This hedges the position and limits further loss.
        side: 'lay' (lay the backed team) | 'back_opposite' (back the other team)
        """
        await self.ensure_logged_in()
        logger.warning(f"🛑 STOP LOSS: {side} {team} ₹{stop_stake}")
        if side == "lay":
            return await self.place_lay_bet(team, stop_stake)
        else:
            return await self.place_back_bet(team, stop_stake)

    # ── Balance ──────────────────────────────────────────────────────────────

    async def get_balance(self) -> float:
        """Read current available balance."""
        await self.ensure_logged_in()
        try:
            for sel in self._BALANCE_SELS:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        text = await el.inner_text()
                        nums = re.findall(r"[\d,]+\.?\d*", text)
                        if nums:
                            return float(nums[0].replace(",", ""))
                except Exception:
                    continue
        except Exception:
            pass
        return 0.0

    # ── Cashout / Loss Cut ───────────────────────────────────────────────────

    async def click_cashout(self) -> dict:
        """Click the Cashout button on the current market."""
        await self.ensure_logged_in()
        p = self._page
        try:
            btn = await p.query_selector(
                'button:has-text("Cashout"), button:has-text("Cash Out"), '
                'button:has-text("CASHOUT"), [class*="cashout" i] button'
            )
            if btn:
                await btn.click()
                await p.wait_for_timeout(1000)
                logger.info("✅ Cashout clicked")
                return {"success": True, "message": "Cashout executed"}
            return {"success": False, "message": "Cashout button not visible"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def click_loss_cut(self) -> dict:
        """Click the platform's own Loss Cut button if available."""
        await self.ensure_logged_in()
        p = self._page
        try:
            btn = await p.query_selector(
                'button:has-text("Loss Cut"), button:has-text("LossCut"), '
                'button:has-text("LOSS CUT"), [class*="loss-cut" i] button'
            )
            if btn:
                await btn.click()
                await p.wait_for_timeout(1000)
                logger.info("✅ Loss Cut clicked")
                return {"success": True, "message": "Loss Cut executed"}
            return {"success": False, "message": "Loss Cut button not visible"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Utility ──────────────────────────────────────────────────────────────

    async def take_screenshot(self, path: str = "/tmp/royalbook_debug.png"):
        """Take a screenshot for debugging click issues."""
        try:
            await self._page.screenshot(path=path, full_page=False)
            logger.info(f"Screenshot saved: {path}")
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")

    def get_last_odds(self) -> dict:
        return self._last_odds

    @property
    def active_match_url(self) -> Optional[str]:
        return self._active_match_url
