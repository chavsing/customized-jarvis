import asyncio
import re
import threading
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
import numpy as np
from google import genai
from google.genai import types
from ui import JarvisUI
import skills_manager
import self_improve
from mcp_client import MCPManager
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.spotify_music     import spotify_music
from actions.clap_detector     import ClapDetector
from actions.wake_monitor      import WakeMonitor
from actions.gmail_brief       import gmail_brief
from actions.calendar_brief    import calendar_brief
from actions.fathom_brief      import fathom_brief, fathom_search, fathom_todos, fathom_analyze, fathom_save_todo
from actions.morning_brief     import morning_brief


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "load_skill",
        "description": (
            "Loads the full step-by-step instructions for a named skill (a reusable "
            "playbook). Call this when the user's request matches one of the AVAILABLE "
            "SKILLS listed in your instructions. After loading, follow the returned "
            "instructions, using your other tools as the steps direct."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {
                    "type": "STRING",
                    "description": "The skill name to load (e.g. 'email-triage')."
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "create_skill",
        "description": (
            "Saves a NEW reusable skill (a playbook) as a markdown file so you can reuse "
            "it later. Call this when the user explicitly asks you to remember how to do "
            "something as a skill, OR when you've just worked out a repeatable, multi-step "
            "procedure worth keeping. Write clear step-by-step instructions in the body."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "name": {
                    "type": "STRING",
                    "description": "Short kebab-case skill name (e.g. 'invoice-followup')."
                },
                "description": {
                    "type": "STRING",
                    "description": "One line: when this skill should be used (the trigger condition)."
                },
                "body": {
                    "type": "STRING",
                    "description": "The full instructions in markdown — numbered steps, which tools to use, tips."
                }
            },
            "required": ["name", "description", "body"]
        }
    },
    {
        "name": "spotify_music",
        "description": (
            "Controls Spotify music playback. "
            "Use for: searching and playing music, play/pause, next/previous track, volume control. "
            "Always call this tool when the user asks to play music on Spotify."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Action to perform: search_play | play_pause | next | previous | volume_up | volume_down"
                },
                "query": {
                    "type": "STRING",
                    "description": "Search query for search_play action (e.g. song name, artist, album)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "morning_brief",
        "description": (
            "Runs the full morning brief: delivers a dramatic greeting, "
            "fetches important Gmail emails, today's Google Calendar appointments, "
            "and Fathom meeting transcripts. "
            "Call this when the user triggers the morning clap sequence, says 'good morning', "
            "asks for a morning report/brief, or asks what's on their schedule and email."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "greeting": {
                    "type": "STRING",
                    "description": "Optional custom greeting. Leave empty for auto-generated."
                },
                "email_hours": {
                    "type": "INTEGER",
                    "description": "Hours back to check emails (default: 24)"
                },
                "max_emails": {
                    "type": "INTEGER",
                    "description": "Max emails to fetch (default: 15)"
                },
                "max_events": {
                    "type": "INTEGER",
                    "description": "Max calendar events to fetch (default: 20)"
                },
                "max_recordings": {
                    "type": "INTEGER",
                    "description": "Max Fathom recordings to include (default: 10)"
                }
            },
            "required": []
        }
    },
    {
        "name": "gmail_brief",
        "description": (
            "Fetches and summarizes important unread emails from Gmail. "
            "Use when the user asks to check email, see important messages, "
            "or wants a Gmail summary. Requires Google OAuth credentials in config/google_credentials.json."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "hours": {
                    "type": "INTEGER",
                    "description": "Hours back to check (default: 24)"
                },
                "max_results": {
                    "type": "INTEGER",
                    "description": "Max emails to fetch (default: 15)"
                }
            },
            "required": []
        }
    },
    {
        "name": "calendar_brief",
        "description": (
            "Fetches today's appointments and events from Google Calendar. "
            "Use when the user asks what's on their schedule, what appointments they have today, "
            "or wants a calendar summary. Requires Google OAuth credentials in config/google_credentials.json."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "max_results": {
                    "type": "INTEGER",
                    "description": "Max events to fetch (default: 20)"
                }
            },
            "required": []
        }
    },
    {
        "name": "fathom_brief",
        "description": (
            "Fetches today's Fathom meeting recordings. Does NOT read transcripts aloud. "
            "Instead, saves transcripts to the knowledge base, creates a todo/action item file, "
            "and returns a brief summary. "
            "Use for daily brief or when the user asks about today's Fathom meetings."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "max_recordings": {
                    "type": "INTEGER",
                    "description": "Max recordings to include (default: 10)"
                }
            },
            "required": []
        }
    },
    {
        "name": "fathom_search",
        "description": (
            "Saves all Fathom meeting transcripts to a searchable knowledge base and "
            "searches them for relevant content. Use when the user asks about previous "
            "meeting discussions, topics, decisions, or action items from past calls. "
            "Examples: 'what did we discuss in the design meeting?', 'find meetings about pricing'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "Search query — topic, keyword, or person name to find in meeting transcripts."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "fathom_todos",
        "description": (
            "Reads back the Fathom meeting todo/action item list. "
            "Use when the user asks 'what are my action items?', 'show me my todos from meetings', "
            "or 'what do I need to do from my calls?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {
                    "type": "STRING",
                    "description": "Optional date YYYY-MM-DD. Defaults to the most recent todo list."
                }
            },
            "required": []
        }
    },
    {
        "name": "fathom_analyze",
        "description": (
            "Loads a Fathom meeting transcript from the knowledge base and returns it "
            "for AI analysis. Use this when the user asks to analyze, summarize, or extract "
            "action items from a specific meeting. "
            "After analyzing the transcript, call fathom_save_todo with the results. "
            "Examples: 'analyze the kellii interview', 'extract todos from the Jordan meeting', "
            "'summarize my last Fathom call'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "kb_file": {
                    "type": "STRING",
                    "description": "Filename of the KB JSON file to load (e.g. '2026-06-05_kellii X Bryan interview_unknown.json'). If omitted, lists available files."
                }
            },
            "required": []
        }
    },
    {
        "name": "fathom_save_todo",
        "description": (
            "Saves an AI-generated analysis (summary + action items) as a todo markdown file "
            "for a Fathom meeting. Call this after analyzing a transcript with fathom_analyze. "
            "The action_items parameter should be a markdown list of tasks."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {
                    "type": "STRING",
                    "description": "Meeting title."
                },
                "meeting_id": {
                    "type": "STRING",
                    "description": "Fathom recording ID."
                },
                "date": {
                    "type": "STRING",
                    "description": "Meeting date YYYY-MM-DD."
                },
                "summary": {
                    "type": "STRING",
                    "description": "AI-generated summary of the meeting."
                },
                "action_items": {
                    "type": "STRING",
                    "description": "AI-generated action items as markdown, e.g. '- [ ] Task one\\n- [ ] Task two (@assignee)'."
                }
            },
            "required": ["title", "date"]
        }
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None

        # Clap-to-wake system
        self._wake_monitor  = WakeMonitor(on_wake=self._on_wake_phrase)
        self._clap_detector = ClapDetector(
            on_double_clap=self._wake_monitor.arm,
            on_state_change=self._on_clap_state_change,
        )
        self._pending_morning_brief = False  # survives reconnect
        self._last_brief_time = 0.0  # timestamp of last brief (for cooldown)
        self.mcp = MCPManager()  # external MCP servers (connected once at startup)

        # Self-improvement loop (Hermes-style counter-triggered review)
        self._conv_history: list[str] = []   # rolling recent transcript
        self._turns_since_memory = 0
        self._iters_since_skill  = 0
        self._review_running     = False
        self._MEMORY_EVERY = 8   # user turns between memory reviews
        self._SKILL_EVERY  = 10  # tool iterations between skill reviews

    # ---- Self-improvement loop ----------------------------------------

    def _record(self, entry: str):
        """Append a line to the rolling conversation history (for reviews)."""
        if not entry:
            return
        self._conv_history.append(entry)
        if len(self._conv_history) > 60:
            self._conv_history = self._conv_history[-60:]

    def _spawn_review(self, kind: str):
        """Fire a background memory/skill review (non-blocking, one at a time)."""
        if self._review_running or not self._loop or not self._conv_history:
            return
        self._review_running = True
        transcript = "\n".join(self._conv_history[-40:])
        self._loop.run_in_executor(None, self._do_review, kind, transcript)

    def _do_review(self, kind: str, transcript: str):
        """Runs in a worker thread: review recent conversation, apply results."""
        try:
            if kind == "memory":
                known = format_memory_for_prompt(load_memory())
                mems = self_improve.review_memory(transcript, known)
                for m in mems:
                    update_memory({m["category"]: {m["key"]: {"value": m["value"]}}})
                    self.ui.write_log(f"SYS: Remembered — {m['key']}: {m['value']}")
                if mems:
                    print(f"[SelfImprove] saved {len(mems)} memory item(s)")
            else:  # skill
                existing = [s["name"] for s in skills_manager.list_skills()]
                skill = self_improve.review_skill(transcript, existing)
                if skill and not skills_manager.skill_exists(skill["name"]):
                    fn = skills_manager.create_skill(
                        skill["name"], skill["description"], skill["body"])
                    self.ui.write_log(f"SYS: Learned new skill — {fn}")
                    print(f"[SelfImprove] created skill {fn}")
        except Exception as e:
            print(f"[SelfImprove] error: {e}")
        finally:
            self._review_running = False

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            was_speaking = self._is_speaking
            self._is_speaking = value
        # Only act on transitions, not every chunk
        if value and not was_speaking:
            self.ui.set_state("SPEAKING")
            self._clap_detector.set_armed(False)
        elif not value and was_speaking and not self.ui.muted:
            self.ui.set_state("LISTENING")
            self._clap_detector.set_armed(True)

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _on_wake_phrase(self):
        """Called when the wake phrase 'wake up daddy's home' is detected after a double clap."""
        import threading as _th
        import time as _time
        print("=" * 60)
        print("[JARVIS] 🎯🎯🎯 WAKE PHRASE DETECTED! _on_wake_phrase CALLED!")
        print(f"[JARVIS] Thread: {_th.current_thread().name}")
        print("=" * 60)
        self.ui.write_log("SYS: Wake phrase detected — triggering morning brief.")

        # Bring window to foreground + fullscreen via signal (thread-safe).
        # QueuedConnection posts to main thread's event loop — returns immediately.
        self.ui.wake_and_focus()

        # Disarm clap detector while we handle the brief
        self._clap_detector.set_armed(False)

        # Mark that we need the morning brief (survives reconnect)
        self._pending_morning_brief = True

        # Wait for main thread to process the signal and run the external script.
        # The external bring_to_front.py needs ~1s to launch and restore the window.
        print("[JARVIS] ⏳ Waiting 2s for main thread to restore window...")
        _time.sleep(2)

        # Fire the brief
        self._fire_morning_brief()

    def _fire_morning_brief(self):
        """Send the morning brief trigger to Gemini. Safe to call even if session is temporarily down."""
        import time as _time
        _time.sleep(0.3)  # visual settling

        if not self._loop or not self.session:
            print("[JARVIS] ⏳ Session not ready — brief will fire after reconnect")
            return

        print("[JARVIS] 📋 Sending morning brief trigger to Gemini...")
        self.speak(
            "[MORNING_BRIEF_TRIGGER] "
            "The user has triggered the morning brief with the clap-and-wake sequence. "
            "Call the morning_brief tool immediately with a dramatic Tony Stark-style greeting, "
            "then fetch Gmail and Calendar summaries."
        )
        self._pending_morning_brief = False
        self._last_brief_time = _time.time()


    def _on_clap_state_change(self, armed: bool):
        """Called when clap detector arms/disarms."""
        state = "armed" if armed else "disarmed"
        print(f"[JARVIS] Clap detector {state}.")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)
        skills_block = skills_manager.skills_prompt_block()
        if skills_block:
            parts.append(skills_block)

        # Built-in tools + any tools discovered from connected MCP servers
        all_declarations = TOOL_DECLARATIONS + self.mcp.declarations

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": all_declarations}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        # Self-improvement: track tool usage; periodically review for new skills
        self._record(f"[tool] {name} {json.dumps(args)[:200]}")
        self._iters_since_skill += 1
        if self._iters_since_skill >= self._SKILL_EVERY:
            self._iters_since_skill = 0
            self._spawn_review("skill")

        # Route to an external MCP server tool if this name belongs to one
        if self.mcp.has_tool(name):
            try:
                r = await self.mcp.call(name, args)
            except Exception as e:
                r = f"MCP error: {str(e)[:200]}"
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": r or "Done."}
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        if name == "load_skill":
            skill_name = args.get("name", "")
            body = skills_manager.load_skill(skill_name)
            if body:
                print(f"[Skill] 📜 Loaded skill: {skill_name}")
                result = (
                    f"SKILL INSTRUCTIONS for '{skill_name}' — follow these now:\n\n{body}"
                )
            else:
                avail = ", ".join(s["name"] for s in skills_manager.list_skills())
                result = f"No skill named '{skill_name}'. Available skills: {avail or 'none'}."
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        if name == "create_skill":
            try:
                fn = skills_manager.create_skill(
                    args.get("name", "skill"),
                    args.get("description", ""),
                    args.get("body", ""),
                )
                self.ui.write_log(f"SYS: Learned new skill — {fn}")
                result = f"Skill saved as {fn}. I'll use it next time it's relevant."
            except Exception as e:
                result = f"Couldn't save skill: {str(e)[:120]}"
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": result}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "spotify_music":
                r = await loop.run_in_executor(None, lambda: spotify_music(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "morning_brief":
                # Cooldown: if the local wake phrase already triggered a brief
                # within the last 30 seconds, skip this Gemini-triggered call
                # to avoid delivering the brief twice.
                import time as _time
                if _time.time() - self._last_brief_time < 30.0:
                    print("[JARVIS] ⏭ morning_brief skipped (cooldown — already delivered)")
                    result = "Morning brief already delivered, sir."
                else:
                    r = await loop.run_in_executor(
                        None,
                        lambda: morning_brief(
                            parameters=args, player=self.ui,
                            session_memory=None, speak=self.speak
                        ),
                    )
                    result = r or "Morning brief delivered."
                    self._last_brief_time = _time.time()

            elif name == "gmail_brief":
                r = await loop.run_in_executor(
                    None,
                    lambda: gmail_brief(parameters=args, player=self.ui),
                )
                result = r or "No important emails."

            elif name == "calendar_brief":
                r = await loop.run_in_executor(
                    None,
                    lambda: calendar_brief(parameters=args, player=self.ui),
                )
                result = r or "No events today."

            elif name == "fathom_brief":
                r = await loop.run_in_executor(
                    None,
                    lambda: fathom_brief(parameters=args, player=self.ui, speak=self.speak),
                )
                result = r or "No Fathom recordings today."

            elif name == "fathom_search":
                r = await loop.run_in_executor(
                    None,
                    lambda: fathom_search(parameters=args, player=self.ui),
                )
                result = r or "No results found."

            elif name == "fathom_todos":
                r = await loop.run_in_executor(
                    None,
                    lambda: fathom_todos(parameters=args, player=self.ui),
                )
                result = r or "No todo list found."

            elif name == "fathom_analyze":
                r = await loop.run_in_executor(
                    None,
                    lambda: fathom_analyze(parameters=args, player=self.ui),
                )
                result = r or "No transcript data."

            elif name == "fathom_save_todo":
                r = await loop.run_in_executor(
                    None,
                    lambda: fathom_save_todo(parameters=args, player=self.ui),
                )
                result = r or "Todo saved."

            elif name == "shutdown_jarvis":
                self._clap_detector.stop()
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            if not jarvis_speaking and not self.ui.muted:
                data = indata.tobytes()
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": data, "mime_type": "audio/pcm"}
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        while True:
            try:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)
                                self._wake_monitor.on_transcript(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                self._record(f"You: {full_in}")
                                self._turns_since_memory += 1
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                                self._record(f"Jarvis: {full_out}")
                            out_buf = []

                            # Self-improvement: periodically review for new memories
                            if self._turns_since_memory >= self._MEMORY_EVERY:
                                self._turns_since_memory = 0
                                self._spawn_review("memory")

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
            except Exception as e:
                print(f"[JARVIS] ❌ Recv: {e}")
                traceback.print_exc()
                # Don't re-raise — let the outer run() loop handle reconnection
                break

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                # Feed real audio amplitude to the HUD for voice-reactive pulsing
                try:
                    samples = np.frombuffer(chunk, dtype=np.int16)
                    if samples.size:
                        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
                        self.ui.set_audio_level(min(1.0, rms / 6000.0))
                except Exception:
                    pass
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            self.ui.set_audio_level(0.0)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        # Connect external MCP servers once (persists across reconnects).
        try:
            await self.mcp.connect_all()
        except Exception as e:
            print(f"[MCP] connect_all failed: {e}")

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")
                    self._clap_detector.start()

                    # If morning brief was interrupted by a disconnect, re-fire it
                    if self._pending_morning_brief:
                        print("[JARVIS] 🔄 Re-firing morning brief after reconnect...")
                        self.ui.write_log("SYS: Reconnecting morning brief...")
                        # Small delay so session is fully ready
                        await asyncio.sleep(1)
                        self._fire_morning_brief()

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()
            self._clap_detector.stop()
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()