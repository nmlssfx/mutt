# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.building.build_main import ANALYSIS, PYZ, EXE
from PyInstaller.building.datas import TOC
import os

block_cipher = None

# Data files to include
datas = []
# Add dist_README.txt as README.txt next to exe
if os.path.exists(r'D:\clouds\ncloud\Dev\ttsgenerator\dist_README.txt'):
    datas.append((r'D:\clouds\ncloud\Dev\ttsgenerator\dist_README.txt', '.'))

# Add .env.example as reference
if os.path.exists(r'D:\clouds\ncloud\Dev\ttsgenerator\.env.example'):
    datas.append((r'D:\clouds\ncloud\Dev\ttsgenerator\.env.example', '.'))

a = ANALYSIS(
    [r'D:\clouds\ncloud\Dev\ttsgenerator\mutt_gui.py'],
    pathex=[r'D:\clouds\ncloud\Dev\ttsgenerator'],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'ttkbootstrap',
        'ttkbootstrap.themes',
        'ttkbootstrap.themes.cosmo',
        'ttkbootstrap.themes.cyborg',
        'pygame',
        'pygame.base',
        'pygame.constants',
        'pygame.display',
        'pygame.mixer',
        'pygame.mixer_music',
        'requests',
        'dotenv',
        'dotenv.main',
        'mutt',
        'mutt_cli',
        'presets',
        'mimetypes',
    ],
    hookspath=[],
    hooksconfig=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'test', 'pydoc'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MuttTTS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed mode
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add: r'D:\clouds\ncloud\Dev\ttsgenerator\icon.ico' if you have one
)
