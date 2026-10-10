#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCS Browser CLI — Navegador de consola seguro
Compatible con Python 3.10+ / Python 3.14 / IDLE / Windows / Linux / macOS
"""

import os
import sys
import json
import re
import shutil
import subprocess
import webbrowser
import urllib.request
import urllib.parse
import urllib.error
import html as html_module
from datetime import datetime


# ============================================================
# SOPORTE ANSI
# ============================================================
if os.name == 'nt':
    os.system('')
    try:
        import ctypes
        _k = ctypes.windll.kernel32
        _k.SetConsoleMode(_k.GetStdHandle(-11), 7)
    except Exception:
        pass


def _supports_ansi():
    if os.environ.get('NO_COLOR'):
        return False
    if os.environ.get('FORCE_COLOR'):
        return True
    if 'idlelib' in sys.modules or 'idlelib.run' in sys.modules:
        return False
    return True


USE_ANSI = _supports_ansi()

if USE_ANSI:
    RESET   = '\033[0m'
    BOLD    = '\033[1m'
    DIM     = '\033[2m'
    RED     = '\033[91m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    BLUE    = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN    = '\033[96m'
    WHITE   = '\033[97m'
else:
    RESET = BOLD = DIM = ''
    RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = ''


# ============================================================
# CONFIGURACIÓN GLOBAL
# ============================================================
CONFIG_FILE = os.path.join(os.path.expanduser('~'), '.ocs_browser_cli.json')
MAX_DISPLAY_CHARS = 9000

# Versión del esquema de config — si cambia, se resetea automáticamente
CONFIG_VERSION = 2

DEFAULT_CONFIG = {
    'config_version': CONFIG_VERSION,
    'lang': 'es',
    'engine': 'osc',
    'url_via_engine': True,
    'external_browser': 'default',
    'browser_mode': 'external',     # ← clave: por defecto SIEMPRE abre navegador
    'adblock': True,
    'tracker': True,
    'history': [],
    'saved': [],
    'blocked_count': 0,
}


# ============================================================
# BANNERS
# ============================================================
BANNER_OSC = r"""
 ██████╗ ███████╗ ██████╗
██╔═══██╗██╔════╝██╔════╝
██║   ██║███████╗██║
██║   ██║╚════██║██║
╚██████╔╝███████║╚██████╗
 ╚═════╝ ╚══════╝ ╚═════╝
"""

BANNER_BROWSER = r"""
██████╗ ██████╗  ██████╗ ██╗    ██╗███████╗███████╗██████╗
██╔══██╗██╔══██╗██╔═══██╗██║    ██║██╔════╝██╔════╝██╔══██╗
██████╔╝██████╔╝██║   ██║██║ █╗ ██║███████╗█████╗  ██████╔╝
██╔══██╗██╔══██╗██║   ██║██║███╗██║╚════██║██╔══╝  ██╔══██╗
██████╔╝██║  ██║╚██████╔╝╚███╔███╔╝███████║███████╗██║  ██║
╚═════╝ ╚═╝  ╚═╝ ╚═════╝  ╚══╝╚══╝ ╚══════╝╚══════╝╚═╝  ╚═╝
"""

BANNER_CLI = r"""
 ██████╗██╗     ██╗
██╔════╝██║     ██║
██║     ██║     ██║
██║     ██║     ██║
╚██████╗███████╗██║
 ╚═════╝╚══════╝╚═╝
