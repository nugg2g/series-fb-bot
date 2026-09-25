import os
import sys
import json
import time
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from core.utils import compute_file_hash

class QueueManager:
    VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mkv', '.avi', '.webm', '.flv', '.wmv')
    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp')
    SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS + IMAGE_EXTENSIONS
    VIDEO_EXTS = VIDEO_EXTENSIONS
    IMAGE_EXTS = IMAGE_EXTENSIONS

    @staticmethod
    def is_image_file(file_path: str) -> bool:
        return file_path.lower().endswith(QueueManager.IMAGE_EXTENSIONS)

    @staticmethod
    def is_video_file(file_path: str) -> bool:
        return file_path.lower().endswith(QueueManager.VIDEO_EXTENSIONS)

    @staticmethod
    def find_companion_text_file(media_path: str) -> Optional[str]:
        """
        Finds a companion .txt file for a given video or photo.
        Checks:
        1. same_name.txt (e.g. clip1.mp4 -> clip1.txt or photo1.jpg -> photo1.txt)
        2. same_name.caption.txt
        3. same_name_caption.txt
        """
        base_no_ext, _ = os.path.splitext(media_path)
        candidates = [
            f"{base_no_ext}.txt",
            f"{base_no_ext}.caption.txt",
            f"{base_no_ext}_caption.txt"
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def resolve_p(val, default_sub):
            p = val if val else default_sub
            if sys.platform != "win32" and isinstance(p, str) and (p.startswith("Z:") or p.startswith("z:") or p.startswith("Y:") or p.startswith("y:")):
                p = p.replace("\\", "/")
                p = p[2:].lstrip("/")
                p = os.path.join("/home/moes/storage", p)
            if not os.path.isabs(p):
                return os.path.abspath(os.path.join(project_root, p))
            return os.path.abspath(p)

        self.video_folder = resolve_p(config.get("video_folder"), "./videos")
        self.completed_folder = resolve_p(config.get("completed_folder"), "./completed")
        self.failed_folder = resolve_p(config.get("failed_folder"), "./failed")
        self.history_file = resolve_p(config.get("history_file"), "./history.json")
        self.move_completed = config.get("move_completed_videos", True)

        self._ensure_directories()
        self.history = self._load_history()
        self._hash_cache = {}

    def _ensure_directories(self):
        for folder in [self.video_folder, self.completed_folder, self.failed_folder]:
            if folder and not os.path.exists(folder):
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception as e:
                    print(f"[QueueManager] Warning creating {folder}: {e}")

    def _load_history(self) -> Dict[str, Any]:
        """
        Loads history and ensures both 'files' and 'hashes' dictionaries exist
        for bulletproof anti-duplicate verification.
        """
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Migrate older flat structure if necessary
                    if "files" not in data and "hashes" not in data:
                        migrated = {"files": {}, "hashes": {}}
                        for fname, rec in data.items():
                            migrated["files"][fname] = rec
                            f_hash = rec.get("file_hash")
                            if f_hash:
                                migrated["hashes"][f_hash] = rec
                        return migrated
                    return data
            except Exception as e:
                print(f"[QueueManager] Error loading history.json: {e}")
                return {"files": {}, "hashes": {}}
        return {"files": {}, "hashes": {}}

    def _save_history(self):
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[QueueManager] Error saving history.json: {e}")

    _GLOBAL_HASH_CACHE: Dict[Tuple[str, float, int], str] = {}

    def get_hash(self, video_path: str) -> str:
        """Returns cached or computed file hash using global (path, mtime, size) cache"""
        if not os.path.exists(video_path):
            return ""
        try:
            mtime = os.path.getmtime(video_path)
            size = os.path.getsize(video_path)
            key = (video_path, mtime, size)
            if key in QueueManager._GLOBAL_HASH_CACHE:
                return QueueManager._GLOBAL_HASH_CACHE[key]
            h = compute_file_hash(video_path)
            QueueManager._GLOBAL_HASH_CACHE[key] = h
            return h
        except Exception:
            return ""

    def scan_videos(self, target_folder: Optional[str] = None) -> List[str]:
        """Scans the specified or default video folder and returns all supported video file paths sorted by name"""
        folder = target_folder or self.video_folder
        if sys.platform != "win32" and isinstance(folder, str) and (folder.startswith("Z:") or folder.startswith("z:") or folder.startswith("Y:") or folder.startswith("y:")):
            folder = folder.replace("\\", "/")
            folder = folder[2:].lstrip("/")
            folder = os.path.join("/home/moes/storage", folder)
        if not folder or not os.path.exists(folder):
            return []

        videos = []
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith(self.SUPPORTED_EXTENSIONS):
                    full_path = os.path.join(root, file)
                    videos.append(full_path)

        videos.sort()
        return videos

    @staticmethod
    def get_lock_file_path(video_path: str) -> str:
        base_dir = os.path.dirname(os.path.abspath(video_path))
        base_name = os.path.basename(video_path)
        return os.path.join(base_dir, f".{base_name}.upload_lock")

    def is_video_locked(self, video_path: str) -> bool:
        """Checks if a video file is currently locked/being uploaded by another process."""
        lock_path = self.get_lock_file_path(video_path)
        if os.path.exists(lock_path):
            try:
                # If lock file is older than 2 hours, it's stale (crashed worker) -> clean it up
                mtime = os.path.getmtime(lock_path)
                if time.time() - mtime > 7200:
                    try:
                        os.remove(lock_path)
                    except Exception:
                        pass
                    return False
                return True
            except Exception:
                return False
        return False

    def acquire_video_lock(self, video_path: str) -> bool:
        """Atomically acquires an exclusive upload lock on the given video file."""
        lock_path = self.get_lock_file_path(video_path)
        if self.is_video_locked(video_path):
            return False
        try:
            with open(lock_path, "x", encoding="utf-8") as f:
                json.dump({"pid": os.getpid(), "locked_at": datetime.now().isoformat()}, f)
            return True
        except FileExistsError:
            return False
        except Exception:
            return False

    def release_video_lock(self, video_path: str):
        """Releases the upload lock for the video file."""
        lock_path = self.get_lock_file_path(video_path)
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass

    def is_already_uploaded(self, video_path: str, completed_folder: Optional[str] = None) -> Tuple[bool, str]:
        """
        High-speed multi-layer anti-duplicate check:
        1. Checks filename in history (Instant O(1), zero disk read!).
        2. Checks if matching file already exists in completed folder (Fast stat check).
        3. Checks digital fingerprint (SHA-256 hash) only if needed.
        
        Returns: (is_duplicate: bool, reason: str)
        """
        if not os.path.exists(video_path):
            return False, "File not found"

        basename = os.path.basename(video_path)
        files_map = self.history.get("files", {})
        hashes_map = self.history.get("hashes", {})

        # 0. Check in-progress lock (prevents duplicate simultaneous uploads across processes)
        if self.is_video_locked(video_path):
            return True, "ກຳລັງຖືກອັບໂຫຼດຢູ່ໂດຍອີກ Worker ໜຶ່ງ (In Progress Lock)"

        # 1. Check filename in history (Instant O(1) in-memory lookup)
        if basename in files_map:
            rec = files_map[basename]
            if rec.get("status") == "success":
                return True, f"ຊື່ໄຟລ໌ຊ້ຳ (ຊື່ '{basename}' ເຄີຍອັບໂຫຼດສຳເລັດແລ້ວ)"

        # 2. Check if identical file exists in completed directory (Fast metadata check)
        c_folder = completed_folder or self.completed_folder
        if c_folder and os.path.exists(c_folder):
            completed_dest = os.path.join(c_folder, basename)
            if os.path.exists(completed_dest):
                try:
                    if os.path.getsize(completed_dest) == os.path.getsize(video_path):
                        return True, f"ໄຟລ໌ມີຢູ່ແລ້ວໃນໂຟນເດີ completed ('{basename}')"
                except Exception:
                    pass

        # 3. Check digital content hash (cached in memory)
        f_hash = self.get_hash(video_path)
        if f_hash and f_hash in hashes_map:
            rec = hashes_map[f_hash]
            if rec.get("status") == "success":
                orig_name = rec.get("filename", basename)
                return True, f"ໄຟລ໌ຊ້ຳ (ເນື້ອຫາວິດີໂອຄືກັບ '{orig_name}' ທີ່ເຄີຍອັບໂຫຼດແລ້ວ)"

        return False, "ລໍຖ້າອັບໂຫຼດ (Pending)"

    def get_uploaded_page_ids(self, video_path: str) -> set:
        """
        Returns set of Page IDs that this video has already been uploaded to.
        Used to skip pages that already have this video when a new page is added.
        """
        basename = os.path.basename(video_path)
        files_map = self.history.get("files", {})
        uploaded_ids = set()

        rec = files_map.get(basename)
        if not rec:
            # Try by hash
            f_hash = self.get_hash(video_path)
            hashes_map = self.history.get("hashes", {})
            rec = hashes_map.get(f_hash) if f_hash else None

        if rec and rec.get("status") in ("success", "in_progress"):
            meta = rec.get("meta", {})
            target_pages = meta.get("target_pages", [])
            for tp in target_pages:
                if tp.get("success"):
                    pid = str(tp.get("page_id", "")).strip()
                    if pid:
                        uploaded_ids.add(pid)

        return uploaded_ids

    def record_page_success(self, video_path: str, page_info: dict, meta: Optional[dict] = None):
        """Immediately records that a video was successfully uploaded to a specific page."""
        basename = os.path.basename(video_path)
        f_hash = self.get_hash(video_path)

        if "files" not in self.history:
            self.history["files"] = {}
        if "hashes" not in self.history:
            self.history["hashes"] = {}

        rec = self.history["files"].get(basename) or (self.history["hashes"].get(f_hash) if f_hash else None)
        if not rec:
            rec = {
                "filename": basename,
                "original_path": video_path,
                "file_hash": f_hash,
                "status": "in_progress",
                "uploaded_at": datetime.now().isoformat(),
                "meta": meta or {}
            }
            self.history["files"][basename] = rec
            if f_hash:
                self.history["hashes"][f_hash] = rec

        if "meta" not in rec:
            rec["meta"] = {}
        target_pages = rec["meta"].setdefault("target_pages", [])
        pid = str(page_info.get("page_id", "")).strip()

        existing = next((p for p in target_pages if str(p.get("page_id", "")).strip() == pid), None)
        if existing:
            existing["success"] = True
            existing["page_name"] = page_info.get("page_name", "")
        else:
            target_pages.append({
                "page_name": page_info.get("page_name", ""),
                "page_id": pid,
                "success": True
            })

        self._save_history()

    def needs_upload_to_pages(self, video_path: str, target_pages: list, completed_folder: Optional[str] = None) -> Tuple[bool, list, list]:
        """
        Smart check: determines which pages still need this video.
        
        Returns: (needs_any_upload: bool, pages_needing_upload: list, pages_already_done: list)
        - If ALL pages already have it → (False, [], all_pages)
        - If SOME pages are missing → (True, missing_pages, done_pages)  
        - If NO pages have it → (True, all_pages, [])
        """
        if not os.path.exists(video_path):
            return False, [], target_pages

        uploaded_ids = self.get_uploaded_page_ids(video_path)
        if not uploaded_ids:
            # Never uploaded at all - need all pages
            return True, list(target_pages), []

        pages_needing = []
        pages_done = []
        for p in target_pages:
            pid = str(p.get("page_id", "")).strip()
            if pid in uploaded_ids:
                pages_done.append(p)
            else:
                pages_needing.append(p)

        if not pages_needing:
            return False, [], pages_done
        return True, pages_needing, pages_done

    def get_pending_videos(self, target_folder: Optional[str] = None, completed_folder: Optional[str] = None, target_pages: Optional[list] = None) -> List[str]:
        """
        Returns list of video paths that need uploading.
        
        If target_pages is provided, also scans completed folder for videos
        that were uploaded to some pages but not all (backfill for new pages).
        """
        all_videos = self.scan_videos(target_folder=target_folder)
        pending = []

        if target_pages:
            # Smart mode: check per-page status
            for v in all_videos:
                needs, _, _ = self.needs_upload_to_pages(v, target_pages, completed_folder)
                if needs:
                    pending.append(v)

            # Also check completed folder for backfill candidates
            c_folder = completed_folder or self.completed_folder
            if c_folder and os.path.exists(c_folder):
                for f in sorted(os.listdir(c_folder)):
                    fp = os.path.join(c_folder, f)
                    if not os.path.isfile(fp):
                        continue
                    ext = os.path.splitext(f)[1].lower()
                    if ext not in self.VIDEO_EXTS and ext not in self.IMAGE_EXTS:
                        continue
                    # Check if this completed file needs upload to new pages
                    needs, _, _ = self.needs_upload_to_pages(fp, target_pages)
                    if needs and fp not in pending:
                        pending.append(fp)
        else:
            # Legacy mode: simple duplicate check
            for v in all_videos:
                is_dup, _ = self.is_already_uploaded(v, completed_folder=completed_folder)
                if not is_dup:
                    pending.append(v)

        return pending

    def mark_completed(self, video_path: str, meta: Optional[Dict[str, Any]] = None, custom_dest_folder: Optional[str] = None):
        """
        Marks video as successfully uploaded, records both filename and SHA-256 hash,
        and optionally moves file to completed folder.
        """
        basename = os.path.basename(video_path)
        f_hash = self.get_hash(video_path)
        record = {
            "filename": basename,
            "original_path": video_path,
            "file_hash": f_hash,
            "file_size": os.path.getsize(video_path) if os.path.exists(video_path) else 0,
            "status": "success",
            "uploaded_at": datetime.now().isoformat(),
            "meta": meta or {}
        }

        if "files" not in self.history:
            self.history["files"] = {}
        if "hashes" not in self.history:
            self.history["hashes"] = {}

        self.history["files"][basename] = record
        if f_hash:
            self.history["hashes"][f_hash] = record
        self._save_history()

        dest_dir = custom_dest_folder or self.completed_folder
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)

        if self.move_completed and os.path.exists(video_path) and dest_dir:
            try:
                # Find companion .txt before moving original media file
                txt_comp = self.find_companion_text_file(video_path)

                dest = os.path.join(dest_dir, basename)
                if os.path.exists(dest):
                    name, ext = os.path.splitext(basename)
                    dest = os.path.join(dest_dir, f"{name}_{int(datetime.now().timestamp())}{ext}")
                shutil.move(video_path, dest)
                print(f"[QueueManager] Moved {basename} to completed folder: {dest_dir}")

                # Also move companion .txt if present
                if txt_comp and os.path.exists(txt_comp):
                    t_base = os.path.basename(txt_comp)
                    t_dest = os.path.join(dest_dir, t_base)
                    if os.path.exists(t_dest):
                        t_name, t_ext = os.path.splitext(t_base)
                        t_dest = os.path.join(dest_dir, f"{t_name}_{int(datetime.now().timestamp())}{t_ext}")
                    shutil.move(txt_comp, t_dest)
                    print(f"[QueueManager] Moved companion caption file {t_base} to: {dest_dir}")
            except Exception as e:
                print(f"[QueueManager] Could not move {basename} to completed: {e}")
        self.release_video_lock(video_path)

    def mark_failed(self, video_path: str, error_message: str, custom_failed_folder: Optional[str] = None):
        """Marks video as failed in history and optionally moves to failed folder"""
        basename = os.path.basename(video_path)
        f_hash = self.get_hash(video_path)
        record = {
            "filename": basename,
            "original_path": video_path,
            "file_hash": f_hash,
            "status": "failed",
            "last_attempt": datetime.now().isoformat(),
            "error": str(error_message)
        }
        if "files" not in self.history:
            self.history["files"] = {}
        self.history["files"][basename] = record
        self._save_history()

        failed_dir = custom_failed_folder or self.failed_folder
        if failed_dir and os.path.exists(video_path):
            try:
                txt_comp = self.find_companion_text_file(video_path)
                os.makedirs(failed_dir, exist_ok=True)
                dest = os.path.join(failed_dir, basename)
                if os.path.exists(dest):
                    name, ext = os.path.splitext(basename)
                    dest = os.path.join(failed_dir, f"{name}_{int(datetime.now().timestamp())}{ext}")
                shutil.move(video_path, dest)

                # Also move companion .txt to failed folder if present
                if txt_comp and os.path.exists(txt_comp):
                    t_base = os.path.basename(txt_comp)
                    t_dest = os.path.join(failed_dir, t_base)
                    shutil.move(txt_comp, t_dest)
            except Exception:
                pass
        self.release_video_lock(video_path)

    def get_stats(self, target_folder: Optional[str] = None, completed_folder: Optional[str] = None, fast: bool = True) -> Dict[str, int]:
        all_videos = self.scan_videos(target_folder=target_folder)
        files_map = self.history.get("files", {})
        success_count = sum(1 for r in files_map.values() if r.get("status") == "success")
        failed_count = sum(1 for r in files_map.values() if r.get("status") == "failed")

        if fast:
            # Ultra-fast O(1) in-memory check without touching slow network disk or computing SHA-256 hashes
            pending_count = 0
            for v in all_videos:
                b = os.path.basename(v)
                if b in files_map and files_map[b].get("status") == "success":
                    continue
                pending_count += 1
            duplicates_count = len(all_videos) - pending_count
            return {
                "total_in_folder": len(all_videos),
                "pending_in_folder": pending_count,
                "duplicates_in_folder": max(0, duplicates_count),
                "total_uploaded": success_count,
                "total_failed": failed_count
            }

        pending = self.get_pending_videos(target_folder=target_folder, completed_folder=completed_folder)
        duplicates_count = len(all_videos) - len(pending)
        return {
            "total_in_folder": len(all_videos),
            "pending_in_folder": len(pending),
            "duplicates_in_folder": max(0, duplicates_count),
            "total_uploaded": success_count,
            "total_failed": failed_count
        }

    def has_posted_cta_today(self, page_id: str) -> bool:
        """Checks if a follower CTA post has already been posted to this page today"""
        today = datetime.now().strftime("%Y-%m-%d")
        cta_dates = self.history.get("cta_posted_dates", {})
        return cta_dates.get(str(page_id).strip()) == today

    def record_cta_posted_today(self, page_id: str, page_name: str = ""):
        """Records today's date for CTA post for this page to enforce 1 post/day"""
        today = datetime.now().strftime("%Y-%m-%d")
        if "cta_posted_dates" not in self.history:
            self.history["cta_posted_dates"] = {}
        self.history["cta_posted_dates"][str(page_id).strip()] = today
        self._save_history()

    def restore_completed_videos(self) -> int:
        """
        Restores all files from completed_folder back to video_folder,
        and resets their status in history.json to 'pending' (removing duplicate locks).
        Returns number of restored videos.
        """
        if not os.path.exists(self.completed_folder):
            return 0

        restored_count = 0
        completed_files = [f for f in os.listdir(self.completed_folder) if f.lower().endswith(self.SUPPORTED_EXTENSIONS)]

        files_map = self.history.get("files", {})
        hashes_map = self.history.get("hashes", {})

        for fname in completed_files:
            src = os.path.join(self.completed_folder, fname)
            dest = os.path.join(self.video_folder, fname)

            try:
                # If destination already exists with same name, resolve conflict
                if os.path.exists(dest):
                    if os.path.getsize(dest) == os.path.getsize(src):
                        os.remove(src)
                    else:
                        base, ext = os.path.splitext(fname)
                        dest = os.path.join(self.video_folder, f"{base}_restored{ext}")
                        shutil.move(src, dest)
                else:
                    shutil.move(src, dest)

                restored_count += 1
            except Exception as e:
                print(f"[QueueManager] Warning moving {fname} to {dest}: {e}")

            # Reset history record to pending so it will not be blocked as duplicate
            if fname in files_map:
                files_map[fname]["status"] = "pending"
                files_map[fname]["restored_at"] = datetime.now().isoformat()
                f_hash = files_map[fname].get("file_hash")
                if f_hash and f_hash in hashes_map:
                    del hashes_map[f_hash]

        self._save_history()
        self._hash_cache.clear()
        print(f"[QueueManager] Successfully restored {restored_count} videos back to {self.video_folder}.")
        return restored_count

    def update_video_history(self, filename: str, new_title: str, new_caption: str, new_status: Optional[str] = None, requeue: bool = False) -> bool:
        """
        Updates title, caption, and optional status of a video in history.
        If requeue is True or new_status is 'pending', resets hash duplicate locks
        and moves file back to video folder if it was in completed folder.
        """
        files_map = self.history.get("files", {})
        if filename not in files_map:
            files_map[filename] = {
                "filename": filename,
                "title": new_title,
                "caption": new_caption,
                "status": "pending" if requeue else (new_status or "pending"),
                "meta": {
                    "title": new_title,
                    "caption": new_caption
                }
            }
        else:
            rec = files_map[filename]
            rec["title"] = new_title
            rec["caption"] = new_caption
            if "meta" not in rec or not isinstance(rec["meta"], dict):
                rec["meta"] = {}
            rec["meta"]["title"] = new_title
            rec["meta"]["caption"] = new_caption
            
            target_status = "pending" if requeue else (new_status or rec.get("status", "pending"))
            rec["status"] = target_status
            
            if requeue or target_status == "pending":
                f_hash = rec.get("file_hash")
                if f_hash and f_hash in self.history.get("hashes", {}):
                    del self.history["hashes"][f_hash]

        effective_status = "pending" if requeue else (new_status or files_map[filename].get("status"))
        # If marked as pending or requeue, check if file is in completed folder and move back to video_folder
        if effective_status == "pending":
            c_path = os.path.join(self.completed_folder, filename)
            v_path = os.path.join(self.video_folder, filename)
            if os.path.exists(c_path) and not os.path.exists(v_path):
                try:
                    shutil.move(c_path, v_path)
                except Exception as e:
                    print(f"[QueueManager] Warning moving {filename} back: {e}")

        self._save_history()
        self._hash_cache.clear()
        return True
