"""The encrypted vault: keeps scripts, plans and research private inside a public GitHub repo.

Everything in PRIVATE is packed into vault.tar.enc, encrypted with the CONTENT_KEY secret. Only
the encrypted file is committed; .gitignore keeps the plain folders out of git.

    uv run python -m esim.vault newkey   # once: prints a key to save as the CONTENT_KEY secret
    uv run python -m esim.vault lock     # pack + encrypt
    uv run python -m esim.vault unlock   # decrypt + unpack
"""

import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault.tar.enc"
PRIVATE = ["videos", "plan", "research", "data", "content-log.md"]
KEY_FILE = ROOT / ".content-key"  # local copy of the key on your Mac; never committed
# Music is big and rarely changes, so each track is encrypted on its own (GitHub refuses files over
# 100 MB, and unchanged tracks then never need re-committing).
MUSIC = ROOT / "music"
MUSIC_VAULT = ROOT / "music.vault"


def _key():
    key = os.environ.get("CONTENT_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not key:
        sys.exit("No CONTENT_KEY. Run `uv run python -m esim.vault newkey` once, or set the secret.")
    return key.encode()


def lock():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in PRIVATE:
            path = ROOT / name
            if path.exists():
                tar.add(path, arcname=name, filter=lambda ti: None if "__pycache__" in ti.name else ti)
    VAULT.write_bytes(Fernet(_key()).encrypt(buf.getvalue()))
    print(f"Locked {', '.join(n for n in PRIVATE if (ROOT / n).exists())} into {VAULT.name}")
    lock_music()


def unlock():
    if not VAULT.exists():
        print("No vault yet; starting empty.")
    else:
        try:
            data = Fernet(_key()).decrypt(VAULT.read_bytes())
        except InvalidToken:
            sys.exit("CONTENT_KEY doesn't match this vault.")
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            tar.extractall(ROOT, filter="data")
        print("Unlocked the vault.")
    unlock_music()


def _music_index(fernet):
    path = MUSIC_VAULT / "index.enc"
    return json.loads(fernet.decrypt(path.read_bytes())) if path.exists() else {"files": {}, "library": None}


def lock_music():
    if not MUSIC.exists():
        return
    fernet = Fernet(_key())
    MUSIC_VAULT.mkdir(exist_ok=True)
    files = {}
    for p in sorted(MUSIC.iterdir()):
        if p.is_file() and p.name != "library.json" and not p.name.startswith("."):
            data = p.read_bytes()
            digest = hashlib.sha256(data).hexdigest()[:24]
            files[digest] = p.name
            out = MUSIC_VAULT / f"{digest}.enc"
            if not out.exists():
                out.write_bytes(fernet.encrypt(data))
    for old in MUSIC_VAULT.glob("*.enc"):
        if old.name != "index.enc" and old.stem not in files:
            old.unlink()
    lib_path = MUSIC / "library.json"
    index = {"files": files, "library": lib_path.read_text() if lib_path.exists() else None}
    if _music_index(fernet) != index:  # only rewrite when something changed, to keep git history small
        (MUSIC_VAULT / "index.enc").write_bytes(fernet.encrypt(json.dumps(index).encode()))
    print(f"Music vault: {len(files)} track(s).")


def unlock_music():
    if not (MUSIC_VAULT / "index.enc").exists():
        return
    fernet = Fernet(_key())
    index = _music_index(fernet)
    MUSIC.mkdir(exist_ok=True)
    for digest, name in index["files"].items():
        target = MUSIC / name
        if not target.exists():
            target.write_bytes(fernet.decrypt((MUSIC_VAULT / f"{digest}.enc").read_bytes()))
    if index.get("library"):
        (MUSIC / "library.json").write_text(index["library"])
    print(f"Unlocked {len(index['files'])} music track(s).")


def newkey():
    key = Fernet.generate_key().decode()
    if not KEY_FILE.exists():
        KEY_FILE.write_text(key + "\n")
        os.chmod(KEY_FILE, 0o600)
        print(f"Saved a new key to {KEY_FILE.name} (kept out of git).")
        print("Add the same key to GitHub as the CONTENT_KEY secret: it's in that file.")
    else:
        print(f"{KEY_FILE.name} already exists; not overwriting it.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"lock": lock, "unlock": unlock, "newkey": newkey}.get(cmd, lambda: sys.exit(__doc__))()
