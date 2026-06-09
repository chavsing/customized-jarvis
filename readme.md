# 🤖 MARK XXXIX (39)
### The Ultimate Cross-Platform Personal AI Assistant — By FatihMakes

> 📺 **[Watch the full setup video on YouTube](https://youtu.be/ej1f5OE3SNQ?si=lCxDhJix9ungq1Ry)**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supporting Windows, macOS, and Linux. Local execution. Zero subscriptions. Engineered for total autonomy.

---

## ✨ Overview

MARK XXXIX represents the pinnacle of the Jarvis series, evolving into a more flexible and robust system. It bridges the gap between the operating system and human intent. Through natural dialogue, Mark 39 analyzes your screen, processes uploaded documents, and executes complex workflows with a brand-new, adaptive interface.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language |
| 🖥️ System Control | Launch apps, manage files, execute terminal commands |
| 🧩 Autonomous Tasks | High-level planning for complex, multi-step goals |
| 👁️ Visual Awareness | Real-time screen processing and webcam vision |
| 🧠 Persistent Memory | Deeply remembers your projects, preferences, and personal context |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

---

## 🆕 What's New in XXXIX

- 📂 **Advanced File Handling** — New support for direct file uploads. Drop PDFs, source code, or images into the assistant to have them analyzed, summarized, or edited instantly.
- 🎨 **Adaptive & Flexible UI** — A complete overhaul of the interface. The new UI is fully resizable and responsive, featuring transparency controls and customizable layouts to fit your workspace perfectly.
- 🐧🍎 **Refined Cross-Platform Stability** — Major fixes for macOS and Linux compatibility. Core system actions are now more consistent across all three major operating systems.
- ⚡ **Optimized Core Engine** — Significant performance boost in tool-calling logic and response generation, resulting in a 40% faster interaction speed.

---

## ⚡ Quick Start

```bash
git clone https://github.com/FatihMakes/Mark-XXXIX.git
cd Mark-XXXIX
pip install -r requirements.txt
playwright install
# Configure your API keys (see below) before running
python main.py
```

> ⚠️ **Installation Note:** To keep the repository lightweight, some OS-specific dependencies are not bundled in `requirements.txt`. If you run into a `ModuleNotFoundError`, simply install the missing package via `pip install <module_name>` for your specific system.

---

## 🔑 Configuration

Your API keys and credentials are **not** included in the repo (they're gitignored). You must create them locally. Example templates are provided in the `config/` folder.

### 1. API Keys (required)

Copy the example file and fill in your own keys:

```bash
# Windows (PowerShell)
Copy-Item config/api_keys.example.json config/api_keys.json

# macOS / Linux
cp config/api_keys.example.json config/api_keys.json
```

Then edit `config/api_keys.json`:

```json
{
    "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
    "os_system": "windows",
    "fathom_api_key": "YOUR_FATHOM_API_KEY_HERE"
}
```

| Key | Required? | Where to get it |
|---|---|---|
| `gemini_api_key` | ✅ Required | [Google AI Studio](https://aistudio.google.com/apikey) — free |
| `os_system` | ✅ Required | `windows`, `macos`, or `linux` |
| `fathom_api_key` | Optional | [Fathom](https://fathom.video) → Settings → API (only needed for meeting briefs) |

### 2. Google OAuth — Gmail & Calendar (optional)

Needed only for the **morning brief** (email + calendar). Skip if you don't use it.

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a project.
2. Enable the **Gmail API** and **Google Calendar API**.
3. Under **APIs & Services → Credentials**, create an **OAuth client ID** (type: *Desktop app*).
4. Download the JSON and save it as `config/google_credentials.json` (a template is at `config/google_credentials.example.json`).
5. On first run, a browser window will open for you to authorize access. Tokens are saved automatically to `config/gmail_token.json` and `config/calendar_token.json`.

### 3. Fathom Meetings (optional)

If you set a `fathom_api_key`, JARVIS will fetch your meeting recordings, save transcripts to a local knowledge base, and generate AI-summarized to-do lists. No extra setup beyond the key.

> 🔒 **Never commit** `api_keys.json`, `google_credentials.json`, or any `*_token.json` — they're already in `.gitignore` to keep your secrets safe.

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Key** | Free Gemini API key |

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Connect with the Creator

Engineered by a developer building a real-world JARVIS-style assistant.
⭐ **Star the repository to support the journey to Mark 100.**

| Platform | Link |
|---|---|
| YouTube | [@FatihMakes](https://www.youtube.com/@FatihMakes) |
| Instagram | [@fatihmakes](https://www.instagram.com/fatihmakes) |
