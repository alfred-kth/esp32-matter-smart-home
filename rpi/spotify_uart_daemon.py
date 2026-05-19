#!/usr/bin/env python3
"""
spotify_uart_daemon.py — Raspberry Pi Zero UART ↔ Spotify bridge

Listens on the serial port for commands from the ESP32-C6 and controls
Spotify playback via the Spotify Web API (spotipy).

Commands recognised (terminated by newline):
  CMD:PLAY   → Transfer playback to the local librespot device
  CMD:STOP   → Pause playback on the current device

Required environment variables (set in .env or export them):
  SPOTIPY_CLIENT_ID       — Spotify application Client ID
  SPOTIPY_CLIENT_SECRET   — Spotify application Client Secret
  SPOTIPY_REDIRECT_URI    — OAuth redirect URI  (https://localhost:8888/callback)
  SPOTIFY_DEVICE_NAME     — Name of your librespot instance (e.g. "raspotify")

Optional:
  SERIAL_PORT             — Serial device path   (default: /dev/serial0)
  SERIAL_BAUD             — Baud rate             (default: 115200)
"""

import os
import sys
import ssl
import time
import logging
import signal
import tempfile
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import serial
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("spotify-uart")

# ── Load .env if present ─────────────────────────────────
load_dotenv()

# ── Configuration ────────────────────────────────────────
SERIAL_PORT   = os.getenv("SERIAL_PORT", "/dev/serial0")
SERIAL_BAUD   = int(os.getenv("SERIAL_BAUD", "115200"))
DEVICE_NAME   = os.getenv("SPOTIFY_DEVICE_NAME", "raspotify")

SCOPE = "user-read-playback-state user-modify-playback-state"

# ── Graceful shutdown ────────────────────────────────────
running = True

def _signal_handler(sig, frame):
    global running
    log.info("Received signal %s – shutting down…", sig)
    running = False

