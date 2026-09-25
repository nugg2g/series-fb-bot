import os
import sys
import argparse
import json
import time
import threading

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

from core.engine import ReelUploadEngine
from core.browser_manager import BrowserManager
from core.queue_manager import QueueManager
from core.web_monitor import start_web_monitor

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

        # Start Web Monitor and Cloud Relay Sync (allows remote control & live dashboard on Render)
        if config.get("web_monitor", {}).get("enabled", True):
            def handle_remote_action(action: str, payload: dict = None):
                payload = payload or {}
                if action == "pause":
                    engine.pause()
                elif action == "resume":
                    engine.resume()
                elif action in ["skip_delay", "upload_now", "skip_cooldown"]:
                    engine.skip_delay()
                elif action == "stop":
                    engine.stop()
                elif action == "post_cta":
                    try:
                        # trigger CTA in background
                        threading.Thread(target=engine.post_follower_cta, daemon=True).start()
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error running CTA: {ex}")
                elif action == "switch_page":
                    p_id = str(payload.get("page_id", "")).strip()
                    p_name = payload.get("page_name", "")
                    if p_id:
                        config["page_id"] = p_id
                        config["page_name"] = p_name
                        engine.apply_config(config)
                        try:
                            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                                json.dump(config, f, ensure_ascii=False, indent=2)
                        except Exception:
                            pass
                elif action == "update_page_id":
                    g_id = payload.get("group_id")
                    p_idx = payload.get("page_index")
                    new_id = str(payload.get("page_id", "")).strip()
                    for grp in config.get("page_groups", []):
                        if grp.get("group_id") == g_id:
                            pages = grp.get("pages", [])
                            if 0 <= p_idx < len(pages):
                                pages[p_idx]["page_id"] = new_id
                                engine.apply_config(config)
                                try:
                                    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                                        json.dump(config, f, ensure_ascii=False, indent=2)
                                except Exception:
                                    pass
                                break
                elif action == "update_settings":
                    try:
                        curr = load_config()
                        # Apply fields from payload
                        for k in ["delay_min_minutes", "delay_max_minutes", "randomize_delay",
                                  "delay_between_posts_minutes", "title_prefix", "caption_template",
                                  "tags_count", "hashtag_pool", "mark_as_ai_content",
                                  "strict_page_guard", "auto_watch_new_files", "cta_post_enabled",
                                  "cta_post_interval_reels"]:
                            if k in payload:
                                curr[k] = payload[k]
                        if "ai_caption" in payload and isinstance(payload["ai_caption"], dict):
                            curr.setdefault("ai_caption", {}).update(payload["ai_caption"])

                        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                            json.dump(curr, f, ensure_ascii=False, indent=2)
                        config.update(curr)
                        engine.apply_config(curr)
                        print("✅ [WebMonitor] Updated and dynamically applied new settings to running bot!")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error updating settings: {ex}")

            try:
                start_web_monitor(config, action_callback=handle_remote_action)
            except Exception as e:
                print(f"⚠️ [WebMonitor] Error starting monitor: {e}")

        try:
            engine._run_loop()
        except KeyboardInterrupt:
            print("\n🛑 Stopped by user.")
            engine.stop()
        return

    parser.print_help()

if __name__ == "__main__":
    main()
