import os
import sys
import time
import json
import random
import urllib.request
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

# Set UTF-8 encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from playwright.sync_api import sync_playwright

# Profile directory for persistent Google Account login
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_DIR = os.environ.get(
    "GEMINI_WEB_PROFILE",
    str(Path(os.environ.get("USERPROFILE", "C:/Users/kee_n")) / ".gemini" / "gemini_web_profile")
)

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser"
]

def get_chrome_executable() -> Optional[str]:
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    return None


def get_thai_font(size: int = 24):
    fonts = [
        r"C:\Windows\Fonts\leelawdb.ttf",
        r"C:\Windows\Fonts\LeelaUIb.ttf",
        r"C:\Windows\Fonts\tahomabd.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf",
        "/usr/share/fonts/truetype/tlwg/Garuda-Bold.ttf"
    ]
    for f in fonts:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def add_cinema_badge(image_path: str, badge_text: str = "เต็มเรื่อง") -> str:
    """Adds signature red pill badge '▶ เต็มเรื่อง' at top right of poster."""
    try:
        im = Image.open(image_path).convert("RGB")
        w, h = im.size
        draw = ImageDraw.Draw(im)

        scale = w / 720.0
        bw = int(190 * scale)
        bh = int(48 * scale)
        r = int(14 * scale)
        bx = w - bw - int(30 * scale)
        by = int(50 * scale)

        # Drop shadow
        draw.rounded_rectangle([(bx + 2, by + 3), (bx + bw + 2, by + bh + 3)], radius=r, fill=(0, 0, 0))
        # Red Pill Badge
        draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=r, fill=(229, 9, 20), outline=(255, 255, 255), width=max(2, int(2 * scale)))

        # Play triangle
        px = bx + int(18 * scale)
        py = by + int(14 * scale)
        draw.polygon([(px, py), (px + int(15 * scale), py + int(10 * scale)), (px, py + int(20 * scale))], fill=(255, 255, 255))

        # Thai Text
        font = get_thai_font(int(24 * scale))
        draw.text((px + int(24 * scale), by + int(8 * scale)), badge_text, font=font, fill=(255, 255, 255))

        im.save(image_path, "JPEG", quality=95)
        print(f"[Gemini Web Poster] 🏷️ Added cinema badge '{badge_text}' to poster.")
    except Exception as e:
        print(f"[Gemini Web Poster] Badge note: {e}")
    return image_path


