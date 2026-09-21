import os
import hashlib
from typing import Optional, List, Tuple

def compute_file_hash(file_path: str, chunk_size: int = 4 * 1024 * 1024) -> str:
    """
    Computes a fast and reliable fingerprint hash for a video file.
    Hashes the file size plus the first 4MB, middle 4MB, and last 4MB.
    This is extremely fast even for multi-gigabyte video files while being virtually collision-proof.
    """
    if not os.path.exists(file_path):
        return ""

    try:
        file_size = os.path.getsize(file_path)
        hasher = hashlib.sha256()
        hasher.update(str(file_size).encode('utf-8'))

        with open(file_path, 'rb') as f:
            # Read first chunk
            first_chunk = f.read(chunk_size)
            hasher.update(first_chunk)

            if file_size > chunk_size * 2:
                # Read middle chunk
                mid_pos = file_size // 2
                f.seek(mid_pos)
                hasher.update(f.read(chunk_size))

                # Read last chunk
                f.seek(max(0, file_size - chunk_size))
                hasher.update(f.read(chunk_size))

        return hasher.hexdigest()
    except Exception as e:
        print(f"[compute_file_hash error]: {e}")
        # Fallback to basic file size + name hash
        return hashlib.sha256(f"{os.path.basename(file_path)}_{os.path.getsize(file_path)}".encode('utf-8')).hexdigest()

def load_external_gemini_key(target_dir: str = "G:/PG/API") -> Tuple[Optional[str], Optional[str]]:
    """
    Attempts to read GEMINI_API_KEY and GEMINI_MODEL from .env in the specified directory.
    Checks candidate directories in order:
    1. target_dir (default: G:/PG/API)
    2. G:/PG/API
    3. G:/PG/Auto flow ຂຽນຂ່າວ
    Returns (api_key_str, model_name).
    """
    candidates = []
    if target_dir:
        candidates.append(target_dir)
    if "G:/PG/API" not in candidates:
        candidates.append("G:/PG/API")
    if "G:/PG/Auto flow ຂຽນຂ່າວ" not in candidates:
        candidates.append("G:/PG/Auto flow ຂຽນຂ່າວ")

    for c_dir in candidates:
        env_path = os.path.join(c_dir, ".env")
        if not os.path.exists(env_path):
            continue

        api_keys = None
        model_name = "gemini-3.6-flash"

        try:
            with open(env_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            api_keys = val
                    elif line.startswith("GEMINI_MODEL="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            model_name = val

            if api_keys:
                print(f"[load_external_gemini_key] Successfully loaded {len(api_keys.split(','))} keys from: {env_path}")
                return api_keys, model_name
        except Exception as e:
            print(f"[load_external_gemini_key error at {c_dir}]: {e}")

    return None, None
