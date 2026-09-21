"""
web_server.py — Cloud & Local Standalone Web Dashboard for Facebook Reels Bot
-----------------------------------------------------------------------------
ຄວາມປອດໄພລະດັບສູງ (Security Hardened):
1. ລະບົບປ້ອງກັນການເຂົ້າເຖິງດ້ວຍ PIN Code & Cryptographic Session Token (HMAC-SHA256).
2. Rate Limiting: ປ້ອງກັນການ Brute-force ລະຫັດ PIN (ຜິດ 5 ຄັ້ງ Block 5 ນາທີ).
3. Cloud Relay Shared Secret Token (`X-Bot-Token`): ປ້ອງກັນຄົນແປກໜ້າຍິງຂໍ້ມູນປອມເຂົ້າ `/api/sync`.
4. Input Sanitization: ກວດສອບ Page ID ແລະ Delays ໃຫ້ປອດໄພຈາກ Injection.
5. Zero Secrets in Client API: ບໍ່ມີການສົ່ງ API Keys ຫຼື Cookies ອອກໄປຫາ Browser.
"""

import os
import sys
import time
import json
import logging
import hashlib
import hmac
import re
from datetime import datetime
from typing import Dict, Any, List
from flask import Flask, jsonify, request, render_template_string

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("web_server")
log_flask = logging.getLogger("werkzeug")
log_flask.setLevel(logging.ERROR)

app = Flask(__name__)

