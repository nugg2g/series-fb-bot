import os
import time
import random
import glob
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Callable, Optional, List

ICT_TZ = timezone(timedelta(hours=7))

def get_lao_now() -> datetime:
    """Returns the current datetime in Laos/Thailand timezone (ICT, UTC+7)."""
    return datetime.now(timezone.utc).astimezone(ICT_TZ)

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
        self._skip_delay = False
        self._thread: Optional[threading.Thread] = None

    def log(self, msg: str):
        timestamp = get_lao_now().strftime("%H:%M:%S")
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
        self._skip_delay = False
        WEB_STATE.update(status="uploading")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self):
        self._is_paused = True
        self.log("⏸️ ພັກການເຮັດວຽກຊົ່ວຄາວ (Paused)")
        WEB_STATE.update(status="paused", progress_text="⏸️ ພັກການເຮັດວຽກຊົ່ວຄາວ (Paused)")

    def resume(self):
        self._is_paused = False
        self.log("▶️ ສືບຕໍ່ເຮັດວຽກ (Resumed)")
        WEB_STATE.update(status="uploading", progress_text="▶️ ສືບຕໍ່ການເຮັດວຽກ...")

    def skip_delay(self):
        self._skip_delay = True
        self._is_paused = False
        self.log("⚡ ໄດ້ຮັບຄຳສັ່ງ: ຂ້າມເວລາພັກລໍຖ້າ (Skip Delay) -> ກຳລັງເລີ່ມຂັ້ນຕອນຕໍ່ໄປທັນທີ!")

    def apply_config(self, new_config: dict):
        try:
            self.config.update(new_config)
            self.queue_mgr.config = self.config
            self.caption_gen.config = self.config
            self.log("⚙️ ອັບເດດການຕັ້ງຄ່າ Bot ຮຽບຮ້ອຍ (Config applied dynamically)")
        except Exception as e:
            self.log(f"⚠️ Error applying dynamic config: {e}")

    def stop(self):
        self._is_running = False
        self._skip_delay = True
        self.log("🛑 ຢຸດການເຮັດວຽກ (Stopped)")
        WEB_STATE.update(status="idle", progress_pct=0, progress_text="ຢຸດການເຮັດວຽກ (Stopped)", delay_remaining_seconds=0, countdown_str="")
        try:
            self.browser_mgr.close()
        except Exception:
            pass

    def is_running(self) -> bool:
        return self._is_running

    def reload_config_from_disk(self):
        """Hot-reloads configuration directly from config.json without requiring program restart."""
        candidates = [
            os.path.abspath("./config.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        ]
        for cfg_path in candidates:
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        new_cfg = json.load(f)
                        self.config.update(new_cfg)
                        self.queue_mgr.config = self.config
                        self.caption_gen.config = self.config
                    break
                except Exception:
                    pass

    def _get_pipeline_pages(self) -> List[Dict[str, Any]]:
        self.reload_config_from_disk()
        raw_pipeline = self.config.get("pages_pipeline", [])
        if raw_pipeline:
            return [p for p in raw_pipeline if p.get("enabled", True)]

        # Fallback: convert legacy page_groups into pipeline
        raw_groups = self.config.get("page_groups", [])
        if raw_groups:
            flat = []
            for g in raw_groups:
                g_folder = g.get("video_folder", self.config.get("video_folder", "./videos"))
                g_comp = g.get("completed_folder", self.config.get("completed_folder", "./completed"))
                g_fail = g.get("failed_folder", self.config.get("failed_folder", "./failed"))
                g_tpl = g.get("caption_template") or self.config.get("caption_template")
                g_tags = g.get("hashtag_pool") or self.config.get("hashtag_pool")
                g_pfx = g.get("title_prefix")
                g_ctype = g.get("content_type", "china_drama")
                g_mode = "sequential" if g.get("group_id") == "group_dedicated_1page" else "random"
                for p in g.get("pages", []):
                    flat.append({
                        "page_name": p.get("page_name", ""),
                        "page_id": str(p.get("page_id", "")),
                        "enabled": True,
                        "video_folder": g_folder,
                        "completed_folder": g_comp,
                        "failed_folder": g_fail,
                        "pick_mode": g_mode,
                        "content_type": g_ctype,
                        "title_prefix": g_pfx,
                        "caption_template": g_tpl,
                        "hashtag_pool": g_tags,
                        "cta_post_enabled": g.get("cta_post_enabled", False)
                    })
            return flat

        # Fallback to single legacy page
        return [{
            "page_name": self.config.get("page_name", "Default Page"),
            "page_id": str(self.config.get("page_id", "")),
            "enabled": True,
            "video_folder": self.config.get("video_folder", "./videos"),
            "completed_folder": self.config.get("completed_folder", "./completed"),
            "failed_folder": self.config.get("failed_folder", "./failed"),
            "pick_mode": "random",
            "content_type": "china_drama",
            "title_prefix": self.config.get("title_prefix", "[เต็มเรื่อง] "),
            "caption_template": self.config.get("caption_template"),
            "hashtag_pool": self.config.get("hashtag_pool"),
            "cta_post_enabled": False
        }]

    def _get_execution_groups(self) -> List[Dict[str, Any]]:
        return self.config.get("page_groups", [])

    def _do_countdown(self, total_seconds: int, target_time_str: str, next_target_name: str, is_round_cooldown: bool = False, round_num: int = 1):
        status_key = "waiting_delay" if is_round_cooldown else "waiting_page_delay"
        for s in range(total_seconds):
            if not self._is_running:
                break
            if self._skip_delay:
                self._skip_delay = False
                self.log(f"⚡ ໄດ້ຮັບຄຳສັ່ງ: ຂ້າມເວລາພັກ (Skip Delay) -> ເລີ່ມຕົ້ນດຳເນີນການຕໍ່ທັນທີ!")
                break
            while self._is_paused:
                time.sleep(1)
                if not self._is_running or self._skip_delay:
                    break

            rem = total_seconds - s
            rem_hrs = rem // 3600
            rem_mins = (rem % 3600) // 60
            rem_secs = rem % 60

            if is_round_cooldown:
                if rem_hrs > 0:
                    cd_str = f"{rem_hrs:02d}:{rem_mins:02d}:{rem_secs:02d}"
                    p_txt = f"🎉 ຈົບຮອບທີ {round_num}! ພັກຈົບຮອບ (Round Cooldown): {rem_hrs}ຊມ {rem_mins}ນ (ເລີ່ມຮອບ {round_num + 1} ເວລາ {target_time_str})"
                else:
                    cd_str = f"{rem_mins:02d}:{rem_secs:02d}"
                    p_txt = f"🎉 ຈົບຮອບທີ {round_num}! ພັກຈົບຮອບ (Round Cooldown): {rem_mins}ນ {rem_secs}ວ (ເລີ່ມຮອບ {round_num + 1} ເວລາ {target_time_str})"
            else:
                cd_str = f"{rem_mins:02d}:{rem_secs:02d}"
                p_txt = f"⏳ ພັກປ່ຽນ Page (Inter-Page Delay): {rem_mins}ນ {rem_secs}ວ (ເປົ້າໝາຍຖັດໄປ: {next_target_name})"

            WEB_STATE.update(
                status=status_key,
                progress_text=p_txt,
                delay_remaining_seconds=rem,
                delay_total_seconds=total_seconds,
                countdown_str=cd_str,
                next_post_time=target_time_str,
                next_target=next_target_name
            )
            time.sleep(1)

        WEB_STATE.update(status="uploading", delay_remaining_seconds=0, countdown_str="")

    def _run_loop(self):
        self._is_running = True
        self._is_paused = False
        self.log("🎬 ເລີ່ມຕົ້ນລະບົບ Auto-Upload Facebook Reels (Two-Tier Multi-Page Round Engine)...")

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

            schedule_interval = float(self.config.get("schedule_interval_hours", 4))
            post_mode = self.config.get("post_mode", "now")
            auto_watch = self.config.get("auto_watch_new_files", True)

            current_schedule_time = datetime.now() + timedelta(hours=1)
            total_uploaded_in_session = 0
            round_num = 1

            while self._is_running:
                pipeline_pages = self._get_pipeline_pages()
                if not pipeline_pages:
                    self.log("⚠️ ບໍ່ພົບ Page ທີ່ເປີດໃຊ້ງານໃນ pages_pipeline, ລໍຖ້າ 10 ວິນາທີ...")
                    time.sleep(10)
                    continue

                pacing_mode = self.config.get("pacing_mode", "two_tier")
                pages_posted_in_round = 0

                self.log(f"\n=======================================================")
                self.log(f"🔄 [ຮອບທີ {round_num}] ເລີ່ມຕົ້ນຮອບອັບໂຫຼດ (ມີທັງໝົດ {len(pipeline_pages)} Page ໃນ Pipeline)")
                self.log(f"=======================================================")

                for idx, p_cfg in enumerate(pipeline_pages):
                    if not self._is_running:
                        break

                    curr_page_name = p_cfg.get("page_name", "")
                    curr_page_id = str(p_cfg.get("page_id", "")).strip()

                    # Find candidate video for this page
                    v_path = self.queue_mgr.get_next_video_for_page(p_cfg, log_cb=self.log)
                    if not v_path:
                        has_cands = bool(self.queue_mgr.get_candidate_videos_for_page(curr_page_id, p_cfg.get("video_folder")))
                        if not has_cands:
                            self.log(f"ℹ️ [ຮອບທີ {round_num}] Page '{curr_page_name}' ບໍ່ມີວິດີໂອໃໝ່ທີ່ລໍຖ້າອັບໂຫຼດ (ຂ້າມໄປ Page ຖັດໄປ)...")
                        continue

                    chosen_video = v_path
                    chosen_page_cfg = p_cfg

                    filename = os.path.basename(chosen_video)
                    content_type = chosen_page_cfg.get("content_type", "china_drama")
                    pick_mode = chosen_page_cfg.get("pick_mode", "random")
                    caption_tpl = chosen_page_cfg.get("caption_template") or self.config.get("caption_template")
                    tags_pool = chosen_page_cfg.get("hashtag_pool") or self.config.get("hashtag_pool")
                    title_prefix = chosen_page_cfg.get("title_prefix")
                    if title_prefix is None and content_type == "china_drama":
                        title_prefix = "[เต็มเรื่อง] "
                    title_mode = chosen_page_cfg.get("title_mode") or self.config.get("title_mode", "filename_clean")
                    p_folder = chosen_page_cfg.get("video_folder") or self.config.get("video_folder", "./videos")
                    p_completed = chosen_page_cfg.get("completed_folder") or self.config.get("completed_folder", "./completed")
                    p_failed = chosen_page_cfg.get("failed_folder") or self.config.get("failed_folder", "./failed")

                    while self._is_paused:
                        time.sleep(1)
                        if not self._is_running:
                            break

                    total_uploaded_in_session += 1

                    self.log(f"\n=======================================================")
                    self.log(f"▶️ [ຮອບທີ {round_num} | ຄລິບລວມທີ {total_uploaded_in_session}] Page: '{curr_page_name}' (ID: {curr_page_id})")
                    self.log(f"📁 Folder: {p_folder} | ຮູບແບບ: {'🎲 ສຸ່ມຄລິບ (Random)' if pick_mode == 'random' else '🔢 ຕາມລຳດັບ (Sequential)'}")
                    self.log(f"🎬 ໄຟລ໌: {filename}")
                    self.log(f"=======================================================")

                    # Build caption
                    cap_data = self.caption_gen.build_caption(
                        chosen_video,
                        index=total_uploaded_in_session,
                        custom_template=caption_tpl,
                        custom_hashtag_pool=tags_pool,
                        title_prefix=title_prefix,
                        content_type=content_type,
                        title_mode=title_mode
                    )
                    title = cap_data["title"]
                    caption = cap_data["caption"]

                    self.log(f"📌 Title: {title}")
                    self.log(f"📝 Caption preview:\n{caption[:120]}...")

                    # Update Web State
                    try:
                        sz = round(os.path.getsize(chosen_video) / (1024 * 1024), 1) if os.path.exists(chosen_video) else 0
                        WEB_STATE.update(
                            status="uploading",
                            page_name=curr_page_name,
                            page_id=curr_page_id,
                            current_video={
                                "filename": filename,
                                "title": title,
                                "size_mb": sz,
                                "page_name": curr_page_name,
                                "group_name": f"{curr_page_name} ({pick_mode})"
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

                    # Ensure active browser page before upload
                    fresh_page = self.browser_mgr.get_active_page()
                    uploader.page = fresh_page

                    self.log(f"\n🌐 ກຳລັງອັບໂຫຼດໄປຍັງ Page: '{curr_page_name}' (ID: {curr_page_id})...")

                    is_img = QueueManager.is_image_file(chosen_video)
                    if is_img:
                        page_success = uploader.upload_photo(
                            chosen_video,
                            caption,
                            schedule_time=sched_dt,
                            target_page=chosen_page_cfg
                        )
                    else:
                        page_success = uploader.upload_reel(
                            chosen_video,
                            caption,
                            schedule_time=sched_dt,
                            target_page=chosen_page_cfg,
                            title=title
                        )

                    uploaded_successfully = False
                    if page_success:
                        self.log(f"✅ ອັບໂຫຼດໄປຍັງ Page '{curr_page_name}' ສຳເລັດຮຽບຮ້ອຍ!")
                        self.queue_mgr.record_page_success(chosen_video, chosen_page_cfg, meta={
                            "title": title, "caption": caption, "content_type": content_type
                        })
                        self.queue_mgr.mark_completed(
                            chosen_video,
                            meta={
                                "title": title,
                                "caption": caption,
                                "page_name": curr_page_name,
                                "page_id": curr_page_id,
                                "mode": post_mode,
                                "scheduled_time": sched_dt.isoformat() if sched_dt else None,
                                "target_pages": [{"page_name": curr_page_name, "page_id": curr_page_id, "success": True}]
                            },
                            custom_dest_folder=p_completed
                        )
                        self.queue_mgr.release_video_lock(chosen_video)
                        self.notifier.notify_upload_success(title, curr_page_name)
                        uploaded_successfully = True

                    else:
                        self.log(f"⚠️ ການອັບໂຫຼດໄປຍັງ Page '{curr_page_name}' ບໍ່ສຳເລັດ, ກຳລັງ Retry ອີກ 1 ຄັ້ງ...")
                        retry_delay = round(random.uniform(2, 4), 1)
                        retry_secs = int(retry_delay * 60)
                        self.log(f"⏳ ພັກ {retry_delay} ນາທີ ກ່ອນ Retry...")
                        target_retry_dt = get_lao_now() + timedelta(seconds=retry_secs)
                        target_retry_str = target_retry_dt.strftime("%H:%M:%S")

                        for _s in range(retry_secs):
                            if not self._is_running:
                                break
                            if self._skip_delay:
                                self._skip_delay = False
                                self.log("⚡ ຂ້າມເວລາພັກ Retry! ກຳລັງລອງອັບໂຫຼດໃໝ່ທັນທີ...")
                                break
                            while self._is_paused:
                                time.sleep(1)
                                if not self._is_running or self._skip_delay:
                                    break

                            rem_r = retry_secs - _s
                            rem_r_m = rem_r // 60
                            rem_r_s = rem_r % 60
                            cd_r_str = f"{rem_r_m:02d}:{rem_r_s:02d}"

                            WEB_STATE.update(
                                status="waiting_retry_delay",
                                progress_text=f"ພັກກ່ອນ Retry: {cd_r_str} (ຮອດ {target_retry_str})",
                                delay_remaining_seconds=rem_r,
                                delay_total_seconds=retry_secs,
                                countdown_str=cd_r_str,
                                next_post_time=target_retry_str,
                                next_target=curr_page_name
                            )
                            time.sleep(1)
                        WEB_STATE.update(status="uploading", delay_remaining_seconds=0, countdown_str="")

                        if self._is_running:
                            self.log(f"🔄 [Retry] ກຳລັງອັບໂຫຼດໄປຍັງ '{curr_page_name}' ອີກຄັ້ງ...")
                            fresh_page = self.browser_mgr.get_active_page()
                            uploader.page = fresh_page
                            if is_img:
                                retry_ok = uploader.upload_photo(chosen_video, caption, schedule_time=sched_dt, target_page=chosen_page_cfg)
                            else:
                                retry_ok = uploader.upload_reel(chosen_video, caption, schedule_time=sched_dt, target_page=chosen_page_cfg, title=title)

                            if retry_ok:
                                self.log(f"✅ [Retry] ອັບໂຫຼດໄປຍັງ '{curr_page_name}' ສຳເລັດແລ້ວ!")
                                self.queue_mgr.record_page_success(chosen_video, chosen_page_cfg, meta={
                                    "title": title, "caption": caption, "content_type": content_type
                                })
                                self.queue_mgr.mark_completed(
                                    chosen_video,
                                    meta={
                                        "title": title, "caption": caption,
                                        "page_name": curr_page_name, "page_id": curr_page_id,
                                        "mode": post_mode,
                                        "target_pages": [{"page_name": curr_page_name, "page_id": curr_page_id, "success": True, "is_retry": True}]
                                    },
                                    custom_dest_folder=p_completed
                                )
                                self.queue_mgr.release_video_lock(chosen_video)
                                self.notifier.notify_upload_success(title, curr_page_name)
                                uploaded_successfully = True
                            else:
                                self.log(f"❌ [Retry] ອັບໂຫຼດໄປຍັງ '{curr_page_name}' ລົ້ມເຫຼວອີກ.")
                                self.queue_mgr.mark_failed(
                                    chosen_video,
                                    f"Upload failed after retry on page: {curr_page_name} (ID: {curr_page_id})",
                                    custom_failed_folder=p_failed
                                )
                                self.queue_mgr.release_video_lock(chosen_video)
                                self.notifier.notify_upload_failed(title, curr_page_name, "Upload failed after retry")

                    pages_posted_in_round += 1

                    # Follower CTA Photo Post trigger (if enabled and not posted today)
                    cta_enabled = self.config.get("cta_post_enabled", False) and chosen_page_cfg.get("cta_post_enabled", False)
                    if cta_enabled and not self.queue_mgr.has_posted_cta_today(curr_page_id):
                        self.log(f"\n📢 [Creator Goal] ກຳລັງໂພສຮູບພາບ AI ເຊີນຊວນຕິດຕາມ ສຳລັບ Page '{curr_page_name}'...")
                        try:
                            self.post_follower_cta(
                                page=page,
                                target_pages=[chosen_page_cfg],
                                group_content_type=content_type
                            )
                        except Exception as e:
                            self.log(f"Warning posting CTA photo: {e}")

                    # Update stats
                    self.update_status(self.queue_mgr.get_stats())

                    # Check delay before next page in this round
                    if self._is_running:
                        if pacing_mode == "legacy":
                            if self.config.get("randomize_delay", True):
                                min_d = float(self.config.get("delay_min_minutes", 60))
                                max_d = float(self.config.get("delay_max_minutes", 120))
                                if min_d > max_d:
                                    min_d, max_d = max_d, min_d
                                delay_mins = round(random.uniform(min_d, max_d), 1)
                            else:
                                delay_mins = float(self.config.get("delay_between_posts_minutes", 60))
                            total_secs = int(delay_mins * 60)
                            target_dt = get_lao_now() + timedelta(seconds=total_secs)
                            target_str = target_dt.strftime("%H:%M:%S")
                            self.log(f"⏳ [Legacy Delay] ພັກລໍຖ້າ {delay_mins} ນາທີ...")
                            self._do_countdown(total_secs, target_str, "Page ຖັດໄປ", is_round_cooldown=False, round_num=round_num)
                        else:
                            # Approach 1: Check if any remaining page in pipeline has candidate videos
                            has_more_in_round = False
                            next_target_name = ""
                            for next_idx in range(idx + 1, len(pipeline_pages)):
                                next_p = pipeline_pages[next_idx]
                                next_pid = str(next_p.get("page_id", "")).strip()
                                next_folder = next_p.get("video_folder") or self.config.get("video_folder")
                                cands = self.queue_mgr.get_candidate_videos_for_page(next_pid, next_folder)
                                if cands:
                                    has_more_in_round = True
                                    next_target_name = next_p.get("page_name", "")
                                    break

                            if has_more_in_round:
                                min_m = float(self.config.get("inter_page_delay_min_minutes", 3))
                                max_m = float(self.config.get("inter_page_delay_max_minutes", 5))
                                if min_m > max_m:
                                    min_m, max_m = max_m, min_m
                                delay_mins = round(random.uniform(min_m, max_m), 1)
                                total_secs = int(delay_mins * 60)
                                target_dt = get_lao_now() + timedelta(seconds=total_secs)
                                target_str = target_dt.strftime("%H:%M:%S")

                                self.log(f"⏳ [Inter-Page Delay] ພັກປ່ຽນ Page {delay_mins} ນາທີ (ສຸ່ມ {min_m}-{max_m} ນາທີ) ກ່ອນເລີ່ມ Page ຖັດໄປ '{next_target_name}' (ເປົ້າໝາຍ {target_str})...")
                                self._do_countdown(total_secs, target_str, next_target_name, is_round_cooldown=False, round_num=round_num)
                            else:
                                self.log(f"🏁 [ຮອບທີ {round_num}] Page ນີ້ເປັນ Page ສຸດທ້າຍໃນຮອບນີ້ທີ່ມີວິດີໂອ -> ກຽມພັກຈົບຮອບ (Round Cooldown)...")

                # End of Round processing
                if not self._is_running:
                    break

                if pages_posted_in_round > 0:
                    if pacing_mode != "legacy":
                        # Tier 2: Round Cooldown
                        min_h = float(self.config.get("round_cooldown_min_hours", 2.0))
                        max_h = float(self.config.get("round_cooldown_max_hours", 2.5))
                        if min_h > max_h:
                            min_h, max_h = max_h, min_h
                        cooldown_hours = round(random.uniform(min_h, max_h), 2)
                        cooldown_secs = int(cooldown_hours * 3600)
                        target_dt = get_lao_now() + timedelta(seconds=cooldown_secs)
                        target_str = target_dt.strftime("%H:%M:%S")

                        first_p_name = pipeline_pages[0].get("page_name", "")

                        self.log(f"\n=======================================================")
                        self.log(f"🎉 [Round Cooldown] ຈົບຮອບທີ {round_num} ສຳເລັດຮຽບຮ້ອຍ! (ອັບໂຫຼດໄປທັງໝົດ {pages_posted_in_round} Page)")
                        self.log(f"⏳ ພັກຈົບຮອບ {cooldown_hours} ຊົ່ວໂມງ ({int(cooldown_hours * 60)} ນາທີ, ສຸ່ມລະຫວ່າງ {min_h}-{max_h} ຊມ)...")
                        self.log(f"🕒 ຮອບທີ {round_num + 1} ຈະເລີ່ມຕົ້ນເວລາ: {target_str} (ເລີ່ມຕົ້ນທີ່ Page: '{first_p_name}')")
                        self.log(f"=======================================================\n")

                        self._do_countdown(cooldown_secs, target_str, f"ຮອບທີ {round_num + 1} ({first_p_name})", is_round_cooldown=True, round_num=round_num)
                    round_num += 1

                else:
                    if not auto_watch:
                        self.log("🏁 ວິດີໂອທັງໝົດໃນທຸກ Page ອັບໂຫຼດຄົບແລ້ວ!")
                        break

                    self.log(f"⏳ [Continuous Watch] ບໍ່ມີວິດີໂອໃໝ່ທີ່ລໍຖ້າອັບໂຫຼດໃນທຸກ Page! ກຳລັງລໍຖ້າໄຟລ໌ໃໝ່ (ກວດສອບທຸກ 30 ວິນາທີ)...")
                    WEB_STATE.update(status="idle", progress_text="ລໍຖ້າໄຟລ໌ວິດີໂອໃໝ່ (Continuous Watch)...", delay_remaining_seconds=0, countdown_str="")
                    for _ in range(30):
                        if not self._is_running or self._skip_delay:
                            if self._skip_delay:
                                self._skip_delay = False
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
