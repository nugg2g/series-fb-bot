import os
import time
import random
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List
from playwright.sync_api import Page
from PIL import Image, ImageDraw, ImageFont

class CtaPoster:
    """
    Handles automated posting of Follower Invitation (CTA) photos to Meta Business Suite.
    Helps Facebook creators fulfill weekly creator goals (~5 posts/week) and gain page followers.
    """
    POST_COMPOSER_URL = "https://business.facebook.com/latest/composer"

    def __init__(self, config: Dict[str, Any], log_cb: Optional[Callable[[str], None]] = None, progress_cb: Optional[Callable[[int, str], None]] = None):
        self.config = config
        self.log_cb = log_cb or print
        self.progress_cb = progress_cb
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.images_dir = os.path.abspath(os.path.join(project_root, "cta_images"))
        os.makedirs(self.images_dir, exist_ok=True)
        self.ensure_default_cta_images()

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_cb(f"[{timestamp}] [CTA Poster] {msg}")

    def emit_progress(self, percent: int, text: str):
        if self.progress_cb:
            try:
                self.progress_cb(max(0, min(100, int(percent))), text)
            except Exception:
                pass

    def ensure_default_cta_images(self):
        """Generates high quality default follower CTA banners if folder is empty"""
        existing = [f for f in os.listdir(self.images_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        if existing:
            return

        # Generate 3 distinct attractive 1080x1080 CTA banners
        themes = [
            {
                "filename": "cta_banner_gold_cinema.jpg",
                "bg_color": (18, 18, 28),
                "accent_color": (250, 179, 135),
                "title": "ซีรีส์จีน เต็มเรื่อง",
                "subtitle": "กดติดตามเพจ เพื่อไม่พลาดเรื่องใหม่ๆ!",
                "badge": "🔥 รวมหนังสั้นจีน AI ครบรส อัปเดตทุกวัน ✨"
            },
            {
                "filename": "cta_banner_neon_blue.jpg",
                "bg_color": (15, 23, 42),
                "accent_color": (56, 189, 248),
                "title": "คอหนังสั้นจีน ห้ามพลาด!",
                "subtitle": "กด Like & Follow เพจนี้ไว้เลย",
                "badge": "🎬 ดราม่าเข้มข้น พากย์ไทย/ซับไทย ดูฟรีเต็มเรื่อง!"
            },
            {
                "filename": "cta_banner_purple_drama.jpg",
                "bg_color": (26, 16, 45),
                "accent_color": (192, 132, 252),
                "title": "ติดตามเพื่อรับชมคลิปใหม่ก่อนใคร",
                "subtitle": "อย่าลืมกดกระดิ่งแจ้งเตือนไว้นะครับ",
                "badge": "🌟 ซีรีส์สั้นยอดนิยม สนุกจนหยุดดูไม่ได้!"
            }
        ]

        for th in themes:
            try:
                img = Image.new("RGB", (1080, 1080), color=th["bg_color"])
                draw = ImageDraw.Draw(img)

                # Draw decorative gradient borders and card background
                draw.rectangle([40, 40, 1040, 1040], outline=th["accent_color"], width=4)
                draw.rectangle([70, 70, 1010, 1010], fill=(th["bg_color"][0] + 10, th["bg_color"][1] + 10, th["bg_color"][2] + 15))

                # Use basic font with fallback sizes
                try:
                    font_title = ImageFont.truetype("tahoma.ttf", 62)
                    font_sub = ImageFont.truetype("tahoma.ttf", 40)
                    font_badge = ImageFont.truetype("tahoma.ttf", 32)
                except Exception:
                    font_title = ImageFont.load_default()
                    font_sub = font_title
                    font_badge = font_title

                # Draw texts centered
                draw.text((540, 340), th["title"], fill=(255, 255, 255), font=font_title, anchor="mm")
                draw.text((540, 470), th["subtitle"], fill=th["accent_color"], font=font_sub, anchor="mm")
                
                # Badge pill
                draw.rounded_rectangle([180, 600, 900, 700], radius=25, fill=(45, 55, 72))
                draw.text((540, 650), th["badge"], fill=(255, 255, 255), font=font_badge, anchor="mm")

                # Follow CTA Button mockup at bottom
                draw.rounded_rectangle([320, 790, 760, 890], radius=50, fill=th["accent_color"])
                draw.text((540, 840), "👉 กดติดตาม (FOLLOW) 👈", fill=(17, 17, 27), font=font_sub, anchor="mm")

                out_path = os.path.join(self.images_dir, th["filename"])
                img.save(out_path, quality=92)
            except Exception as e:
                print(f"[CtaPoster] Warning creating default banner: {e}")

    def get_random_cta_image(self) -> Optional[str]:
        """Returns path to a random CTA image from cta_images directory"""
        files = [
            os.path.join(self.images_dir, f)
            for f in os.listdir(self.images_dir)
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
        ]
        if not files:
            self.ensure_default_cta_images()
            files = [
                os.path.join(self.images_dir, f)
                for f in os.listdir(self.images_dir)
                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
            ]
        return random.choice(files) if files else None

    def generate_cta_caption(self, page_name: str) -> str:
        """Builds an engaging follower invitation caption with Thai hashtags"""
        p_name = page_name or self.config.get("page_name", "ซีรีส์จีน เต็มเรื่อง")
        
        # Check if Gemini AI caption generation is enabled
        ai_cfg = self.config.get("ai_caption", {})
        if ai_cfg.get("enabled", False) and ai_cfg.get("api_key"):
            try:
                from google import genai
                client = genai.Client(api_key=ai_cfg.get("api_key").split(",")[0].strip())
                model = ai_cfg.get("model", "gemini-2.5-flash")
                prompt = (
                    f"Create a short, viral, exciting Facebook Page follower invitation post in Thai language for the Facebook Page '{p_name}'. "
                    f"The page posts AI Chinese mini-series and drama full movies. "
                    f"Include high-energy emojis, a clear Call-to-Action asking viewers to follow the page, and 5-8 trending hashtags. "
                    f"Keep it concise (around 4-6 lines)."
                )
                res = client.models.generate_content(model=model, contents=prompt)
                if res and res.text:
                    return res.text.strip()
            except Exception as e:
                self.log(f"AI caption fallback to curated template: {e}")

        # High converting curated templates pool
        templates = [
            (
                f"🎬 รวมซีรีส์จีนสุดมันส์ สนุก ครบรส เต็มเรื่องจบ! ✨\n\n"
                f"ใครชอบดูหนังสั้นจีน ซีรีส์จีนสนุกๆ อย่าลืมกด 'ติดตาม' (Follow) เพจ {p_name} ไว้นะครับ!\n"
                f"📌 มีเรื่องใหม่ๆ พากย์ไทยและซับไทย มาเสิร์ฟให้รับชมฟรีทุกวัน ห้ามพลาดเด็ดขาด! 🔥\n\n"
                f"#ซีรีส์จีน #หนังสั้นจีน #chinaai #ซีรีส์สั้น #ละครสั้น #ติดตามเพจ"
            ),
            (
                f"✨ คอซีรีส์จีน AI ดราม่าเข้มข้น ห้ามพลาด! ✨\n\n"
                f"กด Like & Follow เพจ {p_name} เพื่อเป็นกำลังใจให้ทีมงานด้วยนะครับ 🙏\n"
                f"อัปเดตเรื่องใหม่สุดเข้มข้นแบบเต็มเรื่องจบทุกวัน กดกระดิ่งแจ้งเตือนไว้เลย! 🔔\n\n"
                f"#หนังสั้นจีน #ซีรีส์จีน #ละครสั้น #chinesedrama #reelsdrama"
            ),
            (
                f"🔥 รวมความสนุกแบบเต็มเรื่องจบ อยู่ที่นี่แล้ว! 🔥\n\n"
                f"ฝากกดติดตามเพจ {p_name} กันด้วยนะครับ จะได้ไม่พลาดคลิปสนุกๆ ใหม่ๆ ที่อัปเดตทุกวัน!\n"
                f"ขอบคุณทุกการติดตามและรับชมนะครับ ✨🎬\n\n"
                f"#ซีรีส์จีนเต็มเรื่อง #หนังสั้นจีน #ละครสั้นจีน #chinaai"
            )
        ]
        return random.choice(templates)

    def post_cta_photo(
        self,
        page: Page,
        image_path: str,
        caption: str,
        target_page: Optional[Dict[str, str]] = None,
        schedule_time: Optional[datetime] = None
    ) -> bool:
        """
        Automates creating and publishing an image post on Meta Business Suite.
        """
        if not os.path.exists(image_path):
            self.log(f"❌ ไม่พบไฟล์รูปภาพ CTA: {image_path}")
            return False

        t_page = target_page or {}
        page_id = str(t_page.get("page_id") or self.config.get("page_id", "")).strip()
        page_name = str(t_page.get("page_name") or self.config.get("page_name", "")).strip()

        self.log(f"📸 เริ่มต้นการโพสต์รูปภาพชวนคนกดติดตามเพจไปยัง: '{page_name}' (ID: {page_id})...")
        self.emit_progress(10, f"กำลังเปิดหน้า Composer โพสต์รูปภาพ ({page_name})...")

        try:
            # 1. Navigate to Composer
            if page_id:
                url = f"{self.POST_COMPOSER_URL}?asset_id={page_id}"
            else:
                url = self.POST_COMPOSER_URL

            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)

            # 2. Strict Page Verification
            from core.uploader import ReelsUploader
            uploader = ReelsUploader(page, self.config, log_cb=self.log_cb, progress_cb=self.progress_cb)
            uploader.dismiss_popups()

            if page_name or page_id:
                page_ok = uploader.verify_and_select_target_page(page_name, page_id)
                if not page_ok:
                    raise Exception(f"ความปลอดภัย: Facebook Page ใน Composer ไม่ตรงกับ '{page_name}'! ยกเลิกการโพสต์รูปภาพเพื่อป้องกันผลกระทบ")

            self.emit_progress(25, f"กำลังเลือกรูปภาพ CTA: {os.path.basename(image_path)}...")

            # 3. Add Photo / File Upload
            file_input = page.locator('input[type="file"][accept*="image"], input[type="file"]').first
            if file_input.count() > 0:
                file_input.set_input_files(image_path)
                self.log("📁 ส่งไฟล์รูปภาพเข้า file input สำเร็จ.")
            else:
                add_photo_btn = page.get_by_text("เพิ่มรูปภาพ", exact=True).or_(
                    page.get_by_text("Add photo", exact=True)
                ).or_(
                    page.get_by_text("เพิ่มรูปภาพ/วิดีโอ", exact=True)
                ).first
                if add_photo_btn.is_visible(timeout=5000):
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        add_photo_btn.click()
                    fc_info.value.set_files(image_path)
                    self.log("📁 ส่งรูปภาพผ่าน File Chooser สำเร็จ.")
                else:
                    raise Exception("ไม่พบช่องทางอัปโหลดรูปภาพในหน้า Meta Business Suite Composer")

            time.sleep(3)
            uploader.dismiss_popups()

            # 4. Input Caption
            self.emit_progress(50, "กำลังป้อนข้อความเชิญชวนกดติดตามเพจ...")
            uploader.input_caption(caption)
            time.sleep(2)

            # 5. Handle Schedule or Publish Now
            is_schedule = (self.config.get("post_mode") == "schedule" and schedule_time is not None)
            if is_schedule:
                self.emit_progress(75, f"กำลังตั้งเวลาโพสต์รูปภาพ: {schedule_time.strftime('%Y-%m-%d %H:%M')}...")
                uploader.set_schedule(schedule_time)

            # 6. Click Publish / Schedule button
            self.emit_progress(85, "กำลังคลิกปุ่มเผยแพร่โพสต์รูปภาพ...")
            uploader.wait_and_click_publish(is_schedule=is_schedule, max_wait_seconds=120)

            # 7. Wait for completion
            self.emit_progress(95, "รอการยืนยันการโพสต์จาก Facebook...")
            success = uploader.wait_for_publish_complete(timeout_seconds=90)
            if success:
                self.emit_progress(100, "โพสต์รูปภาพเชิญชวนติดตามสำเร็จเรียบร้อย! 🎉")
                self.log(f"🎉 โพสต์รูปภาพชวนคนกดติดตามเพจ '{page_name}' สำเร็จเรียบร้อย!")
                return True
            else:
                self.log(f"⚠️ ไม่ได้รับการยืนยันการโพสต์รูปภาพจาก Facebook.")
                return False

        except Exception as e:
            self.log(f"❌ เกิดข้อผิดพลาดในการโพสต์รูปภาพ CTA: {e}")
            return False
