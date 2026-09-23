import os
import time
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright, BrowserContext, Page, Playwright

class BrowserManager:
    """
    Manages a persistent Playwright browser context.
    Stores login session, cookies, and local state so users only log in once.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_profile = os.path.join(project_root, "user_profile")
        raw_profile = config.get("user_profile_dir", default_profile)
        if not os.path.isabs(raw_profile):
            self.profile_dir = os.path.abspath(os.path.join(project_root, raw_profile))
        else:
            self.profile_dir = os.path.abspath(raw_profile)

        self.headless = config.get("headless", False)
        self.playwright: Optional[Playwright] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

        if not os.path.exists(self.profile_dir):
            os.makedirs(self.profile_dir, exist_ok=True)

    def _cleanup_stale_locks(self):
        """Removes orphaned lockfiles and kills background processes locking this profile directory"""
        try:
            import subprocess
            cmd = 'Get-CimInstance Win32_Process | Where-Object { $_.Name -in @("msedge.exe", "chrome.exe") } | Select-Object ProcessId, CommandLine | ConvertTo-Json'
            p = subprocess.Popen(['powershell', '-NoProfile', '-Command', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, _ = p.communicate()
            if out:
                import json
                items = json.loads(out.decode('utf-8', errors='ignore'))
                if isinstance(items, dict): items = [items]
                norm_dir = os.path.normpath(self.profile_dir).lower()
                for it in items:
                    cl = str(it.get('CommandLine', '')).lower()
                    if norm_dir in cl:
                        pid = it.get('ProcessId')
                        try:
                            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True)
                        except Exception:
                            pass
        except Exception:
            pass

        for lock in ['lockfile', 'SingletonLock', 'SingletonCookie', 'SingletonSocket']:
            lp = os.path.join(self.profile_dir, lock)
            if os.path.exists(lp):
                try:
                    os.remove(lp)
                except Exception:
                    pass

    def get_active_page(self, force_headed: bool = False) -> Page:
        """Returns a valid, open Page. Re-launches if context or page was closed."""
        try:
            if self.page and not self.page.is_closed():
                _ = self.page.url
                return self.page
        except Exception:
            pass

        try:
            if self.context and not self.context.is_closed():
                for p in self.context.pages:
                    try:
                        if not p.is_closed():
                            self.page = p
                            return self.page
                    except Exception:
                        pass
                self.page = self.context.new_page()
                return self.page
        except Exception:
            pass

        self.close()
        return self.launch(force_headed=force_headed)

    def launch(self, force_headed: bool = False) -> Page:
        """Launches the persistent browser context and returns the main page."""
        try:
            if self.page and not self.page.is_closed():
                _ = self.page.url
                return self.page
        except Exception:
            pass

        self.close()
        self._cleanup_stale_locks()
        is_headless = False if force_headed else self.headless

        self.playwright = sync_playwright().start()
        
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--start-maximized",
            "--disable-background-mode",
            "--disable-background-networking"
        ]

        # Browser channel selection: msedge (Microsoft Edge), chrome (Google Chrome), or default chromium
        b_type = str(self.config.get("browser_type", "chrome")).strip().lower()
        channel = None
        user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        if b_type in ["msedge", "edge", "microsoft-edge", "microsoft edge"]:
            channel = "msedge"
            user_agent = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
            )
            print("[BrowserManager] Using Microsoft Edge browser channel.")
        elif b_type in ["chrome", "google-chrome", "google chrome"]:
            channel = "chrome"
            print("[BrowserManager] Using Google Chrome browser channel.")
        else:
            print("[BrowserManager] Using default Chromium browser channel.")

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=is_headless,
            channel=channel,
            no_viewport=True,
            args=args,
            accept_downloads=True,
            user_agent=user_agent,
            permissions=['clipboard-read', 'clipboard-write']
        )

        if len(self.context.pages) > 0:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        try:
            self.page.set_viewport_size({"width": 1366, "height": 900})
        except Exception:
            pass

        # Inject saved cookies from In-App browser if present
        cookies_file = os.path.join(self.profile_dir, "cookies.json")
        if os.path.exists(cookies_file):
            try:
                import json
                with open(cookies_file, "r", encoding="utf-8") as f:
                    c_list = json.load(f)
                    if c_list and isinstance(c_list, list):
                        sanitized_cookies = []
                        for c in c_list:
                            clean_c = dict(c)
                            exp = clean_c.get("expires")
                            if exp is not None:
                                try:
                                    exp_num = float(exp)
                                    if exp_num > 1e11:
                                        exp_num = exp_num / 1000.0
                                    clean_c["expires"] = int(exp_num)
                                except Exception:
                                    clean_c.pop("expires", None)
                            sanitized_cookies.append(clean_c)
                        self.context.add_cookies(sanitized_cookies)
                        print(f"[BrowserManager] Injected {len(sanitized_cookies)} cookies from cookies.json.")
            except Exception as e:
                print(f"[BrowserManager] Warning loading cookies.json: {e}")

        # Set standard timeout
        self.page.set_default_timeout(45000)
        return self.page

    def check_login_status(self) -> bool:
        """
        Navigates to Meta Business Suite to check if session is logged in.
        """
        page = self.launch()
        try:
            print("[BrowserManager] Checking Facebook login status...")
            page.goto("https://business.facebook.com/latest/home", wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            current_url = page.url.lower()
            # If redirected to login page
            if "login" in current_url or "checkpoint" in current_url:
                print("[BrowserManager] User is NOT logged in.")
                return False

            # Check if Meta Business Suite home elements exist
            content = page.content()
            if "business.facebook.com" in current_url and ("login" not in current_url):
                print("[BrowserManager] User is authenticated in Meta Business Suite!")
                return True

            return False
        except Exception as e:
            print(f"[BrowserManager] Error checking login status: {e}")
            return False

    def check_active_page_info(self, target_page_name: str = "", target_page_id: str = "") -> Dict[str, Any]:
        """
        Launches browser and queries Meta Business Suite to determine
        what Facebook Page is currently active, who is logged in, and whether it matches target.
        """
        page = self.launch()
        try:
            url = f"https://business.facebook.com/latest/home?asset_id={target_page_id}" if target_page_id else "https://business.facebook.com/latest/home"
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            from core.uploader import inspect_active_page
            info = inspect_active_page(page)

            # Check c_user
            cookies = self.context.cookies()
            c_user = next((c.get("value") for c in cookies if c.get("name") == "c_user"), "")
            info["c_user"] = c_user

            is_logged_in = "login" not in page.url.lower() and "checkpoint" not in page.url.lower()
            info["is_logged_in"] = is_logged_in

            # Check match
            match = False
            if is_logged_in:
                if target_page_id and (f"asset_id={target_page_id}" in page.url or info.get("page_id") == target_page_id):
                    match = True
                elif target_page_name:
                    clean_target = target_page_name.replace("ซี่รีย์", "ซีรีส์").replace(" ", "").lower()
                    clean_detected = info.get("page_name", "").replace("ซี่รีย์", "ซีรีส์").replace(" ", "").lower()
                    clean_title = info.get("title", "").replace("ซี่รีย์", "ซีรีส์").replace(" ", "").lower()
                    if clean_target in clean_detected or clean_target in clean_title:
                        match = True

            info["match"] = match
            return info
        except Exception as e:
            return {
                "error": str(e),
                "is_logged_in": False,
                "match": False,
                "page_name": "",
                "page_id": "",
                "c_user": ""
            }

    def open_for_manual_login(self, callback_message=None):
        """
        Opens a visible browser window allowing the user to manually log in to Facebook/Meta.
        """
        print("[BrowserManager] Opening browser for manual login. Please log in to your account...")
        page = self.launch(force_headed=True)
        page.goto("https://business.facebook.com/latest/home", wait_until="domcontentloaded")
        
        if callback_message:
            callback_message("ກະລຸນາ Login ເຂົ້າສູ່ລະບົບ Facebook / Meta Business Suite ໃນ Browser ທີ່ເປີດຂຶ້ນມາ...")

        # Keep browser open until closed by user or navigation to business suite completes
        return page

    def close(self):
        """Closes browser context and Playwright instance cleanly."""
        try:
            if self.context:
                self.context.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            print(f"[BrowserManager] Error closing browser: {e}")
        finally:
            self.context = None
            self.page = None
            self.playwright = None