"""


def show_banner():
    print()
    print(BLUE + BOLD + BANNER_OSC + RESET)
    print(GREEN + BOLD + BANNER_BROWSER + RESET)
    print(WHITE + BOLD + BANNER_CLI + RESET)
    print(DIM + "         Navegador de consola seguro · v1.5 · Python 3.14" + RESET)
    print(DIM + "         Escribe lo que quieras y se abrirá en tu navegador." + RESET)
    print(DIM + "         " + CYAN + ":help" + DIM + " para ver los comandos." + RESET)
    if not USE_ANSI:
        print()
        print(YELLOW + "⚠ Los colores ANSI no están disponibles en este entorno "
              "(IDLE)." + RESET)
    print()


# ============================================================
# TRADUCCIONES
# ============================================================
TRANSLATIONS = {
    'es': {
        'welcome': '¡Bienvenido a OCS Browser CLI!',
        'prompt_home': 'inicio',
        'help_title': 'COMANDOS DISPONIBLES',
        'help_nav': 'Navegación',
        'help_hist': 'Historial y guardados',
        'help_cfg': 'Configuración',
        'help_browser': 'Navegadores externos',
        'help_ui': 'Interfaz',
        'loading': 'Cargando',
        'blocked': 'Bloqueado por AdBlock',
        'error': 'Error',
        'history_empty': 'Historial vacío.',
        'saved_empty': 'No tienes webs guardadas.',
        'saved_ok': 'Guardado',
        'unsaved_ok': 'Eliminado',
        'adblock_on': 'AdBlock ACTIVADO',
        'adblock_off': 'AdBlock DESACTIVADO',
        'lang_changed': 'Idioma cambiado a',
        'engine_changed': 'Motor de búsqueda cambiado a',
        'browser_changed': 'Navegador cambiado a',
        'browser_disabled': 'Navegador externo desactivado',
        'mode_changed': 'Modo cambiado a',
        'viaengine_on': 'Modo "URL vía motor" ACTIVADO.',
        'viaengine_off': 'Modo "URL vía motor" DESACTIVADO.',
        'browser_not_found': 'No se encontró el navegador',
        'unknown_cmd': 'Comando desconocido',
        'bye': 'Hasta luego',
        'status': 'Estado',
        'chars': 'caracteres',
        'truncated': 'contenido truncado',
        'blocked_total': 'elementos bloqueados en total',
        'opening_in': 'Abriendo en',
        'opening_failed': 'No se pudo abrir',
        'fallback_cli': 'Cambiando a modo CLI...',
        'searching_via': 'Buscando vía',
        'opened_tab': 'Abriendo pestaña',
    },
    'en': {
        'welcome': 'Welcome to OCS Browser CLI!', 'prompt_home': 'home',
        'help_title': 'AVAILABLE COMMANDS', 'help_nav': 'Navigation',
        'help_hist': 'History & saved', 'help_cfg': 'Configuration',
        'help_browser': 'External browsers', 'help_ui': 'Interface',
        'loading': 'Loading', 'blocked': 'Blocked by AdBlock', 'error': 'Error',
        'history_empty': 'History is empty.', 'saved_empty': 'No saved websites.',
        'saved_ok': 'Saved', 'unsaved_ok': 'Removed',
        'adblock_on': 'AdBlock ENABLED', 'adblock_off': 'AdBlock DISABLED',
        'lang_changed': 'Language changed to', 'engine_changed': 'Search engine changed to',
        'browser_changed': 'Browser changed to', 'browser_disabled': 'External browser disabled',
        'mode_changed': 'Mode changed to', 'viaengine_on': '"URL via engine" mode ENABLED.',
        'viaengine_off': '"URL via engine" mode DISABLED.',
        'browser_not_found': 'Browser not found', 'unknown_cmd': 'Unknown command',
        'bye': 'Bye', 'status': 'Status', 'chars': 'characters',
        'truncated': 'content truncated', 'blocked_total': 'elements blocked in total',
        'opening_in': 'Opening in', 'opening_failed': 'Could not open in',
        'fallback_cli': 'Switching to CLI mode...', 'searching_via': 'Searching via',
        'opened_tab': 'Opening tab',
    },
    'pt': {
        'welcome': 'Bem-vindo ao OCS Browser CLI!', 'prompt_home': 'início',
        'help_title': 'COMANDOS DISPONÍVEIS', 'help_nav': 'Navegação',
        'help_hist': 'Histórico e salvos', 'help_cfg': 'Configuração',
        'help_browser': 'Navegadores externos', 'help_ui': 'Interface',
        'loading': 'Carregando', 'blocked': 'Bloqueado pelo AdBlock', 'error': 'Erro',
        'history_empty': 'Histórico vazio.', 'saved_empty': 'Nenhum site salvo.',
        'saved_ok': 'Salvo', 'unsaved_ok': 'Removido',
        'adblock_on': 'AdBlock ATIVADO', 'adblock_off': 'AdBlock DESATIVADO',
        'lang_changed': 'Idioma alterado para', 'engine_changed': 'Motor alterado para',
        'browser_changed': 'Navegador alterado para', 'browser_disabled': 'Navegador externo desativado',
        'mode_changed': 'Modo alterado para', 'viaengine_on': 'Modo "URL via motor" ATIVADO.',
        'viaengine_off': 'Modo "URL via motor" DESATIVADO.',
        'browser_not_found': 'Navegador não encontrado', 'unknown_cmd': 'Comando desconhecido',
        'bye': 'Até logo', 'status': 'Status', 'chars': 'caracteres',
        'truncated': 'conteúdo truncado', 'blocked_total': 'elementos bloqueados',
        'opening_in': 'Abrindo em', 'opening_failed': 'Não foi possível abrir',
        'fallback_cli': 'Mudando para modo CLI...', 'searching_via': 'Pesquisando via',
        'opened_tab': 'Abrindo aba',
    },
    'fr': {
        'welcome': 'Bienvenue sur OCS Browser CLI !', 'prompt_home': 'accueil',
        'help_title': 'COMMANDES DISPONIBLES', 'help_nav': 'Navigation',
        'help_hist': 'Historique et favoris', 'help_cfg': 'Configuration',
        'help_browser': 'Navigateurs externes', 'help_ui': 'Interface',
        'loading': 'Chargement', 'blocked': 'Bloqué par AdBlock', 'error': 'Erreur',
        'history_empty': 'Historique vide.', 'saved_empty': 'Aucun site enregistré.',
        'saved_ok': 'Enregistré', 'unsaved_ok': 'Supprimé',
        'adblock_on': 'AdBlock ACTIVÉ', 'adblock_off': 'AdBlock DÉSACTIVÉ',
        'lang_changed': 'Langue changée pour', 'engine_changed': 'Moteur changé pour',
        'browser_changed': 'Navigateur changé pour', 'browser_disabled': 'Navigateur externe désactivé',
        'mode_changed': 'Mode changé pour', 'viaengine_on': 'Mode "URL via moteur" ACTIVÉ.',
        'viaengine_off': 'Mode "URL via moteur" DÉSACTIVÉ.',
        'browser_not_found': 'Navigateur introuvable', 'unknown_cmd': 'Commande inconnue',
        'bye': 'À bientôt', 'status': 'Statut', 'chars': 'caractères',
        'truncated': 'contenu tronqué', 'blocked_total': 'éléments bloqués',
        'opening_in': 'Ouverture dans', 'opening_failed': 'Impossible d\'ouvrir',
        'fallback_cli': 'Passage en mode CLI...', 'searching_via': 'Recherche via',
        'opened_tab': 'Ouverture d\'onglet',
    },
}


# ============================================================
# MOTORES DE BÚSQUEDA
# ============================================================
SEARCH_ENGINES = {
    'osc':        {'name': 'OSC Search',  'url': 'https://david4524-maker.github.io/OSC-Search/?q={q}'},
    'google':     {'name': 'Google',      'url': 'https://www.google.com/search?q={q}'},
    'duckduckgo': {'name': 'DuckDuckGo',  'url': 'https://duckduckgo.com/html/?q={q}'},
    'bing':       {'name': 'Bing',        'url': 'https://www.bing.com/search?q={q}'},
    'wikipedia':  {'name': 'Wikipedia',   'url': 'https://es.wikipedia.org/w/index.php?search={q}'},
    'youtube':    {'name': 'YouTube',     'url': 'https://www.youtube.com/results?search_query={q}'},
    'ecosia':     {'name': 'Ecosia',      'url': 'https://www.ecosia.org/search?q={q}'},
}


# ============================================================
# NAVEGADORES EXTERNOS
# ============================================================
BROWSER_NAMES = {
    'chrome', 'chromium', 'firefox', 'edge', 'brave', 'opera', 'safari',
    'default', 'predeterminado', 'off', 'ninguno', 'none',
}


def find_browser_exe(name):
    name = name.lower()
    if name == 'predeterminado':
        name = 'default'
    if name in ('off', 'ninguno', 'none'):
        return None

    aliases = {
        'chrome':   ['chrome', 'google-chrome', 'google-chrome-stable'],
        'chromium': ['chromium', 'chromium-browser'],
        'firefox':  ['firefox', 'firefox-esr'],
        'edge':     ['msedge', 'microsoft-edge', 'microsoft-edge-stable'],
        'brave':    ['brave', 'brave-browser'],
        'opera':    ['opera'],
        'safari':   ['safari'],
    }

    for c in aliases.get(name, [name]):
        p = shutil.which(c)
        if p:
            return p

    if os.name == 'nt':
        win_paths = {
            'chrome': [
                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
                os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
            ],
            'chromium': [
                r'C:\Program Files\Chromium\Application\chrome.exe',
                r'C:\Program Files (x86)\Chromium\Application\chrome.exe',
            ],
            'edge': [
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            ],
            'brave': [
                r'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
                r'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe',
            ],
            'firefox': [
                r'C:\Program Files\Mozilla Firefox\firefox.exe',
                r'C:\Program Files (x86)\Mozilla Firefox\firefox.exe',
            ],
            'opera': [
                os.path.expandvars(r'%LOCALAPPDATA%\Programs\Opera\launcher.exe'),
                os.path.expandvars(r'%LOCALAPPDATA%\Programs\Opera\opera.exe'),
            ],
        }
        for p in win_paths.get(name, []):
            if p and os.path.exists(p):
                return p
    elif sys.platform == 'darwin':
        mac_paths = {
            'chrome':   '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            'chromium': '/Applications/Chromium.app/Contents/MacOS/Chromium',
            'firefox':  '/Applications/Firefox.app/Contents/MacOS/firefox',
            'edge':     '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
            'brave':    '/Applications/Brave Browser.app/Contents/MacOS/Brave Browser',
            'opera':    '/Applications/Opera.app/Contents/MacOS/Opera',
            'safari':   '/Applications/Safari.app/Contents/MacOS/Safari',
        }
        if name in mac_paths and os.path.exists(mac_paths[name]):
            return mac_paths[name]

    return None


def launch_browser(browser_name, url, debug=False):
    """
    Abre la URL intentando VARIOS métodos en cascada.
    Devuelve (ok, method_used, error_msg).
    """
    browser_name = (browser_name or 'default').lower()
    if browser_name == 'predeterminado':
        browser_name = 'default'

    errors = []

    # ---------- Método 1: navegador específico con subprocess ----------
    if browser_name not in ('default', 'off', 'none', 'ninguno', ''):
        exe = find_browser_exe(browser_name)
        if exe:
            # En Windows usar os.startfile con --new-tab
            try:
                args = [exe]
                if browser_name in ('chrome', 'chromium', 'edge', 'brave'):
                    args.append('--new-tab')
                elif browser_name == 'firefox':
                    args.append('-new-tab')
                args.append(url)
                kwargs = {}
                if os.name == 'nt':
                    kwargs['creationflags'] = 0x08000000  # CREATE_NO_WINDOW
                subprocess.Popen(
                    args,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **kwargs
                )
                return True, f'subprocess ({exe})', None
            except Exception as e:
                errors.append(f'subprocess: {e}')
        else:
            errors.append(f'exe no encontrado para {browser_name}')

    # ---------- Método 2 (Windows): os.startfile ----------
    if os.name == 'nt':
        try:
            # os.startfile abre con el navegador predeterminado
            os.startfile(url)
            return True, 'os.startfile (Windows nativo)', None
        except Exception as e:
            errors.append(f'os.startfile: {e}')

    # ---------- Método 3: webbrowser.open_new_tab ----------
    try:
        result = webbrowser.open_new_tab(url)
        if result or result is None:
            return True, 'webbrowser.open_new_tab', None
        errors.append('webbrowser.open_new_tab devolvió False')
    except Exception as e:
        errors.append(f'webbrowser: {e}')

    # ---------- Método 4 (Mac): comando open ----------
    if sys.platform == 'darwin':
        try:
            subprocess.Popen(['open', url])
            return True, 'open (macOS)', None
        except Exception as e:
            errors.append(f'open: {e}')

    # ---------- Método 5 (Linux): xdg-open ----------
    if sys.platform.startswith('linux'):
        for opener in ('xdg-open', 'gio', 'gnome-open', 'kde-open'):
            if shutil.which(opener):
                try:
                    args = [opener, 'open', url] if opener == 'gio' else [opener, url]
                    subprocess.Popen(
                        args,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    return True, f'{opener}', None
                except Exception as e:
                    errors.append(f'{opener}: {e}')

    # ---------- Método 6: webbrowser.open (último recurso) ----------
    try:
        webbrowser.open(url)
        return True, 'webbrowser.open (fallback)', None
    except Exception as e:
        errors.append(f'webbrowser.open: {e}')

    return False, None, ' | '.join(errors)


# ============================================================
# LENGUAJE NATURAL
# ============================================================
NATURAL_PREFIXES = [
    (r'^motor\s*[:=]\s*',       'engine_or_browser'),
    (r'^engine\s*[:=]\s*',      'engine_or_browser'),
    (r'^buscador\s*[:=]\s*',    'engine'),
    (r'^navegador\s*[:=]\s*',   'browser'),
    (r'^browser\s*[:=]\s*',     'browser'),
    (r'^idioma\s*[:=]\s*',      'lang'),
    (r'^lang\s*[:=]\s*',        'lang'),
    (r'^modo\s*[:=]\s*',        'mode'),
    (r'^mode\s*[:=]\s*',        'mode'),
    (r'^adblock\s*[:=]\s*',     'adblock'),
    (r'^viaengine\s*[:=]\s*',   'viaengine'),
    (r'^via\s*[:=]\s*',         'viaengine'),
]


# ============================================================
# LISTAS DE BLOQUEO
# ============================================================
AD_DOMAINS = [
    'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
    'pagead2.googlesyndication.com', 'adservice.google.com', 'ads.youtube.com',
    'adnxs.com', 'popads.net', 'adroll.com', 'outbrain.com', 'taboola.com',
]
TRACKER_DOMAINS = [
    'google-analytics.com', 'analytics.google.com', 'connect.facebook.net',
    'scorecardresearch.com', 'hotjar.com', 'clarity.ms', 'mixpanel.com',
]


# ============================================================
# UTILIDADES
# ============================================================
def fetch_url(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                          '(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept-Encoding': 'identity',
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return raw.decode('utf-8', errors='replace'), resp.geturl(), resp.status, None
    except Exception as e:
        return '', url, 0, str(e)


def is_blocked(url):
    u = url.lower()
    return any(d in u for d in AD_DOMAINS + TRACKER_DOMAINS)


def normalize_url(text):
    text = text.strip()
    if re.match(r'^https?://', text, re.I):
        return text
    if re.match(r'^[\w\-]+\.[a-z]{2,}(/.*)?$', text, re.I) and ' ' not in text:
        return 'https://' + text
    return None


# ============================================================
# CLASE PRINCIPAL
# ============================================================
class OcsBrowserCLI:
    def __init__(self):
        self.cfg = self.load_config()
        self.current_url = ''
        self.running = True

    def load_config(self):
        """Carga la config — si es de una versión vieja, la resetea."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # ─── MIGRACIÓN: si la version cambió, resetear ───
                if data.get('config_version', 0) != CONFIG_VERSION:
                    print(f'{YELLOW}⚠ Configuración antigua detectada. Migrando a v{CONFIG_VERSION}...{RESET}')
                    return dict(DEFAULT_CONFIG)
                cfg = dict(DEFAULT_CONFIG)
                cfg.update(data)
                return cfg
            except Exception as e:
                print(f'{YELLOW}⚠ Error leyendo config, usando valores por defecto: {e}{RESET}')
                return dict(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    def save_config(self):
        try:
            self.cfg['config_version'] = CONFIG_VERSION
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f'{RED}No se pudo guardar la configuración: {e}{RESET}')

    def t(self, key):
        lang = self.cfg.get('lang', 'es')
        return TRANSLATIONS.get(lang, TRANSLATIONS['es']).get(key, key)

    def print_prompt(self):
        url = self.current_url or self.t('prompt_home')
        if len(url) > 60:
            url = url[:57] + '...'
        engine_key = self.cfg.get('engine', 'osc')
        engine_name = SEARCH_ENGINES.get(engine_key, {}).get('name', '?')
        mode = self.cfg.get('browser_mode', 'external')
        badge = f'{CYAN}«{engine_name}»{RESET} '
        if mode != 'external':
            badge += f'{MAGENTA}[{mode}]{RESET} '
        prompt = f'{badge}{BLUE}{BOLD}osc{RESET}{GREEN}://{RESET}{WHITE}{url}{RESET}{BLUE}{BOLD}>{RESET} '
        try:
            print()
            print(prompt, end='', flush=True)
        except Exception:
            pass

    # ---------- LA CLAVE: abrir en pestaña ----------
    def open_in_browser(self, url):
        """Abre la URL en una pestaña. Devuelve True/False."""
        browser = self.cfg.get('external_browser', 'default') or 'default'
        ok, method, error = launch_browser(browser, url, debug=True)
        if ok:
            print()
            print(f'{GREEN}🚀 {self.t("opened_tab")}: {url}{RESET}')
            print(f'{DIM}   Método: {method}{RESET}')
            self.current_url = url
            self.cfg.setdefault('history', []).append({
                'url': url,
                'title': url[:60],
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            })
            self.cfg['history'] = self.cfg['history'][-200:]
            self.save_config()
            return True
        else:
            print()
            print(f'{RED}✗ No se pudo abrir el navegador.{RESET}')
            print(f'{DIM}   Intentos fallidos: {error}{RESET}')
            print(f'{YELLOW}   Prueba: :test   (para diagnosticar){RESET}')
            print(f'{YELLOW}   O usa :browser chrome|firefox|edge para forzar uno.{RESET}')
            return False

    def visit(self, url):
        # AdBlock
        if self.cfg.get('adblock', True) and is_blocked(url):
            self.cfg['blocked_count'] = self.cfg.get('blocked_count', 0) + 1
            self.save_config()
            print()
            print(f'{RED}🚫 {self.t("blocked")}: {url}{RESET}')
            return

        mode = self.cfg.get('browser_mode', 'external')

        if mode in ('external', 'both'):
            self.open_in_browser(url)
            if mode == 'external':
                return

        # Modo CLI
        print()
        print(f'{DIM}⏳ {self.t("loading")} {url} ...{RESET}')
        text, final_url, status, error = fetch_url(url)
        self.current_url = final_url or url
        if error:
            print(f'{RED}⚠ {error}{RESET}')
            return
        print()
        print(f'{BLUE}{BOLD}{"═" * 62}{RESET}')
        print(f'{GREEN}{BOLD}📄  {final_url}{RESET}')
        print(f'{BLUE}{BOLD}{"═" * 62}{RESET}')
        print()
        print(text[:MAX_DISPLAY_CHARS])
        print(f'{DIM}   ({len(text)} {self.t("chars")}){RESET}')

    # ---------- Bucle ----------
    def run(self):
        show_banner()
        print(f'{GREEN}{BOLD}{self.t("welcome")}{RESET}')
        self.cmd_info('')

        while self.running:
            try:
                self.print_prompt()
                line = input().strip()
                if not line:
                    continue
                if line.startswith(':'):
                    self.handle_command(line)
                else:
                    self.handle_navigation(line)
            except (KeyboardInterrupt, EOFError):
                print()
                print(f'{YELLOW}{self.t("bye")} 👋{RESET}')
                self.running = False
            except Exception as e:
                print(f'{RED}{self.t("error")}: {e}{RESET}')

    def handle_navigation(self, line):
        if self.try_natural_command(line):
            return
        if self.cfg.get('url_via_engine', True):
            self.cmd_search(line)
        else:
            url = normalize_url(line)
            if url:
                self.visit(url)
            else:
                self.cmd_search(line)

    def try_natural_command(self, line):
        for pattern, kind in NATURAL_PREFIXES:
            m = re.match(pattern, line, re.IGNORECASE)
            if m:
                value = line[m.end():].strip().strip('"\'')
                if not value:
                    return False
                if kind == 'engine_or_browser':
                    return self._apply_engine_or_browser(value)
                elif kind == 'engine':    self.cmd_engine(value);    return True
                elif kind == 'browser':   self.cmd_browser(value);   return True
                elif kind == 'lang':      self.cmd_lang(value);      return True
                elif kind == 'mode':      self.cmd_mode(value);      return True
                elif kind == 'adblock':   self.cmd_adblock(value);   return True
                elif kind == 'viaengine': self.cmd_viaengine(value); return True
        return False

    def _apply_engine_or_browser(self, value):
        v = value.lower()
        if v in BROWSER_NAMES:      self.cmd_browser(v); return True
        if v in SEARCH_ENGINES:     self.cmd_engine(v);  return True
        alias = {'osc search': 'osc', 'oscsearch': 'osc', 'google chrome': 'chrome'}
        if v in alias:
            t = alias[v]
            if t in BROWSER_NAMES:  self.cmd_browser(t)
            elif t in SEARCH_ENGINES: self.cmd_engine(t)
            return True
        print(f'{YELLOW}⚠ "{value}" no es motor ni navegador conocido.{RESET}')
        return True

    def handle_command(self, line):
        parts = line.split(maxsplit=1)
        cmd = parts[0][1:].lower()
        arg = parts[1].strip() if len(parts) > 1 else ''
        handlers = {
            'help': self.cmd_help, 'h': self.cmd_help, '?': self.cmd_help,
            'exit': self.cmd_exit, 'quit': self.cmd_exit, 'q': self.cmd_exit,
            'clear': self.cmd_clear, 'cls': self.cmd_clear,
            'home': self.cmd_home,
            'history': self.cmd_history,
            'save': self.cmd_save, 'unsave': self.cmd_unsave,
            'adblock': self.cmd_adblock, 'ab': self.cmd_adblock,
            'lang': self.cmd_lang,
            'engine': self.cmd_engine, 'engines': self.cmd_engines,
            'browser': self.cmd_browser, 'browsers': self.cmd_browsers,
            'mode': self.cmd_mode,
            'viaengine': self.cmd_viaengine,
            'open': self.cmd_open, 'go': self.cmd_open,
            'search': self.cmd_search, 's': self.cmd_search,
            'info': self.cmd_info, 'config': self.cmd_info,
            'test': self.cmd_test,
            'banner': self.cmd_banner,
        }
        fn = handlers.get(cmd)
        if fn: fn(arg)
        else:
            print(f'{RED}⚠ {self.t("unknown_cmd")}: :{cmd}{RESET}')

    # ---------- COMANDOS ----------
    def cmd_help(self, _):
        print()
        print(f'{BLUE}{BOLD}{"═" * 15} {self.t("help_title")} {"═" * 15}{RESET}')
        print(f'{GREEN}{BOLD}▸ {self.t("help_nav")}{RESET}')
        print(f'  {CYAN}<cualquier cosa>{RESET}        Se envía al motor y se abre en el navegador')
        print(f'  {CYAN}:open <url>{RESET}              Abrir URL directamente (sin motor)')
        print(f'  {CYAN}:search <q>{RESET}              Forzar búsqueda')
        print()
        print(f'{GREEN}{BOLD}▸ {self.t("help_browser")}{RESET}')
        print(f'  {CYAN}:browser <nombre>{RESET}        chrome | chromium | firefox | edge | brave | opera | safari | default')
        print(f'  {CYAN}:browsers{RESET}                Ver navegadores detectados')
        print(f'  {CYAN}:mode cli|external|both{RESET}  Modo de apertura')
        print(f'  {CYAN}:test{RESET}                    Probar apertura del navegador 🆕')
        print()
        print(f'{GREEN}{BOLD}▸ {self.t("help_cfg")}{RESET}')
        print(f'  {CYAN}:viaengine on|off{RESET}         Todo va al motor')
        print(f'  {CYAN}:engine <nombre>{RESET}         Cambiar motor')
        print(f'  {CYAN}:adblock on|off{RESET}          Activar/desactivar AdBlock')
        print(f'  {CYAN}:lang <es|en|pt|fr>{RESET}      Cambiar idioma')
        print(f'  {CYAN}:info{RESET}                    Ver configuración')
        print()
        print(f'{GREEN}{BOLD}▸ {self.t("help_ui")}{RESET}')
        print(f'  {CYAN}:banner{RESET} · {CYAN}:clear{RESET} · {CYAN}:exit{RESET}')
        print()

    def cmd_exit(self, _):
        print(f'\n{YELLOW}{self.t("bye")} 👋{RESET}')
        self.running = False

    def cmd_clear(self, _):
        os.system('cls' if os.name == 'nt' else 'clear')

    def cmd_banner(self, _):
        show_banner()

    def cmd_home(self, _):
        self.current_url = ''
        print(f'\n{GREEN}🏠 {self.t("prompt_home")}{RESET}')

    # ---------- COMANDO :test (NUEVO) ----------
    def cmd_test(self, _):
        """Diagnóstico: prueba a abrir una URL con todos los métodos."""
        print()
        print(f'{BLUE}{BOLD}{"═" * 20} TEST DE NAVEGADOR {"═" * 20}{RESET}')
        print(f'{DIM}SO: {sys.platform} · Python {sys.version.split()[0]}{RESET}')
        print(f'{DIM}Config: external_browser={self.cfg.get("external_browser")!r} · '
              f'browser_mode={self.cfg.get("browser_mode")!r}{RESET}')
        print()

        test_url = 'https://example.com'
        print(f'{CYAN}Probando a abrir: {test_url}{RESET}')

        # Probar todos los métodos en orden
        methods = []

        # 1) Navegador específico
        browser = self.cfg.get('external_browser', 'default')
        if browser and browser not in ('default', ''):
            exe = find_browser_exe(browser)
            methods.append((f'find_browser_exe({browser})', exe or 'NO ENCONTRADO'))

        # 2) os.startfile (Windows)
        if os.name == 'nt':
            try:
                has_startfile = hasattr(os, 'startfile')
                methods.append(('os.startfile', 'DISPONIBLE' if has_startfile else 'NO DISPONIBLE'))
            except Exception as e:
                methods.append(('os.startfile', f'ERROR: {e}'))

        # 3) webbrowser
        try:
            wb = webbrowser.get()
            methods.append(('webbrowser.get()', str(wb)))
        except Exception as e:
            methods.append(('webbrowser.get()', f'ERROR: {e}'))

        for name, info in methods:
            print(f'  {GREEN}●{RESET} {name}: {info}')

        print()
        print(f'{CYAN}▶ Intentando abrir {test_url} ...{RESET}')
        ok, method, error = launch_browser(browser, test_url, debug=True)
        if ok:
            print(f'{GREEN}✓ FUNCIONA con: {method}{RESET}')
            print(f'{DIM}  ¿Se abrió una pestaña en tu navegador? (y/n){RESET}')
        else:
            print(f'{RED}✗ Todos los métodos fallaron:{RESET}')
            print(f'{DIM}  {error}{RESET}')
        print()

    def cmd_open(self, arg):
        if not arg:
            print(f'{YELLOW}Uso: :open <url>{RESET}')
            return
        url = normalize_url(arg)
        if url:
            self.open_in_browser(url)
        else:
            print(f'{RED}URL inválida: {arg}{RESET}')

    def cmd_search(self, arg):
        if not arg:
            print(f'{YELLOW}Uso: :search <query>{RESET}')
            return
        engine_key = self.cfg.get('engine', 'osc')
        engine = SEARCH_ENGINES.get(engine_key, SEARCH_ENGINES['osc'])
        url = engine['url'].format(q=urllib.parse.quote(arg))
        print(f'{DIM}🔎 {engine["name"]}: {arg}{RESET}')
        self.visit(url)

    def cmd_history(self, _):
        hist = self.cfg.get('history', [])
        if not hist:
            print(f'{DIM}{self.t("history_empty")}{RESET}')
            return
        print(f'\n{BLUE}{BOLD}📜 Historial ({len(hist)}){RESET}')
        for entry in hist[-30:]:
            print(f'  {DIM}{entry.get("time", "")[:19]}{RESET}  {CYAN}{entry.get("url", "")[:70]}{RESET}')
        print()

    def cmd_save(self, arg):
        if not self.current_url:
            print(f'{YELLOW}No hay web abierta para guardar.{RESET}')
            return
        name = arg or self.current_url[:40]
        self.cfg.setdefault('saved', []).append({
            'name': name, 'url': self.current_url,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        self.save_config()
        print(f'{GREEN}✓ {self.t("saved_ok")}: {name}{RESET}')

    def cmd_unsave(self, arg):
        if not arg:
            print(f'{YELLOW}Uso: :unsave <nombre>{RESET}')
            return
        saved = self.cfg.get('saved', [])
        new_saved = [s for s in saved if s['name'].lower() != arg.lower()]
        if len(new_saved) == len(saved):
            print(f'{YELLOW}No se encontró "{arg}".{RESET}')
            return
        self.cfg['saved'] = new_saved
        self.save_config()
        print(f'{GREEN}✓ {self.t("unsaved_ok")}: {arg}{RESET}')

    def cmd_adblock(self, arg):
        arg = arg.lower()
        if arg == 'on':
            self.cfg['adblock'] = True
            self.save_config()
            print(f'{GREEN}🛡️ {self.t("adblock_on")}{RESET}')
        elif arg == 'off':
            self.cfg['adblock'] = False
            self.save_config()
            print(f'{YELLOW}🔓 {self.t("adblock_off")}{RESET}')
        else:
            state = self.cfg.get('adblock', True)
            print(f'{GREEN if state else YELLOW}{"ON" if state else "OFF"}{RESET}')

    def cmd_lang(self, arg):
        arg = arg.lower()
        if arg in TRANSLATIONS:
            self.cfg['lang'] = arg
            self.save_config()
            print(f'{GREEN}🌐 {self.t("lang_changed")} {arg}{RESET}')
        else:
            print(f'{YELLOW}Idiomas: {", ".join(TRANSLATIONS.keys())}{RESET}')

    def cmd_engine(self, arg):
        arg = arg.lower()
        if arg in SEARCH_ENGINES:
            self.cfg['engine'] = arg
            self.save_config()
            print(f'{GREEN}🔎 {self.t("engine_changed")} {SEARCH_ENGINES[arg]["name"]}{RESET}')
        else:
            print(f'{YELLOW}Uso: :engine <nombre>. Usa :engines.{RESET}')

    def cmd_engines(self, _):
        print(f'\n{BLUE}{BOLD}🔎 Motores de búsqueda{RESET}')
        for key, e in SEARCH_ENGINES.items():
            m = f'{GREEN}●{RESET}' if key == self.cfg.get('engine') else ' '
            print(f'  {m} {CYAN}{key}{RESET}  — {e["name"]}')
        print()

    def cmd_viaengine(self, arg):
        arg = arg.lower()
        if arg in ('on', 'true', 'yes', '1', 'si', 'sí'):
            self.cfg['url_via_engine'] = True
            self.save_config()
            print(f'{GREEN}🔗 {self.t("viaengine_on")}{RESET}')
        elif arg in ('off', 'false', 'no', '0'):
            self.cfg['url_via_engine'] = False
            self.save_config()
            print(f'{YELLOW}🔗 {self.t("viaengine_off")}{RESET}')
        else:
            state = self.cfg.get('url_via_engine', True)
            print(f'{GREEN if state else YELLOW}URL vía motor: {"ON" if state else "OFF"}{RESET}')

    def cmd_browser(self, arg):
        arg = arg.lower()
        if arg in ('off', 'none', 'ninguno'):
            self.cfg['external_browser'] = ''
            self.cfg['browser_mode'] = 'cli'
            self.save_config()
            print(f'{GREEN}🌐 {self.t("browser_disabled")}{RESET}')
            return
        if arg == 'predeterminado':
            arg = 'default'
        if arg not in BROWSER_NAMES:
            print(f'{YELLOW}Opciones: chrome, chromium, firefox, edge, brave, opera, safari, default, off{RESET}')
            return
        if arg != 'default':
            exe = find_browser_exe(arg)
            if not exe:
                print(f'{RED}✗ {self.t("browser_not_found")}: {arg}{RESET}')
                return
            print(f'{DIM}✓ Encontrado: {exe}{RESET}')
        self.cfg['external_browser'] = arg
        self.cfg['browser_mode'] = 'external'
        self.save_config()
        print(f'{GREEN}🌐 {self.t("browser_changed")} {arg}{RESET}')

    def cmd_browsers(self, _):
        print(f'\n{BLUE}{BOLD}🌐 Navegadores detectados{RESET}')
        current = self.cfg.get('external_browser') or ''
        for n in ['chrome', 'chromium', 'firefox', 'edge', 'brave', 'opera', 'safari']:
            exe = find_browser_exe(n)
            m = f'{GREEN}●{RESET}' if n == current else ' '
            if exe:
                print(f'  {m} {CYAN}{n:9}{RESET} {GREEN}✓{RESET} {DIM}{exe[:60]}{RESET}')
            else:
                print(f'  {m} {DIM}{n:9} ✗ no encontrado{RESET}')
        m = f'{GREEN}●{RESET}' if current == 'default' else ' '
        print(f'  {m} {CYAN}{"default":9}{RESET} {GREEN}✓{RESET} {DIM}navegador del sistema{RESET}')
        print()

    def cmd_mode(self, arg):
        arg = arg.lower()
        if arg in ('cli', 'external', 'both'):
            self.cfg['browser_mode'] = arg
            self.save_config()
            print(f'{GREEN}⚙ {self.t("mode_changed")} {arg}{RESET}')
        else:
            print(f'{YELLOW}Uso: :mode cli|external|both{RESET}')

    def cmd_info(self, _):
        print(f'\n{BLUE}{BOLD}⚙  Configuración actual{RESET}')
        print(f'  {DIM}Idioma:{RESET}           {self.cfg.get("lang")}')
        print(f'  {DIM}Motor:{RESET}            {SEARCH_ENGINES.get(self.cfg.get("engine"), {}).get("name", "?")}')
        via = self.cfg.get('url_via_engine', True)
        print(f'  {DIM}URL vía motor:{RESET}    {GREEN if via else YELLOW}{"ON" if via else "OFF"}{RESET}')
        ab = self.cfg.get('adblock', True)
        print(f'  {DIM}AdBlock:{RESET}          {GREEN if ab else YELLOW}{"ON" if ab else "OFF"}{RESET}')
        print(f'  {DIM}Navegador:{RESET}        {self.cfg.get("external_browser", "default")}')
        print(f'  {DIM}Modo:{RESET}             {self.cfg.get("browser_mode", "external")}')
        print(f'  {DIM}Config:{RESET}           {CONFIG_FILE}')
        print()


# ============================================================
# MAIN
# ============================================================
def main():
    try:
        OcsBrowserCLI().run()
    except KeyboardInterrupt:
        print(f'\n{YELLOW}Saliendo...{RESET}')


if __name__ == '__main__':
    main()
