import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Tuple
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

class ReelsUploader:
    """
    Automates uploading Reels via Meta Business Suite Reels Composer.
    Handles video selection, caption typing, page verification, and publishing/scheduling.
    """
    REELS_COMPOSER_URL = "https://business.facebook.com/latest/reels_composer"
    POST_COMPOSER_URL = "https://business.facebook.com/latest/composer"

    def __init__(self, page: Page, config: Dict[str, Any], log_cb: Optional[Callable[[str], None]] = None, progress_cb: Optional[Callable[[int, str], None]] = None, browser_mgr=None):
        self.page = page
        self.config = config
        self.log_cb = log_cb or print
        self.progress_cb = progress_cb
        self.browser_mgr = browser_mgr
        self.screenshot_dir = os.path.abspath("./logs/screenshots")
        os.makedirs(self.screenshot_dir, exist_ok=True)

    def ensure_active_page(self) -> Page:
        """Ensures self.page is alive and responsive before any browser interaction."""
        is_alive = False
        try:
            if self.page and not self.page.is_closed():
                self.page.evaluate("1 + 1")
                is_alive = True
        except Exception:
            is_alive = False

        if not is_alive:
            self.log("🔄 Browser page ຖືກປິດ ຫຼື ຫຼຸດການເຊື່ອມຕໍ່, ກຳລັງເຊື່ອມຕໍ່ໃໝ່ອັດຕະໂນມັດ...")
            if hasattr(self, 'browser_mgr') and self.browser_mgr:
                self.page = self.browser_mgr.get_active_page()
            elif self.page and hasattr(self.page, 'context') and self.page.context and not self.page.context.is_closed():
                try:
                    for p in self.page.context.pages:
                        if not p.is_closed():
                            self.page = p
                            return self.page
                    self.page = self.page.context.new_page()
                except Exception:
                    pass
        return self.page

    def emit_progress(self, percent: int, text: str):
        if self.progress_cb:
            try:
                self.progress_cb(max(0, min(100, int(percent))), text)
            except Exception:
                pass

    def log(self, message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        self.log_cb(formatted)

    def save_screenshot(self, name: str):
        try:
            filename = f"{name}_{int(time.time())}.png"
            path = os.path.join(self.screenshot_dir, filename)
            self.page.screenshot(path=path)
            self.log(f"Saved screenshot: {path}")
            return path
        except Exception as e:
            self.log(f"Warning: Could not save screenshot: {e}")
            return None

    def dismiss_popups(self):
        """Dismisses any random guide, banner or onboarding popups in Meta Business Suite safely"""
        try:
            close_selectors = [
                'div[role="banner"] button[aria-label*="close" i]',
                'div[role="banner"] div[aria-label*="close" i]',
                'div[role="dialog"] div[aria-label="Close"]',
                'div[role="dialog"] div[aria-label="ปิด"]',
                'div[role="dialog"] div[aria-label="ປິດ"]',
                'button:has-text("ไม่ใช่ตอนนี้")',
                'button:has-text("Not now")',
                'button:has-text("ບໍ່ແມ່ນຕອນນີ້")',
                'div[role="button"]:has-text("รับทราบ")',
                'div[role="button"]:has-text("Got it")',
                'div[role="button"]:has-text("ຮັບຊາບ")'
            ]
            for sel in close_selectors:
                el = self.page.locator(sel).first
                if el.is_visible(timeout=500):
                    el.click()
                    time.sleep(1)
        except Exception:
            pass

    def upload_reel(self, video_path: str, caption: str, schedule_time: Optional[datetime] = None, target_page: Optional[Dict[str, str]] = None) -> bool:
        """
        Uploads a single video to Meta Business Suite as a Reel.
        
        :param video_path: Absolute path to the video file
        :param caption: The full caption text including hashtags
        :param schedule_time: Optional datetime to schedule the post
        :param target_page: Optional specific target page dict {"page_name": ..., "page_id": ...}
        :return: True if successful, False otherwise
        """
        if not os.path.exists(video_path):
            self.log(f"❌ ไม่พบไฟล์วิดีโอ: {video_path}")
            return False

        filename = os.path.basename(video_path)
        self.log(f"🚀 เริ่มต้นขั้นตอนอัปโหลด: {filename}")

        t_page = target_page or {}
        page_id = str(t_page.get("page_id") or self.config.get("page_id", "")).strip()
        target_page_name = str(t_page.get("page_name") or self.config.get("page_name", "")).strip()

        try:
            self.ensure_active_page()
            self.emit_progress(5, f"ເລີ່ມຕົ້ນອັບໂຫຼດ: {filename}")

            # 1. Navigate to Reels Composer (using asset_id if available)
            if page_id:
                target_url = f"{self.REELS_COMPOSER_URL}?asset_id={page_id}"
                self.log(f"🌐 ກຳລັງເປີດ Meta Business Suite Reels Composer ສຳລັບ Page: '{target_page_name}' (ID: {page_id})...")
            else:
                target_url = self.REELS_COMPOSER_URL
                self.log("🌐 ກຳລັງເປີດ Meta Business Suite Reels Composer...")

            self.emit_progress(10, f"ກຳລັງເປີດ Reels Composer ({target_page_name or 'Meta Business Suite'})...")
            self.page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            self.dismiss_popups()

            # Check if redirected to login
            curr_url_lower = self.page.url.lower()
            if "login" in curr_url_lower or "checkpoint" in curr_url_lower:
                self.log("⚠️ ຍັງບໍ່ໄດ້ Login ເຂົ້າສູ່ລະບົບ Facebook! ກະລຸນາ Login ກ່ອນ.")
                self.emit_progress(0, "ຍັງບໍ່ໄດ້ Login Facebook (ກະລຸນາ Login)")
                return False

            # 2. Strict Page Verification & Safety Lock
            if target_page_name or page_id:
                self.emit_progress(15, f"ກວດສອບຄວາມປອດໄພຂອງ Page: '{target_page_name}'...")
                page_ok = self.verify_and_select_target_page(target_page_name, page_id)
                if not page_ok:
                    self.emit_progress(0, f"🚨 ຢຸດເຮັດວຽກ: ກວດພົບ Page ບໍ່ກົງກັບ '{target_page_name}'")
                    raise Exception(f"ຄວາມປອດໄພຂັ້ນສູງ: Facebook Page ໃນ Composer ບໍ່ກົງກັບເປົ້າໝາຍ '{target_page_name}' (ID: {page_id})! ລະບົບຍົກເລີກການອັບໂຫຼດທັນທີເພື່ອປົກປ້ອງ Page ຂອງບໍລິສັດ.")

            # 3. Upload the video file
            self.emit_progress(20, f"ກຳລັງສົ່ງໄຟລ໌ວິດີໂອ {filename} ເຂົ້າສູ່ລະບົບ...")
            self.log("📤 ກຳລັງເລືອກໄຟລ໌ວິດີໂອເຂົ້າສູ່ລະບົບ...")
            add_btn = self.page.get_by_text("เพิ่มวิดีโอ", exact=True).or_(
                self.page.get_by_text("Add Video", exact=True)
            ).or_(
                self.page.get_by_text("ເພີ່ມວິດີໂອ", exact=True)
            ).first

            if add_btn.is_visible(timeout=5000):
                with self.page.expect_file_chooser(timeout=15000) as fc_info:
                    add_btn.click()
                fc_info.value.set_files(video_path)
                self.log("📁 ສົ່ງໄຟລ໌ວິດີໂອເຂົ້າ File Chooser ສຳເລັດ.")
            else:
                # Fallback to direct input
                file_input = self.page.locator('input[type="file"]').first
                if file_input.count() > 0:
                    file_input.set_input_files(video_path)
                    self.log("📁 ສົ່ງໄຟລ໌ວິດີໂອເຂົ້າ input[type=file] ສຳເລັດ.")
                else:
                    raise Exception("ບໍ່ພົບປຸ່ມ 'Add Video' / 'ເພີ່ມວິດີໂອ' ໃນໜ້າເວັບ")

            time.sleep(3)
            self.dismiss_popups()

            # 4. Fill in Caption / Description
            self.emit_progress(25, f"ກຳລັງປ້ອນ Title & Caption...")
            self.log("✍️ ກຳລັງປ້ອນ Caption ແລະ Tags...")
            self.input_caption(caption)
            time.sleep(2)

            # 5. Wait for video upload to reach completion (100%)
            # Calculate dynamic timeout: min 600s (10 min), +1s per MB for large files (>300MB)
            try:
                v_size_mb = os.path.getsize(video_path) / (1024 * 1024)
                dynamic_timeout = max(600, int(v_size_mb * 1.5))
            except Exception:
                dynamic_timeout = 600

            self.emit_progress(30, f"ກຳລັງອັບໂຫຼດວິດີໂອຂຶ້ນ Meta Business Suite (ຂະໜາດ {v_size_mb:.1f} MB, timeout {dynamic_timeout}s)...")
            upload_ok = self.wait_for_video_ready(max_wait_seconds=dynamic_timeout)
            if not upload_ok:
                self.log("⚠️ ການອັບໂຫຼດອາດໃຊ້ເວລາດົນ ແຕ່ຈະລອງກົດຖັດໄປ...")

            # Check and enable AI-generated content label in Step 1 if requested
            if self.config.get("mark_as_ai_content", True):
                self.enable_ai_content_label()

            # 6. Click Next through Steps
            # Step 1 -> Step 2 (Edit)
            self.emit_progress(88, "ກົດຖັດໄປ (ຂັ້ນຕອນທີ 1: ສ້າງ -> ແກ້ໄຂ)...")
            self.log("➡️ ກົດຖັດໄປ (ຂັ້ນຕອນທີ 1: ສ້າງ -> ແກ້ໄຂ)...")
            self.click_next_button()
            time.sleep(4)
            self.dismiss_popups()

            # Step 2 -> Step 3 (Publish / Share options)
            self.emit_progress(92, "ກົດຖັດໄປ (ຂັ້ນຕອນທີ 2: ແກ້ໄຂ -> ເຜີຍແຜ່)...")
            self.log("➡️ ກົດຖັດໄປ (ຂັ້ນຕອນທີ 2: ແກ້ໄຂ -> ເຜີຍແຜ່)...")
            self.click_next_button()
            time.sleep(4)
            self.dismiss_popups()

            # Check and enable AI-generated content label in Step 3 if requested
            if self.config.get("mark_as_ai_content", True):
                self.enable_ai_content_label()

            # 7. Step 3: Publish or Schedule
            mode = self.config.get("post_mode", "now")
            is_schedule = (mode == "schedule" and schedule_time is not None)
            if is_schedule:
                self.emit_progress(94, f"ກຳລັງຕັ້ງເວລາ Schedule: {schedule_time.strftime('%Y-%m-%d %H:%M')}")
                self.log(f"⏰ ກຳລັງຕັ້ງເວລາ Schedule: {schedule_time.strftime('%Y-%m-%d %H:%M')}")
                self.set_schedule(schedule_time)

            # Wait for upload 100% and button to be fully enabled before clicking publish
            self.emit_progress(96, "ກຳລັງກົດປຸ່ມ Publish / Schedule...")
            self.wait_and_click_publish(is_schedule=is_schedule, max_wait_seconds=600)

            # 8. Wait for completion confirmation
            self.emit_progress(98, "ລໍຖ້າການຢືນຢັນການໂພສຈາກ Facebook...")
            self.log("⏳ ລໍຖ້າການຢືນຢັນການໂພສຈາກ Facebook...")
            success = self.wait_for_publish_complete(timeout_seconds=120)
            if success:
                self.emit_progress(100, f"ອັບໂຫຼດ Reel ສຳເລັດຮຽບຮ້ອຍ: {filename} 🎉")
                self.log(f"🎉 ອັບໂຫຼດ Reel ສຳເລັດຮຽບຮ້ອຍ: {filename}")
                return True
            else:
                self.emit_progress(0, f"❌ Facebook ບໍ່ຢືນຢັນການໂພສ: {filename}")
                self.log(f"❌ ບໍ່ໄດ້ຮັບການຢືນຢັນການໂພສຈາກ Facebook (ອັບໂຫຼດບໍ່ສຳເລັດ): {filename}")
                self.save_screenshot(f"failed_confirm_{os.path.splitext(filename)[0]}")
                return False

        except Exception as e:
            self.emit_progress(0, f"❌ ເກີດຂໍ້ຜິດພາດ: {str(e)[:40]}")
            self.log(f"❌ ເກີດຂໍ້ຜິດພາດໃນການອັບໂຫຼດ {filename}: {e}")
            self.save_screenshot(f"error_{os.path.splitext(filename)[0]}")
            return False

    def upload_photo(self, image_path: str, caption: str, schedule_time: Optional[datetime] = None, target_page: Optional[Dict[str, str]] = None) -> bool:
        """
        Uploads an image post via Meta Business Suite standard post composer.
        
        :param image_path: Absolute path to the image file (.jpg, .png, .webp, etc.)
        :param caption: The full caption text
        :param schedule_time: Optional datetime to schedule
        :param target_page: Optional specific target page dict {"page_name": ..., "page_id": ...}
        :return: True if successful, False otherwise
        """
        image_path = os.path.normpath(os.path.abspath(image_path))
        if not os.path.exists(image_path):
            self.log(f"❌ ບໍ່ພົບໄຟລ໌ຮູບພາບ: {image_path}")
            return False

        filename = os.path.basename(image_path)
        self.log(f"📸 ເລີ່ມຕົ້ນຂັ້ນຕອນໂພສຮູບພາບ: {filename}")

        t_page = target_page or {}
        page_id = str(t_page.get("page_id") or self.config.get("page_id", "")).strip()
        target_page_name = str(t_page.get("page_name") or self.config.get("page_name", "")).strip()

        try:
            self.ensure_active_page()
            self.emit_progress(5, f"ເລີ່ມຕົ້ນໂພສຮູບພາບ: {filename}")

            # 1. Navigate to Composer (using asset_id if available)
            if page_id:
                target_url = f"{self.POST_COMPOSER_URL}?asset_id={page_id}"
                self.log(f"🌐 ກຳລັງເປີດ Meta Business Suite Composer ສຳລັບ Page: '{target_page_name}' (ID: {page_id})...")
            else:
                target_url = self.POST_COMPOSER_URL
                self.log("🌐 ກຳລັງເປີດ Meta Business Suite Composer...")

            self.emit_progress(10, f"ກຳລັງເປີດ Composer ({target_page_name or 'Meta Business Suite'})...")
            self.page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(4)
            self.dismiss_popups()

            # 2. Strict Page Guard
            if target_page_name or page_id:
                self.emit_progress(20, f"ກວດສອບ Page: {target_page_name}...")
                page_ok = self.verify_and_select_target_page(target_page_name, page_id)
                if not page_ok:
                    raise Exception(f"Facebook Page ບໍ່ກົງກັບ '{target_page_name}'! ຍົກເລີກການໂພສເພື່ອຄວາມປອດໄພ")

            # 3. Add Photo / File Upload
            self.emit_progress(35, f"ກຳລັງອັບໂຫຼດໄຟລ໌ຮູບພາບ: {filename}...")
            file_input = self.page.locator('input[type="file"][accept*="image"], input[type="file"]').first
            uploaded_via_input = False
            if file_input.count() > 0:
                try:
                    file_input.set_input_files(image_path)
                    self.log("📁 ສົ່ງໄຟລ໌ຮູບພາບເຂົ້າ file input ສຳເລັດ.")
                    uploaded_via_input = True
                except Exception:
                    pass

            if not uploaded_via_input:
                add_photo_btn = (
                    self.page.locator('div[role="button"]:has-text("Add photo"), button:has-text("Add photo"), div:has-text("Add photo/video")').last.or_(
                        self.page.get_by_text("เพิ่มรูปภาพ", exact=False)
                    ).or_(
                        self.page.get_by_text("ເພີ່ມຮູບ", exact=False)
                    ).first
                )
                if add_photo_btn.is_visible(timeout=7000):
                    try:
                        with self.page.expect_file_chooser(timeout=8000) as fc_info:
                            add_photo_btn.click()
                        fc_info.value.set_files(image_path)
                        self.log("📁 ສົ່ງຮູບພາບຜ່ານ File Chooser ສຳເລັດ.")
                    except Exception as ex_fc:
                        file_input = self.page.locator('input[type="file"]').first
                        if file_input.count() > 0:
                            file_input.set_input_files(image_path)
                            self.log("📁 ສົ່ງໄຟລ໌ຮູບພາບເຂົ້າ file input ຫຼັງກົດປຸ່ມສຳເລັດ.")
                        else:
                            raise Exception(f"ບໍ່ສາມາດເລືອກໄຟລ໌ຮູບພາບໄດ້: {ex_fc}")
                else:
                    raise Exception("ບໍ່ພົບຊ່ອງທາງອັບໂຫຼດຮູບພາບໃນ Meta Business Suite Composer")

            time.sleep(4)
            self.dismiss_popups()

            # 4. Input Caption
            self.emit_progress(55, "ກຳລັງປ້ອນຂໍ້ຄວາມ Caption...")
            self.input_caption(caption)
            time.sleep(2)

            # Verification screenshot showing both photo and caption in composer
            self.save_screenshot(f"ready_to_publish_{os.path.splitext(filename)[0]}")

            # 5. Handle Schedule or Publish Now
            is_schedule = (self.config.get("post_mode") == "schedule" and schedule_time is not None)
            if is_schedule:
                self.emit_progress(75, f"ກຳລັງຕັ້ງເວລາໂພສຮູບພາບ: {schedule_time.strftime('%Y-%m-%d %H:%M')}...")
                self.set_schedule(schedule_time)

            # 6. Click Publish / Schedule button
            self.emit_progress(85, "ກຳລັງກົດປຸ່ມເຜີຍແຜ່ / Publish...")
            self.wait_and_click_publish(is_schedule=is_schedule, max_wait_seconds=120)

            # 7. Wait for completion confirmation
            self.emit_progress(95, "ລໍຖ້າການຢືນຢັນຈາກ Facebook...")
            confirmed = self.wait_for_publish_complete(timeout_seconds=120)

            if confirmed:
                self.emit_progress(100, f"✅ ໂພສຮູບພາບສຳເລັດ: {filename}")
                self.log(f"✅ ໂພສຮູບພາບ {filename} ສຳເລັດຮຽບຮ້ອຍ!")
                return True
            else:
                self.emit_progress(0, f"❌ Facebook ບໍ່ຢືນຢັນການໂພສ: {filename}")
                self.log(f"❌ ບໍ່ໄດ້ຮັບການຢືນຢັນການໂພສຈາກ Facebook (ອັບໂຫຼດບໍ່ສຳເລັດ): {filename}")
                self.save_screenshot(f"failed_confirm_{os.path.splitext(filename)[0]}")
                return False

        except Exception as e:
            self.emit_progress(0, f"❌ ເກີດຂໍ້ຜິດພາດ: {str(e)[:40]}")
            self.log(f"❌ ເກີດຂໍ້ຜິດພາດໃນການໂພສຮູບພາບ {filename}: {e}")
            self.save_screenshot(f"error_{os.path.splitext(filename)[0]}")
            return False

    def verify_and_select_target_page(self, page_name: str, page_id: str = "") -> bool:
        """
        Strictly verifies that the Reels Composer is active on the expected Facebook Page.
        If a mismatch is detected (e.g. stale session or company page active), attempts to
        switch to the correct page via Meta Business Suite Page Switcher dropdown.
        If verification fails, strictly HALTS execution to protect company/personal accounts!
        """
        self.log(f"🛡️ [Strict Page Guard] ກວດສອບຄວາມຖືກຕ້ອງຂອງ Facebook Page: '{page_name}' (ID: {page_id})...")

        clean_target = page_name.replace("ซี่รีย์", "ซีรีส์").replace(" ", "").lower() if page_name else ""
        
        # Support alias matching for Page 3 (ID: 104640754387216 - สถานีซีรีย์ / ສະຫະພັນບານເຕະແຂວງສະຫວັນນະເຂດ)
        target_aliases = [clean_target] if clean_target else []
        if str(page_id).strip() == "104640754387216" or "สถานีซีรีย์" in page_name or "สถานีซีรีส์" in page_name or "ສະຫະພັນ" in page_name:
            for alias in ["สถานีซีรีย์", "สถานีซีรีส์", "ສະຫະພັນ", "savannakhet"]:
                clean_al = alias.replace("ซี่รีย์", "ซีรีส์").replace(" ", "").lower()
                if clean_al not in target_aliases:
                    target_aliases.append(clean_al)

        def check_dom_page_match() -> Tuple[bool, str]:
            try:
                texts = self.page.evaluate("""() => {
                    let results = [];
                    let selectors = [
                        'div[aria-label*="Profile"]',
                        'div[aria-label*="โปรไฟล์"]',
                        'div[aria-label*="ບັນຊີ"]',
                        'div[aria-label*="Page"]',
                        'div[aria-label*="เพจ"]',
                        'div[role="navigation"]',
                        'div[role="banner"]',
                        'div[role="combobox"]',
                        'div[aria-haspopup="menu"]'
                    ];
                    for (let s of selectors) {
                        let elements = document.querySelectorAll(s);
                        elements.forEach(el => {
                            let t = (el.innerText || '').trim();
                            if (t && t.length > 2 && t.length < 100) results.push(t);
                        });
                    }
                    document.querySelectorAll('span, div[role="button"], h1, h2').forEach(el => {
                        let t = (el.innerText || '').trim();
                        if (t && t.length > 3 && t.length < 80) results.push(t);
                    });
                    return results;
                }""")
                for a in target_aliases:
                    for t in texts:
                        clean_t = t.replace("ซี่รีย์", "ซีรีส์").replace(" ", "").lower()
                        if a in clean_t or clean_t in a:
                            return True, t
            except Exception as e:
                self.log(f"Notice inspecting DOM: {e}")
            return False, ""

        # Check 1: Direct inspection
        for attempt in range(3):
            matched, detected_text = check_dom_page_match()
            if matched:
                self.log(f"✅ ຢືນຢັນ Facebook Page ເທິງໜ້າຈໍຖືກຕ້ອງ: '{detected_text}'")
                return True
            time.sleep(1.5)

        # Check 2: Try switching page via Meta Business Suite Dropdown
        self.log(f"🔄 ບໍ່ພົບຊື່ '{page_name}' ໃນໜ້າທຳອິດ, ກຳລັງລອງກວດສອບ Page Switcher Dropdown...")
        try:
            switcher_selectors = [
                'div[aria-label*="Select a business or account"]',
                'div[aria-label*="เลือกธุรกิจหรือบัญชี"]',
                'div[aria-label*="ເລືອກທຸລະກິດ"]',
                'div[aria-label*="เลือกเพจ"]',
                'div[aria-label*="Select page"]',
                'div[role="combobox"]',
                'div[aria-haspopup="menu"]'
            ]
            for sel in switcher_selectors:
                el = self.page.locator(sel).first
                if el.is_visible(timeout=1000):
                    el.click()
                    time.sleep(2)
                    self.log("📋 ເປີດເມນູເລືອກ Page ແລ້ວ, ກຳລັງຄົ້ນຫາຊື່ Page ເປົ້າໝາຍ...")
                    # Look for page name or aliases inside the opened menu
                    switcher_candidates = [page_name]
                    if str(page_id).strip() == "104640754387216" or "สถานีซีรีย์" in page_name or "ສະຫະພັນ" in page_name:
                        switcher_candidates.extend(["สถานีซีรีย์", "สถานีซีรีส์", "ສະຫະພັນ", "Savannakhet"])

                    for cand in switcher_candidates:
                        target_item = self.page.locator(f'div[role="menuitem"]:has-text("{cand}"), div[role="option"]:has-text("{cand}"), span:has-text("{cand}")').first
                        if target_item.is_visible(timeout=1500):
                            target_item.click()
                            time.sleep(4)
                            self.log(f"✅ ກົດສະຫຼັບໄປຫາ Page '{cand}' ສຳເລັດ!")
                            break
                    break
        except Exception as e:
            self.log(f"Notice attempting page switcher: {e}")

        # Check 3: Final confirmation pass
        matched, detected_text = check_dom_page_match()
        if matched:
            self.log(f"✅ ຢືນຢັນ Facebook Page ເທິງໜ້າຈໍຖືກຕ້ອງຫຼັງສະຫຼັບ: '{detected_text}'")
            return True

        # Fallback check: asset_id in URL
        curr_url = self.page.url
        if page_id and f"asset_id={page_id}" in curr_url:
            self.log(f"✅ ຢືນຢັນຜ່ານ asset_id={page_id} ໃນ URL ຮຽບຮ້ອຍ.")
            return True

        # STRICT HALT! Protect company pages!
        self.log(f"🚨 [ຄວາມປອດໄພສູງສຸດ] ບໍ່ສາມາດຢືນຢັນວ່າໜ້າຈໍປັດຈຸບັນແມ່ນ Page '{page_name}' (ID: {page_id})!")
        self.log(f"🛑 ລະບົບຍົກເລີກການອັບໂຫຼດທັນທີ (Abort) ເພື່ອປ້ອງກັນການໂພສຜິດ Page ຂອງບໍລິສັດ 100%!")
        self.save_screenshot(f"page_mismatch_guard_{page_id or 'unknown'}")
        return False

    def find_active_caption_editor(self):
        """
        Finds the true, visible contenteditable editor in Meta Business Suite Composer / Reels Composer.
        Bypasses invisible/unmounted clones that Meta places at (0, 0) with width 0.
        """
        selectors = [
            'div[contenteditable="true"][aria-label*="dialogue"]',
            'div[contenteditable="true"][aria-label*="Describe your reel"]',
            'div[contenteditable="true"][aria-label*="caption" i]',
            'div[contenteditable="true"][aria-label*="คำอธิบาย"]',
            'div[contenteditable="true"][aria-label*="ຄຳອະທິບາຍ"]',
            'div[role="combobox"][contenteditable="true"]',
            'div[role="textbox"][contenteditable="true"]',
            'div[contenteditable="true"]',
            '[data-lexical-editor="true"]',
            'textarea'
        ]
        for sel in selectors:
            loc = self.page.locator(sel)
            cnt = loc.count()
            for i in range(cnt):
                el = loc.nth(i)
                try:
                    if el.is_visible(timeout=500):
                        box = el.bounding_box()
                        if box and box['width'] > 50 and box['height'] > 15:
                            return el
                except Exception:
                    pass
        return None

    def input_caption(self, caption: str):
        """
        Finds caption box and enters the text with full title, story, and hashtags.
        Ensures both Reels Composer and Standard Post Composer receive full caption,
        story, emojis, and hashtags without losing React/Lexical/Draft state.
        """
        if not caption:
            return

        first_line = caption.strip().split("\n")[0] if caption else ""

        # Grant clipboard permissions if possible
        try:
            if hasattr(self.page, 'context') and self.page.context:
                self.page.context.grant_permissions(['clipboard-read', 'clipboard-write'])
        except Exception:
            pass

        for attempt in range(3):
            editor = self.find_active_caption_editor()
            if not editor and attempt < 2:
                time.sleep(1.5)
                continue

            if not editor:
                self.log("⚠️ ບໍ່ພົບຊ່ອງປ້ອນ Caption ທີ່ເປີດຢູ່ (Visible Caption Editor)")
                return

            try:
                editor.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass

            time.sleep(0.5)
            editor.click()
            time.sleep(0.5)

            # Clear existing text cleanly
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            time.sleep(0.2)

            # Insert text line-by-line via keyboard.insert_text (safest for Draft.js & Lexical)
            lines = caption.split("\n")
            for i, line in enumerate(lines):
                if line:
                    self.page.keyboard.insert_text(line)
                if i < len(lines) - 1:
                    self.page.keyboard.press("Shift+Enter")
                    time.sleep(0.04)

            time.sleep(1)
            # Dismiss any hashtag autocomplete popup with Space
            self.page.keyboard.press("Space")
            time.sleep(0.5)

            final_text = editor.inner_text() or ""
            if first_line and first_line in final_text:
                preview = final_text.replace('\n', ' ')[:70]
                self.log(f"✍️ ປ້ອນ Caption ສຳເລັດ ({len(final_text)} ຕົວອັກສອນ): {preview}...")
                return
            elif len(final_text) > 10:
                self.log(f"✍️ ປ້ອນ Caption ສຳເລັດ ({len(final_text)} ຕົວອັກສອນ)")
                return

        self.log("⚠️ ບໍ່ສາມາດຢືນຢັນ Caption ໃນ Editor ໄດ້ຄົບຖ້ວນ")

        raise Exception("ไม่พบช่องใส่ Caption/Description")

    def wait_for_video_ready(self, max_wait_seconds: int = 300) -> bool:
        """Waits until the video reaches 100% upload and Next button is active"""
        self.log("⏳ กำลังรอให้วิดีโออัปโหลดขึ้นระบบเรียบร้อย 100%...")
        start = time.time()
        last_logged_pct = None
        while time.time() - start < max_wait_seconds:
            progress = self.page.evaluate("""() => {
                let el = Array.from(document.querySelectorAll('*')).find(e => e.innerText && /^\\d{1,3}%$/.test(e.innerText.trim()));
                return el ? el.innerText.trim() : null;
            }""")
            if progress and progress != last_logged_pct:
                self.log(f"📊 ความคืบหน้าการอัปโหลด: {progress}")
                last_logged_pct = progress
                try:
                    p_num = int(progress.replace("%", "").strip())
                    mapped_pct = int(30 + (p_num * 0.55))
                    self.emit_progress(mapped_pct, f"ກຳລັງອັບໂຫຼດວິດີໂອ: {p_num}% (ຂຶ້ນລະບົບ Facebook)...")
                except Exception:
                    pass

            next_btn = self.get_next_button()
            if next_btn and next_btn.is_visible():
                is_disabled = next_btn.evaluate("""el => {
                    let curr = el;
                    while (curr && curr !== document.body) {
                        if (curr.getAttribute('aria-disabled') === 'true' || curr.hasAttribute('disabled')) {
                            return true;
                        }
                        curr = curr.parentElement;
                    }
                    return false;
                }""")
                if not is_disabled:
                    self.emit_progress(85, "ວິດີໂອອັບໂຫຼດຄົບ 100%! ປຸ່ມ 'ຖັດໄປ' ພ້ອມເຮັດວຽກ.")
                    self.log("✅ วิดีโออัปโหลดขึ้นระบบเรียบร้อย 100%! ปุ่ม 'ถัดไป' พร้อมใช้งาน.")
                    return True

            time.sleep(2)

        self.log("⚠️ หมดเวลารอวิดีโอ (300 วินาที) จะลองดำเนินการต่อ...")
        return False

    def get_next_button(self):
        btn = self.page.get_by_text("ถัดไป", exact=True).or_(
            self.page.get_by_text("Next", exact=True)
        ).or_(
            self.page.get_by_text("ຖັດໄປ", exact=True)
        ).last
        if btn.is_visible(timeout=1000):
            return btn

        next_selectors = [
            'div[role="button"]:has-text("ถัดไป")',
            'div[role="button"]:has-text("Next")',
            'div[role="button"]:has-text("ຖັດໄປ")',
            'button:has-text("Next")'
        ]
        for sel in next_selectors:
            b = self.page.locator(sel).last
            if b.is_visible(timeout=500):
                return b
        return None

    def click_next_button(self):
        btn = self.get_next_button()
        if btn:
            for _ in range(15):
                is_disabled = btn.evaluate("""el => {
                    let curr = el;
                    while (curr && curr !== document.body) {
                        if (curr.getAttribute('aria-disabled') === 'true' || curr.hasAttribute('disabled')) {
                            return true;
                        }
                        curr = curr.parentElement;
                    }
                    return false;
                }""")
                if not is_disabled:
                    break
                time.sleep(1)

            clicked = False
            try:
                btn.click(timeout=5000)
                clicked = True
            except Exception:
                try:
                    btn.click(force=True, timeout=5000)
                    clicked = True
                except Exception:
                    try:
                        btn.evaluate("el => el.click()")
                        clicked = True
                    except Exception:
                        pass
            time.sleep(2)
        else:
            raise Exception("ไม่พบปุ่ม 'Next' / 'ถัดไป'")

    def set_schedule(self, target_time: datetime):
        """Selects schedule radio/button and inputs date/time"""
        try:
            sched_btn = self.page.get_by_text("กำหนดเวลา", exact=True).or_(
                self.page.get_by_text("Schedule", exact=True)
            ).or_(
                self.page.get_by_text("ຕັ້ງເວລາ", exact=True)
            ).first
            if sched_btn.is_visible(timeout=2000):
                sched_btn.click()
                time.sleep(1)
                self.log(f"⏰ เลือกโหมด Schedule: {target_time.strftime('%Y-%m-%d %H:%M')}")
        except Exception as e:
            self.log(f"Warning setting schedule: {e}. Defaulting to Publish Now.")

    def get_publish_button(self):
        """
        Locates the exact, clickable submit button (Publish / แชร์ / เผยแพร่ / โพสต์)
        prioritizing actionable button and role=button elements in the bottom toolbar.
        """
        # 1. Primary selectors targeting interactive button elements
        publish_selectors = [
            'button[type="submit"]:has-text("Publish")',
            'button[type="submit"]:has-text("เผยแพร่")',
            'button[type="submit"]:has-text("แชร์")',
            'button[type="submit"]:has-text("โพสต์")',
            'div[role="button"]:has-text("Publish"):not(:has-text("later"))',
            'button:has-text("Publish"):not(:has-text("later"))',
            'div[role="button"]:has-text("เผยแพร่")',
            'button:has-text("เผยแพร่")',
            'div[role="button"]:has-text("แชร์")',
            'button:has-text("แชร์")',
            'div[role="button"]:has-text("โพสต์")',
            'button:has-text("โพสต์")',
            'div[role="button"]:has-text("ແບ່ງປັນ")',
            'button:has-text("ແບ່ງປັນ")',
            'div[role="button"]:has-text("Share")',
            'button:has-text("Share")'
        ]
        for sel in publish_selectors:
            try:
                btn = self.page.locator(sel).last
                if btn.is_visible(timeout=300):
                    return btn
            except Exception:
                pass

        # 2. Text locator with ancestor lookup
        publish_btn = self.page.get_by_text("แชร์", exact=True).or_(
            self.page.get_by_text("โพสต์", exact=True)
        ).or_(
            self.page.get_by_text("เผยแพร่", exact=True)
        ).or_(
            self.page.get_by_text("Publish", exact=True)
        ).or_(
            self.page.get_by_text("Share", exact=True)
        ).or_(
            self.page.get_by_text("ແບ່ງປັນ", exact=True)
        ).last
        if publish_btn.is_visible(timeout=500):
            try:
                parent_btn = publish_btn.locator('xpath=ancestor-or-self::*[@role="button" or self::button]').last
                if parent_btn.is_visible(timeout=300):
                    return parent_btn
            except Exception:
                pass
            return publish_btn

        return None

    def get_schedule_button(self):
        sched_selectors = [
            'div[role="button"]:has-text("กำหนดเวลา")',
            'div[role="button"]:has-text("Schedule")',
            'div[role="button"]:has-text("ຕັ້ງເວລາ")',
            'button:has-text("กำหนดเวลา")',
            'button:has-text("Schedule")',
            'button:has-text("ຕັ້ງເວລາ")'
        ]
        for sel in sched_selectors:
            try:
                btn = self.page.locator(sel).last
                if btn.is_visible(timeout=300):
                    return btn
            except Exception:
                pass

        schedule_btn = self.page.get_by_text("กำหนดเวลา", exact=True).or_(
            self.page.get_by_text("Schedule", exact=True)
        ).or_(
            self.page.get_by_text("ຕັ້ງເວລາ", exact=True)
        ).or_(
            self.page.get_by_text("แชร์", exact=True)
        ).or_(
            self.page.get_by_text("ແບ່ງປັນ", exact=True)
        ).last
        if schedule_btn.is_visible(timeout=500):
            try:
                parent_btn = schedule_btn.locator('xpath=ancestor-or-self::*[@role="button" or self::button]').last
                if parent_btn.is_visible(timeout=300):
                    return parent_btn
            except Exception:
                pass
            return schedule_btn

        return self.get_publish_button()

    def is_element_disabled(self, locator) -> bool:
        if not locator:
            return True
        try:
            return locator.evaluate("""el => {
                let curr = el;
                while (curr && curr !== document.body) {
                    if (curr.getAttribute('aria-disabled') === 'true' || curr.hasAttribute('disabled') || curr.classList.contains('disabled')) {
                        return true;
                    }
                    curr = curr.parentElement;
                }
                return false;
            }""")
        except Exception:
            return False

    def wait_and_click_publish(self, is_schedule: bool = False, max_wait_seconds: int = 600) -> bool:
        """
        Waits until the upload has finished and the Share / Schedule button is truly enabled.
        Prevents submitting premature uploads while still uploading in the background.
        """
        btn_name = "Schedule (กำหนดเวลา)" if is_schedule else "แชร์ (Publish)"
        self.log(f"⏳ กำลังรอให้สื่ออัปโหลดขึ้นระบบครบ 100% และปุ่ม '{btn_name}' พร้อมทำงาน...")
        start = time.time()
        last_pct = None

        while time.time() - start < max_wait_seconds:
            # Check for upload progress percentage in page
            progress = self.page.evaluate("""() => {
                let el = Array.from(document.querySelectorAll('*')).find(e => e.innerText && /^\\d{1,3}%$/.test(e.innerText.trim()));
                return el ? el.innerText.trim() : null;
            }""")
            if progress and progress != last_pct:
                self.log(f"📊 ความคืบหน้าการอัปโหลดไฟล์: {progress}")
                last_pct = progress

            btn = self.get_schedule_button() if is_schedule else self.get_publish_button()
            if btn and btn.is_visible():
                disabled = self.is_element_disabled(btn)
                if not disabled:
                    self.log(f"✅ สื่ออัปโหลดเสร็จสมบูรณ์ 100%! ปุ่ม '{btn_name}' พร้อมใช้งานแล้ว.")
                    time.sleep(1)
                    self.dismiss_popups()

                    clicked = False
                    try:
                        btn.scroll_into_view_if_needed(timeout=2000)
                    except Exception:
                        pass

                    try:
                        btn.click(timeout=5000)
                        clicked = True
                    except Exception as e_click:
                        self.log(f"Notice: Normal click on '{btn_name}' intercepted ({e_click}), trying force click...")
                        try:
                            btn.click(force=True, timeout=5000)
                            clicked = True
                        except Exception as e_force:
                            self.log(f"Notice: Force click failed ({e_force}), falling back to JavaScript click...")

                    # ALWAYS also trigger native browser events in JS to guarantee React handles the submission
                    try:
                        btn.evaluate("""el => {
                            let target = el.closest('button, div[role="button"]') || el;
                            target.focus();
                            ['mouseover', 'mousedown', 'mouseup', 'click'].forEach(evt => {
                                target.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                            });
                        }""")
                        clicked = True
                    except Exception:
                        pass

                    if clicked:
                        self.log(f"🚀 กดปุ่ม '{btn_name}' เรียบร้อยแล้ว.")
                        return True
                else:
                    if int(time.time() - start) % 15 == 0:
                        pct_msg = f" ({progress})" if progress else ""
                        self.log(f"⏳ สื่อกำลังประมวลผลบนเซิร์ฟเวอร์{pct_msg}... รอให้ปุ่ม '{btn_name}' ปลดล็อค")

            time.sleep(2)

        raise Exception(f"หมดเวลารอ (Timeout 600s): ปุ่ม '{btn_name}' ยังคงถูกปิดใช้งาน (Disabled)")

    def wait_for_publish_complete(self, timeout_seconds: int = 120) -> bool:
        """
        Waits strictly after clicking publish/share button.
        Requires genuine confirmation from Facebook before declaring success.
        - Checks for URL navigation away from reels_composer
        - Checks for post-publish dialog specifically inside div[role="dialog"]
        - Immediately catches and logs any error alert
        """
        self.log("⏳ กำลังติดตามการยืนยันการโพสต์จาก Facebook...")
        time.sleep(4)
        start = time.time()
        last_retry_click = time.time()

        while time.time() - start < timeout_seconds:
            # Retry click after 14s if Publish button is still sitting enabled on screen
            if time.time() - last_retry_click > 14:
                last_retry_click = time.time()
                try:
                    p_btn = self.get_publish_button()
                    if p_btn and p_btn.is_visible() and not self.is_element_disabled(p_btn):
                        self.log("🔄 ປຸ່ມ Publish ຍັງຄົງເປີດຢູ່ (ຍັງບໍ່ທັນໄປ), ກຳລັງກົດຊ້ຳອີກຄັ້ງ (Retry Click)...")
                        try:
                            p_btn.click(force=True, timeout=3000)
                        except Exception:
                            pass
                        try:
                            p_btn.evaluate("""el => {
                                let target = el.closest('button, div[role="button"]') || el;
                                target.click();
                            }""")
                        except Exception:
                            pass
                except Exception:
                    pass

            # 1. Check for error alerts or toast messages
            error_msg = self.page.evaluate("""() => {
                let alert = document.querySelector('div[role="alert"], div[aria-label*="Error" i], div[aria-label*="ข้อผิดพลาด" i]');
                if (alert && alert.innerText && alert.innerText.length > 3) {
                    return alert.innerText.trim();
                }
                let errText = Array.from(document.querySelectorAll('div, span, p')).find(e => {
                    let t = e.innerText || '';
                    return (t.includes('เกิดข้อผิดพลาด') || t.includes('Something went wrong') || t.includes('ไม่สามารถเผยแพร่') || t.includes('ບໍ່ສາມາດເຜີຍແຜ່')) && t.length < 120;
                });
                return errText ? errText.innerText.trim() : null;
            }""")
            if error_msg:
                self.log(f"❌ Facebook แจ้งเตือนข้อผิดพลาด: {error_msg}")
                self.save_screenshot("publish_error_alert")
                return False

            # 2. Check if URL redirected away from composer to content management, planner, or home
            curr_url = self.page.url.lower()
            is_composer_url = ("reels_composer" in curr_url or "composer" in curr_url)
            if ("content_management" in curr_url or "planner" in curr_url or "home" in curr_url or "published_posts" in curr_url or "all_posts" in curr_url) and not ("reels_composer" in curr_url or curr_url.endswith("/composer")):
                self.log(f"🎉 ໜ້າເວັບປ່ຽນໄປທີ່: {curr_url} (ຢືນຢັນການໂພສສຳເລັດ ແລະ ປິດໜ້າ Composer ຮຽບຮ້ອຍ)")
                self.save_screenshot("publish_success_redirect")
                return True

            # 3. Check for specific post-publish dialog that pops up after sharing
            dialog_res = self.page.evaluate("""() => {
                let dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
                for (let d of dialogs) {
                    let t = d.innerText || '';
                    if (t.includes('Reel processing') || t.includes('Reels processing') || 
                        t.includes('กำลังประมวลผล') || t.includes('กําลังประมวลผล') ||
                        t.includes('โพสต์คลิปรีลของคุณแล้ว') || t.includes('แชร์คลิปรีลแล้ว') ||
                        t.includes('Your reel is being processed') || t.includes('Your reel has been published') ||
                        t.includes('ໂພສ Reel ແລ້ວ') || t.includes('ແບ່ງປັນ Reel ແລ້ວ') ||
                        t.includes('Try creating a reel from the video you just published') ||
                        t.includes('Reel scheduled') || t.includes('กำหนดเวลาคลิปรีลแล้ว') ||
                        t.includes('โพสต์ของคุณแล้ว') || t.includes('แชร์โพสต์แล้ว') ||
                        t.includes('Your post has been published') || t.includes('Post published') ||
                        t.includes('Your post is published') || t.includes('Post is published') ||
                        t.includes('Your post is live') ||
                        t.includes('Post scheduled') || t.includes('กำหนดเวลาโพสต์แล้ว') ||
                        t.includes('ໂພສຮູບພາບແລ້ວ') || t.includes('ໂພສແລ້ວ')) {
                        return t;
                    }
                }
                return null;
            }""")
            if dialog_res:
                self.log(f"🎉 ພົບ Dialog ຢືນຢັນການເຜີຍແຜ່ຈາກ Facebook (ໂພສສຳເລັດ!): {dialog_res[:60]}...")
                # Dismiss recommendation dialog if present
                for sel in ['button:has-text("ไม่ใช่ตอนนี้")', 'button:has-text("ບໍ່ແມ່ນຕອນນີ້")', 'button:has-text("Not now")', 'button:has-text("Done")', 'button:has-text("เรียบร้อย")', 'div[role="dialog"] button[aria-label="Close"]']:
                    try:
                        b = self.page.locator(sel).first
                        if b.is_visible(timeout=500):
                            b.click()
                            break
                    except Exception:
                        pass
                self.save_screenshot("publish_success_dialog")
                return True

            # 4. Check if the composer form has closed / vanished from the screen
            is_composer_open = self.page.evaluate("""() => {
                let composer = document.querySelector('div[aria-label*="reel" i], div[aria-label*="รีล" i], div[aria-label*="ຣີລ" i], div[aria-label*="post" i], div[aria-label*="โพสต์" i], form');
                if (!composer) return false;
                let text = composer.innerText || '';
                return text.includes('Caption') || text.includes('คำอธิบาย') || text.includes('ຄຳອະທິບາຍ') || text.includes('What\\'s on your mind') || text.includes('คุณกำลังคิดอะไรอยู่');
            }""")
            if not is_composer_open and int(time.time() - start) > 8:
                self.log("🎉 ໜ້າຕ່າງ Composer ປິດຕົວລົງຮຽບຮ້ອຍ (ຢືນຢັນການໂພສສຳເລັດ)")
                self.save_screenshot("publish_success_closed")
                return True

            time.sleep(2)

        self.log("❌ หมดเวลารอการยืนยัน (Timeout 120s): หน้าต่าง Reels Composer ยังคงเปิดค้างอยู่ ไม่ได้รับการยืนยันการโพสต์จาก Facebook")
        self.save_screenshot("publish_timeout_stuck")
        return False

    def enable_ai_content_label(self):
        """
        Detects and enables the 'AI-generated content' / 'Made with AI' (เนื้อหา AI) label in Meta Business Suite.
        Supports multi-lingual selectors (Thai, Lao, English) and confirmation modals.
        """
        try:
            self.log("🤖 กำลังตรวจสอบและติ๊กเลือก 'เนื้อหา AI' (AI-generated / Made with AI)...")
            
            # Step A: Expand any "More options" or "Show more" or "Advanced" sections if present
            expand_selectors = [
                'div[role="button"]:has-text("ตัวเลือกเพิ่มเติม")',
                'div[role="button"]:has-text("เพิ่มเติม")',
                'div[role="button"]:has-text("More options")',
                'div[role="button"]:has-text("Show more")',
                'div[role="button"]:has-text("ຕົວເລືອກເພີ່ມເຕີມ")',
                'div[role="button"]:has-text("ເພີ່ມເຕີມ")',
                'span:has-text("ตัวเลือกเพิ่มเติม")',
                'span:has-text("More options")',
                'span:has-text("Show more")',
                'span:has-text("ຕົວເລືອກເພີ່ມເຕີມ")'
            ]
            for sel in expand_selectors:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible(timeout=800):
                        el.click()
                        time.sleep(1)
                except Exception:
                    pass

            # Step B: Look for AI label toggles, switches, or checkboxes
            ai_terms = [
                "เนื้อหา AI", "สร้างด้วย AI", "ป้ายกำกับ AI", "เนื้อหาที่สร้างด้วย AI",
                "AI label", "Made with AI", "AI-generated", "Created with AI",
                "Digital or AI", "AI info", "Let people know this content was created with AI",
                "ເນື້ອຫາ AI", "ປ້າຍກຳກັບ AI", "ສ້າງດ້ວຍ AI", "ເນື້ອຫາທີ່ສ້າງໂດຍ AI"
            ]

            # 1. Look for direct switches or checkboxes associated with AI text
            for term in ai_terms:
                container = self.page.locator(f'div:has-text("{term}"), label:has-text("{term}"), span:has-text("{term}")').last
                if container.is_visible(timeout=1000):
                    switch = container.locator('input[type="checkbox"], div[role="switch"], div[role="checkbox"]').first
                    if not switch.is_visible(timeout=500):
                        switch = container.locator('xpath=..//input[@type="checkbox"] | ..//div[@role="switch"] | ..//div[@role="checkbox"]').first

                    if switch.is_visible(timeout=500):
                        checked = switch.get_attribute("aria-checked") == "true" or switch.is_checked()
                        if checked:
                            self.log(f"✅ ป้ายกำกับ '{term}' ถูกเปิดใช้งานอยู่แล้ว (Already ON).")
                            return True
                        else:
                            switch.click()
                            time.sleep(1)
                            self.log(f"✅ ติ๊กเปิดใช้งาน '{term}' สำเร็จ!")
                            self._confirm_ai_modal_if_present()
                            return True
                    else:
                        # Clicking the container itself
                        container.click()
                        time.sleep(1)
                        self.log(f"✅ กดเลือก '{term}' สำเร็จ!")
                        self._confirm_ai_modal_if_present()
                        return True

            # 2. General role="switch" check with aria-label containing AI
            switches = self.page.locator('div[role="switch"], input[type="checkbox"]').all()
            for sw in switches:
                label_text = (sw.get_attribute("aria-label") or "") + " " + (sw.inner_text() or "")
                if any(t.lower() in label_text.lower() for t in ["ai", "เนื้อหา ai", "ເນື້ອຫາ ai"]):
                    checked = sw.get_attribute("aria-checked") == "true" or sw.is_checked()
                    if checked:
                        self.log("✅ เนื้อหา AI ถูกเปิดใช้งานอยู่แล้ว.")
                        return True
                    else:
                        sw.click()
                        time.sleep(1)
                        self.log("✅ ติ๊กเปิดใช้งานเนื้อหา AI สำเร็จ!")
                        self._confirm_ai_modal_if_present()
                        return True

            self.log("ℹ️ ไม่พบปุ่มเลือกเนื้อหา AI ในขั้นตอนนี้.")
            return False
        except Exception as e:
            self.log(f"Warning checking AI content label: {e}")
            return False

    def _confirm_ai_modal_if_present(self):
        """Confirms any dialog that pops up after toggling the AI label"""
        try:
            confirm_selectors = [
                'div[role="dialog"] div[role="button"]:has-text("เปิดใช้")',
                'div[role="dialog"] div[role="button"]:has-text("บันทึก")',
                'div[role="dialog"] div[role="button"]:has-text("ตกลง")',
                'div[role="dialog"] div[role="button"]:has-text("Turn on")',
                'div[role="dialog"] div[role="button"]:has-text("Save")',
                'div[role="dialog"] div[role="button"]:has-text("Yes")',
                'div[role="dialog"] div[role="button"]:has-text("ຕົກລົງ")',
                'div[role="dialog"] div[role="button"]:has-text("ເປີດໃຊ້")',
                'div[role="dialog"] div[role="button"]:has-text("ບັນທຶກ")',
                'button:has-text("Turn on")',
                'button:has-text("Save")'
            ]
            for sel in confirm_selectors:
                btn = self.page.locator(sel).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    time.sleep(1)
                    self.log("✅ กดยืนยันในหน้าต่าง AI Dialog สำเร็จ.")
                    return
        except Exception:
            pass


def inspect_active_page(page: Page) -> Dict[str, Any]:
    """
    Inspects the currently open Meta Business Suite page to detect active Page Name and Page ID.
    Returns dict: {'page_name': str, 'page_id': str, 'url': str, 'title': str}
    """
    url = page.url
    page_id = ""
    if "asset_id=" in url:
        try:
            page_id = url.split("asset_id=")[1].split("&")[0].split("#")[0]
        except Exception:
            pass

    page_title = page.title()
    detected_name = ""
    try:
        if " - " in page_title:
            parts = page_title.split(" - ")
            detected_name = parts[-1].strip()

        dom_name = page.evaluate("""() => {
            let selectors = [
                'div[aria-label*="Profile"]',
                'div[aria-label*="โปรไฟล์"]',
                'div[aria-label*="ບັນຊີ"]',
                'div[aria-label*="Page"]',
                'div[aria-label*="เพจ"]',
                'div[role="navigation"] h1',
                'div[role="navigation"] h2',
                'div[role="banner"] span'
            ];
            for (let sel of selectors) {
                let el = document.querySelector(sel);
                if (el && el.innerText && el.innerText.trim().length > 2 && el.innerText.trim().length < 80) {
                    return el.innerText.trim();
                }
            }
            return "";
        }""")
        if dom_name:
            detected_name = dom_name
    except Exception:
        pass

    return {
        "page_name": detected_name,
        "page_id": page_id,
        "url": url,
        "title": page_title
    }

