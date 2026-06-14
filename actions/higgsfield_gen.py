"""
Higgsfield image/video generation via the official Higgsfield CLI.

We use the CLI (not MCP) because Higgsfield's hosted MCP server only allows
pre-registered managed clients over OAuth, and there's no public API-key
dashboard. The CLI authenticates with your normal Higgsfield account
(`higgsfield auth login`, one-time browser login).

Setup (once):
    npm install -g @higgsfield/cli
    higgsfield auth login

Generation runs in the BACKGROUND so JARVIS stays responsive, and the result
is downloaded to generated/ so you get a real file (not a fragile URL).
"""

import platform
import re
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

_IS_WINDOWS = platform.system().lower().startswith("win")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _save_dir() -> Path:
    d = _base_dir() / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cli(args: list[str], timeout: int = 600) -> tuple[int, str, str]:
    cmd = (["cmd", "/c", "higgsfield"] if _IS_WINDOWS else ["higgsfield"]) + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()
    except FileNotFoundError:
        return 127, "", "higgsfield CLI not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"


def _download(url: str, dest: Path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as f:
        f.write(r.read())


def _run(prompt: str, model: str, images: list[str] | None = None, player=None) -> str:
    """Run the CLI, download the result, return a spoken-friendly message.
    If `images` are given, they're passed as --image inputs (image editing)."""
    args = ["generate", "create", model, "--prompt", prompt]
    for img in (images or []):
        args += ["--image", img]
    args.append("--wait")
    code, out, err = _cli(args, timeout=600)

    if code == 127:
        return ("The Higgsfield CLI isn't installed, sir. Install it with "
                "'npm install -g @higgsfield/cli' then 'higgsfield auth login'.")
    blob = (out + "\n" + err).strip()
    if "auth" in blob.lower() and ("login" in blob.lower() or "authenticat" in blob.lower()):
        return "Higgsfield needs sign-in, sir. Run 'higgsfield auth login' in a terminal."
    if code != 0:
        return f"Higgsfield generation failed: {(err or out or 'unknown error')[:200]}"

    urls = re.findall(r"https?://\S+", out)
    if not urls:
        return f"Generation finished, but I couldn't find the result link. Output: {out[:200]}"

    url = urls[-1].rstrip(").,'\"")
    print(f"[Higgsfield] Result URL: {url}")   # full URL in the log

    # Try to download to a real file
    ext = Path(url.split("?")[0]).suffix or ".png"
    fname = f"higgsfield_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    dest = _save_dir() / fname
    try:
        _download(url, dest)
        if player:
            try:
                player.write_log(f"[Higgsfield] Saved: generated/{fname}  ({url})")
            except Exception:
                pass
        return f"Your {model} result is ready, sir — I saved it as {fname} in the generated folder."
    except Exception as e:
        print(f"[Higgsfield] download failed: {e}")
        return f"Your {model} result is ready, sir. The link is: {url}"


def higgsfield_generate(parameters: dict, player=None, session_memory=None, speak=None) -> str:
    """Generate OR edit an image/video with Higgsfield. Runs in the background
    so JARVIS stays responsive; announces the saved file when done.

    Parameters:
        prompt (str): What to generate, or how to edit the input image.
        model (str): Higgsfield model (default 'nano_banana_2').
        image (str): Optional input image path(s) to EDIT (comma-separated for
                     multiple). If omitted, an image dropped onto JARVIS is used.
    """
    prompt = (parameters.get("prompt") or "").strip()
    model = (parameters.get("model") or "nano_banana_2").strip()
    if not prompt:
        return "What would you like me to generate, sir?"

    # Collect input images (for editing): explicit param, else the dropped file.
    images: list[str] = []
    raw = parameters.get("image") or parameters.get("images")
    if isinstance(raw, str):
        images = [p.strip() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, list):
        images = [str(p).strip() for p in raw if str(p).strip()]

    verb = "Editing" if images else "Generating"
    if player:
        try:
            extra = f" (editing {len(images)} image)" if images else ""
            player.write_log(f"[Higgsfield] {verb} with {model}: {prompt[:60]}...{extra}")
        except Exception:
            pass

    # Background mode: reply immediately, announce the result when ready.
    if speak:
        def _bg():
            msg = _run(prompt, model, images, player)
            try:
                speak(f"[PROGRESS] {msg}")
            except Exception:
                pass
        threading.Thread(target=_bg, daemon=True).start()
        action = "editing your image" if images else f"generating your {model}"
        return (f"On it, sir — {action} now. It takes a moment; "
                f"I'll tell you the second it's ready.")

    # Synchronous fallback (text/manual)
    return _run(prompt, model, images, player)


def higgsfield_models(parameters: dict, player=None, session_memory=None) -> str:
    """List available Higgsfield models."""
    code, out, err = _cli(["model", "list"], timeout=60)
    if code == 127:
        return "The Higgsfield CLI isn't installed, sir."
    if code != 0:
        return f"Couldn't list models: {(err or out)[:200]}"
    return out[:1500] or "No models returned."
