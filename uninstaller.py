#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import shutil
import threading

try:
    import tkinter as tk
    from tkinter import ttk, messagebox
except ImportError:
    print("Нужно установить пакет: sudo dnf install python3-tkinter")
    exit(1)

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


IS_FLATPAK = bool(os.environ.get('FLATPAK_ID')) or os.path.exists('/.flatpak-info')


def wrap_host_cmd(cmd):
    if IS_FLATPAK:
        return ['flatpak-spawn', '--host'] + cmd
    return cmd


def host_path(path):
    if not path:
        return path
    if IS_FLATPAK and (path.startswith('/usr/') or path.startswith('/var/') or path.startswith('/etc/')):
        mapped = '/run/host' + path
        if os.path.exists(mapped):
            return mapped
    return path


def host_which(binary):
    if not IS_FLATPAK:
        return bool(shutil.which(binary))
    try:
        res = subprocess.run(
            ['flatpak-spawn', '--host', 'which', binary],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return res.returncode == 0
    except Exception:
        return False


# ==========================================
# Фирменная палитра (Красный стиль)
# ==========================================
COLORS = {
    'brand': '#C62828',
    'brand_dark': '#8E0000',
    'bg_main': '#F2F4F7',
    'bg_card': '#FFFFFF',
    'bg_zebra': '#FAFBFD',
    'primary': '#1565C0',
    'danger': '#D32F2F',
    'danger_hover': '#B71C1C',
    'text_primary': '#1E242B',
    'text_secondary': '#606F7B',
    'text_on_brand': '#FFFFFF',
    'border': '#DCE1E7',
    'row_hover': '#EEF3F8',
    'row_selected': '#FDECEA',
    'selected_text': '#B71C1C',
}

CRITICAL_PACKAGES = {
    'kernel', 'kernel-core', 'systemd', 'glibc', 'bash', 'dnf', 'rpm',
    'sudo', 'passwd', 'grub2', 'xorg-x11-server-Xorg', 'networkmanager',
    'apt', 'dpkg', 'pacman'
}


# ==========================================
# Работа с пакетными менеджерами
# ==========================================
def detect_managers():
    managers = []
    if host_which('dnf') or host_which('yum') or host_which('rpm'):
        managers.append('rpm')
    if host_which('flatpak'):
        managers.append('flatpak')
    if host_which('snap'):
        managers.append('snap')
    if host_which('dpkg') and host_which('apt'):
        managers.append('apt')
    elif host_which('pacman'):
        managers.append('pacman')
    elif host_which('zypper'):
        managers.append('zypper')
    return managers


def get_packages_flatpak():
    try:
        out = subprocess.check_output(
            wrap_host_cmd(['flatpak', 'list', '--app', '--columns=application,name,version']),
            universal_newlines=True,
            stderr=subprocess.DEVNULL
        )
        packages = []
        for line in out.strip().split('\n'):
            parts = line.split('\t')
            if len(parts) >= 2 and parts[0] != 'Application ID':
                packages.append({
                    'name': parts[1] if parts[1] else parts[0],
                    'id': parts[0],
                    'version': parts[2] if len(parts) >= 3 and parts[2].strip() else '—',
                    'manager': 'flatpak'
                })
        return packages
    except Exception:
        return []


def get_packages_snap():
    try:
        out = subprocess.check_output(
            wrap_host_cmd(['snap', 'list']),
            universal_newlines=True,
            stderr=subprocess.DEVNULL
        )
        packages = []
        for line in out.strip().split('\n')[1:]:
            parts = line.split()
            if len(parts) >= 3:
                packages.append({
                    'name': parts[0],
                    'id': parts[0],
                    'version': parts[1],
                    'manager': 'snap'
                })
        return packages
    except Exception:
        return []


def get_packages_apt():
    try:
        out = subprocess.check_output(
            wrap_host_cmd(['dpkg-query', '-W', '-f=${Package}\t${Version}\n']),
            universal_newlines=True,
            stderr=subprocess.DEVNULL
        )
        packages = []
        for line in out.strip().split('\n'):
            if '\t' in line:
                name, version = line.split('\t', 1)
                packages.append({
                    'name': name,
                    'id': name,
                    'version': version,
                    'manager': 'apt'
                })
        return packages
    except Exception:
        return []


def get_packages_pacman():
    try:
        out = subprocess.check_output(
            wrap_host_cmd(['pacman', '-Q']),
            universal_newlines=True,
            stderr=subprocess.DEVNULL
        )
        packages = []
        for line in out.strip().split('\n'):
            parts = line.split()
            if len(parts) >= 2:
                packages.append({
                    'name': parts[0],
                    'id': parts[0],
                    'version': parts[1],
                    'manager': 'pacman'
                })
        return packages
    except Exception:
        return []


def get_packages_rpm():
    try:
        out = subprocess.check_output(
            wrap_host_cmd(['rpm', '-qa', '--qf', '%{NAME}\t%{VERSION}-%{RELEASE}\n']),
            universal_newlines=True,
            stderr=subprocess.DEVNULL
        )
        packages = []
        for line in out.strip().split('\n'):
            if '\t' in line:
                name, version = line.split('\t', 1)
                packages.append({
                    'name': name,
                    'id': name,
                    'version': version,
                    'manager': 'rpm'
                })
        return packages
    except Exception:
        return []


def get_packages_zypper():
    if host_which('rpm'):
        pkgs = get_packages_rpm()
        for p in pkgs:
            p['manager'] = 'zypper'
        return pkgs
    return []


# ==========================================
# Поиск, загрузка и генерация иконок
# ==========================================
def load_desktop_metadata():
    """Собирает иконки и локализованные названия приложений из .desktop файлов."""
    icons = {}
    ru_names = {}
    raw_dirs = [
        '/app/share/applications', '/usr/share/applications',
        '/usr/local/share/applications',
        os.path.expanduser('~/.local/share/applications'),
        '/var/lib/flatpak/exports/share/applications',
        os.path.expanduser('~/.local/share/flatpak/exports/share/applications')
    ]
    dirs = [host_path(d) for d in raw_dirs]

    for d in dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith('.desktop'):
                continue
            path = os.path.join(d, f)
            try:
                name = None
                name_ru = None
                icon = None
                exec_cmd = None
                no_display = False
                with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
                    for line in fh:
                        line = line.strip()
                        if line.startswith('Name=') and not name:
                            name = line[5:].strip()
                        elif line.startswith('Name[ru]=') and not name_ru:
                            name_ru = line[9:].strip()
                        elif line.startswith('Icon=') and not icon:
                            icon = line[5:].strip()
                        elif line.startswith('Exec=') and not exec_cmd:
                            parts = line[5:].split()
                            if parts:
                                exec_cmd = parts[0].split('/')[-1]
                        elif line == 'NoDisplay=true':
                            no_display = True

                base = os.path.splitext(f)[0].lower()
                if icon:
                    icons[base] = icon
                    if name:
                        icons[name.lower()] = icon
                    if name_ru:
                        icons[name_ru.lower()] = icon
                    if exec_cmd:
                        icons[exec_cmd.lower()] = icon

                if not no_display and (name_ru or name):
                    display = name_ru if name_ru else name
                    ru_names[base] = display
                    if exec_cmd:
                        ru_names[exec_cmd.lower()] = display
            except Exception:
                pass
    return icons, ru_names


def build_icon_index():
    """Индексирует PNG иконки в системных и пользовательских директориях."""
    index = {}
    raw_roots = [
        '/app/share/icons/hicolor', '/usr/share/pixmaps',
        '/usr/share/icons/hicolor',
        '/usr/share/icons/Papirus',
        '/usr/share/icons/Adwaita',
        '/usr/share/icons/breeze',
        '/var/lib/flatpak/exports/share/icons/hicolor',
        os.path.expanduser('~/.local/share/flatpak/exports/share/icons/hicolor'), '/var/home/moroziv/.local/share/flatpak/exports/share/icons/hicolor',
        os.path.expanduser('~/.local/share/icons')
    ]
    search_roots = [host_path(r) for r in raw_roots]
    preferred_sizes = ['32x32', '48x48', '24x24', '64x64', '128x128', '256x256', '16x16']

    for root_dir in search_roots:
        if not os.path.isdir(root_dir):
            continue
        for root, _, files in os.walk(root_dir):
            for file in files:
                if file.endswith('.png'):
                    key = os.path.splitext(file)[0].lower()
                    full_path = os.path.join(root, file)
                    if key not in index:
                        index[key] = full_path
                    else:
                        for sz in preferred_sizes[:3]:
                            if sz in full_path:
                                index[key] = full_path
                                break
    return index


def load_icon_image(path, size=24):
    path = host_path(path)
    if not path or not os.path.exists(path):
        return None
    try:
        if HAS_PIL:
            img = Image.open(path).convert("RGBA")
            img = img.resize((size, size), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
        else:
            img = tk.PhotoImage(file=path)
            w, h = img.width(), img.height()
            if w > size or h > size:
                factor = max(round(w / size), round(h / size))
                if factor > 1:
                    img = img.subsample(factor, factor)
            return img
    except Exception:
        return None


def find_app_window_icon():
    """Ищет иконку самого приложения для заголовка окна."""
    candidates = [
        '/app/share/icons/hicolor/128x128/apps/io.github.moroziv.AppUninstaller.png',
        '/usr/share/pixmaps/app-uninstaller.png',
        '/usr/share/icons/hicolor/128x128/apps/app-uninstaller.png',
        os.path.expanduser('~/.local/share/icons/app-uninstaller.png'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app-uninstaller.png'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def create_default_icon(size=24):
    """Аккуратная иконка пакета для системных компонентов."""
    img = tk.PhotoImage(width=size, height=size)
    img.put('#E4E8EE', to=(3, 4, size - 3, size - 3))
    img.put('#B0BEC5', to=(6, 9, size - 6, size - 6))
    img.put('#90A4AE', to=(6, 6, size - 6, 9))
    return img


def find_terminal():
    terms = [
        ('konsole', '-e'),
        ('mate-terminal', '-e'),
        ('gnome-terminal', '--'),
        ('xfce4-terminal', '-e'),
        ('lxterminal', '-e'),
        ('xterm', '-e'),
    ]
    for t, flag in terms:
        if host_which(t):
            return t, flag
    return None, None


# ==========================================
# Главное окно приложения
# ==========================================
class UninstallerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Управление программами")
        self.root.geometry("1040x690")
        self.root.minsize(820, 520)
        self.root.configure(bg=COLORS['bg_main'])

        self.window_icon_ref = None
        win_icon_path = find_app_window_icon()
        if win_icon_path:
            img = load_icon_image(win_icon_path, size=64)
            if img:
                self.window_icon_ref = img
                self.root.iconphoto(True, img)

        self.all_packages = []
        self.pkg_icons = {}
        self.icon_refs = []
        self.default_icon = create_default_icon(24)

        self.sort_col = 'name'
        self.sort_reverse = False
        self.hovered_item = None
        self.placeholder_active = False

        self.setup_styles()
        self.build_ui()
        self.load_packages_async()

    def setup_styles(self):
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')

        font_family = "DejaVu Sans"
        self.font_header = (font_family, 13, "bold")
        self.font_sub_header = (font_family, 9)
        self.font_body = (font_family, 10)
        self.font_bold = (font_family, 10, "bold")
        self.font_small = (font_family, 9)

        style.configure("Main.TFrame", background=COLORS['bg_main'])
        style.configure("Card.TFrame", background=COLORS['bg_card'])
        style.configure("Sub.TLabel", background=COLORS['bg_main'], foreground=COLORS['text_secondary'], font=self.font_small)
        style.configure("InfoTitle.TLabel", background=COLORS['bg_card'], foreground=COLORS['text_primary'], font=self.font_bold)
        style.configure("InfoText.TLabel", background=COLORS['bg_card'], foreground=COLORS['text_secondary'], font=self.font_small)

        style.configure(
            "Filter.TCombobox",
            fieldbackground='#FFFFFF',
            background='#FFFFFF',
            foreground=COLORS['text_primary'],
            bordercolor=COLORS['border'],
            padding=(8, 6)
        )

        style.configure(
            "BrandFlat.TButton",
            background='#B71C1C',
            foreground="#FFFFFF",
            borderwidth=0,
            font=self.font_bold,
            padding=(12, 7)
        )
        style.map(
            "BrandFlat.TButton",
            background=[('active', '#9A0007'), ('pressed', '#7F0000')]
        )

        style.configure(
            "Danger.TButton",
            background=COLORS['danger'],
            foreground="#FFFFFF",
            borderwidth=0,
            font=self.font_bold,
            padding=(20, 9)
        )
        style.map(
            "Danger.TButton",
            background=[('active', COLORS['danger_hover']), ('disabled', '#D8DEE4')],
            foreground=[('disabled', '#8C98A4')]
        )

        style.configure(
            "App.Treeview",
            background=COLORS['bg_card'],
            fieldbackground=COLORS['bg_card'],
            foreground=COLORS['text_primary'],
            rowheight=38,
            borderwidth=0,
            font=self.font_body
        )
        style.configure(
            "App.Treeview.Heading",
            background='#F7F9FB',
            foreground=COLORS['text_secondary'],
            font=self.font_bold,
            borderwidth=1,
            relief="flat",
            padding=(10, 10)
        )
        style.map(
            "App.Treeview.Heading",
            background=[('active', '#EDF1F5')]
        )
        style.map(
            "App.Treeview",
            background=[('selected', COLORS['row_selected'])],
            foreground=[('selected', COLORS['selected_text'])]
        )

        style.configure(
            "App.Horizontal.TProgressbar",
            troughcolor=COLORS['brand_dark'],
            background='#FFCDD2',
            thickness=3,
            borderwidth=0
        )

    def build_ui(self):
        # 1. Верхняя панель (AppBar)
        appbar = tk.Frame(self.root, bg=COLORS['brand'], height=68)
        appbar.pack(side=tk.TOP, fill=tk.X)
        appbar.pack_propagate(False)

        brand_box = tk.Frame(appbar, bg=COLORS['brand'])
        brand_box.pack(side=tk.LEFT, padx=20)

        title_texts = tk.Frame(brand_box, bg=COLORS['brand'])
        title_texts.pack(side=tk.LEFT)
        tk.Label(
            title_texts, text="Управление программами",
            bg=COLORS['brand'], fg=COLORS['text_on_brand'],
            font=self.font_header
        ).pack(anchor="w")
        tk.Label(
            title_texts, text="Просмотр и удаление установленных пакетов",
            bg=COLORS['brand'], fg='#FFCDD2',
            font=self.font_sub_header
        ).pack(anchor="w")

        controls = tk.Frame(appbar, bg=COLORS['brand'])
        controls.pack(side=tk.RIGHT, padx=20)

        self.filter_var = tk.StringVar(value="Приложения (с иконкой)")
        self.filter_combo = ttk.Combobox(
            controls,
            textvariable=self.filter_var,
            state="readonly",
            width=22,
            style="Filter.TCombobox",
            font=self.font_body
        )
        self.filter_combo['values'] = (
            "Приложения (с иконкой)",
            "Все пакеты",
            "rpm",
            "flatpak",
            "snap",
            "apt"
        )
        self.filter_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.filter_combo.bind("<<ComboboxSelected>>", self.filter_packages)

        search_wrap = tk.Frame(controls, bg='#FFFFFF', bd=0, padx=8, pady=4)
        search_wrap.pack(side=tk.LEFT, padx=(0, 10))

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_wrap,
            textvariable=self.search_var,
            width=24,
            bd=0,
            bg='#FFFFFF',
            fg=COLORS['text_primary'],
            font=self.font_body,
            highlightthickness=0
        )
        self.search_entry.pack(side=tk.LEFT, padx=4)
        self.set_placeholder()

        self.search_entry.bind("<FocusIn>", self.clear_placeholder)
        self.search_entry.bind("<FocusOut>", self.restore_placeholder)
        self.search_var.trace_add('write', self.on_search_change)

        self.btn_clear_search = tk.Label(
            search_wrap, text="x", bg='#FFFFFF',
            fg=COLORS['text_secondary'], cursor="hand2", font=("DejaVu Sans", 10, "bold")
        )
        self.btn_clear_search.pack(side=tk.LEFT, padx=(4, 0))
        self.btn_clear_search.bind("<Button-1>", self.reset_search)

        self.btn_refresh = ttk.Button(
            controls,
            text="Обновить",
            style="BrandFlat.TButton",
            command=self.load_packages_async
        )
        self.btn_refresh.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(
            self.root,
            mode='indeterminate',
            style="App.Horizontal.TProgressbar"
        )
        self.progress.pack(side=tk.TOP, fill=tk.X)

        # 2. Основная рабочая область
        container = tk.Frame(self.root, bg=COLORS['bg_main'])
        container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=(16, 8))

        card = tk.Frame(
            container,
            bg=COLORS['bg_card'],
            highlightbackground=COLORS['border'],
            highlightthickness=1
        )
        card.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            card,
            columns=('name', 'pkg_id', 'version', 'manager'),
            show='tree headings',
            style="App.Treeview",
            selectmode='browse'
        )

        self.tree.heading('#0', text='')
        self.tree.heading('name', text='Программа ▲', anchor='w', command=lambda: self.sort_by('name'))
        self.tree.heading('pkg_id', text='Имя пакета', anchor='w', command=lambda: self.sort_by('id'))
        self.tree.heading('version', text='Версия', anchor='w', command=lambda: self.sort_by('version'))
        self.tree.heading('manager', text='Источник', anchor='center', command=lambda: self.sort_by('manager'))

        self.tree.column('#0', width=52, minwidth=52, stretch=False, anchor='center')
        self.tree.column('name', width=320, minwidth=180, anchor='w')
        self.tree.column('pkg_id', width=260, minwidth=150, anchor='w')
        self.tree.column('version', width=200, minwidth=120, anchor='w')
        self.tree.column('manager', width=110, minwidth=80, anchor='center')

        self.tree.tag_configure('odd', background=COLORS['bg_card'])
        self.tree.tag_configure('even', background=COLORS['bg_zebra'])
        self.tree.tag_configure('hover', background=COLORS['row_hover'])

        scrollbar = ttk.Scrollbar(card, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<<TreeviewSelect>>', self.on_select_package)
        self.tree.bind('<Double-1>', lambda e: self.remove_selected())
        self.tree.bind('<Motion>', self.on_tree_hover)
        self.tree.bind('<Leave>', self.on_tree_leave)

        # 3. Карточка информации о выбранном пакете
        info_card = tk.Frame(
            container,
            bg=COLORS['bg_card'],
            highlightbackground=COLORS['border'],
            highlightthickness=1,
            height=64
        )
        info_card.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        info_card.pack_propagate(False)

        info_inner = tk.Frame(info_card, bg=COLORS['bg_card'])
        info_inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=10)

        self.lbl_pkg_title = ttk.Label(
            info_inner,
            text="Выберите программу в списке для просмотра подробностей",
            style="InfoTitle.TLabel"
        )
        self.lbl_pkg_title.pack(anchor="w")

        self.lbl_pkg_desc = ttk.Label(
            info_inner,
            text="Двойной клик по строке или нажатие кнопки «Удалить программу» запустит деинсталляцию.",
            style="InfoText.TLabel"
        )
        self.lbl_pkg_desc.pack(anchor="w", pady=(2, 0))

        # 4. Нижняя панель (Footer)
        footer = tk.Frame(self.root, bg=COLORS['bg_main'], height=56)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))

        self.status_label = ttk.Label(footer, text="Инициализация...", style="Sub.TLabel")
        self.status_label.pack(side=tk.LEFT, pady=10)

        self.btn_remove = ttk.Button(
            footer,
            text="Удалить программу",
            style="Danger.TButton",
            command=self.remove_selected
        )
        self.btn_remove.pack(side=tk.RIGHT, pady=6)

    # ==========================================
    # Логика плейсхолдера поиска и наведения
    # ==========================================
    def set_placeholder(self):
        self.placeholder_active = True
        self.search_entry.config(fg=COLORS['text_secondary'])
        self.search_var.set("Поиск программы...")

    def clear_placeholder(self, event=None):
        if self.placeholder_active:
            self.placeholder_active = False
            self.search_entry.config(fg=COLORS['text_primary'])
            self.search_var.set("")

    def restore_placeholder(self, event=None):
        if not self.search_var.get().strip():
            self.set_placeholder()

    def reset_search(self, event=None):
        self.placeholder_active = False
        self.search_entry.config(fg=COLORS['text_primary'])
        self.search_var.set("")
        self.search_entry.focus_set()

    def on_search_change(self, *args):
        if not self.placeholder_active:
            self.filter_packages()

    def on_tree_hover(self, event):
        item = self.tree.identify_row(event.y)
        if item != self.hovered_item:
            if self.hovered_item and self.tree.exists(self.hovered_item):
                idx = self.tree.index(self.hovered_item)
                base_tag = 'even' if idx % 2 else 'odd'
                self.tree.item(self.hovered_item, tags=(base_tag,))
            self.hovered_item = item
            if item and item not in self.tree.selection():
                self.tree.item(item, tags=('hover',))

    def on_tree_leave(self, event):
        if self.hovered_item and self.tree.exists(self.hovered_item):
            idx = self.tree.index(self.hovered_item)
            base_tag = 'even' if idx % 2 else 'odd'
            self.tree.item(self.hovered_item, tags=(base_tag,))
        self.hovered_item = None

    # ==========================================
    # Просмотр деталей о выбранном пакете
    # ==========================================
    def on_select_package(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        values = self.tree.item(selection[0])['values']
        disp_name, pkg_id, version, manager = str(values[0]), str(values[1]), str(values[2]), str(values[3])

        self.lbl_pkg_title.config(text=f"{disp_name}  ({pkg_id}  •  {version})")
        self.lbl_pkg_desc.config(text="Получение описания пакета...")

        threading.Thread(
            target=self.fetch_package_summary,
            args=(pkg_id, manager.lower()),
            daemon=True
        ).start()

    def fetch_package_summary(self, pkg_id, manager):
        summary = "Описание недоступно."
        try:
            if manager == 'rpm':
                out = subprocess.check_output(
                    wrap_host_cmd(['rpm', '-q', '--qf', '%{SUMMARY} (Размер: %{SIZE} байт)', pkg_id]),
                    universal_newlines=True,
                    stderr=subprocess.DEVNULL
                )
                if '(Размер: ' in out:
                    text_part, size_part = out.split('(Размер: ')
                    size_bytes = int(size_part.replace(' байт)', '').strip())
                    size_mb = round(size_bytes / (1024 * 1024), 1)
                    summary = f"{text_part.strip()}  •  Размер на диске: ~{size_mb} МБ"
                else:
                    summary = out.strip()
            elif manager == 'flatpak':
                out = subprocess.check_output(
                    wrap_host_cmd(['flatpak', 'info', pkg_id]),
                    universal_newlines=True,
                    stderr=subprocess.DEVNULL
                )
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                if len(lines) > 1:
                    summary = f"Приложение Flatpak: {lines[1]}"
            elif manager == 'apt':
                out = subprocess.check_output(
                    wrap_host_cmd(['dpkg-query', '-W', '-f=${binary:Summary}', pkg_id]),
                    universal_newlines=True,
                    stderr=subprocess.DEVNULL
                )
                summary = out.strip()
        except Exception:
            pass

        self.root.after(0, lambda: self.lbl_pkg_desc.config(text=summary))

    # ==========================================
    # Асинхронная загрузка данных и иконок
    # ==========================================
    def load_packages_async(self):
        self.btn_refresh.config(state='disabled')
        self.btn_remove.config(state='disabled')
        self.tree.delete(*self.tree.get_children())
        self.icon_refs.clear()
        self.status_label.config(text="Сканирование установленных пакетов и иконок...")
        self.progress.start(12)

        threading.Thread(target=self.load_packages_thread, daemon=True).start()

    def load_packages_thread(self):
        managers = detect_managers()
        packages = []

        for m in managers:
            if m == 'rpm':
                packages.extend(get_packages_rpm())
            elif m == 'flatpak':
                packages.extend(get_packages_flatpak())
            elif m == 'snap':
                packages.extend(get_packages_snap())
            elif m == 'apt':
                packages.extend(get_packages_apt())
            elif m == 'pacman':
                packages.extend(get_packages_pacman())
            elif m == 'zypper':
                packages.extend(get_packages_zypper())

        desktop_icons, ru_names = load_desktop_metadata()
        icon_index = build_icon_index()

        matched_paths = {}
        for pkg in packages:
            name_low = pkg['name'].lower()
            id_low = pkg['id'].lower()

            pretty_name = ru_names.get(id_low) or ru_names.get(name_low) or pkg['name']
            pkg['display_name'] = pretty_name

            icon_key = (
                desktop_icons.get(id_low)
                or desktop_icons.get(name_low)
                or id_low
            )

            if icon_key and os.path.isabs(icon_key) and os.path.exists(host_path(icon_key)):
                matched_paths[id_low] = icon_key
                continue

            icon_base = os.path.splitext(os.path.basename(icon_key))[0].lower() if icon_key else id_low
            if icon_base in icon_index:
                matched_paths[id_low] = icon_index[icon_base]
            elif id_low in icon_index:
                matched_paths[id_low] = icon_index[id_low]
            elif name_low in icon_index:
                matched_paths[id_low] = icon_index[name_low]

        self.all_packages = packages
        self.root.after(0, lambda: self.finish_loading(matched_paths))

    def finish_loading(self, matched_paths):
        self.pkg_icons.clear()
        for id_low, path in matched_paths.items():
            img = load_icon_image(path, size=24)
            if img:
                self.pkg_icons[id_low] = img

        self.progress.stop()
        self.btn_refresh.config(state='normal')
        self.btn_remove.config(state='normal')
        self.sort_packages_data()
        self.filter_packages()

    # ==========================================
    # Сортировка и фильтрация
    # ==========================================
    def sort_by(self, col):
        if self.sort_col == col:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_col = col
            self.sort_reverse = False

        arrow = " ▼" if self.sort_reverse else " ▲"
        headers = {
            'name': 'Программа',
            'id': 'Имя пакета',
            'version': 'Версия',
            'manager': 'Источник'
        }
        col_map = {'name': 'name', 'id': 'pkg_id', 'version': 'version', 'manager': 'manager'}
        for key, title in headers.items():
            suffix = arrow if key == col else ""
            self.tree.heading(col_map[key], text=title + suffix)

        self.sort_packages_data()
        self.filter_packages()

    def sort_packages_data(self):
        key_name = 'display_name' if self.sort_col == 'name' else self.sort_col
        self.all_packages.sort(
            key=lambda x: str(x.get(key_name, '')).lower(),
            reverse=self.sort_reverse
        )

    def filter_packages(self, *args):
        query = "" if self.placeholder_active else self.search_var.get().lower().strip()
        mode = self.filter_var.get()

        self.tree.delete(*self.tree.get_children())
        self.icon_refs.clear()
        self.hovered_item = None

        shown = 0
        for pkg in self.all_packages:
            disp_low = pkg['display_name'].lower()
            id_low = pkg['id'].lower()
            mgr = pkg['manager']
            has_custom_icon = id_low in self.pkg_icons

            if mode == "Приложения (с иконкой)" and not has_custom_icon:
                continue
            elif mode not in ("Все пакеты", "Приложения (с иконкой)") and mgr != mode:
                continue

            if query and (query not in disp_low and query not in id_low):
                continue

            icon = self.pkg_icons.get(id_low, self.default_icon)
            self.icon_refs.append(icon)

            row_tag = 'even' if shown % 2 else 'odd'
            self.tree.insert(
                '',
                'end',
                text='',
                image=icon,
                values=(pkg['display_name'], pkg['id'], pkg['version'], mgr.upper()),
                tags=(row_tag,)
            )
            shown += 1

        env_note = "  •  Режим Flatpak" if IS_FLATPAK else ""
        self.status_label.config(
            text=f"Показано: {shown} из {len(self.all_packages)}  •  Приложений с иконками: {len(self.pkg_icons)}{env_note}"
        )

    # ==========================================
    # Удаление программ
    # ==========================================
    def remove_selected(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("Внимание", "Выберите программу из списка для удаления.")
            return

        values = self.tree.item(selection[0])['values']
        disp_name = str(values[0])
        pkg_id = str(values[1])
        manager = str(values[3]).lower()

        pkg = next(
            (p for p in self.all_packages if p['id'] == pkg_id and p['manager'] == manager),
            None
        )
        if not pkg:
            messagebox.showerror("Ошибка", "Не удалось определить пакет для удаления.")
            return

        if pkg_id.lower() in CRITICAL_PACKAGES:
            if not messagebox.askyesno(
                "Критически важный пакет системы!",
                f"Пакет «{pkg_id}» является системным компонентом.\n"
                "Его удаление может сделать систему неработоспособной!\n\n"
                "Вы абсолютно уверены, что хотите продолжить?",
                icon='warning'
            ):
                return

        if not messagebox.askyesno(
            "Подтверждение удаления",
            f"Удалить «{disp_name}» (пакет: {pkg_id}, {manager.upper()})?\n\n"
            "Зависимые пакеты также могут быть удалены."
        ):
            return

        cmd, need_root = self.build_remove_command(pkg)
        if not cmd:
            messagebox.showerror("Ошибка", "Неизвестный пакетный менеджер.")
            return

        self.run_remove_command(cmd, need_root)

    def build_remove_command(self, pkg):
        m = pkg['manager']
        pid = pkg['id']

        if m == 'flatpak':
            return ['flatpak', 'uninstall', '-y', pid], False
        elif m == 'snap':
            return ['snap', 'remove', pid], True
        elif m == 'apt':
            return ['apt', 'remove', '-y', pid], True
        elif m == 'pacman':
            return ['pacman', '-Rns', '--noconfirm', pid], True
        elif m == 'rpm':
            if host_which('dnf'):
                return ['dnf', 'remove', '-y', pid], True
            elif host_which('yum'):
                return ['yum', 'remove', '-y', pid], True
            else:
                return ['rpm', '-e', pid], True
        elif m == 'zypper':
            return ['zypper', 'remove', '-y', pid], True

        return None, False

    def run_remove_command(self, cmd, need_root):
        self.btn_remove.config(state='disabled')
        self.status_label.config(text=f"Выполняется удаление: {' '.join(cmd)}...")
        self.progress.start(12)

        if need_root:
            if host_which('pkexec'):
                full_cmd = wrap_host_cmd(['pkexec'] + cmd)
                threading.Thread(target=self.execute_removal, args=(full_cmd,), daemon=True).start()
            else:
                term, flag = find_terminal()
                if term:
                    sudo_cmd = ['sudo'] + cmd
                    raw_term_cmd = [term, '--'] + sudo_cmd if flag == '--' else [term, flag, ' '.join(sudo_cmd)]
                    subprocess.Popen(wrap_host_cmd(raw_term_cmd))
                    self.progress.stop()
                    self.btn_remove.config(state='normal')
                    messagebox.showinfo("Удаление", "Процесс удаления запущен в окне терминала.")
                else:
                    self.progress.stop()
                    self.btn_remove.config(state='normal')
                    messagebox.showerror("Ошибка", "Не найден pkexec или терминал для повышения прав.")
        else:
            threading.Thread(target=self.execute_removal, args=(wrap_host_cmd(cmd),), daemon=True).start()

    def execute_removal(self, cmd):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            self.root.after(0, self.progress.stop)
            self.root.after(0, lambda: self.btn_remove.config(state='normal'))

            if result.returncode == 0:
                msg = "Программа успешно удалена."
                if result.stdout:
                    msg += "\n\n" + result.stdout[-400:]
                self.root.after(0, lambda: messagebox.showinfo("Готово", msg))
                self.root.after(0, self.load_packages_async)
            else:
                msg = "Не удалось удалить программу."
                if result.stderr:
                    msg += "\n\n" + result.stderr[-400:]
                self.root.after(0, lambda: messagebox.showerror("Ошибка удаления", msg))
                self.root.after(0, lambda: self.status_label.config(text="Ошибка при удалении."))
        except Exception as e:
            self.root.after(0, self.progress.stop)
            self.root.after(0, lambda: self.btn_remove.config(state='normal'))
            self.root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))


if __name__ == '__main__':
    root = tk.Tk()
    app = UninstallerApp(root)
    root.mainloop()