# Security Configuration
def load_security_settings():
    pin = os.environ.get("ACCESS_PIN", "").strip()
    token = os.environ.get("SYNC_SECRET_TOKEN", "").strip()
    
    # Try reading from local config.json if available
    try:
        cfg_path = os.path.abspath("./config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                c = json.load(f)
                wm = c.get("web_monitor", {})
                if not pin:
                    pin = str(wm.get("access_pin", "")).strip()
                if not token:
                    token = str(wm.get("sync_secret_token", "")).strip()
    except Exception:
        pass

    return pin or "8888", token or "b0015017e92db8567376789a3d0c12b0"

ACCESS_PIN, SYNC_SECRET_TOKEN = load_security_settings()
SECRET_SALT = os.environ.get("SECRET_SALT", "reels_bot_secure_salt_9988")

# Rate Limiting Tracker: {ip: [timestamps]}
FAILED_ATTEMPTS: Dict[str, List[float]] = {}


def get_client_ip() -> str:
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def is_rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = FAILED_ATTEMPTS.get(ip, [])
    attempts = [t for t in attempts if now - t < 300]
    FAILED_ATTEMPTS[ip] = attempts
    return len(attempts) >= 5


def record_failed_attempt(ip: str):
    now = time.time()
    if ip not in FAILED_ATTEMPTS:
        FAILED_ATTEMPTS[ip] = []
    FAILED_ATTEMPTS[ip].append(now)


def clear_failed_attempts(ip: str):
    if ip in FAILED_ATTEMPTS:
        FAILED_ATTEMPTS.pop(ip, None)


def generate_session_token(pin: str) -> str:
    return hmac.new(SECRET_SALT.encode(), pin.encode(), hashlib.sha256).hexdigest()


def verify_auth(req) -> bool:
    auth_header = req.headers.get("Authorization", "").strip()
    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif req.headers.get("X-Access-Token"):
        token = req.headers.get("X-Access-Token").strip()
    elif req.args.get("token"):
        token = req.args.get("token").strip()

    valid_token = generate_session_token(ACCESS_PIN)
    if token and hmac.compare_digest(token, valid_token):
        return True

    direct_pin = req.headers.get("X-Access-PIN", "").strip()
    if direct_pin and hmac.compare_digest(direct_pin, ACCESS_PIN):
        return True

    return False


# In-memory shared state for Cloud Relay
SERVER_STATE = {
    "status": "idle",
    "progress_pct": 0,
    "progress_text": "ພ້ອມເຮັດວຽກ (Ready)",
    "current_video": {
        "filename": "",
        "title": "",
        "size_mb": 0,
        "page_name": "",
        "group_name": ""
    },
    "page_name": "ซี่รีย์จีน เต็มเรื่อง",
    "page_id": "1332661329928072",
    "is_safe": True,
    "page_groups": [],
    "queue_stats": {
        "total_in_folder": 0,
        "pending_in_folder": 0,
        "duplicates_in_folder": 0,
        "total_uploaded": 0,
        "total_failed": 0
    },
    "queue_items": [],
    "recent_logs": [
        "[System] 🛡️ Web Dashboard Security Server ເລີ່ມຕົ້ນສຳເລັດແລ້ວ (PIN Lock Protected)."
    ],
    "last_sync_time": 0,
    "bot_connected": False,
    "server_time": ""
}

# Queue of pending commands to be picked up by the local bot
PENDING_COMMANDS: List[Dict[str, Any]] = []

MOBILE_UI_HTML = """<!DOCTYPE html>
<html lang="lo">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>Reels Bot Mobile Manager</title>
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <style>
    :root {
      --bg: #090b10;
      --card: #131722;
      --card-border: #23293e;
      --accent: #38bdf8;
      --accent-grad: linear-gradient(135deg, #2563eb, #7c3aed, #06b6d4);
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --purple: #a855f7;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Roboto, "Sarabun", "Phetsarath OT", sans-serif;
      padding-bottom: 75px;
      font-size: 14px;
      line-height: 1.4;
    }
    /* Sticky Top Header */
    .top-bar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(19, 23, 34, 0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--card-border);
      padding: 10px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .brand-title {
      font-size: 16px;
      font-weight: 800;
      letter-spacing: -0.3px;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .brand-title span {
      background: var(--accent-grad);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .top-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .conn-badge {
      display: flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 20px;
    }
    .conn-online {
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .conn-offline {
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.4);
    }
    .pulse-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: currentColor;
      animation: pulse 1.6s infinite;
    }
    @keyframes pulse {
      0% { opacity: 0.4; }
      50% { opacity: 1; }
      100% { opacity: 0.4; }
    }

    /* Tab navigation at bottom */
    .bottom-nav {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 100;
      background: rgba(19, 23, 34, 0.96);
      backdrop-filter: blur(14px);
      border-top: 1px solid var(--card-border);
      display: flex;
      justify-content: space-around;
      padding: 8px 4px;
    }
    .nav-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 3px;
      color: var(--text-muted);
      font-size: 10px;
      font-weight: 600;
      cursor: pointer;
      flex: 1;
      padding: 4px 0;
      transition: all 0.2s;
    }
    .nav-item.active {
      color: var(--accent);
    }
    .nav-item svg {
      width: 20px;
      height: 20px;
      fill: currentColor;
    }

    /* Container */
    .container {
      padding: 12px;
      max-width: 600px;
      margin: 0 auto;
    }

    /* Cards */
    .card {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 14px;
      margin-bottom: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }
    .card-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 10px;
    }
    .card-title {
      font-size: 13px;
      font-weight: 700;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 6px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
    }

    /* Hero Progress */
    .hero-status-box {
      background: #0d0f17;
      border-radius: 12px;
      padding: 12px;
      border: 1px solid #1c2236;
      margin-bottom: 12px;
    }
    .hero-top-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .status-pill {
      font-size: 12px;
      font-weight: 800;
      padding: 4px 10px;
      border-radius: 20px;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .status-uploading { background: rgba(56, 189, 248, 0.2); color: var(--accent); border: 1px solid var(--accent); }
    .status-paused { background: rgba(245, 158, 11, 0.2); color: var(--warning); border: 1px solid var(--warning); }
    .status-idle { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid var(--success); }

    .progress-track {
      background: #171a29;
      height: 26px;
      border-radius: 13px;
      overflow: hidden;
      position: relative;
      border: 1px solid #2d334d;
      margin: 8px 0;
    }
    .progress-fill {
      height: 100%;
      width: 0%;
      background: var(--accent-grad);
      transition: width 0.4s ease;
      border-radius: 13px;
    }
    .progress-text-overlay {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      font-size: 12px;
      font-weight: 800;
      color: #fff;
      text-shadow: 0 1px 3px rgba(0,0,0,0.8);
      white-space: nowrap;
    }
    .current-step-lbl {
      font-size: 12px;
      color: var(--accent);
      font-weight: 600;
      margin-top: 4px;
    }
    .active-video-lbl {
      font-size: 13px;
      font-weight: 700;
      color: #fde047;
      margin-top: 6px;
      word-break: break-all;
    }

    /* Action Buttons */
    .btn-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 8px;
    }
    .btn {
      padding: 13px 12px;
      border-radius: 10px;
      border: none;
      font-weight: 700;
      font-size: 13px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      color: white;
      transition: all 0.15s;
    }
    .btn:active {
      transform: scale(0.97);
      opacity: 0.85;
    }
    .btn-start { background: linear-gradient(135deg, #2563eb, #1d4ed8); }
    .btn-pause { background: linear-gradient(135deg, #d97706, #b45309); }
    .btn-resume { background: linear-gradient(135deg, #059669, #047857); }
    .btn-stop { background: linear-gradient(135deg, #dc2626, #b91c1c); }
    .btn-cta {
      background: linear-gradient(135deg, #7c3aed, #9333ea);
      grid-column: span 2;
      padding: 14px;
      font-size: 14px;
    }
    .btn-secondary {
      background: #1e2438;
      border: 1px solid #2d3550;
      color: var(--text);
    }

    /* Stats 4-Grid */
    .stat-quad {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
    }
    .stat-cell {
      background: #0e111a;
      border: 1px solid #1c2236;
      border-radius: 10px;
      padding: 10px;
      text-align: center;
    }
    .stat-num {
      font-size: 22px;
      font-weight: 900;
    }
    .stat-sub {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 2px;
    }

    /* Page Groups */
    .group-card {
      background: #0d0f17;
      border-radius: 12px;
      padding: 12px;
      border: 1px solid #20273c;
      margin-bottom: 10px;
    }
    .group-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .group-name {
      font-size: 13px;
      font-weight: 800;
    }
    .page-row {
      background: #131724;
      border-radius: 8px;
      padding: 10px;
      margin-top: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border: 1px solid #1f253a;
    }
    .page-row.active-row {
      border: 1px solid var(--accent);
      background: rgba(56, 189, 248, 0.08);
    }
    .page-info-name {
      font-size: 13px;
      font-weight: 700;
      color: #fff;
    }
    .page-info-id {
      font-size: 11px;
      color: var(--text-muted);
    }
    .page-actions {
      display: flex;
      gap: 6px;
    }
    .btn-sm {
      padding: 6px 9px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      border: none;
      cursor: pointer;
      color: white;
    }

    /* Inputs */
    .input-field {
      width: 100%;
      background: #0d0f17;
      border: 1px solid #23293e;
      border-radius: 8px;
      padding: 10px 12px;
      color: #fff;
      font-size: 13px;
      margin-top: 4px;
      outline: none;
    }
    .input-field:focus {
      border-color: var(--accent);
    }
    .form-group {
      margin-bottom: 12px;
    }
    .form-lbl {
      font-size: 11px;
      font-weight: 700;
      color: var(--text-muted);
      text-transform: uppercase;
    }

    /* Terminal Log */
    .term-box {
      background: #07080d;
      border: 1px solid #1c2133;
      border-radius: 10px;
      padding: 10px;
      height: 320px;
      overflow-y: auto;
      font-family: Consolas, monospace;
      font-size: 11px;
      color: #94a3b8;
    }
    .term-line { margin-bottom: 3px; word-break: break-all; }
    .term-ok { color: #34d399; }
    .term-err { color: #f87171; }
    .term-warn { color: #fbbf24; }

    /* Modals */
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.85);
      backdrop-filter: blur(8px);
      z-index: 500;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .modal-box {
      background: var(--card);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 18px;
      width: 100%;
      max-width: 420px;
    }

    /* Keypad buttons */
    .key-btn {
      background: #171b29;
      border: 1px solid #252b3f;
      border-radius: 10px;
      color: #fff;
      font-size: 20px;
      font-weight: 700;
      padding: 14px 0;
      cursor: pointer;
      transition: all 0.1s;
    }
    .key-btn:active {
      background: #252e47;
      transform: scale(0.95);
    }

    /* Tab Switching */
    .tab-content { display: none; }
    .tab-content.active { display: block; }
  </style>
</head>
<body>

  <!-- PIN Lock Screen Overlay -->
  <div class="modal-overlay" id="pinLockModal" style="display: flex; z-index: 1000;">
    <div class="modal-box" style="text-align: center; max-width: 320px; padding: 22px 14px;">
      <div style="font-size: 36px; margin-bottom: 4px;">🔒</div>
      <div style="font-size: 17px; font-weight: 800; color: #fff;">Reels Bot Security</div>
      <div style="font-size: 11px; color: var(--text-muted); margin: 4px 0 14px 0;">
        ກະລຸນາໃສ່ລະຫັດ PIN ເພື່ອເຂົ້າຈັດການ Bot
      </div>

      <div style="margin-bottom: 12px;">
        <input type="password" id="pinDisplay" maxlength="8" readonly
               style="width: 150px; text-align: center; font-size: 24px; letter-spacing: 6px; background: #07080d; border: 2px solid var(--accent); border-radius: 10px; color: #fff; padding: 6px;">
      </div>

      <div id="pinErrorMsg" style="color: var(--danger); font-size: 11px; font-weight: bold; min-height: 18px; margin-bottom: 10px;"></div>

      <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; max-width: 250px; margin: 0 auto;">
        <button class="key-btn" onclick="pressKey('1')">1</button>
        <button class="key-btn" onclick="pressKey('2')">2</button>
        <button class="key-btn" onclick="pressKey('3')">3</button>
        <button class="key-btn" onclick="pressKey('4')">4</button>
        <button class="key-btn" onclick="pressKey('5')">5</button>
        <button class="key-btn" onclick="pressKey('6')">6</button>
        <button class="key-btn" onclick="pressKey('7')">7</button>
        <button class="key-btn" onclick="pressKey('8')">8</button>
        <button class="key-btn" onclick="pressKey('9')">9</button>
        <button class="key-btn" style="color: var(--warning); font-size: 15px;" onclick="pressKey('C')">C</button>
        <button class="key-btn" onclick="pressKey('0')">0</button>
        <button class="key-btn" style="color: var(--danger); font-size: 15px;" onclick="pressKey('DEL')">⌫</button>
      </div>

      <button class="btn btn-start" style="width: 100%; margin-top: 14px; padding: 12px;" onclick="submitPinLogin()">
        🔓 ປົດລັອກ (Unlock)
      </button>
    </div>
  </div>

  <!-- Top Sticky Header -->
  <div class="top-bar">
    <div class="brand-title">
      <span>⚡ Reels Bot</span> Manager
    </div>
    <div class="top-actions">
      <div class="conn-badge conn-offline" id="connBadge">
        <div class="pulse-dot"></div>
        <span id="connStatusText">ກຳລັງເຊື່ອມຕໍ່...</span>
      </div>
      <button class="btn-sm btn-secondary" onclick="lockApp()" title="ລັອກລະບົບ">🔒 ລັອກ</button>
    </div>
  </div>

  <div class="container">

    <!-- ================== TAB 1: DASHBOARD ================== -->
    <div class="tab-content active" id="tabDashboard">
      
      <!-- Hero Status Card -->
      <div class="card">
        <div class="hero-status-box">
          <div class="hero-top-row">
            <span class="status-pill status-idle" id="heroPill">⏳ ພ້ອມເຮັດວຽກ</span>
            <span style="font-size: 11px; color: var(--text-muted);" id="lblServerTime">-</span>
          </div>

          <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 2px;">⚡ ເພຈ Facebook ທີ່ເລືອກ:</div>
          <div style="font-size: 15px; font-weight: 800; color: #fff;" id="heroPageName">-</div>
          <div style="font-size: 11px; color: var(--accent);" id="heroPageId">ID: -</div>

          <!-- Progress Bar -->
          <div class="progress-track">
            <div class="progress-fill" id="progressFill"></div>
            <div class="progress-text-overlay" id="progressOverlay">0%</div>
          </div>
          <div class="current-step-lbl" id="currentStepLbl">⏳ ພ້ອມເລີ່ມອັບໂຫຼດ</div>

          <div style="margin-top: 8px;">
            <span style="font-size: 11px; color: var(--text-muted);">🎬 ວິດີໂອປັດຈຸບັນ:</span>
            <div class="active-video-lbl" id="activeVideoTitle">-</div>
          </div>
        </div>

        <!-- Touch Controls -->
        <div class="card-title">🎮 ປຸ່ມຄວບຄຸມ Bot ດ່ວນ (Remote Actions)</div>
        <div class="btn-grid">
          <button class="btn btn-start" id="btnStart" onclick="triggerAction('start')">
            🚀 ເລີ່ມອັບໂຫຼດ
          </button>
          <button class="btn btn-pause" id="btnPause" onclick="triggerAction('pause')">
            ⏸️ ພັກຊົ່ວຄາວ
          </button>
          <button class="btn btn-resume" id="btnResume" style="display:none;" onclick="triggerAction('resume')">
            ▶️ ສືບຕໍ່ເຮັດວຽກ
          </button>
          <button class="btn btn-stop" id="btnStop" onclick="triggerAction('stop')">
            ⏹️ ຢຸດ (Stop)
          </button>
          <button class="btn btn-cta" onclick="confirmCTA()">
            📸 ສັ່ງ AI ສ້າງຮູບ & ໂພສ CTA ດຽວນີ້
          </button>
        </div>
      </div>

      <!-- Stats Card -->
      <div class="card">
        <div class="card-title">📊 ສະຖິຕິຄິວວິດີໂອ (Queue Overview)</div>
        <div class="stat-quad">
          <div class="stat-cell">
            <div class="stat-num" style="color: #38bdf8;" id="cntTotal">0</div>
            <div class="stat-sub">📦 ໄຟລ໌ທັງໝົດ</div>
          </div>
          <div class="stat-cell">
            <div class="stat-num" style="color: #f59e0b;" id="cntPending">0</div>
            <div class="stat-sub">⏳ ລໍຖ້າອັບໂຫຼດ</div>
          </div>
          <div class="stat-cell">
            <div class="stat-num" style="color: #10b981;" id="cntUploaded">0</div>
            <div class="stat-sub">✅ ອັບໂຫຼດແລ້ວ</div>
          </div>
          <div class="stat-cell">
            <div class="stat-num" style="color: #ef4444;" id="cntFailed">0</div>
            <div class="stat-sub">❌ ລົ້ມເຫຼວ</div>
          </div>
        </div>
      </div>

    </div>

    <!-- ================== TAB 2: PAGES MANAGER ================== -->
    <div class="tab-content" id="tabPages">
      <div class="card">
        <div class="card-head">
          <div class="card-title">🌐 ຈັດການ 4 Pages Facebook</div>
          <button class="btn-sm btn-secondary" onclick="fetchState()">🔄 ຣີເຟຣຊ</button>
        </div>
        <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">
          ເລືອກ Page ທີ່ຕ້ອງການໃຫ້ Bot ອັບໂຫຼດ ຫຼື ແກ້ໄຂ Page ID ໄດ້ໂດຍກົງຈາກໂທລະສັບ:
        </p>

        <div id="pagesListContainer">
          <div style="text-align: center; color: var(--text-muted); padding: 20px;">ກຳລັງໂຫຼດຂໍ້ມູນ Pages...</div>
        </div>
      </div>
    </div>

    <!-- ================== TAB 3: QUEUE LIST ================== -->
    <div class="tab-content" id="tabQueue">
      <div class="card">
        <div class="card-head">
          <div class="card-title">📋 ລາຍການວິດີໂອໃນຄິວ</div>
          <button class="btn-sm btn-secondary" onclick="fetchState()">🔄 ຣີເຟຣຊ</button>
        </div>
        <div id="queueListContainer" style="display: flex; flex-direction: column; gap: 6px; max-height: 480px; overflow-y: auto;">
          <div style="text-align: center; color: var(--text-muted); padding: 20px;">ກຳລັງໂຫຼດລາຍການຄິວ...</div>
        </div>
      </div>
    </div>

    <!-- ================== TAB 4: SETTINGS ================== -->
    <div class="tab-content" id="tabSettings">
      <div class="card">
        <div class="card-title">⚙️ ຕັ້ງຄ່າ Bot ຜ່ານມືຖື (Remote Config)</div>
        <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 12px;">
          ຄ່າທີ່ບັນທຶກຢູ່ນີ້ ຈະຖືກສົ່ງໄປອັບເດດໃນຄອມພິວເຕີທັນທີ:
        </p>

        <div class="form-group">
          <label class="form-lbl">⏱️ Delay ຕໍ່າສຸດ (ວິນາທີ)</label>
          <input type="number" class="input-field" id="cfgMinDelay" value="180">
        </div>

        <div class="form-group">
          <label class="form-lbl">⏱️ Delay ສູງສຸດ (ວິນາທີ)</label>
          <input type="number" class="input-field" id="cfgMaxDelay" value="360">
        </div>

        <div class="form-group">
          <label class="form-lbl">🎬 ຄຳນຳໜ້າຊື່ເລື່ອງ (Title Prefix)</label>
          <input type="text" class="input-field" id="cfgTitlePrefix" value="[เต็มเรื่อง] ">
        </div>

        <button class="btn btn-start" style="width: 100%; margin-top: 8px;" onclick="saveRemoteSettings()">
          💾 ບັນທຶກການຕັ້ງຄ່າລົງຄອມພິວເຕີ
        </button>
      </div>
    </div>

    <!-- ================== TAB 5: LOGS ================== -->
    <div class="tab-content" id="tabLogs">
      <div class="card">
        <div class="card-head">
          <div class="card-title">📜 ບັນທຶກການເຮັດວຽກສົດ (Live Logs)</div>
          <button class="btn-sm btn-secondary" onclick="clearLogsUI()">🧹 ລ້າງໜ້າຈໍ</button>
        </div>
        <div class="term-box" id="termBox">
          <div class="term-line">ກຳລັງເຊື່ອມຕໍ່ Log...</div>
        </div>
      </div>
    </div>

  </div>

  <!-- Bottom App Navigation Bar -->
  <div class="bottom-nav">
    <div class="nav-item active" onclick="switchTab('tabDashboard', this)">
      <svg viewBox="0 0 24 24"><path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/></svg>
      <span>ໜ້າຫຼັກ</span>
    </div>
    <div class="nav-item" onclick="switchTab('tabPages', this)">
      <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
      <span>4 ເພຈ</span>
    </div>
    <div class="nav-item" onclick="switchTab('tabQueue', this)">
      <svg viewBox="0 0 24 24"><path d="M4 6H2v14c0 1.1.9 2 2 2h14v-2H4V6zm16-4H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H8V4h12v12z"/></svg>
      <span>ຄິວວິດີໂອ</span>
    </div>
    <div class="nav-item" onclick="switchTab('tabSettings', this)">
      <svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg>
      <span>ຕັ້ງຄ່າ</span>
    </div>
    <div class="nav-item" onclick="switchTab('tabLogs', this)">
      <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z"/></svg>
      <span>Logs</span>
    </div>
  </div>

  <!-- Modal Edit Page ID -->
  <div class="modal-overlay" id="editModal">
    <div class="modal-box">
      <div style="font-size: 14px; font-weight: 800; margin-bottom: 8px;">✏️ ແກ້ໄຂ Page ID</div>
      <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;" id="modalPageName">-</div>
      <input type="hidden" id="modalGroupId">
      <input type="hidden" id="modalPageIndex">
      <div class="form-group">
        <label class="form-lbl">Facebook Page ID ໃໝ່ (ຕົວເລກເທົ່ານັ້ນ):</label>
        <input type="number" class="input-field" id="modalPageIdInput" placeholder="ຕົວຢ່າງ: 1332661329928072">
      </div>
      <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 14px;">
        <button class="btn btn-secondary" style="padding: 8px 14px;" onclick="closeModal()">ຍົກເລີກ</button>
        <button class="btn btn-start" style="padding: 8px 16px;" onclick="submitPageId()">💾 ບັນທຶກ</button>
      </div>
    </div>
  </div>

  <script>
    let gAuthToken = localStorage.getItem('reels_auth_token') || '';
    let currPinInput = '';

    function getAuthHeaders() {
      const h = { 'Content-Type': 'application/json' };
      if (gAuthToken) h['Authorization'] = 'Bearer ' + gAuthToken;
      return h;
    }

    function pressKey(k) {
      const disp = document.getElementById('pinDisplay');
      if (k === 'C') {
        currPinInput = '';
      } else if (k === 'DEL') {
        currPinInput = currPinInput.slice(0, -1);
      } else {
        if (currPinInput.length < 8) currPinInput += k;
      }
      disp.value = currPinInput;
    }

    async function submitPinLogin() {
      const errMsg = document.getElementById('pinErrorMsg');
      errMsg.innerText = '';
      if (!currPinInput) {
        errMsg.innerText = 'ກະລຸນາໃສ່ລະຫັດ PIN';
        return;
      }

      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pin: currPinInput })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          gAuthToken = data.token;
          localStorage.setItem('reels_auth_token', gAuthToken);
          document.getElementById('pinLockModal').style.display = 'none';
          currPinInput = '';
          document.getElementById('pinDisplay').value = '';
          fetchState();
        } else {
          errMsg.innerText = data.message || 'ລະຫັດ PIN ບໍ່ຖືກຕ້ອງ';
          currPinInput = '';
          document.getElementById('pinDisplay').value = '';
        }
      } catch (e) {
        errMsg.innerText = 'ເກີດຂໍ້ຜິດພາດ: ' + e;
      }
    }

    function lockApp() {
      gAuthToken = '';
      localStorage.removeItem('reels_auth_token');
      document.getElementById('pinLockModal').style.display = 'flex';
      currPinInput = '';
      document.getElementById('pinDisplay').value = '';
      document.getElementById('pinErrorMsg').innerText = '';
    }

    async function checkAuthOnLoad() {
      if (!gAuthToken) {
        document.getElementById('pinLockModal').style.display = 'flex';
        return;
      }
      try {
        const res = await fetch('/api/auth/check', { headers: getAuthHeaders() });
        const data = await res.json();
        if (data.authenticated) {
          document.getElementById('pinLockModal').style.display = 'none';
          fetchState();
        } else {
          lockApp();
        }
      } catch (e) {
        lockApp();
      }
    }

    function switchTab(tabId, el) {
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
      const t = document.getElementById(tabId);
      if (t) t.classList.add('active');
      if (el) el.classList.add('active');
    }

    async function fetchState() {
      if (!gAuthToken) return;
      try {
        const res = await fetch('/api/state', { headers: getAuthHeaders() });
        if (res.status === 401) {
          lockApp();
          return;
        }
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();

        // Connection Badge
        const cBadge = document.getElementById('connBadge');
        const cText = document.getElementById('connStatusText');
        if (data.bot_connected) {
          cBadge.className = 'conn-badge conn-online';
          cText.innerText = '🟢 Bot ອອນລາຍ';
        } else {
          cBadge.className = 'conn-badge conn-offline';
          cText.innerText = '🔴 Bot ອອບລາຍ';
        }

        // Server Time
        document.getElementById('lblServerTime').innerText = data.server_time || '';

        // Active Hero Page
        document.getElementById('heroPageName').innerText = data.page_name || 'ຍັງບໍ່ໄດ້ເລືອກ';
        document.getElementById('heroPageId').innerText = 'Page ID: ' + (data.page_id || '-');

        // Status Pill
        const heroPill = document.getElementById('heroPill');
        if (data.status === 'uploading' || data.status === 'running') {
          heroPill.className = 'status-pill status-uploading';
          heroPill.innerText = '🚀 ກຳລັງອັບໂຫຼດ';
        } else if (data.status === 'paused') {
          heroPill.className = 'status-pill status-paused';
          heroPill.innerText = '⏸️ ພັກຊົ່ວຄາວ';
        } else {
          heroPill.className = 'status-pill status-idle';
          heroPill.innerText = '⏳ ພ້ອມເຮັດວຽກ';
        }

        // Progress
        const pct = Math.max(0, Math.min(100, data.progress_pct || 0));
        document.getElementById('progressFill').style.width = pct + '%';
        document.getElementById('progressOverlay').innerText = pct + '%';
        document.getElementById('currentStepLbl').innerText = data.progress_text || 'ພ້ອມເລີ່ມອັບໂຫຼດ';

        // Active Video
        const vid = data.current_video || {};
        document.getElementById('activeVideoTitle').innerText = vid.title || vid.filename || '(ບໍ່ມີວິດີໂອທີ່ກຳລັງອັບໂຫຼດ)';

        // Counters
        const q = data.queue_stats || {};
        document.getElementById('cntTotal').innerText = q.total_in_folder || 0;
        document.getElementById('cntPending').innerText = q.pending_in_folder || 0;
        document.getElementById('cntUploaded').innerText = q.total_uploaded || 0;
        document.getElementById('cntFailed').innerText = q.total_failed || 0;

        // Button states
        const bStart = document.getElementById('btnStart');
        const bPause = document.getElementById('btnPause');
        const bResume = document.getElementById('btnResume');
        const bStop = document.getElementById('btnStop');
        if (data.status === 'paused') {
          bStart.style.display = 'none';
          bPause.style.display = 'none';
          bResume.style.display = 'flex';
          bStop.style.display = 'flex';
        } else if (data.status === 'uploading' || data.status === 'running') {
          bStart.style.display = 'none';
          bPause.style.display = 'flex';
          bResume.style.display = 'none';
          bStop.style.display = 'flex';
        } else {
          bStart.style.display = 'flex';
          bPause.style.display = 'none';
          bResume.style.display = 'none';
          bStop.style.display = 'none';
        }

        // Render Pages
        renderPagesList(data.page_groups || [], data.page_id);

        // Render Queue
        renderQueueList(data.queue_items || []);

        // Render Logs
        renderLogs(data.recent_logs || []);

      } catch (e) {
        const cBadge = document.getElementById('connBadge');
        const cText = document.getElementById('connStatusText');
        cBadge.className = 'conn-badge conn-offline';
        cText.innerText = '⚠️ ບໍ່ສາມາດເຊື່ອມຕໍ່ Server';
      }
    }

    function renderPagesList(groups, activePageId) {
      const container = document.getElementById('pagesListContainer');
      if (!groups || groups.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">ຍັງບໍ່ມີຂໍ້ມູນ Groups</div>';
        return;
      }
      let html = '';
      groups.forEach((grp, gIdx) => {
        const isG1 = grp.group_id === 'group_shared_3pages';
        const color = isG1 ? '#38bdf8' : '#c084fc';
        const catName = grp.content_type === 'lao_girl_khaohom' ? '🌸 ນ້ອງເຂົ້າຫອມ ສາວຂີ້ດື້' : '🎬 ໜັງສັ້ນຈີນ AI';

        html += `<div class="group-card">
          <div class="group-header">
            <div class="group-name" style="color: ${color};">${grp.group_name || 'Group ' + (gIdx+1)}</div>
            <span style="font-size: 10px; background: #1c2236; padding: 2px 7px; border-radius: 10px; color: ${color}; font-weight: 700;">${catName}</span>
          </div>
          <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">📁 ໂຟນເດີ: <span style="color: #cbd5e1;">${grp.video_folder || '-'}</span></div>`;

        (grp.pages || []).forEach((p, pIdx) => {
          const hasId = p.page_id && String(p.page_id).trim() !== '';
          const isActive = activePageId && p.page_id && String(activePageId) === String(p.page_id);

          html += `<div class="page-row ${isActive ? 'active-row' : ''}">
            <div style="flex: 1; padding-right: 8px;">
              <div class="page-info-name">${p.page_name || 'Page ' + (pIdx+1)}</div>
              <div class="page-info-id">ID: ${hasId ? p.page_id : '<span style="color: var(--warning); font-weight: bold;">(ຍັງບໍ່ມີ ID)</span>'}</div>
            </div>
            <div class="page-actions">
              <button class="btn-sm btn-secondary" onclick="openEditModal('${grp.group_id}', ${pIdx}, '${escapeJs(p.page_name)}', '${p.page_id || ''}')">✏️ ໃສ່ ID</button>
              ${isActive 
                ? '<span class="btn-sm" style="background: #059669;">⚡ Active</span>' 
                : `<button class="btn-sm btn-start" onclick="switchActivePage('${grp.group_id}', '${p.page_id || ''}', '${escapeJs(p.page_name)}')">ເລືອກ</button>`}
            </div>
          </div>`;
        });

        html += `</div>`;
      });
      container.innerHTML = html;
    }

    function renderQueueList(items) {
      const container = document.getElementById('queueListContainer');
      if (!items || items.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; text-align: center; padding: 15px;">ບໍ່ມີລາຍການວິດີໂອໃນຄິວ</div>';
        return;
      }
      container.innerHTML = items.slice(0, 30).map((it, idx) => `
        <div style="background: #0d0f17; border: 1px solid #1c2236; border-radius: 8px; padding: 8px 10px; font-size: 12px; display: flex; justify-content: space-between; align-items: center;">
          <div style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 75%;">
            <span style="color: var(--text-muted); font-weight: bold;">#${idx+1}</span> ${it.filename}
          </div>
          <span style="color: #38bdf8; font-size: 10px; font-weight: bold;">${it.size_mb ? it.size_mb + ' MB' : ''}</span>
        </div>
      `).join('');
    }

    function renderLogs(logs) {
      const box = document.getElementById('termBox');
      if (!logs || logs.length === 0) return;
      box.innerHTML = logs.map(line => {
        let cls = 'term-line';
        if (line.includes('✅') || line.includes('ສຳເລັດ')) cls += ' term-ok';
        else if (line.includes('❌') || line.includes('ລົ້ມເຫຼວ') || line.includes('Error')) cls += ' term-err';
        else if (line.includes('⚠️') || line.includes('ຄຳເຕືອນ')) cls += ' term-warn';
        return `<div class="${cls}">${escapeHtml(line)}</div>`;
      }).join('');
      box.scrollTop = box.scrollHeight;
    }

    function clearLogsUI() {
      document.getElementById('termBox').innerHTML = '<div class="term-line">🧹 ລ້າງບັນທຶກໜ້າຈໍແລ້ວ</div>';
    }

    async function triggerAction(action) {
      try {
        const res = await fetch('/api/action/' + action, {
          method: 'POST',
          headers: getAuthHeaders()
        });
        if (res.status === 401) { lockApp(); return; }
        const json = await res.json();
        alert(json.message || 'ສົ່ງຄຳສັ່ງແລ້ວ');
        fetchState();
      } catch (e) {
        alert('ຜິດພາດ: ' + e);
      }
    }

    function confirmCTA() {
      if (confirm('ທ່ານຕ້ອງການໃຫ້ AI ສ້າງຮູບໃໝ່ ແລະ ໂພສເຊີນຊວນຕິດຕາມเพจ Facebook ດຽວນີ້ເລີຍຫຼືບໍ່?')) {
        triggerAction('post_cta');
      }
    }

    async function switchActivePage(groupId, pageId, pageName) {
      if (!pageId) {
        alert('Page ນີ້ຍັງບໍ່ມີ Page ID! ກະລຸນາກົດ ✏️ ໃສ່ ID ກ່ອນ.');
        return;
      }
      try {
        const res = await fetch('/api/action/switch_page', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ group_id: groupId, page_id: pageId, page_name: pageName })
        });
        if (res.status === 401) { lockApp(); return; }
        const json = await res.json();
        alert(json.message || 'ປ່ຽນເພຈສຳເລັດ');
        fetchState();
      } catch (e) {
        alert('ຜິດພາດ: ' + e);
      }
    }

    function openEditModal(groupId, pageIdx, pageName, currId) {
      document.getElementById('modalGroupId').value = groupId;
      document.getElementById('modalPageIndex').value = pageIdx;
      document.getElementById('modalPageName').innerText = pageName;
      document.getElementById('modalPageIdInput').value = currId || '';
      document.getElementById('editModal').style.display = 'flex';
    }

    function closeModal() {
      document.getElementById('editModal').style.display = 'none';
    }

    async function submitPageId() {
      const gId = document.getElementById('modalGroupId').value;
      const pIdx = document.getElementById('modalPageIndex').value;
      const newId = document.getElementById('modalPageIdInput').value.trim();

      if (!newId) {
        alert('ກະລຸນາໃສ່ Page ID');
        return;
      }

      try {
        const res = await fetch('/api/action/update_page_id', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ group_id: gId, page_index: parseInt(pIdx), page_id: newId })
        });
        if (res.status === 401) { lockApp(); return; }
        const json = await res.json();
        alert(json.message || 'ອັບເດດ Page ID ສຳເລັດ');
        closeModal();
        fetchState();
      } catch (e) {
        alert('ຜິດພາດ: ' + e);
      }
    }

    async function saveRemoteSettings() {
      const minD = document.getElementById('cfgMinDelay').value;
      const maxD = document.getElementById('cfgMaxDelay').value;
      const prefix = document.getElementById('cfgTitlePrefix').value;

      try {
        const res = await fetch('/api/action/update_settings', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({ min_delay: parseInt(minD), max_delay: parseInt(maxD), title_prefix: prefix })
        });
        if (res.status === 401) { lockApp(); return; }
        const json = await res.json();
        alert(json.message || 'ບັນທຶກການຕັ້ງຄ່າສຳເລັດ');
        fetchState();
      } catch (e) {
        alert('ຜິດພາດ: ' + e);
      }
    }

    function escapeHtml(t) {
      const d = document.createElement('div');
      d.innerText = t;
      return d.innerHTML;
    }

    function escapeJs(t) {
      return (t || '').replace(/'/g, "\\'");
    }

    // Initialize Auth and Poller
    checkAuthOnLoad();
    setInterval(fetchState, 2500);
  </script>
</body>
</html>
"""

@app.route("/")
@app.route("/dashboard")
def index():
    return render_template_string(MOBILE_UI_HTML)


@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    ip = get_client_ip()
    if is_rate_limited(ip):
        return jsonify({"success": False, "message": "⚠️ ພະຍາຍາມໃສ່ລະຫັດຜິດຫຼາຍຄັ້ງເກີນໄປ. ກະລຸນາລໍຖ້າ 5 ນາທີ."}), 429

    data = request.get_json(silent=True) or {}
    pin = str(data.get("pin", "")).strip()

    if pin and hmac.compare_digest(pin, ACCESS_PIN):
        clear_failed_attempts(ip)
        token = generate_session_token(pin)
        return jsonify({"success": True, "token": token, "message": "ປົດລັອກສຳເລັດ (Unlock success)"})

    record_failed_attempt(ip)
    attempts = len(FAILED_ATTEMPTS.get(ip, []))
    remaining = max(0, 5 - attempts)
    return jsonify({
        "success": False,
        "message": f"❌ ລະຫັດ PIN ບໍ່ຖືກຕ້ອງ (ຍັງເຫຼືອໂອກາດ {remaining} ຄັ້ງ)"
    }), 401


@app.route("/api/auth/check", methods=["GET"])
def api_auth_check():
    return jsonify({"authenticated": verify_auth(request)})


@app.route("/api/state", methods=["GET"])
def api_state():
    if not verify_auth(request):
        return jsonify({"error": "Unauthorized", "require_pin": True}), 401

    now = time.time()
    SERVER_STATE["bot_connected"] = (now - SERVER_STATE.get("last_sync_time", 0)) < 35
    SERVER_STATE["server_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(SERVER_STATE)


@app.route("/api/action/<action_name>", methods=["POST"])
def api_action(action_name: str):
    if not verify_auth(request):
        return jsonify({"error": "Unauthorized", "require_pin": True}), 401

    payload = request.get_json(silent=True) or {}

    action_clean = action_name.lower().strip()

    # Input Sanitization
    if action_clean == "switch_page":
        raw_id = str(payload.get("page_id", "")).strip()
        clean_id = re.sub(r'[^0-9]', '', raw_id)
        if not clean_id or len(clean_id) < 5 or len(clean_id) > 32:
            return jsonify({"success": False, "message": "❌ Page ID ບໍ່ຖືກຕ້ອງ (ຕ້ອງເປັນຕົວເລກ 5-32 ຫຼັກ)"}), 400
        payload["page_id"] = clean_id

    elif action_clean == "update_page_id":
        raw_id = str(payload.get("page_id", "")).strip()
        clean_id = re.sub(r'[^0-9]', '', raw_id)
        if not clean_id or len(clean_id) < 5 or len(clean_id) > 32:
            return jsonify({"success": False, "message": "❌ Page ID ບໍ່ຖືກຕ້ອງ (ຕ້ອງເປັນຕົວເລກ 5-32 ຫຼັກ)"}), 400
        payload["page_id"] = clean_id

    elif action_clean == "update_settings":
        try:
            min_d = max(10, min(7200, int(payload.get("min_delay", 180))))
            max_d = max(10, min(7200, int(payload.get("max_delay", 360))))
            if min_d > max_d:
                min_d, max_d = max_d, min_d
            payload["min_delay"] = min_d
            payload["max_delay"] = max_d
            if "title_prefix" in payload:
                payload["title_prefix"] = str(payload["title_prefix"])[:50]
        except Exception:
            return jsonify({"success": False, "message": "❌ ຄ່າ Delay ບໍ່ຖືກຕ້ອງ"}), 400

    cmd = {
        "id": f"cmd_{int(time.time()*1000)}",
        "action": action_clean,
        "payload": payload,
        "created_at": datetime.now().strftime("%H:%M:%S")
    }
    PENDING_COMMANDS.append(cmd)
    if len(PENDING_COMMANDS) > 50:
        PENDING_COMMANDS.pop(0)

    logger.info(f"Authorized command received from IP {get_client_ip()}: {cmd['action']}")

    lao_msgs = {
        "start": "🚀 ສັ່ງເລີ່ມອັບໂຫຼດສຳເລັດ",
        "pause": "⏸️ ສັ່ງພັກຊົ່ວຄາວສຳເລັດ",
        "resume": "▶️ ສັ່ງສືບຕໍ່ເຮັດວຽກສຳເລັດ",
        "stop": "⏹️ ສັ່ງຢຸດການອັບໂຫຼດສຳເລັດ",
        "post_cta": "📸 ສັ່ງ Gen ຮູບ AI & Post Follower CTA ແລ້ວ",
        "switch_page": f"⚡ ປ່ຽນ Target Page ເປັນ '{payload.get('page_name', '')}' ແລ້ວ",
        "update_page_id": f"💾 ບັນທຶກ Page ID ໃໝ່: {payload.get('page_id', '')} ແລ້ວ",
        "update_settings": "⚙️ ບັນທຶກການຕັ້ງຄ່າສຳເລັດແລ້ວ"
    }

    msg = lao_msgs.get(action_clean, f"ຮັບຄຳສັ່ງ '{action_clean}' ແລ້ວ")
    return jsonify({"success": True, "message": msg, "cmd_id": cmd["id"]})


@app.route("/api/sync", methods=["POST"])
def api_sync():
    """
    Called by the local PC bot every 2-3 seconds:
    Requires authentication via X-Bot-Token header.
    """
    bot_token = request.headers.get("X-Bot-Token", "").strip()
    auth_h = request.headers.get("Authorization", "").strip()
    if auth_h.startswith("Bearer "):
        bot_token = auth_h[7:].strip()

    if not bot_token or not hmac.compare_digest(bot_token, SYNC_SECRET_TOKEN):
        logger.warning(f"Unauthorized sync attempt rejected from IP: {get_client_ip()}")
        return jsonify({"error": "Forbidden: Invalid Bot Token"}), 403

    global PENDING_COMMANDS
    if not request.is_json:
        return jsonify({"error": "Expected JSON payload"}), 400

    data = request.get_json(silent=True) or {}
    now = time.time()

    for k in ["status", "progress_pct", "progress_text", "current_video", 
              "page_name", "page_id", "is_safe", "page_groups", "queue_stats", 
              "queue_items", "recent_logs"]:
        if k in data:
            SERVER_STATE[k] = data[k]

    SERVER_STATE["last_sync_time"] = now
    SERVER_STATE["bot_connected"] = True

    commands_to_send = list(PENDING_COMMANDS)
    PENDING_COMMANDS.clear()

    return jsonify({
        "success": True,
        "commands": commands_to_send,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


def main():
    port = int(os.environ.get("PORT", 5555))
    logger.info(f"Starting secure web server on port {port} (PIN Protection: Active)...")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
