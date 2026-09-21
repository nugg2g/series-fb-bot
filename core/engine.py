import os
import time
import random
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional

from core.queue_manager import QueueManager
from core.caption_generator import CaptionGenerator
from core.browser_manager import BrowserManager
from core.uploader import ReelsUploader
from core.notifier import MobileNotifier
from core.web_monitor import STATE as WEB_STATE

class ReelUploadEngine:
    """
    Orchestrates the entire batch uploading process.
    Supports running in a background thread with pause/stop signals and live status updates.
    """
    def __init__(self, config: Dict[str, Any], log_cb: Optional[Callable[[str], None]] = None, status_cb: Optional[Callable[[Dict[str, Any]], None]] = None, progress_cb: Optional[Callable[[int, str], None]] = None):
        self.config = config
        self.log_cb = log_cb or print
        self.status_cb = status_cb
        self.progress_cb = progress_cb

        self.queue_mgr = QueueManager(config)
        self.caption_gen = CaptionGenerator(config)
        self.browser_mgr = BrowserManager(config)
        self.notifier = MobileNotifier(config)
        self.cta_poster = None

        self._is_running = False
        self._is_paused = False
        self._thread: Optional[threading.Thread] = None

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_cb(f"[{timestamp}] {msg}")
        try:
            WEB_STATE.add_log(msg)
        except Exception:
            pass

    def update_progress(self, percent: int, text: str):
        if self.progress_cb:
            try:
                self.progress_cb(percent, text)
            except Exception:
                pass
        try:
            WEB_STATE.update(progress_pct=percent, progress_text=text)
        except Exception:
            pass

    def update_status(self, stats: Dict[str, Any]):
        if self.status_cb:
            self.status_cb(stats)
        try:
            WEB_STATE.update(queue_stats=stats)
        except Exception:
            pass

    def start(self):
        if self._is_running:
            return
        self._is_running = True
        self._is_paused = False
        WEB_STATE.update(status="uploading")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self):
        self._is_paused = not self._is_paused
        status_text = "⏸️ พักการทำงานชั่วคราว (Paused)" if self._is_paused else "▶️ ดำเนินการต่อ (Resumed)"
        self.log(status_text)
        WEB_STATE.update(status="paused" if self._is_paused else "uploading")

    def stop(self):
        self._is_running = False
        self.log("🛑 หยุดการทำงาน (Stopped)")
        WEB_STATE.update(status="idle", progress_pct=0, progress_text="ຢຸດການເຮັດວຽກ (Stopped)")
        try:
            self.browser_mgr.close()
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._is_running

    def _get_execution_groups(self) -> List[Dict[str, Any]]:
        raw_groups = self.config.get("page_groups", [])
        if raw_groups:
            return raw_groups
        # Fallback to single legacy group from global settings
        return [{
            "group_id": "default",
            "group_name": self.config.get("page_name", "Default Group"),
            "video_folder": self.config.get("video_folder", "./videos"),
            "completed_folder": self.config.get("completed_folder", "./completed"),
            "failed_folder": self.config.get("failed_folder", "./failed"),
            "caption_template": self.config.get("caption_template"),
            "hashtag_pool": self.config.get("hashtag_pool"),
            "pages": self.config.get("target_pages", []) or [{
                "page_name": self.config.get("page_name", ""),
                "page_id": str(self.config.get("page_id", ""))
            }]
        }]

    def _run_loop(self):
        self._is_running = True
        self._is_paused = False
        self.log("🎬 ເລີ່ມຕົ້ນລະບົບ Auto-Upload Facebook Reels (Multi-Page Unified Engine)...")
        
        try:
            # Launch browser
            page = self.browser_mgr.launch()
            uploader = ReelsUploader(page, self.config, log_cb=self.log, progress_cb=self.update_progress)

            # Check login
            if not self.browser_mgr.check_login_status():
                self.log("⚠️ ກະລຸນາ Login ເຂົ້າສູ່ລະບົບ Facebook ໃນ Browser ກ່ອນ...")
                self.log("💡 ຄຳແນະນຳ: ໃຫ້ກົດປຸ່ມ 'ເປີດ Browser ເພື່ອ Login Facebook' ໃນໂປຣແກຣມ ເພື່ອ Login ຄັ້ງດຽວ.")
                self._is_running = False
                return

            delay_mins = float(self.config.get("delay_between_posts_minutes", 20))
            schedule_interval = float(self.config.get("schedule_interval_hours", 4))
            post_mode = self.config.get("post_mode", "now")
            auto_watch = self.config.get("auto_watch_new_files", True)

            current_schedule_time = datetime.now() + timedelta(hours=1)
            total_uploaded_in_session = 0

            while self._is_running:
                groups = self._get_execution_groups()
                any_video_processed = False

                for g_idx, group in enumerate(groups, start=1):
                    if not self._is_running:
                        break

                    g_id = group.get("group_id", f"group_{g_idx}")
                    g_name = group.get("group_name", f"Group {g_idx}")
                    g_content_type = group.get("content_type", "china_drama" if g_id != "group_dedicated_1page" else "lao_girl_khaohom")
                    g_folder = group.get("video_folder", self.config.get("video_folder", "./videos"))
                    g_completed = group.get("completed_folder", self.config.get("completed_folder", "./completed"))
                    g_failed = group.get("failed_folder", self.config.get("failed_folder", "./failed"))
                    g_caption_tpl = group.get("caption_template") or self.config.get("caption_template")
                    g_tags_pool = group.get("hashtag_pool") or self.config.get("hashtag_pool")
                    g_title_prefix = group.get("title_prefix")
                    if g_title_prefix is None and g_id == "group_shared_3pages":
                        g_title_prefix = "[เต็มเรื่อง] "
                    g_pages = group.get("pages", [])

                    if not g_pages:
                        g_pages = [{
                            "page_name": self.config.get("page_name", ""),
                            "page_id": str(self.config.get("page_id", ""))
                        }]

                    # Check pending videos for this specific group
                    pending_videos = self.queue_mgr.get_pending_videos(target_folder=g_folder, completed_folder=g_completed)
                    if not pending_videos:
                        continue

                    # Process the first available video for this group
                    video_path = pending_videos[0]
                    filename = os.path.basename(video_path)

                    while self._is_paused:
                        time.sleep(1)
                        if not self._is_running:
                            break

                    is_dup, dup_reason = self.queue_mgr.is_already_uploaded(video_path, completed_folder=g_completed)
                    if is_dup:
                        self.log(f"⚠️ [ລະວັງໄຟລ໌ຊ້ຳ] ຂ້າມໄຟລ໌ '{filename}': {dup_reason}")
                        continue

                    total_uploaded_in_session += 1
                    any_video_processed = True

                    self.log(f"\n=======================================================")
                    self.log(f"▶️ [ຄລິບທີ {total_uploaded_in_session}] [{g_name} | ໝວດ: {g_content_type}] {filename}")
                    self.log(f"📁 Folder: {g_folder} | ເປົ້າໝາຍ: {len(g_pages)} Pages")
                    self.log(f"=======================================================")

                    # Build caption with this group's custom template, hashtags, prefix & content_type
                    cap_data = self.caption_gen.build_caption(
                        video_path,
                        index=total_uploaded_in_session,
                        custom_template=g_caption_tpl,
                        custom_hashtag_pool=g_tags_pool,
                        title_prefix=g_title_prefix,
                        content_type=g_content_type
                    )
                    title = cap_data["title"]
                    caption = cap_data["caption"]

                    self.log(f"📌 Title: {title}")
                    self.log(f"📝 Caption preview:\n{caption[:120]}...")

                    # Update Web State
                    try:
                        sz = round(os.path.getsize(video_path) / (1024 * 1024), 1) if os.path.exists(video_path) else 0
                        WEB_STATE.update(
                            status="uploading",
                            current_video={
                                "filename": filename,
                                "title": title,
                                "size_mb": sz,
                                "group_name": g_name
                            }
                        )
                    except Exception:
                        pass

                    # Schedule time calculation if needed
                    sched_dt = None
                    if post_mode == "schedule":
                        sched_dt = current_schedule_time
                        if self.config.get("randomize_schedule", True):
                            jitter_mins = random.randint(-15, 25)
                            current_schedule_time += timedelta(hours=schedule_interval, minutes=jitter_mins)
                        else:
                            current_schedule_time += timedelta(hours=schedule_interval)

                    # Upload to each page in this group
                    all_pages_succeeded = True
                    pages_results = []

                    for p_idx, page_info in enumerate(g_pages, start=1):
                        curr_page_name = page_info.get("page_name", "")
                        curr_page_id = str(page_info.get("page_id", ""))

                        try:
                            WEB_STATE.update(page_name=curr_page_name, page_id=curr_page_id)
                        except Exception:
                            pass

                        self.log(f"\n🌐 [{g_name} - Page {p_idx}/{len(g_pages)}] ກຳລັງອັບໂຫຼດໄປຍັງ: '{curr_page_name}' (ID: {curr_page_id})...")

                        is_img = QueueManager.is_image_file(video_path)
                        if is_img:
                            page_success = uploader.upload_photo(
                                video_path,
                                caption,
                                schedule_time=sched_dt,
                                target_page=page_info
                            )
                        else:
                            page_success = uploader.upload_reel(
                                video_path,
                                caption,
                                schedule_time=sched_dt,
                                target_page=page_info
                            )
                        pages_results.append({
                            "page_name": curr_page_name,
                            "page_id": curr_page_id,
                            "success": page_success
                        })
                        if not page_success:
                            all_pages_succeeded = False
                            self.log(f"⚠️ ການອັບໂຫຼດໄປຍັງ Page '{curr_page_name}' ບໍ່ສຳເລັດ.")
                        else:
                            self.log(f"✅ ອັບໂຫຼດໄປຍັງ Page '{curr_page_name}' ສຳເລັດຮຽບຮ້ອຍ!")

                        if p_idx < len(g_pages) and self._is_running:
                            self.log("⏳ ພັກລໍຖ້າ 15 ວິນາທີ ກ່ອນເລີ່ມອັບໂຫຼດໄປຍັງ Page ຖັດໄປ...")
                            time.sleep(15)

                    if all_pages_succeeded:
                        self.queue_mgr.mark_completed(
                            video_path,
                            meta={
                                "title": title,
                                "caption": caption,
                                "group_id": g_id,
                                "group_name": g_name,
                                "mode": post_mode,
                                "scheduled_time": sched_dt.isoformat() if sched_dt else None,
                                "target_pages": pages_results
                            },
                            custom_dest_folder=g_completed
                        )
                        self.log(f"🎉 ອັບໂຫຼດສຳເລັດຄົບທຸກ Page ({len(g_pages)} Pages) ໃນກຸ່ມ '{g_name}': {filename}")
                        for p_res in pages_results:
                            p_name = p_res.get("page_name", "")
                            self.notifier.notify_upload_success(title, p_name)
                    else:
                        self.queue_mgr.mark_failed(
                            video_path,
                            f"Upload failed on some pages: {pages_results}",
                            custom_failed_folder=g_failed
                        )
                        self.log(f"❌ ອັບໂຫຼດບໍ່ສົມບູນ (ບາງ Page ລົ້ມເຫຼວ): {filename}")
                        for p_res in pages_results:
                            if not p_res.get("success"):
                                p_name = p_res.get("page_name", "")
                                self.notifier.notify_upload_failed(title, p_name, p_res.get("error", "Unknown error"))

                    # Follower CTA Photo Post trigger
                    cta_enabled = self.config.get("cta_post_enabled", True)
                    cta_interval = int(self.config.get("cta_post_interval_reels", 5))
                    if cta_enabled and (total_uploaded_in_session % cta_interval == 0):
                        self.log(f"\n📢 [Creator Goal] ຄົບຮອບອັບໂຫຼດ {total_uploaded_in_session} ຄລິບ -> ກຳລັງໂພສຮູບພາບເຊີນຊວນກົດຕິດຕາມ Page...")
                        try:
                            self.post_follower_cta(page=page, target_pages=g_pages)
                        except Exception as e:
                            self.log(f"Warning posting CTA photo: {e}")

                    # Update stats
                    self.update_status(self.queue_mgr.get_stats())

                    # Delay before next post (with random jitter)
                    if self._is_running:
                        WEB_STATE.update(status="waiting_delay")
                        if self.config.get("randomize_delay", True):
                            min_d = float(self.config.get("delay_min_minutes", 15))
                            max_d = float(self.config.get("delay_max_minutes", 35))
                            if min_d > max_d:
                                min_d, max_d = max_d, min_d
                            delay_mins = round(random.uniform(min_d, max_d), 1)
                            self.log(f"⏳ ສຸ່ມເວລາພັກລໍຖ້າ (Random Delay): {delay_mins} ນາທີ ກ່ອນເລີ່ມຄລິບຖັດໄປ (ສຸ່ມລະຫວ່າງ {int(min_d)}-{int(max_d)} ນາທີ ເພື່ອຄວາມເປັນທຳມະຊາດ)...")
                        else:
                            delay_mins = float(self.config.get("delay_between_posts_minutes", 20))
                            self.log(f"⏳ ພັກລໍຖ້າ (Delay) {delay_mins} ນາທີ ເພື່ອປ້ອງກັນ Facebook Spam...")

                        total_seconds = int(delay_mins * 60)
                        for s in range(total_seconds):
                            if not self._is_running:
                                break
                            while self._is_paused:
                                time.sleep(1)
                                if not self._is_running:
                                    break
                            time.sleep(1)

                    # Break inner group loop to re-evaluate groups fresh
                    break

                if not any_video_processed:
                    if not auto_watch:
                        self.log("🏁 ວິດີໂອທັງໝົດໃນທຸກກຸ່ມອັບໂຫຼດຄົບແລ້ວ!")
                        break

                    self.log("⏳ ວິດີໂອທັງໝົດໃນທຸກກຸ່ມຖືກອັບໂຫຼດແລ້ວ! ກຳລັງລໍຖ້າໄຟລ໌ໃໝ່ທີ່ເພີ່ມເຂົ້າມາ (Continuous Watch)...")
                    for _ in range(15):
                        if not self._is_running:
                            break
                        while self._is_paused:
                            time.sleep(1)
                            if not self._is_running:
                                break
                        time.sleep(1)

            self.log("🏁 ສິ້ນສຸດການເຮັດວຽກຂອງລະບົບອັບໂຫຼດ.")
            WEB_STATE.update(status="finished", progress_pct=100, progress_text="ອັບໂຫຼດຄົບຮຽບຮ້ອຍ (Done)")

        except Exception as e:
            self.log(f"❌ ระบบเกิดข้อผิดพลาด: {e}")
            WEB_STATE.update(status="error", progress_text=f"ຜິດພາດ: {e}")
        finally:
            self._is_running = False
            self.update_status(self.queue_mgr.get_stats())

    def post_follower_cta(self, page=None, target_pages=None) -> bool:
        """
        Posts a Follower CTA photo post to target page(s) to fulfill Facebook creator goals.
        Generates brand new unique AI images & captions on the fly!
        """
        from core.cta_poster import CtaPoster
        if not self.cta_poster:
            self.cta_poster = CtaPoster(self.config, log_cb=self.log, progress_cb=self.update_progress)

        ai_gen_enabled = self.config.get("ai_image_gen", {}).get("enabled", True)
        ai_caption = None
        img_title = "Follower Invitation"

        if ai_gen_enabled:
            try:
                from core.ai_image_generator import AiImageGenerator
                self.log("🎨 ກຳລັງໃຫ້ AI ສ້າງຮູບພາບໂປສເຕີ ແລະ ແຄບຊັ່ນໃໝ່ (ບໍ່ຊ້ຳກັນ 100%)...")
                self.update_progress(10, "AI ກຳລັງສັງເຄາະຮູບພາບ ແລະ ສ້າງແຄບຊັ່ນ...")
                ai_gen = AiImageGenerator(self.config)
                img_path, ai_caption, img_title = ai_gen.generate_unique_cta_post()
                self.log(f"✅ AI ສ້າງຮູບພາບ ແລະ ແຄບຊັ່ນສຳເລັດ: '{img_title}' -> {os.path.basename(img_path)}")
            except Exception as e:
                self.log(f"⚠️ AI Image Gen failed, fallback to default banner: {e}")
                img_path = self.cta_poster.get_random_cta_image()
        else:
            img_path = self.cta_poster.get_random_cta_image()

        if not img_path:
            self.log("⚠️ ບໍ່ພົບຮູບພາບ CTA ຂ້າມຂັ້ນຕອນໂພສຮູບພາບ.")
            return False

        pages_to_post = target_pages
        if not pages_to_post:
            pages_to_post = self.config.get("target_pages", [])
            if not pages_to_post:
                p_name = self.config.get("page_name", "")
                p_id = str(self.config.get("page_id", ""))
                pages_to_post = [{"page_name": p_name, "page_id": p_id}]

        browser_page = page
        need_close = False
        if not browser_page or browser_page.is_closed():
            browser_page = self.browser_mgr.launch()
            need_close = True

        overall_ok = True
        try:
            for p_info in pages_to_post:
                p_name = p_info.get("page_name", "")
                caption = ai_caption or self.cta_poster.generate_cta_caption(p_name)
                self.log(f"\n📢 [Creator Goal] ກຳລັງໂພສຮູບພາບ AI ເຊີນຊວນກົດຕິດຕາມ Page: '{p_name}'...")
                ok = self.cta_poster.post_cta_photo(
                    page=browser_page,
                    image_path=img_path,
                    caption=caption,
                    target_page=p_info,
                    schedule_time=None
                )
                if ok:
                    self.notifier.notify_cta_posted(img_title, p_name, image_path=img_path)
                else:
                    overall_ok = False
        finally:
            if need_close:
                try:
                    self.browser_mgr.close()
                except Exception:
                    pass
        return overall_ok