signal.signal(signal.SIGINT,  _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


# ── Self-signed certificate helper ──────────────────────

def _generate_self_signed_cert():
    """Generate a temporary self-signed cert+key pair for the HTTPS callback server."""
    cert_dir = tempfile.mkdtemp(prefix="spotify_cert_")
    cert_path = os.path.join(cert_dir, "cert.pem")
    key_path = os.path.join(cert_dir, "key.pem")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "365", "-nodes",
            "-subj", "/CN=localhost",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log.info("Generated self-signed TLS cert in %s", cert_dir)
    return cert_path, key_path


# ── HTTPS OAuth callback server ─────────────────────────

class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Tiny handler that captures the OAuth 'code' query-param."""

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [None])[0]
        if code:
            self.server.auth_code = code
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authenticated!</h1>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing 'code' parameter.")

    def log_message(self, format, *args):  # noqa: A002
        log.debug("Callback server: %s", format % args)


def _wait_for_oauth_code(port: int = 8888, timeout: int = 120) -> str | None:
    """Start an HTTPS server on *port* and block until the OAuth code arrives."""
    cert_path, key_path = _generate_self_signed_cert()

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)

    server = HTTPServer(("", port), _OAuthCallbackHandler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    server.auth_code = None

    log.info("HTTPS callback server listening on https://localhost:%d/callback", port)

    deadline = time.time() + timeout
    while server.auth_code is None and time.time() < deadline:
        server.timeout = max(1, deadline - time.time())
        server.handle_request()

    server.server_close()
    return server.auth_code


# ── Spotify helpers ──────────────────────────────────────

def create_spotify_client() -> spotipy.Spotify:
    """Create an authenticated Spotify client using OAuth Authorization Code Flow.

    If no cached token exists, this will start a local HTTPS server on port 8888
    and print a URL to visit. After the user authenticates in a browser,
    the server captures the code and exchanges it for a token.
    """
    auth_manager = SpotifyOAuth(
        scope=SCOPE,
        open_browser=False,     # headless Pi – print URL to terminal
    )

    # If we already have a valid cached token, skip the server
    token_info = auth_manager.cache_handler.get_cached_token()
    if token_info and not auth_manager.is_token_expired(token_info):
        log.info("Using cached Spotify token")
    else:
        # Print the auth URL for the user to open
        auth_url = auth_manager.get_authorize_url()
        log.info("\n" + "=" * 60)
        log.info("Open this URL in a browser to authenticate with Spotify:")
        log.info("\n  %s\n", auth_url)
        log.info("(Accept any browser warning about the self-signed certificate)")
        log.info("=" * 60 + "\n")

        # Start HTTPS server and wait for the callback
        code = _wait_for_oauth_code(port=8888, timeout=120)
        if code is None:
            log.error("Timed out waiting for Spotify OAuth callback")
            sys.exit(1)

        # Exchange the code for an access token
        auth_manager.get_access_token(code, as_dict=False)
        log.info("OAuth token obtained successfully")

    sp = spotipy.Spotify(auth_manager=auth_manager)
    # Force an early request to validate/refresh the token
    sp.current_user()
    log.info("Spotify authenticated successfully")
    return sp


def resolve_device_id(sp: spotipy.Spotify, device_name: str) -> str | None:
    """Look up the Spotify device ID by its human-readable name."""
    try:
        devices = sp.devices()
        for dev in devices.get("devices", []):
            if device_name.lower() in dev["name"].lower():
                log.info("Resolved device '%s' → %s", dev["name"], dev["id"])
                return dev["id"]
        log.warning("Device '%s' not found.  Available devices: %s",
                    device_name,
                    [d["name"] for d in devices.get("devices", [])])
    except Exception as exc:
        log.error("Failed to list Spotify devices: %s", exc)
    return None


def transfer_playback(sp: spotipy.Spotify, device_name: str) -> bool:
    """Transfer Spotify playback to the named device and start playing."""
    try:
        device_id = resolve_device_id(sp, device_name)
        if device_id is None:
            log.error("Cannot transfer – device not found")
            return False

        # Transfer to the target device
        sp.transfer_playback(device_id=device_id, force_play=True)

        # Also explicitly start playback to handle the case where
        # nothing was actively playing before the transfer.
        try:
            sp.start_playback(device_id=device_id)
        except spotipy.exceptions.SpotifyException:
            pass  # start_playback can fail if no context; transfer is enough

        log.info("✅  Playback transferred to '%s'", device_name)
        return True

    except spotipy.exceptions.SpotifyException as exc:
        if exc.http_status == 401:
            log.warning("Token expired – forcing refresh…")
            sp.auth_manager.get_access_token(as_dict=False, check_cache=False)
            return transfer_playback(sp, device_name)   # retry once
        log.error("Spotify API error: %s", exc)
    except Exception as exc:
        log.error("Unexpected error during transfer: %s", exc)
    return False


def pause_playback(sp: spotipy.Spotify) -> bool:
    """Pause playback on whatever device is currently active."""
    try:
        sp.pause_playback()
        log.info("⏸  Playback paused")
        return True
    except spotipy.exceptions.SpotifyException as exc:
        if exc.http_status == 401:
            log.warning("Token expired – forcing refresh…")
            sp.auth_manager.get_access_token(as_dict=False, check_cache=False)
            return pause_playback(sp)
        if exc.http_status == 403:
            log.warning("Pause not allowed (maybe already paused or no active device)")
            return True
        log.error("Spotify API error during pause: %s", exc)
    except Exception as exc:
        log.error("Unexpected error during pause: %s", exc)
    return False


# ── Serial loop ──────────────────────────────────────────

def main():
    log.info("Starting Spotify UART daemon")
    log.info("Serial port: %s @ %d baud", SERIAL_PORT, SERIAL_BAUD)
    log.info("Target Spotify device name: '%s'", DEVICE_NAME)

    # ── Authenticate with Spotify ────────────────────────
    sp = create_spotify_client()

    # ── Open serial port ─────────────────────────────────
    ser = None
    while running and ser is None:
        try:
            ser = serial.Serial(
                port=SERIAL_PORT,
                baudrate=SERIAL_BAUD,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1,          # 1-second read timeout – keeps the loop responsive
            )
            log.info("Serial port %s opened", SERIAL_PORT)
        except serial.SerialException as exc:
            log.error("Cannot open serial port: %s – retrying in 5 s…", exc)
            time.sleep(5)

    # ── Main read loop ───────────────────────────────────
    buffer = b""
    while running:
        try:
            chunk = ser.read(ser.in_waiting or 1)
            if not chunk:
                continue

            buffer += chunk

            # Process complete lines
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                cmd = line.decode("utf-8", errors="replace").strip()

                if not cmd:
                    continue

                # Look for commands anywhere in the line (ESP32 log
                # lines wrap the raw command in debug output).
                if "CMD:PLAY" in cmd:
                    log.info("<<< Matched CMD:PLAY")
                    transfer_playback(sp, DEVICE_NAME)
                elif "CMD:STOP" in cmd:
                    log.info("<<< Matched CMD:STOP")
                    pause_playback(sp)
                # Silently ignore other ESP32 log chatter

        except serial.SerialException as exc:
            log.error("Serial error: %s – attempting reconnect…", exc)
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            while running and ser is None:
                try:
                    time.sleep(2)
                    ser = serial.Serial(
                        port=SERIAL_PORT,
                        baudrate=SERIAL_BAUD,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        timeout=1,
                    )
                    log.info("Serial port reconnected")
                    buffer = b""
                except serial.SerialException:
                    log.warning("Reconnect failed – retrying in 5 s…")
                    time.sleep(3)

        except Exception as exc:
            log.error("Unexpected error in main loop: %s", exc)
            time.sleep(1)

    # ── Cleanup ──────────────────────────────────────────
    if ser and ser.is_open:
        ser.close()
        log.info("Serial port closed")
    log.info("Daemon stopped")


if __name__ == "__main__":
    main()
