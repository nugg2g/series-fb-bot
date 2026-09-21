import os
import sys
import argparse
import json
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.engine import ReelUploadEngine
from core.browser_manager import BrowserManager
from core.queue_manager import QueueManager

CONFIG_PATH = os.path.abspath("./config.json")

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def main():
    parser = argparse.ArgumentParser(description="Facebook Page Reels Auto Uploader (CLI)")
    parser.add_argument("--login", action="store_true", help="Open browser to log in to Facebook / Meta Business Suite")
    parser.add_argument("--start", action="store_true", help="Start batch upload process")
    parser.add_argument("--check", action="store_true", help="Check queue status and pending videos")
    parser.add_argument("--folder", type=str, help="Override video folder path")
    parser.add_argument("--delay", type=int, help="Override delay between posts (minutes)")
    parser.add_argument("--mode", type=str, choices=["now", "schedule"], help="Post mode: now or schedule")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    args = parser.parse_args()
    config = load_config()

    if args.folder:
        config["video_folder"] = args.folder
    if args.delay:
        config["delay_between_posts_minutes"] = args.delay
    if args.mode:
        config["post_mode"] = args.mode
    if args.headless:
        config["headless"] = True

    if args.login:
        print("🌐 Opening browser for manual login...")
        mgr = BrowserManager(config)
        page = mgr.open_for_manual_login()
        print("👉 Please log in to Facebook in the opened browser window.")
        print("👉 Press Enter in this terminal after you have finished logging in...")
        try:
            input()
        except KeyboardInterrupt:
            pass
        finally:
            mgr.close()
        print("✅ Session saved to ./user_profile. You can now start uploading!")
        return

    if args.check:
        qm = QueueManager(config)
        stats = qm.get_stats()
        pending = qm.get_pending_videos()
        print("\n================== QUEUE STATUS ==================")
        print(f"Total videos in folder: {stats['total_in_folder']}")
        print(f"Pending to upload:     {stats['pending_in_folder']}")
        print(f"Uploaded successfully: {stats['total_uploaded']}")
        print("--------------------------------------------------")
        for i, v in enumerate(pending[:10], 1):
            print(f"  {i}. {os.path.basename(v)}")
        if len(pending) > 10:
            print(f"  ... and {len(pending) - 10} more.")
        print("==================================================\n")
        return

    if args.start:
        engine = ReelUploadEngine(config, log_cb=print)
        try:
            engine._run_loop()
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
            engine.stop()
        return

    parser.print_help()

if __name__ == "__main__":
    main()
