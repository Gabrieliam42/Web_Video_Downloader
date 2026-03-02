# Script Developer: Gabriel Mihai Sandu
# GitHub Profile: https://github.com/Gabrieliam42

import sys
import os

if getattr(sys, 'frozen', False):
    python_root = r'C:\Program Files\Python312'
    if not os.path.exists(python_root):
        python_root = sys.base_prefix
    print(f"Running as PyInstaller bundle. Using system Python: {python_root}")
else:
    python_root = sys.base_prefix
    print(f"Running as Python script. Using Python: {python_root}")

tcl_library_path = os.path.join(python_root, 'tcl', 'tcl8.6')
tk_library_path = os.path.join(python_root, 'tcl', 'tk8.6')

if not os.path.exists(tcl_library_path):
    print(f"WARNING: TCL library not found at {tcl_library_path}")
if not os.path.exists(tk_library_path):
    print(f"WARNING: TK library not found at {tk_library_path}")

os.environ['TCL_LIBRARY'] = tcl_library_path
os.environ['TK_LIBRARY'] = tk_library_path
print(f"TCL_LIBRARY: {tcl_library_path}")
print(f"TK_LIBRARY: {tk_library_path}")

import ctypes
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading
import yt_dlp
import re
import json
import shutil
from playwright.sync_api import sync_playwright
import browser_cookie3

os.environ['PLAYWRIGHT_BROWSERS_PATH'] = os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'ms-playwright')


def is_admin():
    print("Checking for administrator privileges...")
    try:
        admin_status = ctypes.windll.shell32.IsUserAnAdmin()
        print(f"Administrator status: {admin_status}")
        return admin_status
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False


def elevate_privileges():
    print("Not running as administrator. Attempting to elevate privileges...")
    try:
        script_path = os.path.abspath(sys.argv[0])
        print(f"Script path: {script_path}")

        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        print(f"Parameters: {params}")

        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script_path}" {params}',
            None,
            1
        )

        print(f"ShellExecuteW return value: {ret}")

        if ret > 32:
            print("Successfully spawned elevated process. Exiting non-elevated instance.")
            sys.exit(0)
        else:
            print(f"Failed to elevate. Return code: {ret}")
            messagebox.showerror("Elevation Failed", f"Could not elevate privileges. Error code: {ret}")
            sys.exit(1)

    except Exception as e:
        print(f"Error during elevation: {e}")
        messagebox.showerror("Elevation Error", f"Failed to elevate: {str(e)}")
        sys.exit(1)


