#!/usr/bin/env python3
"""
fetch_device_id.py — One-shot helper to list all Spotify Connect devices
and their IDs.  Run this AFTER librespot/raspotify is running to find the
device name you need to put in SPOTIFY_DEVICE_NAME.

Usage:
  python3 fetch_device_id.py
"""

import os
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

load_dotenv()

SCOPE = "user-read-playback-state"

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=SCOPE, open_browser=False))

devices = sp.devices()
if not devices["devices"]:
    print("⚠  No Spotify Connect devices found.")
    print("   Make sure librespot / raspotify is running and logged in.")
else:
    print(f"\n{'Name':<30} {'ID':<45} {'Type':<15} {'Active'}")
    print("─" * 95)
    for d in devices["devices"]:
        print(f"{d['name']:<30} {d['id']:<45} {d['type']:<15} {'✓' if d['is_active'] else ''}")
    print()
