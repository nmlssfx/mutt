# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.building.build_main import Analysis, PYZ, EXE

block_cipher = None

a = Analysis(
    [r'D:\clouds\ncloud\Dev\ttsgenerator\mutt_gui.py'],
    pathex=[r'D:\clouds\ncloud\Dev\ttsgenerator'],
    binaries=[],
    datas=[
        (r'D:\clouds\ncloud\Dev\ttsgenerator\.env.example', '.'),
        (r'D:\clouds\ncloud\Dev\ttsgenerator\dist_README.txt', '.'),
    ],
    hiddenimports=[
        'ttkbootstrap',
        'ttkbootstrap.themes',
        'tkinter',
        'tkinter.ttk',
        'pygame',
        'pygame.mixer',
        'requests',
        'dotenv',
        'mutt',
        'presets',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['unittest', 'test'],  # Remove 'tkinter' from excludes!
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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