def extract_video_url_playwright(url, output_widget):
    """Extract video URL using Playwright browser automation (fallback for yt-dlp failures)"""
    print(f"Attempting Playwright extraction for: {url}")

    def safe_log(msg):
        """Thread-safe logging to output widget"""
        try:
            output_widget.insert(tk.END, msg + "\n")
            output_widget.see(tk.END)
            output_widget.update()
        except Exception:
            print(msg)

    safe_log("yt-dlp failed, trying Playwright browser automation (headless)...")

    import urllib.parse
    target_video_id = None
    is_facebook = 'facebook.com' in url
    is_youtube = ('youtube.com' in url) or ('youtu.be' in url)
    if is_facebook:
        parts = url.split('/')
        if 'reel' in parts:
            idx = parts.index('reel')
            if idx + 1 < len(parts):
                target_video_id = parts[idx + 1].split('?')[0]
        elif 'watch' in url and '?v=' in url:
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            target_video_id = params.get('v', [None])[0]

        if target_video_id:
            safe_log(f"Target video ID: {target_video_id}")
    elif is_youtube:
        try:
            parsed = urllib.parse.urlparse(url)
            if 'youtu.be' in parsed.netloc:
                path = parsed.path.strip('/')
                if path:
                    target_video_id = path.split('/')[0]
            else:
                params = urllib.parse.parse_qs(parsed.query)
                if params.get('v'):
                    target_video_id = params.get('v', [None])[0]
                elif '/shorts/' in parsed.path:
                    target_video_id = parsed.path.split('/shorts/')[1].split('/')[0]
                elif '/embed/' in parsed.path:
                    target_video_id = parsed.path.split('/embed/')[1].split('/')[0]
            if target_video_id:
                safe_log(f"Target video ID: {target_video_id}")
        except Exception:
            pass

    video_urls = []
    dom_candidates = []
    playable_urls = []
    candidate_urls = []

    def extract_playable_urls_from_text(text):
        urls = []
        if not text:
            return urls
        keys = (
            'playable_url_quality_hd',
            'playable_url',
            'playable_url_quality_sd',
            'playable_url_dash',
            'playable_url_dash_sd',
            'dash_manifest_url',
            'dash_manifest_urls',
            'hls_playlist_url',
            'hls_playlist_urls',
            'browser_native_hd_url',
            'browser_native_sd_url',
            'progressive_url',
            'progressive_urls',
            'manifest_url',
            'base_url',
            'base_url_secure',
        )
        for key in keys:
            pattern = rf'"{key}":"([^"]+)"'
            for m in re.finditer(pattern, text):
                raw = m.group(1)
                if not raw or raw == 'null':
                    continue
                try:
                    u = json.loads(f'"{raw}"')
                except Exception:
                    u = raw.replace('\\/', '/').replace('\\u0026', '&')
                if u.startswith('http'):
                    urls.append(u)
        return urls

    def normalize_fbcdn_url(u):
        try:
            parsed = urllib.parse.urlparse(u)
            host = parsed.netloc.lower()
            if 'fbcdn' not in host and 'facebook.com' not in host:
                return u
            q = urllib.parse.parse_qs(parsed.query)
            removed = False
            for k in ('bytestart', 'byteend', 'range', 'rangeStart', 'rangeEnd'):
                if k in q:
                    q.pop(k, None)
                    removed = True
            if removed:
                new_query = urllib.parse.urlencode(q, doseq=True)
                return parsed._replace(query=new_query).geturl()
        except Exception:
            pass
        return u

    def parse_efg_info(u):
        if not target_video_id or not is_facebook:
            return None
        try:
            parsed = urllib.parse.urlparse(u)
            query_params = urllib.parse.parse_qs(parsed.query)
            efg = query_params.get('efg', [''])[0]
            if not efg:
                return None
            import base64
            decoded_efg = urllib.parse.unquote(efg)
            return json.loads(base64.b64decode(decoded_efg).decode('utf-8'))
        except Exception:
            return None
        return None

    def url_matches_target(u):
        if not target_video_id:
            return True
        try:
            parsed = urllib.parse.urlparse(u)
            query_params = urllib.parse.parse_qs(parsed.query)
            if is_facebook:
                for key in ('v', 'video_id'):
                    if key in query_params and query_params[key]:
                        if str(query_params[key][0]) != str(target_video_id):
                            return False
                efg_json = parse_efg_info(u)
                if efg_json:
                    video_id_in_url = str(efg_json.get('video_id', ''))
                    if video_id_in_url and video_id_in_url != str(target_video_id):
                        return False
            elif is_youtube:
                if 'youtube.com' in parsed.netloc:
                    if query_params.get('v'):
                        if str(query_params.get('v', [''])[0]) != str(target_video_id):
                            return False
                if '/shorts/' in parsed.path:
                    vid = parsed.path.split('/shorts/')[1].split('/')[0]
                    if vid and vid != str(target_video_id):
                        return False
                if '/embed/' in parsed.path:
                    vid = parsed.path.split('/embed/')[1].split('/')[0]
                    if vid and vid != str(target_video_id):
                        return False
        except Exception:
            pass
        return True

    def is_video_url(u):
        try:
            u = u.lower()
            if re.search(r'\\.(mp4|m4s|m3u8|mpd|webm)(\\?|$)', u):
                return True
            if 'googlevideo.com' in u and ('videoplayback' in u or '/api/manifest' in u):
                return True
            if 'manifest.googlevideo.com' in u or 'youtube.com/api/manifest' in u:
                return True
            if 'mime=video%2f' in u or 'mime=audio%2f' in u or 'mime=video/' in u or 'mime=audio/' in u:
                return True
            return False
        except Exception:
            return False

    def extract_manifest_urls(manifest_xml):
        urls = []
        try:
            import html as html_mod
            import xml.etree.ElementTree as ET
            root = ET.fromstring(manifest_xml)
            ns = {'mpd': 'urn:mpeg:dash:schema:mpd:2011'}
            for el in root.findall('.//mpd:BaseURL', ns):
                if el.text:
                    u = html_mod.unescape(el.text.strip())
                    if is_video_url(u):
                        urls.append(u)
        except Exception:
            pass
        return urls

    def extract_manifest_urls_from_text(text):
        urls = []
        if not text or 'manifest_xml' not in text:
            return urls
        for m in re.finditer(r'\"manifest_xml\":\"([^\"]+)\"', text):
            raw = m.group(1)
            try:
                xml_text = json.loads(f'\"{raw}\"')
            except Exception:
                xml_text = raw.replace('\\/', '/').replace('\\u003C', '<').replace('\\u003E', '>').replace('\\u0026', '&')
            if xml_text:
                urls.extend(extract_manifest_urls(xml_text))
        return urls

    def extract_urls_from_json_bytes(body_bytes):
        urls = []
        if not body_bytes:
            return urls
        text = body_bytes.decode('utf-8', errors='ignore')

        def walk(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)
            elif isinstance(obj, str):
                if 'http' in obj and is_video_url(obj):
                    urls.append(obj)

        parsed = False
        try:
            data = json.loads(text)
            walk(data)
            parsed = True
        except Exception:
            pass

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                walk(data)
                def walk_manifest(o):
                    if isinstance(o, dict):
                        for k,v in o.items():
                            if k == 'manifest_xml' and isinstance(v, str):
                                urls.extend(extract_manifest_urls(v))
                            else:
                                walk_manifest(v)
                    elif isinstance(o, list):
                        for it in o:
                            walk_manifest(it)
                walk_manifest(data)
                parsed = True
            except Exception:
                continue

        if not parsed:
            for m in re.finditer(r'https?://[^\"\\s]+', text):
                u = m.group(0)
                if is_video_url(u):
                    urls.append(u)

        return urls

    def load_facebook_cookies():
        def has_c_user(cookie_list):
            return any(c.name == 'c_user' for c in cookie_list)

        cookies_local = None
        try:
            cookies_local = list(browser_cookie3.firefox(domain_name='facebook.com'))
            safe_log(f"Extracted {len(cookies_local)} cookies from Firefox (default profile)")
        except Exception as e:
            safe_log(f"Cookie extraction failed (default profile): {e}")

        if cookies_local and has_c_user(cookies_local):
            return cookies_local

        try:
            import glob
            profile_paths = []
            for base in (os.getenv('APPDATA'), os.getenv('LOCALAPPDATA')):
                if base:
                    profile_paths += glob.glob(os.path.join(base, 'Mozilla', 'Firefox', 'Profiles', '*', 'cookies.sqlite'))
            profile_paths = list(dict.fromkeys(profile_paths))

            best = None
            best_path = None
            best_count = -1
            best_has_c_user = False

            for path in profile_paths:
                try:
                    cj = browser_cookie3.firefox(cookie_file=path, domain_name='facebook.com')
                    lst = list(cj)
                    if not lst:
                        continue
                    has_c = has_c_user(lst)
                    if has_c and (not best_has_c_user or len(lst) > best_count):
                        best = lst
                        best_path = path
                        best_count = len(lst)
                        best_has_c_user = True
                    elif not best_has_c_user and len(lst) > best_count:
                        best = lst
                        best_path = path
                        best_count = len(lst)
                except Exception as e:
                    safe_log(f"Cookie read failed for {path}: {e}")

            if best:
                safe_log(f"Using cookies from profile: {best_path} ({best_count} cookies)")
                return best
        except Exception as e:
            safe_log(f"Profile scan failed: {e}")

        if cookies_local:
            if not has_c_user(cookies_local):
                safe_log("Warning: Facebook login cookie (c_user) not found. Please log in to Facebook in Firefox.")
            return cookies_local

        safe_log("No Firefox cookies found for Facebook.")
        return None

    def load_youtube_cookies():
        def has_login_cookie(cookie_list):
            names = {
                'SID', 'HSID', 'SSID', 'APISID', 'SAPISID',
                '__Secure-1PSID', '__Secure-3PSID', '__Secure-3PAPISID',
                'LOGIN_INFO'
            }
            return any(c.name in names for c in cookie_list)

        def dedup(cookies_in):
            seen = set()
            out = []
            for c in cookies_in:
                key = (c.name, c.domain, c.path, c.value)
                if key in seen:
                    continue
                seen.add(key)
                out.append(c)
            return out

        domains = [
            'youtube.com',
            'google.com',
            'accounts.google.com',
            'consent.youtube.com',
            'consent.google.com',
        ]

        cookies_local = []
        try:
            for d in domains:
                try:
                    cookies_local.extend(list(browser_cookie3.firefox(domain_name=d)))
                except Exception:
                    pass
            cookies_local = dedup(cookies_local)
            safe_log(f"Extracted {len(cookies_local)} cookies from Firefox (default profile)")
        except Exception as e:
            safe_log(f"Cookie extraction failed (default profile): {e}")

        if cookies_local and has_login_cookie(cookies_local):
            return cookies_local

        try:
            import glob
            profile_paths = []
            for base in (os.getenv('APPDATA'), os.getenv('LOCALAPPDATA')):
                if base:
                    profile_paths += glob.glob(os.path.join(base, 'Mozilla', 'Firefox', 'Profiles', '*', 'cookies.sqlite'))
            profile_paths = list(dict.fromkeys(profile_paths))

            best = None
            best_path = None
            best_count = -1
            best_has_login = False

            for path in profile_paths:
                try:
                    lst = []
                    for d in domains:
                        try:
                            lst.extend(list(browser_cookie3.firefox(cookie_file=path, domain_name=d)))
                        except Exception:
                            pass
                    lst = dedup(lst)
                    if not lst:
                        continue
                    has_login = has_login_cookie(lst)
                    if has_login and (not best_has_login or len(lst) > best_count):
                        best = lst
                        best_path = path
                        best_count = len(lst)
                        best_has_login = True
                    elif not best_has_login and len(lst) > best_count:
                        best = lst
                        best_path = path
                        best_count = len(lst)
                except Exception as e:
                    safe_log(f"Cookie read failed for {path}: {e}")

            if best:
                safe_log(f"Using cookies from profile: {best_path} ({best_count} cookies)")
                return best
        except Exception as e:
            safe_log(f"Profile scan failed: {e}")

        if cookies_local:
            if not has_login_cookie(cookies_local):
                safe_log("Warning: YouTube login cookies not found. Logged-out access only.")
            return cookies_local

        safe_log("No Firefox cookies found for YouTube.")
        return None

    cookies = None
    if is_facebook:
        cookies = load_facebook_cookies()
    elif is_youtube:
        cookies = load_youtube_cookies()

    def extract_mobile_urls(target_id):
        if not target_id:
            return []
        try:
            import urllib.request
            import http.cookiejar
            import html as html_mod

            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': url,
            }

            cj = http.cookiejar.CookieJar()
            if cookies:
                for c in cookies:
                    cj.set_cookie(c)

            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

            page_urls = [
                f'https://m.facebook.com/reel/{target_id}/',
                f'https://m.facebook.com/watch/?v={target_id}',
            ]

            found = []

            def add_url(u):
                if u and u.startswith('http') and is_video_url(u):
                    u_norm = normalize_fbcdn_url(u)
                    if u_norm not in found:
                        found.append(u_norm)

            for page_url in page_urls:
                try:
                    req = urllib.request.Request(page_url, headers=headers)
                    with opener.open(req, timeout=30) as resp:
                        raw = resp.read()
                    html_text = raw.decode('utf-8', errors='ignore')

                    for u in extract_playable_urls_from_text(html_text):
                        add_url(u)

                    for key in ('hd_src', 'sd_src'):
                        for m in re.finditer(rf'"{key}":"([^"]+)"', html_text):
                            raw_u = m.group(1)
                            try:
                                u = json.loads(f'"{raw_u}"')
                            except Exception:
                                u = raw_u.replace('\\/', '/').replace('\\u0026', '&')
                            add_url(u)

                    for m in re.finditer(r'<video[^>]+src="([^"]+)"', html_text, re.I):
                        u = html_mod.unescape(m.group(1))
                        add_url(u)

                    for m in re.finditer(r'data-video-src="([^"]+)"', html_text, re.I):
                        u = html_mod.unescape(m.group(1))
                        add_url(u)
                except Exception:
                    continue

            return found
        except Exception:
            return []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])

            context_options = {
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
            }

            if cookies:
                playwright_cookies = []
                for cookie in cookies:
                    expires = -1
                    if cookie.expires:
                        try:
                            expires_float = float(cookie.expires)
                            if expires_float > 0:
                                if expires_float > 9999999999:

                                    expires = expires_float / 1000.0
                                else:
                                    expires = expires_float
                        except Exception:
                            pass

                    playwright_cookies.append({
                        'name': cookie.name,
                        'value': cookie.value,
                        'domain': cookie.domain,
                        'path': cookie.path,
                        'expires': expires,
                        'httpOnly': bool(cookie.has_nonstandard_attr('HttpOnly')),
                        'secure': bool(cookie.secure),
                        'sameSite': 'Lax'
                    })
                context_options['storage_state'] = {'cookies': playwright_cookies, 'origins': []}

            context = browser.new_context(**context_options)
            page = context.new_page()

            def handle_response(response):
                try:
                    content_type = response.headers.get('content-type', '')
                    resp_url = response.url
                    norm_url = normalize_fbcdn_url(resp_url)

                    if is_video_url(resp_url) or ('video' in content_type) or ('application/dash' in content_type) or ('mpegurl' in content_type):
                        if url_matches_target(resp_url):
                            if norm_url not in video_urls:
                                video_urls.append(norm_url)
                                print(f"Captured video URL: {norm_url[:100]}")

                    if ('graphql' in resp_url or 'application/json' in content_type or 'text/javascript' in content_type) and 'facebook.com' in url:
                        try:
                            body_bytes = response.body()
                            urls = []
                            if body_bytes:
                                urls.extend(extract_urls_from_json_bytes(body_bytes))
                            body = None
                            try:
                                body = body_bytes.decode('utf-8', errors='ignore') if body_bytes else ''
                            except Exception:
                                body = ''
                            if body and 'playable_url' in body:
                                urls.extend(extract_playable_urls_from_text(body))
                            if urls:
                                added = 0
                                for u in urls:
                                    if not u.startswith('http'):
                                        continue
                                    if not is_video_url(u):
                                        continue
                                    if not url_matches_target(u):
                                        continue
                                    u_norm = normalize_fbcdn_url(u)
                                    if u_norm not in video_urls:
                                        video_urls.append(u_norm)
                                    if u_norm not in playable_urls:
                                        playable_urls.append(u_norm)
                                    added += 1
                                if added:
                                    print(f"Extracted {added} playable URL(s) from response")
                        except Exception:
                            pass
                except Exception:
                    pass

            def handle_request(request):
                try:
                    req_url = request.url
                    if not is_video_url(req_url):
                        return
                    if not url_matches_target(req_url):
                        return
                    norm_url = normalize_fbcdn_url(req_url)
                    if norm_url not in video_urls:
                        video_urls.append(norm_url)
                    if norm_url not in playable_urls:
                        playable_urls.append(norm_url)
                        print(f"Captured request URL: {norm_url[:100]}")
                except Exception:
                    pass

            page.on('response', handle_response)
            page.on('request', handle_request)

            safe_log("Loading page...")

            try:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
            except Exception:
                pass

            page.wait_for_timeout(1500)

            if is_youtube:
                try:
                    player_data = page.evaluate("""() => {
                        if (window.ytInitialPlayerResponse) return window.ytInitialPlayerResponse;
                        try {
                            const args = window.ytplayer && window.ytplayer.config && window.ytplayer.config.args;
                            if (args && args.player_response) {
                                return JSON.parse(args.player_response);
                            }
                        } catch (e) {}
                        return null;
                    }""")
                    if isinstance(player_data, dict):
                        streaming = player_data.get('streamingData') or {}
                        yt_found = 0
                        for f in (streaming.get('formats') or []):
                            u = f.get('url')
                            if not u:
                                continue
                            u_norm = normalize_fbcdn_url(u)
                            if u_norm not in video_urls:
                                video_urls.append(u_norm)
                            if u_norm not in playable_urls:
                                playable_urls.append(u_norm)
                            try:
                                w = int(f.get('width') or 0)
                                h = int(f.get('height') or 0)
                                dur_ms = float(f.get('approxDurationMs') or 0)
                                if w and h:
                                    dom_candidates.append({
                                        'src': u_norm,
                                        'width': w,
                                        'height': h,
                                        'duration': dur_ms / 1000 if dur_ms else 0
                                    })
                            except Exception:
                                pass
                            yt_found += 1
                        for f in (streaming.get('adaptiveFormats') or []):
                            u = f.get('url')
                            if not u:
                                continue
                            u_norm = normalize_fbcdn_url(u)
                            if u_norm not in video_urls:
                                video_urls.append(u_norm)
                            if u_norm not in playable_urls:
                                playable_urls.append(u_norm)
                            try:
                                w = int(f.get('width') or 0)
                                h = int(f.get('height') or 0)
                                dur_ms = float(f.get('approxDurationMs') or 0)
                                if w and h:
                                    dom_candidates.append({
                                        'src': u_norm,
                                        'width': w,
                                        'height': h,
                                        'duration': dur_ms / 1000 if dur_ms else 0
                                    })
                            except Exception:
                                pass
                            yt_found += 1

                        for key in ('dashManifestUrl', 'hlsManifestUrl'):
                            u = streaming.get(key)
                            if u:
                                u_norm = normalize_fbcdn_url(u)
                                if u_norm not in video_urls:
                                    video_urls.append(u_norm)
                                if u_norm not in playable_urls:
                                    playable_urls.append(u_norm)
                                yt_found += 1

                        if streaming.get('serverAbrStreamingUrl'):
                            u = streaming.get('serverAbrStreamingUrl')
                            u_norm = normalize_fbcdn_url(u)
                            if u_norm not in video_urls:
                                video_urls.append(u_norm)
                                yt_found += 1

                        if yt_found:
                            safe_log(f"Found {yt_found} YouTube streaming URL(s) in player response")
                except Exception as e:
                    safe_log(f"YouTube player response extraction error: {e}")

            if is_youtube:
                try:
                    page.click('button.ytp-large-play-button', timeout=2000, force=True)
                except Exception:
                    pass
                try:
                    page.click('button.ytp-play-button', timeout=2000, force=True)
                except Exception:
                    pass
                try:
                    page.click('#movie_player', timeout=2000, force=True)
                except Exception:
                    pass
                try:
                    page.evaluate("""() => {
                        const p = document.getElementById('movie_player');
                        if (p && typeof p.playVideo === 'function') {
                            p.playVideo();
                        }
                        const v = document.querySelector('video');
                        if (v) {
                            try { v.muted = true; v.play(); } catch (e) {}
                        }
                    }""")
                except Exception:
                    pass
                page.wait_for_timeout(2500)

            def try_click_label(target, label):
                import re
                pattern = re.compile(label, re.I)

                for role in ('button', 'link'):
                    try:
                        locator = target.get_by_role(role, name=pattern)
                        if locator.count() > 0:
                            locator.first.click(timeout=2000, force=True)
                            try:
                                target.wait_for_timeout(2000)
                            except Exception:
                                pass
                            return True
                    except Exception:
                        pass

                try:
                    locator = target.get_by_text(pattern)
                    if locator.count() > 0:
                        locator.first.click(timeout=2000, force=True)
                        try:
                            target.wait_for_timeout(2000)
                        except Exception:
                            pass
                        return True
                except Exception:
                    pass

                return False

            def try_click_labels_js(target, labels):
                try:
                    clicked_label = target.evaluate("""(labels) => {
                        const lower = labels.map(l => l.toLowerCase());
                        const candidates = Array.from(document.querySelectorAll(
                            'a,button,div[role="button"],span[role="button"],div[role="link"],span[role="link"]'
                        ));
                        for (const el of candidates) {
                            const text = (el.innerText || el.textContent || '').trim().toLowerCase();
                            const aria = (el.getAttribute('aria-label') || '').trim().toLowerCase();
                            const name = text || aria;
                            if (!name) continue;
                            for (const l of lower) {
                                if (name === l || name.includes(l)) {
                                    el.click();
                                    return l;
                                }
                            }
                        }
                        return null;
                    }""", labels)
                    return clicked_label
                except Exception:
                    return None

            def try_click_labels_anywhere(labels):
                clicked_any = False

                for label in labels:
                    if try_click_label(page, label):
                        safe_log(f"Clicked '{label}' to unlock content")
                        clicked_any = True

                clicked_label = try_click_labels_js(page, labels)
                if clicked_label:
                    safe_log(f"Clicked '{clicked_label}' to unlock content (JS)")
                    try:
                        page.wait_for_timeout(2000)
                    except Exception:
                        pass
                    clicked_any = True

                for frame in page.frames:
                    if frame == page.main_frame:
                        continue
                    for label in labels:
                        if try_click_label(frame, label):
                            safe_log(f"Clicked '{label}' to unlock content (frame)")
                            clicked_any = True
                    clicked_label = try_click_labels_js(frame, labels)
                    if clicked_label:
                        safe_log(f"Clicked '{clicked_label}' to unlock content (JS in frame)")
                        try:
                            frame.wait_for_timeout(2000)
                        except Exception:
                            pass
                        clicked_any = True

                return clicked_any

            if 'facebook.com' in url:
                try_click_labels_anywhere(['Learn more'])
                page.wait_for_timeout(2000)
                try_click_labels_anywhere(['See video'])
                page.wait_for_timeout(2000)

                labels = [
                    'Learn more',
                    'Learn More',
                    'See video',
                    'See Video',
                    'See Reel',
                    'See Content',
                    'Watch Video',
                    'View Video',
                    'View Content',
                    'Continue',
                    'I Understand'
                ]

                for _ in range(3):
                    clicked_any = try_click_labels_anywhere(labels)
                    if not clicked_any:
                        break
                    page.wait_for_timeout(2000)

            try:
                html = page.content()
                urls = extract_playable_urls_from_text(html)
                if urls:
                    safe_log(f"Found {len(urls)} playable URL(s) in HTML")
                    for u in urls:
                        if not is_video_url(u):
                            continue
                        if not url_matches_target(u):
                            continue
                        u_norm = normalize_fbcdn_url(u)
                        if u_norm not in video_urls:
                            video_urls.append(u_norm)
                        if u_norm not in playable_urls:
                            playable_urls.append(u_norm)
                manifest_urls = extract_manifest_urls_from_text(html)
                if manifest_urls:
                    safe_log(f"Found {len(manifest_urls)} manifest URL(s) in HTML")
                    for u in manifest_urls:
                        if not is_video_url(u):
                            continue
                        if not url_matches_target(u):
                            continue
                        u_norm = normalize_fbcdn_url(u)
                        if u_norm not in video_urls:
                            video_urls.append(u_norm)
                        if u_norm not in playable_urls:
                            playable_urls.append(u_norm)
            except Exception as e:
                safe_log(f"HTML playable_url extraction error: {e}")

            try:
                page.evaluate("""() => {
                    const v = document.querySelector('video');
                    if (v) {
                        try { v.muted = true; v.play(); } catch (e) {}
                    }
                }""")
            except Exception:
                pass

            try:
                try:
                    video_count = page.evaluate("() => document.querySelectorAll('video').length")
                    if video_count:
                        safe_log(f"Detected {video_count} video element(s), waiting for content to load...")
                    else:
                        safe_log("No video element detected yet, polling for content...")
                except Exception:
                    safe_log("Could not query video elements, polling for content...")

                import time
                max_wait = 25

                dom_srcs = []

                for attempt in range(max_wait):
                    dom_srcs = page.evaluate("""() => {
                        const videos = document.querySelectorAll('video');
                        const srcs = [];
                        for (let v of videos) {
                            const src = v.src || v.currentSrc;
                            if (src && src.startsWith('http') && v.duration > 0 && v.videoWidth > 0) {
                                srcs.push({
                                    src: src,
                                    duration: v.duration,
                                    readyState: v.readyState,
                                    width: v.videoWidth,
                                    height: v.videoHeight
                                });
                            }
                        }
                        return srcs;
                    }""")

                    if dom_srcs:
                        break

                    time.sleep(1)

                if dom_srcs:
                    dom_candidates = dom_srcs
                    safe_log(f"Found {len(dom_srcs)} valid video(s) with loaded content")
                    for vid in dom_srcs:
                        if not url_matches_target(vid['src']):
                            continue
                        src_norm = normalize_fbcdn_url(vid['src'])
                        if src_norm not in video_urls:
                            video_urls.append(src_norm)
                            print(f"Extracted: {vid['duration']:.1f}s, {vid['width']}x{vid['height']}, src={src_norm[:100]}")
                else:
                    safe_log("No valid videos found after 15s wait")

            except Exception as e:
                safe_log(f"DOM extraction error: {e}")

            if not video_urls:
                try:
                    title = page.title()
                    safe_log(f"Page title: {title}")
                except Exception:
                    pass
                try:
                    preview = page.evaluate("""() => {
                        const t = document.body ? document.body.innerText : '';
                        return (t || '').replace(/\\s+/g, ' ').slice(0, 200);
                    }""")
                    if preview:
                        safe_log(f"Page text preview: {preview}")
                except Exception:
                    pass

            safe_log(f"Waiting for more content... ({len(video_urls)} URLs captured)")
            page.wait_for_timeout(5000)

            if 'facebook.com' in url and target_video_id and len(playable_urls) < 2:
                mobile_urls = extract_mobile_urls(target_video_id)
                if mobile_urls:
                    safe_log(f"Found {len(mobile_urls)} playable URL(s) from mobile site")
                    for u in mobile_urls:
                        if not url_matches_target(u):
                            continue
                        u_norm = normalize_fbcdn_url(u)
                        if u_norm not in video_urls:
                            video_urls.append(u_norm)
                        if u_norm not in playable_urls:
                            playable_urls.append(u_norm)

            browser.close()

    except Exception as e:
        safe_log(f"Playwright error: {e}")
        print(f"Playwright error: {e}")
        import traceback
        traceback.print_exc()
        return None

    if video_urls:
        safe_log(f"Successfully extracted {len(video_urls)} video URL(s)")

        seen = set()

        def add_candidate(u):
            if u and u not in seen:
                candidate_urls.append(u)
                seen.add(u)

        for u in playable_urls:
            add_candidate(u)

        if dom_candidates:
            for vid in sorted(
                dom_candidates,
                key=lambda v: (v.get('width', 0) * v.get('height', 0), v.get('duration', 0)),
                reverse=True
            ):
                add_candidate(vid.get('src'))

        mpd_urls = [u for u in video_urls if u.lower().endswith('.mpd')]
        m3u8_urls = [u for u in video_urls if u.lower().endswith('.m3u8')]
        for u in mpd_urls:
            add_candidate(u)
        for u in m3u8_urls:
            add_candidate(u)

        for u in video_urls:
            add_candidate(u)

        try:
            def rank_candidates(urls):
                video = []
                audio = []
                other = []
                for u in urls:
                    info = parse_efg_info(u)
                    if info:
                        bitrate = int(info.get('bitrate') or 0)
                        tag = str(info.get('vencode_tag', ''))
                        if 'audio' in tag:
                            audio.append((bitrate, u))
                        else:
                            video.append((bitrate, u))
                    else:
                        other.append(u)
                video.sort(key=lambda x: x[0], reverse=True)
                audio.sort(key=lambda x: x[0], reverse=True)
                ordered = []
                ordered.extend([u for _, u in video[:4]])
                ordered.extend([u for _, u in audio[:2]])
                ordered.extend([u for _, u in video[4:]])
                ordered.extend([u for _, u in audio[2:]])
                ordered.extend(other)
                seen_local = set()
                out = []
                for u in ordered:
                    if u and u not in seen_local:
                        seen_local.add(u)
                        out.append(u)
                return out

            candidate_urls[:] = rank_candidates(candidate_urls)
        except Exception:
            pass

        safe_log(f"Prepared {len(candidate_urls)} candidate URL(s)")
        if candidate_urls:
            print(f"Selected URL: {candidate_urls[0][:100]}...")
            return candidate_urls

    safe_log("No video URLs found")
    return None


