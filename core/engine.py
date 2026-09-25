import os
import time
import random
import glob
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Callable, Optional, List

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

    def reload_config_from_disk(self):
        """Hot-reloads configuration directly from config.json without requiring program restart."""
        cfg_path = os.path.abspath("./config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    new_cfg = json.load(f)
                    self.config.update(new_cfg)
            except Exception:
                pass

    def _get_execution_groups(self) -> List[Dict[str, Any]]:
        self.reload_config_from_disk()
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
            page = self.browser_mgr.get_active_page()
            uploader = ReelsUploader(page, self.config, log_cb=self.log, progress_cb=self.update_progress, browser_mgr=self.browser_mgr)

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
            # Round-Robin: ສະຫຼັບກຸ່ມເທື່ອລະກຸ່ມ (ກຸ່ມ1 → ກຸ່ມ2 → ກຸ່ມ1 → ...)
            total_uploaded_in_session = 0
            current_group_index = 0

            while self._is_running:
                groups = self._get_execution_groups()
                if not groups:
                    break

                # 1. ກວດສອບກຸ່ມ Priority (ນ້ອງເຂົ້າຫອມ / priority='immediate') ກ່ອນສະເໝີ
                priority_group = None
                for g in groups:
                    if g.get("priority") == "immediate" or g.get("group_id") == "group_dedicated_1page":
                        p_fol = g.get("video_folder", self.config.get("video_folder", "./videos"))
                        p_comp = g.get("completed_folder", self.config.get("completed_folder", "./completed"))
                        p_pgs = g.get("pages", [])
                        if self.queue_mgr.get_pending_videos(target_folder=p_fol, completed_folder=p_comp, target_pages=p_pgs):
                            priority_group = g
                            break

                any_video_processed = False

                if priority_group:
                    target_candidate_groups = [(priority_group, False)]  # (group, should_advance_round_robin)
                    self.log(f"⚡ [Priority #1] ພົບ Content ໃໝ່ຂອງເພຈ '{priority_group.get('group_name')}'! ດຶງມາອັບໂຫຼດທັນທີ...")
                else:
                    # Round-Robin: ລອງແຕ່ລະກຸ່ມເລີ່ມຈາກ current_group_index
                    target_candidate_groups = [
                        (groups[(current_group_index + i) % len(groups)], True)
                        for i in range(len(groups))
                    ]

                for group, should_advance in target_candidate_groups:
                    if not self._is_running:
                        break

                    if should_advance:
                        current_group_index = (current_group_index + 1) % len(groups)

                    g_id = group.get("group_id", "group")
                    g_name = group.get("group_name", "Group")
                    g_content_type = group.get("content_type", "china_drama" if g_id != "group_dedicated_1page" else "lao_girl_khaohom")
                    g_folder = group.get("video_folder", self.config.get("video_folder", "./videos"))
                    g_completed = group.get("completed_folder", self.config.get("completed_folder", "./completed"))
                    g_failed = group.get("failed_folder", self.config.get("failed_folder", "./failed"))
                    g_caption_tpl = group.get("caption_template") or self.config.get("caption_template")
                    g_tags_pool = group.get("hashtag_pool") or self.config.get("hashtag_pool")
                    g_title_prefix = group.get("title_prefix")
                    if g_title_prefix is None and g_id == "group_shared_3pages":
                        g_title_prefix = "[เต็มเรื่อง] "
                    g_title_mode = group.get("title_mode") or self.config.get("title_mode", "filename_clean")
                    g_pages = group.get("pages", [])

                    if not g_pages:
                        g_pages = [{
                            "page_name": self.config.get("page_name", ""),
                            "page_id": str(self.config.get("page_id", ""))
                        }]

                    # Check pending videos for this specific group (including backfill for new pages)
                    pending_videos = self.queue_mgr.get_pending_videos(
                        target_folder=g_folder, completed_folder=g_completed, target_pages=g_pages
                    )
                    if not pending_videos:
                        continue

                    # Found a video for this group - acquire exclusive lock to prevent duplicate uploads
                    video_path = None
                    for cand_v in pending_videos:
                        if self.queue_mgr.acquire_video_lock(cand_v):
                            video_path = cand_v
                            break

                    if not video_path:
                        self.log(f"ℹ️ ວິດີໂອທັງໝົດໃນຄິວຂອງກຸ່ມ '{g_name}' ກຳລັງຖືກອັບໂຫຼດໂດຍອີກ Worker ໜຶ່ງ, ຂ້າມໄປກຸ່ມຖັດໄປ...")
                        continue

                    filename = os.path.basename(video_path)

                    while self._is_paused:
                        time.sleep(1)
                        if not self._is_running:
                            break

                    # Smart per-page duplicate check: ກວດວ່າ Page ໃດລົງແລ້ວ Page ໃດຍັງບໍ່ລົງ
                    needs_upload, pages_todo, pages_done = self.queue_mgr.needs_upload_to_pages(
                        video_path, g_pages, completed_folder=g_completed
                    )

                    if not needs_upload:
                        self.log(f"⏭️ ຂ້າມ '{filename}': ລົງຄົບທຸກ {len(g_pages)} Pages ແລ້ວ")
                        self.queue_mgr.release_video_lock(video_path)
                        continue

                    if pages_done:
                        done_names = [p.get("page_name", "") for p in pages_done]
                        todo_names = [p.get("page_name", "") for p in pages_todo]
                        self.log(f"🔍 '{filename}': ລົງແລ້ວ {len(pages_done)} Pages ({', '.join(done_names)}), ຍັງເຫຼືອ {len(pages_todo)} Pages ({', '.join(todo_names)})")

                    total_uploaded_in_session += 1
                    any_video_processed = True

                    self.log(f"\n=======================================================")
                    self.log(f"▶️ [ຄລິບທີ {total_uploaded_in_session}] [{g_name} | ໝວດ: {g_content_type}] {filename}")
                    self.log(f"📁 Folder: {g_folder} | ເປົ້າໝາຍ: {len(pages_todo)}/{len(g_pages)} Pages")
                    self.log(f"=======================================================")

                    # Build caption with this group's custom template, hashtags, prefix & content_type
                    cap_data = self.caption_gen.build_caption(
                        video_path,
                        index=total_uploaded_in_session,
                        custom_template=g_caption_tpl,
                        custom_hashtag_pool=g_tags_pool,
                        title_prefix=g_title_prefix,
                        content_type=g_content_type,
                        title_mode=g_title_mode
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

                    # Upload only to pages that don't have this video yet
                    pages_results = list(pages_done)  # Keep already-done pages in results

                    # Ensure active browser page before starting page uploads (re-opens after delay)
                    fresh_page = self.browser_mgr.get_active_page()
                    uploader.page = fresh_page

                    for p_idx, page_info in enumerate(pages_todo, start=1):
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
                            self.log(f"⚠️ ການອັບໂຫຼດໄປຍັງ Page '{curr_page_name}' ບໍ່ສຳເລັດ.")
                        else:
                            self.log(f"✅ ອັບໂຫຼດໄປຍັງ Page '{curr_page_name}' ສຳເລັດຮຽບຮ້ອຍ!")
                            try:
                                self.queue_mgr.record_page_success(video_path, page_info, meta={
                                    "title": title, "caption": caption, "group_id": g_id, "group_name": g_name
                                })
                            except Exception as e:
                                self.log(f"Warning recording page success: {e}")

                        if p_idx < len(g_pages) and self._is_running:
                            page_delay_mins = round(random.uniform(3, 10), 1)
                            page_delay_secs = int(page_delay_mins * 60)
                            next_page = g_pages[p_idx] if p_idx < len(g_pages) else {}
                            next_name = next_page.get("page_name", "Page ຖັດໄປ")
                            self.log(f"⏳ ພັກລໍຖ້າ {page_delay_mins} ນາທີ ກ່ອນອັບໂຫຼດໄປຍັງ '{next_name}' (ສຸ່ມ 3-10 ນາທີ ເພື່ອປ້ອງກັນ Spam)...")
                            WEB_STATE.update(status="waiting_page_delay", progress_text=f"ລໍຖ້າ {page_delay_mins} ນາທີ ກ່ອນ Page ຖັດໄປ")
                            for _s in range(page_delay_secs):
                                if not self._is_running:
                                    break
                                while self._is_paused:
                                    time.sleep(1)
                                    if not self._is_running:
                                        break
                                remaining = page_delay_secs - _s
                                if remaining % 60 == 0 and remaining > 0:
                                    self.log(f"⏳ ເຫຼືອອີກ {remaining // 60} ນາທີ ກ່ອນ Page ຖັດໄປ...")
                                time.sleep(1)
                            WEB_STATE.update(status="uploading")

                    succeeded_pages = [p for p in pages_results if p.get("success")]
                    failed_pages = [p for p in pages_results if not p.get("success")]

                    if not failed_pages:
                        # ✅ ທຸກ Page ສຳເລັດ 100%
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
                        for p_res in succeeded_pages:
                            self.notifier.notify_upload_success(title, p_res.get("page_name", ""))

                    elif succeeded_pages:
                        # ⚠️ ບາງ Page ສຳເລັດ ບາງ Page ລົ້ມເຫຼວ → Retry ສະເພາະ Page ທີ່ລົ້ມເຫຼວ
                        self.log(f"\n⚠️ ອັບໂຫຼດສຳເລັດ {len(succeeded_pages)}/{len(g_pages)} Pages, ລົ້ມເຫຼວ {len(failed_pages)} Pages")
                        for fp in failed_pages:
                            self.log(f"   ❌ ລົ້ມເຫຼວ: '{fp.get('page_name', '')}' (ID: {fp.get('page_id', '')})")
                        for sp in succeeded_pages:
                            self.log(f"   ✅ ສຳເລັດ: '{sp.get('page_name', '')}'")
                            self.notifier.notify_upload_success(title, sp.get("page_name", ""))

                        # Retry ສະເພາະ Page ທີ່ລົ້ມເຫຼວ (ລອງອີກ 1 ຄັ້ງ)
                        self.log(f"\n🔄 ກຳລັງ Retry ສະເພາະ {len(failed_pages)} Page ທີ່ລົ້ມເຫຼວ...")
                        retry_delay = round(random.uniform(2, 5), 1)
                        self.log(f"⏳ ພັກ {retry_delay} ນາທີ ກ່ອນ Retry...")
                        for _s in range(int(retry_delay * 60)):
                            if not self._is_running:
                                break
                            time.sleep(1)

                        retry_results = []
                        for fp in failed_pages:
                            if not self._is_running:
                                break
                            fp_name = fp.get("page_name", "")
                            fp_id = str(fp.get("page_id", ""))
                            self.log(f"🔄 [Retry] ກຳລັງອັບໂຫຼດໄປຍັງ '{fp_name}' ອີກຄັ້ງ...")

                            is_img = QueueManager.is_image_file(video_path)
                            if is_img:
                                retry_ok = uploader.upload_photo(video_path, caption, schedule_time=sched_dt, target_page=fp)
                            else:
                                retry_ok = uploader.upload_reel(video_path, caption, schedule_time=sched_dt, target_page=fp)

                            retry_results.append({"page_name": fp_name, "page_id": fp_id, "success": retry_ok, "is_retry": True})
                            if retry_ok:
                                self.log(f"✅ [Retry] ອັບໂຫຼດໄປຍັງ '{fp_name}' ສຳເລັດແລ້ວ!")
                                self.notifier.notify_upload_success(title, fp_name)
                            else:
                                self.log(f"❌ [Retry] ອັບໂຫຼດໄປຍັງ '{fp_name}' ລົ້ມເຫຼວອີກ.")
                                self.notifier.notify_upload_failed(title, fp_name, "Retry failed")

                        all_results = succeeded_pages + retry_results
                        still_failed = [p for p in all_results if not p.get("success")]

                        if not still_failed:
                            # Retry ສຳເລັດທັງໝົດ → ຍ້າຍໄປ completed
                            self.queue_mgr.mark_completed(
                                video_path,
                                meta={
                                    "title": title, "caption": caption,
                                    "group_id": g_id, "group_name": g_name,
                                    "mode": post_mode,
                                    "scheduled_time": sched_dt.isoformat() if sched_dt else None,
                                    "target_pages": all_results
                                },
                                custom_dest_folder=g_completed
                            )
                            self.log(f"🎉 [Retry ສຳເລັດ] ອັບໂຫຼດຄົບທຸກ Page ແລ້ວ: {filename}")
                        else:
                            # ຍັງມີ Page ລົ້ມເຫຼວ → ບັນທຶກ partial success ແລະ ຍ້າຍໄປ failed
                            self.queue_mgr.mark_failed(
                                video_path,
                                f"Partial upload: {len(succeeded_pages)+len([r for r in retry_results if r.get('success')])} OK, {len(still_failed)} FAILED: {[p.get('page_name') for p in still_failed]}",
                                custom_failed_folder=g_failed
                            )
                            self.log(f"⚠️ ອັບໂຫຼດບໍ່ຄົບ: ສຳເລັດ {len(all_results)-len(still_failed)}/{len(g_pages)} Pages, ລົ້ມເຫຼວ: {[p.get('page_name') for p in still_failed]}")
                    else:
                        # ❌ ທຸກ Page ລົ້ມເຫຼວ 100%
                        self.queue_mgr.mark_failed(
                            video_path,
                            f"All pages failed: {pages_results}",
                            custom_failed_folder=g_failed
                        )
                        self.log(f"❌ ອັບໂຫຼດລົ້ມເຫຼວທຸກ Page ({len(g_pages)} Pages): {filename}")
                        for p_res in failed_pages:
                            self.notifier.notify_upload_failed(title, p_res.get("page_name", ""), p_res.get("error", "Unknown error"))

                    # Follower CTA Photo Post trigger (1 post per day per page - ສະເພາະ 3 Pages ຊີຣີຈີນເທົ່ານັ້ນ)
                    cta_enabled = self.config.get("cta_post_enabled", True) and group.get("cta_post_enabled", True)
                    is_khao_hom_group = (
                        g_id == "group_dedicated_1page" or 
                        g_content_type == "lao_girl_khaohom" or 
                        "ເຂົ້າຫອມ" in g_name or 
                        "ข้าวหอม" in g_name
                    )
                    if cta_enabled and not is_khao_hom_group:
                        pages_needing_cta = [
                            p for p in g_pages 
                            if not self.queue_mgr.has_posted_cta_today(str(p.get("page_id", "")))
                        ]
                        if pages_needing_cta:
                            self.log(f"\n📢 [Creator Goal - ມື້ລະ 1 Post] ກຳລັງໂພສຮູບພາບ AI ເຊີນຊວນຕິດຕາມສຳລັບ {len(pages_needing_cta)} Pages (ຊີຣີຈີນ) ທີ່ຍັງບໍ່ໄດ້ໂພສມື້ນີ້...")
                            try:
                                self.post_follower_cta(
                                    page=page, 
                                    target_pages=pages_needing_cta, 
                                    group_content_type=g_content_type
                                )
                            except Exception as e:
                                self.log(f"Warning posting CTA photo: {e}")

                    # Update stats
                    self.update_status(self.queue_mgr.get_stats())

                    # Delay before next post (with random jitter)
                    if self._is_running:
                        # RAM Optimization: Close Edge browser during long delay (60-120 min) to free ~1.2 GB RAM
                        try:
                            self.browser_mgr.close()
                            self.log("💤 [RAM Saver] ປິດ Browser ຊົ່ວຄາວໃນຊ່ວງພັກລໍຖ້າ (ຄືນ RAM 1.2 GB ໃຫ້ເຄື່ອງ)...")
                        except Exception:
                            pass
                        WEB_STATE.update(status="waiting_delay")
                        if self.config.get("randomize_delay", True):
                            min_d = float(self.config.get("delay_min_minutes", 60))
                            max_d = float(self.config.get("delay_max_minutes", 120))
                            if min_d > max_d:
                                min_d, max_d = max_d, min_d
                            delay_mins = round(random.uniform(min_d, max_d), 1)
                            self.log(f"⏳ ສຸ່ມເວລາພັກລໍຖ້າ (Random Delay): {delay_mins} ນາທີ ກ່ອນເລີ່ມຄລິບຖັດໄປ (ສຸ່ມລະຫວ່າງ {int(min_d)}-{int(max_d)} ນາທີ ເພື່ອຄວາມເປັນທຳມະຊາດ)...")
                        else:
                            delay_mins = float(self.config.get("delay_between_posts_minutes", 60))
                            self.log(f"⏳ ພັກລໍຖ້າ (Delay) {delay_mins} ນາທີ ເພື່ອປ້ອງກັນ Facebook Spam...")

                        total_seconds = int(delay_mins * 60)
                        for s in range(total_seconds):
                            if not self._is_running:
                                break
                            while self._is_paused:
                                time.sleep(1)
                                if not self._is_running:
                                    break

                            rem = total_seconds - s
                            if s % 5 == 0 or rem <= 5:
                                rem_mins = rem // 60
                                rem_secs = rem % 60
                                WEB_STATE.update(
                                    status="waiting_delay",
                                    progress_text=f"ພັກລໍຖ້າໂພສຖັດໄປ: {rem_mins:02d}:{rem_secs:02d} ນາທີ",
                                    delay_remaining_seconds=rem
                                )

                            time.sleep(1)

                    # Break inner tried loop - go back to main while loop
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

    def post_follower_cta(self, page=None, target_pages=None, group_content_type: str = "china_drama", force: bool = False) -> bool:
        """
        Posts a Follower CTA photo post to target page(s) to fulfill Facebook creator goals.
        Enforces 1 post/day per page (unless force=True).
        Tailors image and caption for China Drama vs. Nong Khao Hom!
        """
        from core.cta_poster import CtaPoster
        if not self.cta_poster:
            self.cta_poster = CtaPoster(self.config, log_cb=self.log, progress_cb=self.update_progress)

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
            browser_page = self.browser_mgr.get_active_page()
            need_close = not self._is_running

        overall_ok = True
        try:
            for p_info in pages_to_post:
                p_name = p_info.get("page_name", "")
                p_id = str(p_info.get("page_id", "")).strip()

                if not force and self.queue_mgr.has_posted_cta_today(p_id):
                    self.log(f"⏭️ ຂ້າມ CTA ສຳລັບ Page '{p_name}': ມື້ນີ້ໄດ້ໂພສໄປແລ້ວ 1 ຄັ້ງ (ໂຄຕ້າ 1 ໂພສ/ມື້)")
                    continue

                is_khaohom = (
                    group_content_type == "lao_girl_khaohom" or 
                    "ເຂົ້າຫອມ" in p_name or 
                    "ข้าวหอม" in p_name or
                    p_id == "1384777811375983"
                )

                if is_khaohom:
                    self.log(f"⏭️ ຂ້າມ CTA ສຳລັບ Page '{p_name}': ປິດການໂພສເຊີນຊວນ (ໂພສສະເພາະເນື້ອຫາຈາກ Folder ເທົ່ານັ້ນ)")
                    continue
                else:
                    # China Drama AI Poster & Caption
                    ai_gen_enabled = self.config.get("ai_image_gen", {}).get("enabled", True)
                    img_title = "Follower Invitation"
                    img_path = None
                    caption = None

                    if ai_gen_enabled:
                        try:
                            from core.ai_image_generator import AiImageGenerator
                            self.log("🎨 ກຳລັງໃຫ້ AI ສ້າງຮູບພາບໂປສເຕີ ແລະ ແຄບຊັ່ນໃໝ່ (ບໍ່ຊ້ຳກັນ 100%)...")
                            self.update_progress(10, "AI ກຳລັງສັງເຄາະຮູບພາບ ແລະ ສ້າງແຄບຊັ່ນ...")
                            ai_gen = AiImageGenerator(self.config)
                            img_path, caption, img_title = ai_gen.generate_unique_cta_post()
                            self.log(f"✅ AI ສ້າງຮູບພາບ ແລະ ແຄບຊັ່ນສຳເລັດ: '{img_title}' -> {os.path.basename(img_path)}")
                        except Exception as e:
                            self.log(f"⚠️ AI Image Gen failed, fallback to default banner: {e}")

                    if not img_path or not os.path.exists(img_path):
                        img_path = self.cta_poster.get_random_cta_image()
                    if not caption:
                        caption = self.cta_poster.generate_cta_caption(p_name)

                if not img_path or not os.path.exists(img_path):
                    self.log(f"⚠️ ບໍ່ພົບຮູບພາບ CTA ສຳລັບ Page '{p_name}', ຂ້າມຂັ້ນຕອນ.")
                    continue

                # Enforce strictly 100% Thai language for China Drama CTA post
                import re
                if caption:
                    caption = re.sub(r'[\u0E80-\u0EFF]', '', caption).strip()

                self.log(f"\n📢 [Creator Goal - ພາສາໄທລ້ວນ] ກຳລັງໂພສຮູບພາບ AI ເຊີນຊວນກົດຕິດຕາມ Page: '{p_name}'...")
                ok = self.cta_poster.post_cta_photo(
                    page=browser_page,
                    image_path=img_path,
                    caption=caption,
                    target_page=p_info,
                    schedule_time=None
                )
                if ok:
                    self.queue_mgr.record_cta_posted_today(p_id, p_name)
                    self.notifier.notify_cta_posted(img_title, p_name, image_path=img_path)
                    self.log(f"✅ ບັນທຶກປະຫວັດ: Page '{p_name}' ໄດ້ໂພສ CTA ປະຈຳມື້ແລ້ວ.")
                else:
                    overall_ok = False

                # Safe pacing between different pages for CTA posts
                if self._is_running and p_info != pages_to_post[-1]:
                    cta_delay = random.randint(60, 120)
                    self.log(f"⏳ ພັກລໍຖ້າ {cta_delay} ວິນາທີ ກ່ອນດຳເນີນການ CTA ເພຈຖັດໄປ...")
                    time.sleep(cta_delay)
        finally:
            if need_close and not self._is_running:
                try:
                    self.browser_mgr.close()
                except Exception:
                    pass
        return overall_ok

    def _pick_khaohom_cta_image(self) -> str:
        """Finds or picks a dedicated image for Nong Khao Hom CTA post"""
        dedicated_folders = [
            "Y:/Movies FB Dedicated",
            "G:/PG/ນ້ອງເຂົ້າຫອມ",
            "G:/PG/ນ້ອງເຂົ້າຫອມ/output",
            "./videos/dedicated"
        ]
        candidates = []
        for d in dedicated_folders:
            if os.path.exists(d):
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    candidates.extend(glob.glob(os.path.join(d, f"*{ext}")))
        if candidates:
            return random.choice(candidates)
        # Fallback to general cta image
        if self.cta_poster:
            return self.cta_poster.get_random_cta_image()
        return ""