class GeminiWebPoster:
    def __init__(self, profile_dir: Optional[str] = None):
        self.profile_dir = profile_dir or DEFAULT_PROFILE_DIR
        os.makedirs(self.profile_dir, exist_ok=True)
        self.chrome_exe = get_chrome_executable()

    def launch_browser(self, p, headless: bool = False):
        """Launches Chrome or bundled Chromium with anti-detection args and persistent profile."""
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--start-maximized"
        ]
        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                executable_path=self.chrome_exe,
                headless=headless,
                viewport=None if not headless else {"width": 1280, "height": 900},
                args=launch_args
            )
        except Exception as e:
            print(f"[Gemini Web Poster] Note on Chrome launch: {e}, falling back to bundled Chromium...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=self.profile_dir,
                headless=headless,
                viewport=None if not headless else {"width": 1280, "height": 900},
                args=launch_args
            )
        context.add_init_script("delete Object.getPrototypeOf(navigator).webdriver")
        return context

    def interactive_login(self, default_email: str = "mahaxok.83@gmail.com"):
        """
        Opens a visible Chrome window for the user to log in to Google (mahaxok.83@gmail.com).
        Waits until the user reaches Gemini home screen.
        """
        print("=" * 65)
        print("🌐 GEMINI WEB ONE-TIME GOOGLE LOGIN")
        print(f"📁 Profile Directory: {self.profile_dir}")
        print(f"📧 Target Account   : {default_email}")
        print("=" * 65)
        print("🚀 ກຳລັງເປີດ Browser Chrome...")

        with sync_playwright() as p:
            context = self.launch_browser(p, headless=False)
            page = context.pages[0] if context.pages else context.new_page()

            # Go directly to Google Login with redirect back to Gemini
            login_url = "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fgemini.google.com%2Fapp"
            print(f"🌐 ກຳລັງເປີດໜ້າຈໍ Login Google: {login_url}")
            page.goto(login_url, timeout=60000)
            time.sleep(2)

            # Auto-fill email if on email screen
            try:
                email_input = page.locator('input[type="email"]').first
                if email_input.is_visible(timeout=4000):
                    email_input.fill(default_email)
                    time.sleep(1)
                    page.keyboard.press("Enter")
                    print(f"✅ ປ້ອນອີເມວ {default_email} ຮຽບຮ້ອຍ.")
            except Exception as e:
                print(f"ℹ️ Note email input: {e}")

            print("\n" + "=" * 65)
            print("👉 ກະລຸນາໃສ່ Password ແລະ ຢືນຢັນ 2FA ໃນໜ້າຕ່າງ Chrome ທີ່ເປີດຂຶ້ນມານີ້...")
            print("=" * 65 + "\n")

            try:
                input("👉 ເມື່ອທ່ານໃສ່ Password ແລະ ເຂົ້າສູ່ໜ້າ Gemini ສຳເລັດແລ້ວ, ກະລຸນາກົດ [Enter] ຢູ່ປ່ອງນີ້ເພື່ອບັນທຶກ Session: ")
            except Exception:
                # If non-interactive, wait for actual Gemini domain
                while True:
                    if page.url.startswith("https://gemini.google.com") and not page.url.startswith("https://accounts.google.com"):
                        time.sleep(3)
                        break
                    time.sleep(2)

            print("\n🎉 ສຸດຍອດ! Login ເຂົ້າ Gemini ດ້ວຍບັນຊີ Google ສຳເລັດຮຽບຮ້ອຍແລ້ວ!")
            print(f"💾 Session ຖືກບັນທຶກໄວ້ໃນ: {self.profile_dir}")
            time.sleep(2)
            context.close()
            print("✅ ປິດ Browser ຮຽບຮ້ອຍ. ຕອນນີ້ Bot ພ້ອມສັ່ງສ້າງ Poster ອັດຕະໂນມັດແລ້ວ!")

    def generate_poster(
        self,
        drama_title: str,
        output_path: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        add_pillow_badge: bool = False,
        headless: bool = False
    ) -> Optional[str]:
        """
        Navigates to gemini.google.com/app, asks Gemini to generate an 8K 9:16 movie poster,
        downloads the generated image, and returns local file path.
        """
        clean_title = drama_title.strip()
        if not clean_title:
            clean_title = "ซีรีส์จีนยอดฮิต"

        if not output_path:
            out_dir = BASE_DIR / "data" / "thumbnails"
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / f"gemini_poster_{int(time.time())}_{random.randint(100, 999)}.jpg")

        # Build high-impact Hollywood Drama Poster prompt with badge embedded directly
        if custom_prompt:
            prompt = custom_prompt
        else:
            prompt = (
                f"Generate a cinematic high-end vertical 9:16 movie poster for a Chinese drama: '{clean_title}'. "
                f"In the top right corner, an official bright red pill badge with a white play triangle icon and clear white bold text 'เต็มเรื่อง'. "
                f"In the center is a handsome Chinese CEO male lead in an expensive luxury black suit and tie, "
                f"next to a gorgeous elegant female lead in a glamorous red silk dress. "
                f"In the background: luxury modern city skyline at night with glowing skyscrapers, luxury Rolls Royce car, "
                f"and a helicopter flying in the sky. Floating banknotes and golden embers in the air. "
                f"At the bottom, a massive glowing 3D fiery title banner with explosive lightning sparks reading '{clean_title}', "
                f"intense cinematic rim lighting, 8k resolution, dramatic blockbuster look, vertical aspect ratio 9:16."
            )

        print(f"[Gemini Web Poster] 🎨 Requesting 9:16 poster from gemini.google.com for: '{clean_title}'")

        with sync_playwright() as p:
            context = self.launch_browser(p, headless=headless)
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto("https://gemini.google.com/app", timeout=60000)
                time.sleep(3)

                # Verify login status
                if "accounts.google.com" in page.url or page.locator('a:has-text("Sign in"), button:has-text("Sign in")').first.is_visible(timeout=2000):
                    print("❌ Error: ຍັງບໍ່ໄດ້ Login ເຂົ້າ Google Account! ກະລຸນາຣັນດ້ວຍຄຳສັ່ງ login_gemini.bat ກ່ອນ.")
                    context.close()
                    return None

                # Click "New chat" to have a clean generation session
                new_chat_btn = page.locator('button[aria-label*="New chat"], button[aria-label*="แชทใหม่"]').first
                if new_chat_btn.is_visible(timeout=3000):
                    try:
                        new_chat_btn.click()
                        time.sleep(2)
                    except Exception:
                        pass

                # Locate Prompt Textbox and type via keyboard
                input_box = page.locator('div.ql-editor[contenteditable="true"], rich-textarea, div[role="textbox"]').first
                input_box.wait_for(state="visible", timeout=20000)
                input_box.click()
                time.sleep(1)

                # Type prompt cleanly into rich-textarea
                page.keyboard.insert_text(prompt)
                time.sleep(1)

                # Send prompt
                send_btn = page.locator('button[aria-label="Send message"]').or_(
                    page.locator('button[aria-label="ส่งข้อความ"]')
                ).or_(
                    page.locator('button.send-button')
                ).or_(
                    page.locator('button[mattooltip="Send message"]')
                ).first

                if send_btn.is_visible(timeout=2000):
                    send_btn.click()
                else:
                    page.keyboard.press("Enter")

                print("[Gemini Web Poster] ⏳ ສົ່ງ Prompt ແລ້ວ, ກຳລັງລໍຖ້າ Gemini ສ້າງຮູບ Poster (ປະມານ 15-30 ວິນາທີ)...")

                chat_img_selector = 'img.image.animate, img[src*="/gg/"], img[alt*="AI"], img[alt*="ສ້າງໂດຍ AI"], .image-container img'
                target_img = page.locator(chat_img_selector).last

                saved = False
                try:
                    print("[Gemini Web Poster] ⏳ ກຳລັງລໍຖ້າຮູບພາບທີ່ Gemini ສ້າງ...")
                    target_img.wait_for(state="visible", timeout=90000)
                    time.sleep(2)
                    # Method A: Direct Canvas Extraction (Instant, no CSP / network issues)
                    try:
                        print(f"[Gemini Web Poster] 📥 ກຳລັງດຶງຮູບພາບຜ່ານ Canvas Render...")
                        b64_data = page.evaluate("""() => {
                            const sel = 'img.image.animate, img[src*="/gg/"], img[src*="blob:"], .image-container img';
                            const imgs = document.querySelectorAll(sel);
                            if (!imgs || imgs.length === 0) return null;
                            const img = imgs[imgs.length - 1];
                            const canvas = document.createElement('canvas');
                            canvas.width = img.naturalWidth || img.width || 1280;
                            canvas.height = img.naturalHeight || img.height || 720;
                            const ctx = canvas.getContext('2d');
                            ctx.drawImage(img, 0, 0);
                            return canvas.toDataURL('image/jpeg', 0.98);
                        }""")
                        if b64_data and "base64," in b64_data:
                            import base64
                            raw_b64 = b64_data.split("base64,")[1]
                            img_bytes = base64.b64decode(raw_b64)
                            if len(img_bytes) > 10000:
                                with open(output_path, "wb") as f_out:
                                    f_out.write(img_bytes)
                                print(f"[Gemini Web Poster] 📥 ບັນທຶກຮູບພາບຜ່ານ Canvas ສຳເລັດ ({len(img_bytes)} bytes): {output_path}")
                                saved = True
                    except Exception as ex_canvas:
                        print(f"[Gemini Web Poster] Canvas extraction note: {ex_canvas}")

                    # Method B: Direct Element Screenshot
                    if not saved:
                        try:
                            if target_img.is_visible():
                                target_img.screenshot(path=output_path)
                                if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                                    print(f"[Gemini Web Poster] 📸 ບັນທຶກຜ່ານ Element Screenshot ສຳເລັດ: {output_path}")
                                    saved = True
                        except Exception as ex_ss:
                            print(f"[Gemini Web Poster] Screenshot note: {ex_ss}")

                    # Method C: HTTP Session Request if src is http
                    if not saved:
                        src = target_img.get_attribute("src")
                        if src and src.startswith("http"):
                            hd_src = src.split("=s")[0] + "=s2048" if "=s" in src else src
                            resp = context.request.get(hd_src)
                            if resp.status == 200 and len(resp.body()) > 10000:
                                with open(output_path, "wb") as f_out:
                                    f_out.write(resp.body())
                                print(f"[Gemini Web Poster] 📥 ດາວໂຫຼດຮູບຜ່ານ HTTP Session ສຳເລັດ: {output_path}")
                                saved = True

                except Exception as ex_fetch:
                    print(f"[Gemini Web Poster] Image extraction general note: {ex_fetch}")

                if not saved:
                    # Method D: Fallback download button
                    try:
                        download_btn = page.locator(
                            'button[aria-label*="Download"], button[aria-label*="ດາວໂຫລດ"], button[aria-label*="ດາວໂຫຼດ"], button[aria-label*="ดาวน์โหลด"]'
                        ).last
                        if download_btn.is_visible(timeout=2000):
                            with page.expect_download(timeout=8000) as dl_info:
                                download_btn.click(force=True)
                            dl = dl_info.value
                            dl.save_as(output_path)
                            print(f"[Gemini Web Poster] 📥 ດາວໂຫຼດຜ່ານປຸ່ມດາວໂຫຼດສຳເລັດ: {output_path}")
                            saved = True
                    except Exception as ex_btn:
                        print(f"[Gemini Web Poster] Button download note: {ex_btn}")

                if saved and os.path.exists(output_path):
                    if add_pillow_badge:
                        add_cinema_badge(output_path, badge_text="เต็มเรื่อง")
                    print(f"🎉 ສ້າງ Poster ສຳເລັດສົມບູນ: {output_path}")
                    context.close()
                    return output_path
                else:
                    print("❌ ບໍ່ພົບຮູບພາບທີ່ Gemini ສ້າງອອກມາ.")

            except Exception as e:
                print(f"❌ ເກີດຂໍ້ຜິດພາດໃນການສ້າງຮູບຜ່ານ Gemini Web: {e}")
                try:
                    page.screenshot(path=str(BASE_DIR / "logs" / "screenshots" / f"gemini_web_error_{int(time.time())}.png"))
                except Exception:
                    pass

            context.close()
        return None


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gemini Web Poster Generator")
    parser.add_argument("--login", action="store_true", help="Launch browser for Google Account login")
    parser.add_argument("--email", type=str, default="mahaxok.83@gmail.com", help="Google Email")
    parser.add_argument("--title", type=str, default="คุณชายถูกทิ้งกลับมา ขยี้ทุกคำเยาะเย้ย!", help="Drama title")
    parser.add_argument("--headful", action="store_true", help="Run browser visibly")
    args = parser.parse_args()

    bot = GeminiWebPoster()
    if args.login:
        bot.interactive_login(default_email=args.email)
    else:
        out = bot.generate_poster(drama_title=args.title, headless=not args.headful)
        if out:
            print(f"RESULT: {out}")
        else:
            print("FAILED")
