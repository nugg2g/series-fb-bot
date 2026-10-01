import os
import sys
import argparse
import json
import time
import threading

# Ensure working directory is always the script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

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

CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

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
    parser.add_argument("--add-page", action="store_true", help="Add or update a page in pages_pipeline")
    parser.add_argument("--page-name", type=str, help="Name of the Facebook page")
    parser.add_argument("--page-id", type=str, help="ID of the Facebook page")
    parser.add_argument("--pick-mode", type=str, choices=["random", "sequential"], default="random", help="Pick mode: random or sequential")

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
    if args.add_page:
        if not args.page_id or not args.page_name:
            print("❌ Error: Both --page-name and --page-id are required!")
            return
        v_folder = args.folder or "/home/moes/storage/Reels/Movies FB"
        p_mode = args.pick_mode or "random"
        pipeline = config.setdefault("pages_pipeline", [])
        new_entry = {
            "page_id": str(args.page_id).strip(),
            "page_name": str(args.page_name).strip(),
            "enabled": True,
            "video_folder": v_folder,
            "completed_folder": "./completed/shared" if "/Movies FB" in v_folder and "Dedicated" not in v_folder else "./completed/dedicated",
            "failed_folder": "./failed/shared" if "/Movies FB" in v_folder and "Dedicated" not in v_folder else "./failed/dedicated",
            "pick_mode": p_mode,
            "content_type": "china_drama" if "Movies FB" in v_folder and "Dedicated" not in v_folder else "general",
            "title_prefix": "[เต็มเรื่อง] " if "Movies FB" in v_folder and "Dedicated" not in v_folder else "",
            "title_mode": "filename_clean",
            "caption_template": config.get("caption_template", "🎬 {title}\n\n{tags}"),
            "hashtag_pool": config.get("hashtag_pool", ["#reels", "#fyp"]),
            "cta_post_enabled": False
        }
        found = False
        for idx, p in enumerate(pipeline):
            if str(p.get("page_id", "")).strip() == str(args.page_id).strip():
                pipeline[idx].update(new_entry)
                found = True
                break
        if not found:
            pipeline.append(new_entry)

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✅ Successfully added/updated Page in pipeline: '{args.page_name}' (ID: {args.page_id}, Mode: {p_mode})")
        return

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
        from core.single_instance import ensure_single_instance
        if not ensure_single_instance("ThaiMovieDrama_ReelsBot_PG2"):
            print("🚨 [SingleInstance] Facebook Reels Auto Bot is already running! Exiting duplicate process...")
            sys.exit(0)

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
                elif action == "retry_failed":
                    try:
                        res = engine.queue_mgr.retry_failed_videos()
                        print(f"✅ [WebMonitor] Retried failed videos: {res} items reset to pending")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error retrying failed videos: {ex}")
                elif action == "clear_failed":
                    try:
                        res = engine.queue_mgr.clear_failed_history()
                        print(f"✅ [WebMonitor] Cleared failed history: {res} items cleared")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error clearing failed history: {ex}")
                elif action == "update_settings":
                    try:
                        curr = load_config()
                        # Apply fields from payload
                        for k in ["delay_min_minutes", "delay_max_minutes", "randomize_delay",
                                  "delay_between_posts_minutes", "pacing_mode",
                                  "inter_page_delay_min_minutes", "inter_page_delay_max_minutes",
                                  "round_cooldown_min_hours", "round_cooldown_max_hours",
                                  "title_prefix", "caption_template",
                                  "tags_count", "hashtag_pool", "mark_as_ai_content",
                                  "strict_page_guard", "auto_watch_new_files", "cta_post_enabled",
                                  "cta_post_interval_reels"]:
                            if k in payload:
                                curr[k] = payload[k]
                        if "caption_template" in payload:
                            curr["caption_template"] = payload["caption_template"]
                            for grp in curr.get("page_groups", []):
                                grp["caption_template"] = payload["caption_template"]
                        if "ai_caption" in payload and isinstance(payload["ai_caption"], dict):
                            curr.setdefault("ai_caption", {}).update(payload["ai_caption"])

                        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                            json.dump(curr, f, ensure_ascii=False, indent=2)
                        config.update(curr)
                        engine.apply_config(curr)
                        print("✅ [WebMonitor] Updated and dynamically applied new settings to running bot!")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error updating settings: {ex}")
                elif action == "add_pipeline_page":
                    try:
                        p_name = str(payload.get("page_name", "")).strip()
                        p_id = str(payload.get("page_id", "")).strip()
                        v_folder = str(payload.get("video_folder", "/home/moes/storage/Reels/Movies FB")).strip()
                        pick_mode = str(payload.get("pick_mode", "random")).strip().lower()
                        content_type = str(payload.get("content_type", "china_drama")).strip()
                        title_prefix = payload.get("title_prefix")
                        if title_prefix is None:
                            title_prefix = "[เต็มเรื่อง] " if content_type == "china_drama" else ""

                        curr = load_config()
                        pipeline = curr.setdefault("pages_pipeline", [])

                        default_tpl = curr.get("caption_template", "🎬 {title}\n\n{tags}")
                        default_tags = curr.get("hashtag_pool", ["#reels", "#fyp"])

                        new_entry = {
                            "page_id": p_id,
                            "page_name": p_name,
                            "enabled": True,
                            "video_folder": v_folder,
                            "completed_folder": "./completed/shared" if "/Movies FB" in v_folder and "Dedicated" not in v_folder else "./completed/dedicated",
                            "failed_folder": "./failed/shared" if "/Movies FB" in v_folder and "Dedicated" not in v_folder else "./failed/dedicated",
                            "pick_mode": pick_mode,
                            "content_type": content_type,
                            "title_prefix": title_prefix,
                            "title_mode": "filename_clean",
                            "caption_template": default_tpl,
                            "hashtag_pool": default_tags,
                            "cta_post_enabled": False
                        }
                        found = False
                        for idx, p in enumerate(pipeline):
                            if str(p.get("page_id", "")).strip() == p_id:
                                pipeline[idx].update(new_entry)
                                found = True
                                break
                        if not found:
                            pipeline.append(new_entry)

                        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                            json.dump(curr, f, ensure_ascii=False, indent=2)
                        config.update(curr)
                        engine.apply_config(curr)
                        print(f"✅ [WebMonitor] Added/Updated Page in pipeline: '{p_name}' (ID: {p_id}, Mode: {pick_mode})")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error adding pipeline page: {ex}")
                elif action == "toggle_pipeline_page":
                    try:
                        p_id = str(payload.get("page_id", "")).strip()
                        curr = load_config()
                        for p in curr.get("pages_pipeline", []):
                            if str(p.get("page_id", "")).strip() == p_id:
                                p["enabled"] = not p.get("enabled", True)
                                break
                        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                            json.dump(curr, f, ensure_ascii=False, indent=2)
                        config.update(curr)
                        engine.apply_config(curr)
                        print(f"✅ [WebMonitor] Toggled pipeline page ID: {p_id}")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error toggling pipeline page: {ex}")
                elif action == "delete_pipeline_page":
                    try:
                        p_id = str(payload.get("page_id", "")).strip()
                        curr = load_config()
                        pipeline = [p for p in curr.get("pages_pipeline", []) if str(p.get("page_id", "")).strip() != p_id]
                        curr["pages_pipeline"] = pipeline
                        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                            json.dump(curr, f, ensure_ascii=False, indent=2)
                        config.update(curr)
                        engine.apply_config(curr)
                        print(f"✅ [WebMonitor] Deleted pipeline page ID: {p_id}")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error deleting pipeline page: {ex}")
                elif action == "update_pipeline_page_folder":
                    try:
                        p_id = str(payload.get("page_id", "")).strip()
                        v_folder = str(payload.get("video_folder", "")).strip()
                        if p_id and v_folder:
                            curr = load_config()
                            for p in curr.get("pages_pipeline", []):
                                if str(p.get("page_id", "")).strip() == p_id:
                                    p["video_folder"] = v_folder
                                    break
                            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                                json.dump(curr, f, ensure_ascii=False, indent=2)
                            config.update(curr)
                            engine.apply_config(curr)
                            print(f"✅ [WebMonitor] Updated Page '{p_id}' folder to: {v_folder}")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error updating page folder: {ex}")
                elif action in ["update_pipeline_page_pick_mode", "toggle_pipeline_page_pick_mode"]:
                    try:
                        p_id = str(payload.get("page_id", "")).strip()
                        new_mode = str(payload.get("pick_mode", "")).strip().lower()
                        if p_id:
                            curr = load_config()
                            for p in curr.get("pages_pipeline", []):
                                if str(p.get("page_id", "")).strip() == p_id:
                                    if new_mode in ["random", "sequential"]:
                                        p["pick_mode"] = new_mode
                                    else:
                                        p["pick_mode"] = "sequential" if p.get("pick_mode", "random") == "random" else "random"
                                    break
                            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                                json.dump(curr, f, ensure_ascii=False, indent=2)
                            config.update(curr)
                            engine.apply_config(curr)
                            print(f"✅ [WebMonitor] Updated Page '{p_id}' pick_mode to: {p.get('pick_mode')}")
                    except Exception as ex:
                        print(f"⚠️ [WebMonitor] Error updating pick_mode: {ex}")
                elif action == "restart":
                    print("🔄 [WebMonitor] Restart command received! Restarting bot process...")
                    try:
                        engine.stop()
                    except Exception:
                        pass
                    time.sleep(2)
                    # Re-exec the same process to reload all code from disk
                    os.execv(sys.executable, [sys.executable] + sys.argv)

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