def download_video(video_url, output_widget):
    print(f"Starting download process for URL: {video_url}")

    cwd = os.getcwd()
    print(f"Download location (current working directory): {cwd}")

    def probe_media(path):
        try:
            import subprocess
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'stream=codec_type,width,height',
                '-show_entries', 'format=duration',
                '-of', 'json',
                path
            ]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                return None
            data = json.loads(res.stdout or '{}')
            duration = float(data.get('format', {}).get('duration') or 0)
            streams = data.get('streams') or []
            has_video = False
            has_audio = False
            width = 0
            height = 0
            for s in streams:
                if s.get('codec_type') == 'video':
                    has_video = True
                    if width == 0 and height == 0:
                        width = int(s.get('width', 0) or 0)
                        height = int(s.get('height', 0) or 0)
                elif s.get('codec_type') == 'audio':
                    has_audio = True
            return {
                'duration': duration,
                'width': width,
                'height': height,
                'has_video': has_video,
                'has_audio': has_audio,
            }
        except Exception:
            return None

    def best_media_file(paths):
        best_path = None
        best_score = None
        best_meta = None
        for path in paths:
            if not path or not os.path.exists(path):
                continue
            size = os.path.getsize(path)
            probe = probe_media(path)
            duration = probe.get('duration', 0) if probe else 0
            width = probe.get('width', 0) if probe else 0
            height = probe.get('height', 0) if probe else 0
            has_video = probe.get('has_video', False) if probe else False
            has_audio = probe.get('has_audio', False) if probe else False
            score = (width * height, duration, size)
            if best_score is None or score > best_score:
                best_score = score
                best_path = path
                best_meta = {
                    'duration': duration,
                    'width': width,
                    'height': height,
                    'size': size,
                    'has_video': has_video,
                    'has_audio': has_audio,
                }
        return best_path, best_meta

    def looks_like_placeholder(meta):
        if not meta:
            return True
        if not meta.get('has_video'):
            return True
        if meta.get('width', 0) == 0 or meta.get('height', 0) == 0:
            return True
        if meta.get('width', 0) < 200 or meta.get('height', 0) < 200:
            return True
        if meta.get('size', 0) < 1_000_000 and meta.get('duration', 0) < 2.0:
            return True
        return False

    def resolve_downloaded_files(ydl, info):
        files = []
        for key in ('_filename', 'filepath'):
            path = info.get(key)
            if path:
                files.append(path)
        try:
            files.append(ydl.prepare_filename(info))
        except Exception:
            pass
        for d in info.get('requested_downloads') or []:
            for key in ('filepath', 'filename', '_filename', 'final_filepath'):
                path = d.get(key)
                if path:
                    files.append(path)
        uniq = []
        for f in files:
            if f and f not in uniq:
                uniq.append(f)
        return [f for f in uniq if os.path.exists(f)]

    def progress_hook(d):
        if d['status'] == 'downloading':
            msg = f"Downloading: {d.get('_percent_str', 'N/A')} at {d.get('_speed_str', 'N/A')} ETA: {d.get('_eta_str', 'N/A')}\n"
            output_widget.insert(tk.END, msg)
            output_widget.see(tk.END)
            output_widget.update()
        elif d['status'] == 'finished':
            msg = "Download finished, now processing...\n"
            output_widget.insert(tk.END, msg)
            output_widget.see(tk.END)
            output_widget.update()

    def find_node_path():
        candidates = []
        for name in ('node', 'node.exe'):
            p = shutil.which(name)
            if p:
                candidates.append(p)
        for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'), os.environ.get('LOCALAPPDATA')):
            if not base:
                continue
            candidates.append(os.path.join(base, 'nodejs', 'node.exe'))
            candidates.append(os.path.join(base, 'Programs', 'nodejs', 'node.exe'))
        for p in candidates:
            if p and os.path.exists(p):
                return p
        return None

    node_path = find_node_path()
    if node_path:
        output_widget.insert(tk.END, f"Using Node.js runtime: {node_path}\n")
        output_widget.see(tk.END)
        output_widget.update()
    else:
        output_widget.insert(tk.END, "Warning: Node.js runtime not found. YouTube restricted videos may fail.\n")
        output_widget.see(tk.END)
        output_widget.update()

    ydl_opts = {
        'format': '137+140/137+251/137+bestaudio/bestvideo[height>=1080][ext=mp4]+bestaudio/bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': '%(title).80B [%(id)s].%(ext)s',
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': ['en'],
        'convertsubtitles': 'srt',
        'sleep_interval': 2,
        'max_sleep_interval': 5,
        'retries': 20,
        'fragment_retries': 20,
        'concurrent_fragment_downloads': 1,
        'progress_hooks': [progress_hook],
        'quiet': False,
        'no_warnings': False,
        'verbose': True,
        'cookiesfrombrowser': ('firefox',),
        'js_runtimes': {'node': {'path': node_path}} if node_path else {'node': {}},
        'remote_components': {'ejs:github'},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
    }

    try:
        ydl_opts['http_headers']['Referer'] = video_url
        if 'facebook.com' in video_url:
            ydl_opts['http_headers']['Origin'] = 'https://www.facebook.com'
    except Exception:
        pass

    if 'youtube.com' in video_url or 'youtu.be' in video_url:
        ydl_opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'tv', 'web', 'web_safari'],
            }
        }

    try:
        output_widget.insert(tk.END, f"Starting download for: {video_url}\n")
        output_widget.insert(tk.END, f"Download directory: {cwd}\n")
        output_widget.insert(tk.END, "-" * 80 + "\n")
        output_widget.see(tk.END)
        output_widget.update()

        def run_ytdlp(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                print("Starting yt-dlp download...")
                info_local = ydl.extract_info(video_url, download=True)
                print(f"Download completed for: {info_local.get('title', 'Unknown')}")
                downloaded_files_local = resolve_downloaded_files(ydl, info_local)
            return info_local, downloaded_files_local

        try:
            info, downloaded_files = run_ytdlp(ydl_opts)

            best_path, best_meta = best_media_file(downloaded_files)
            if not best_path:
                raise Exception("Download produced no output file")
            if looks_like_placeholder(best_meta):
                size = best_meta.get('size', 0) if best_meta else 0
                output_widget.insert(tk.END, f"Downloaded file looks like a placeholder ({size} bytes). Falling back...\n")
                output_widget.see(tk.END)
                output_widget.update()
                raise Exception("Downloaded file appears to be placeholder")

            print("Download completed successfully")
            output_widget.insert(tk.END, "\n" + "=" * 80 + "\n")
            output_widget.insert(tk.END, "Download completed successfully!\n")
            output_widget.insert(tk.END, "=" * 80 + "\n")
            output_widget.see(tk.END)
            messagebox.showinfo("Success", "Download completed successfully!")

        except Exception as ytdlp_error:
            if 'youtube.com' in video_url or 'youtu.be' in video_url:
                msg = str(ytdlp_error)
                if ('Requested format is not available' in msg) or ('No video formats found' in msg):
                    try:
                        output_widget.insert(tk.END, "\nRetrying YouTube with relaxed format...\n")
                        output_widget.see(tk.END)
                        output_widget.update()

                        alt_opts = ydl_opts.copy()
                        alt_opts['format'] = 'bestvideo+bestaudio/best'
                        alt_opts['extractor_args'] = {
                            'youtube': {
                                'player_client': ['android', 'tv', 'web', 'web_safari'],
                            }
                        }

                        info, downloaded_files = run_ytdlp(alt_opts)
                        best_path, best_meta = best_media_file(downloaded_files)
                        if not best_path:
                            raise Exception("Download produced no output file")
                        if looks_like_placeholder(best_meta):
                            size = best_meta.get('size', 0) if best_meta else 0
                            output_widget.insert(tk.END, f"Downloaded file looks like a placeholder ({size} bytes). Falling back...\n")
                            output_widget.see(tk.END)
                            output_widget.update()
                            raise Exception("Downloaded file appears to be placeholder")

                        print("Download completed successfully")
                        output_widget.insert(tk.END, "\n" + "=" * 80 + "\n")
                        output_widget.insert(tk.END, "Download completed successfully!\n")
                        output_widget.insert(tk.END, "=" * 80 + "\n")
                        output_widget.see(tk.END)
                        messagebox.showinfo("Success", "Download completed successfully!")
                        return
                    except Exception:
                        pass
            if 'youtube.com' in video_url or 'youtu.be' in video_url:
                try:
                    output_widget.insert(tk.END, "\nRetrying YouTube with Android client (no cookies)...\n")
                    output_widget.see(tk.END)
                    output_widget.update()

                    android_opts = ydl_opts.copy()
                    android_opts['format'] = 'best'
                    android_opts['cookiesfrombrowser'] = None
                    android_opts['extractor_args'] = {
                        'youtube': {
                            'player_client': ['android'],
                            'player_skip': ['webpage'],
                        }
                    }
                    android_opts.pop('js_runtimes', None)
                    android_opts.pop('remote_components', None)

                    info, downloaded_files = run_ytdlp(android_opts)
                    best_path, best_meta = best_media_file(downloaded_files)
                    if not best_path:
                        raise Exception("Download produced no output file")
                    if looks_like_placeholder(best_meta):
                        size = best_meta.get('size', 0) if best_meta else 0
                        output_widget.insert(tk.END, f"Downloaded file looks like a placeholder ({size} bytes). Falling back...\n")
                        output_widget.see(tk.END)
                        output_widget.update()
                        raise Exception("Downloaded file appears to be placeholder")

                    print("Download completed successfully (Android client)")
                    output_widget.insert(tk.END, "\n" + "=" * 80 + "\n")
                    output_widget.insert(tk.END, "Download completed successfully (Android client)!\n")
                    output_widget.insert(tk.END, "=" * 80 + "\n")
                    output_widget.see(tk.END)
                    messagebox.showinfo("Success", "Download completed successfully (Android client)!")
                    return
                except Exception as android_error:
                    output_widget.insert(tk.END, f"Android client fallback failed: {android_error}\n")
                    output_widget.see(tk.END)
                    output_widget.update()
            output_widget.insert(tk.END, f"\nyt-dlp error: {str(ytdlp_error)}\n")
            output_widget.see(tk.END)
            output_widget.update()
            print(f"yt-dlp failed: {ytdlp_error}")

            extracted_url = extract_video_url_playwright(video_url, output_widget)

            if extracted_url:
                output_widget.insert(tk.END, "\n" + "-" * 80 + "\n")
                output_widget.insert(tk.END, "Retrying download with extracted URL...\n")
                output_widget.see(tk.END)
                output_widget.update()

                import time
                timestamp = int(time.time())
                direct_url_opts = ydl_opts.copy()

                extracted_urls = extracted_url if isinstance(extracted_url, list) else [extracted_url]

                def probe_media(path):
                    try:
                        import subprocess
                        cmd = [
                            'ffprobe', '-v', 'error',
                            '-show_entries', 'stream=codec_type,width,height',
                            '-show_entries', 'format=duration',
                            '-of', 'json',
                            path
                        ]
                        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        if res.returncode != 0:
                            return None
                        data = json.loads(res.stdout or '{}')
                        duration = float(data.get('format', {}).get('duration') or 0)
                        streams = data.get('streams') or []
                        has_video = False
                        has_audio = False
                        width = 0
                        height = 0
                        for s in streams:
                            if s.get('codec_type') == 'video':
                                has_video = True
                                if width == 0 and height == 0:
                                    width = int(s.get('width', 0) or 0)
                                    height = int(s.get('height', 0) or 0)
                            elif s.get('codec_type') == 'audio':
                                has_audio = True
                        return {
                            'duration': duration,
                            'width': width,
                            'height': height,
                            'has_video': has_video,
                            'has_audio': has_audio,
                        }
                    except Exception:
                        return None

                def is_valid_media(path):
                    try:
                        size = os.path.getsize(path)
                    except Exception:
                        return False
                    if size <= 0:
                        return False
                    probe = probe_media(path)
                    if probe:
                        if probe['duration'] >= 1.0 and probe['width'] > 0 and probe['height'] > 0:
                            return True
                        if size >= 3 * 1024 * 1024 and probe['duration'] > 0:
                            return True
                        return False
                    return size >= 2 * 1024 * 1024

                if 'facebook.com' in video_url:
                    out_base = f'Facebook_Video_{timestamp}'
                elif 'youtube.com' in video_url or 'youtu.be' in video_url:
                    out_base = f'YouTube_Video_{timestamp}'
                else:
                    out_base = f'Video_{timestamp}'

                success = False
                best_video = None
                best_video_score = None
                best_video_meta = None
                best_audio = None
                best_audio_score = None
                downloaded_paths = []

                max_candidates = 6 if 'facebook.com' in video_url else len(extracted_urls)
                candidate_pool = extracted_urls[:max_candidates]

                for idx, candidate in enumerate(candidate_pool, start=1):
                    output_widget.insert(tk.END, f"Trying candidate {idx}/{len(candidate_pool)}...\n")
                    output_widget.see(tk.END)
                    output_widget.update()

                    direct_url_opts = ydl_opts.copy()
                    direct_url_opts['outtmpl'] = f'{out_base}_try{idx}.%(ext)s'

                    try:
                        with yt_dlp.YoutubeDL(direct_url_opts) as ydl:
                            info = ydl.extract_info(candidate, download=True)
                            downloaded_path = ydl.prepare_filename(info)
                            info.get('ext') or 'mp4'

                        if os.path.exists(downloaded_path):
                            downloaded_paths.append(downloaded_path)

                        if os.path.exists(downloaded_path):
                            size = os.path.getsize(downloaded_path)
                            probe = probe_media(downloaded_path)
                            duration = probe.get('duration', 0) if probe else 0
                            width = probe.get('width', 0) if probe else 0
                            height = probe.get('height', 0) if probe else 0
                            has_video = probe.get('has_video', False) if probe else False
                            has_audio = probe.get('has_audio', False) if probe else False
                            output_widget.insert(
                                tk.END,
                                f"Candidate stats: size={size} bytes, duration={duration:.2f}s, res={width}x{height}, "
                                f"video={has_video}, audio={has_audio}\n"
                            )
                            output_widget.see(tk.END)
                            output_widget.update()

                            if has_video:
                                score = (width * height, duration, size)
                                if best_video_score is None or score > best_video_score:
                                    best_video_score = score
                                    best_video = downloaded_path
                                    best_video_meta = {
                                        'duration': duration,
                                        'width': width,
                                        'height': height,
                                        'size': size,
                                        'has_video': has_video,
                                        'has_audio': has_audio,
                                    }
                            elif has_audio:
                                score = (duration, size)
                                if best_audio_score is None or score > best_audio_score:
                                    best_audio_score = score
                                    best_audio = downloaded_path
                        else:
                            output_widget.insert(tk.END, "Candidate download produced no file. Trying next...\n")
                            output_widget.see(tk.END)
                            output_widget.update()
                    except Exception as e:
                        output_widget.insert(tk.END, f"Candidate failed: {e}\n")
                        output_widget.see(tk.END)
                        output_widget.update()

                final_path = None

                if best_video and os.path.exists(best_video):
                    if looks_like_placeholder(best_video_meta):
                        raise Exception("All candidates appear to be placeholders (very small/low-res).")

                    final_path = f'{out_base}.mp4'

                    if best_video_meta and best_video_meta.get('has_audio'):
                        if best_video != final_path:
                            try:
                                os.replace(best_video, final_path)
                            except Exception:
                                final_path = best_video
                        success = True
                    elif best_audio and os.path.exists(best_audio):
                        import subprocess
                        ffmpeg_cmd = [
                            'ffmpeg', '-i', best_video, '-i', best_audio,
                            '-c', 'copy', '-shortest', final_path, '-y'
                        ]
                        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
                        if result.returncode == 0 and os.path.exists(final_path):
                            success = True
                        else:
                            raise Exception(f"FFmpeg merge failed: {result.stderr}")
                    else:
                        if best_video != final_path:
                            try:
                                os.replace(best_video, final_path)
                            except Exception:
                                final_path = best_video
                        success = True

                for path in downloaded_paths:
                    if best_video and path == best_video:
                        continue
                    if best_audio and path == best_audio:
                        continue
                    if os.path.exists(path):
                        os.remove(path)

                if success and final_path:
                    if best_video and best_video != final_path and os.path.exists(best_video):
                        os.remove(best_video)
                    if best_audio and best_audio != final_path and os.path.exists(best_audio):
                        os.remove(best_audio)

                if success:
                    print("Download completed successfully via Playwright fallback")
                    output_widget.insert(tk.END, "\n" + "=" * 80 + "\n")
                    output_widget.insert(tk.END, "Download completed successfully (via browser automation)!\n")
                    output_widget.insert(tk.END, "=" * 80 + "\n")
                    output_widget.see(tk.END)
                    messagebox.showinfo("Success", "Download completed successfully via browser automation!")
                else:
                    raise Exception("Playwright candidates produced only tiny/invalid files")
            else:
                raise Exception("Both yt-dlp and Playwright fallback failed to extract video")

    except Exception as e:
        error_msg = f"Error during download: {str(e)}"
        print(error_msg)
        output_widget.insert(tk.END, f"\n{error_msg}\n")
        output_widget.see(tk.END)
        messagebox.showerror("Download Error", error_msg)


def start_download_thread(url_entry, output_widget, download_button):
    video_url = url_entry.get().strip()

    if not video_url:
        print("No URL provided")
        messagebox.showwarning("No URL", "Please enter a video URL")
        return

    print(f"URL entered: {video_url}")

    download_button.config(state=tk.DISABLED, text="Downloading...")

    thread = threading.Thread(
        target=lambda: download_and_enable_button(video_url, output_widget, download_button),
        daemon=True
    )
    thread.start()


def download_and_enable_button(video_url, output_widget, download_button):
    try:
        download_video(video_url, output_widget)
    finally:
        download_button.config(state=tk.NORMAL, text="Download Video")


def create_gui():
    print("Creating GUI window...")

    root = tk.Tk()
    root.title("YT-DLP Video Downloader (Administrator Mode)")
    root.geometry("900x600")
    root.resizable(True, True)
    root.configure(bg="#1C1C1C")

    cwd = os.getcwd()

    info_frame = tk.Frame(root, padx=10, pady=10, bg="#1C1C1C")
    info_frame.pack(fill=tk.X)

    tk.Label(
        info_frame,
        text=f"Download Directory: {cwd}",
        font=("Arial", 9),
        fg="white",
        bg="#1C1C1C",
        anchor="w"
    ).pack(fill=tk.X)

    tk.Label(
        info_frame,
        text="YT-DLP: Python Library (Installed)",
        font=("Arial", 9),
        fg="white",
        bg="#1C1C1C",
        anchor="w"
    ).pack(fill=tk.X)

    input_frame = tk.Frame(root, padx=10, pady=5, bg="#1C1C1C")
    input_frame.pack(fill=tk.X)

    tk.Label(
        input_frame,
        text="Video URL:",
        font=("Arial", 10, "bold"),
        fg="white",
        bg="#1C1C1C"
    ).pack(side=tk.LEFT, padx=(0, 10))

    url_var = tk.StringVar(master=root)
    url_entry = tk.Entry(
        input_frame,
        textvariable=url_var,
        font=("Arial", 10),
        width=60,
        bg="#2B2B2B",
        fg="white",
        insertbackground="white"
    )
    url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

    download_button = tk.Button(
        input_frame,
        text="Download Video",
        font=("Arial", 10, "bold"),
        bg="#4CAF50",
        fg="white",
        padx=20,
        pady=5,
        command=lambda: start_download_thread(url_entry, output_text, download_button)
    )
    download_button.pack(side=tk.LEFT)

    output_frame = tk.Frame(root, padx=10, pady=5, bg="#1C1C1C")
    output_frame.pack(fill=tk.BOTH, expand=True)

    tk.Label(
        output_frame,
        text="Download Output:",
        font=("Arial", 10, "bold"),
        fg="white",
        bg="#1C1C1C",
        anchor="w"
    ).pack(fill=tk.X)

    output_text = scrolledtext.ScrolledText(
        output_frame,
        font=("Consolas", 9),
        bg="#1C1C1C",
        fg="white",
        insertbackground="white",
        wrap=tk.WORD
    )
    output_text.pack(fill=tk.BOTH, expand=True)

    button_frame = tk.Frame(root, padx=10, pady=10, bg="#1C1C1C")
    button_frame.pack(fill=tk.X)

    clear_button = tk.Button(
        button_frame,
        text="Clear Output",
        font=("Arial", 9),
        bg="#2B2B2B",
        fg="white",
        command=lambda: output_text.delete(1.0, tk.END)
    )
    clear_button.pack(side=tk.LEFT, padx=(0, 10))

    exit_button = tk.Button(
        button_frame,
        text="Exit",
        font=("Arial", 9),
        bg="#2B2B2B",
        fg="white",
        command=root.quit
    )
    exit_button.pack(side=tk.LEFT)

    print("GUI created successfully")
    output_text.insert(tk.END, "YT-DLP Video Downloader Ready\n")
    output_text.insert(tk.END, "=" * 80 + "\n")
    output_text.insert(tk.END, f"Working Directory: {cwd}\n")
    output_text.insert(tk.END, f"YT-DLP: Python Library v{yt_dlp.version.__version__}\n")
    output_text.insert(tk.END, "=" * 80 + "\n\n")
    output_text.insert(tk.END, "Enter a video URL and click 'Download Video' to begin.\n\n")

    print("Starting GUI main loop...")
    root.mainloop()


def main():
    print("=" * 80)
    print("YT-DLP Video Downloader with Administrator Privileges")
    print("=" * 80)

    if not is_admin():
        elevate_privileges()

    print("Running with administrator privileges")

    cwd = os.getcwd()
    print(f"Current working directory: {cwd}")

    try:
        print(f"YT-DLP library version: {yt_dlp.version.__version__}")
    except Exception as e:
        print(f"Error getting yt-dlp version: {e}")

    create_gui()

    print("Application closed")


if __name__ == "__main__":
    main()
