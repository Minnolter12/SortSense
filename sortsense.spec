# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build specification for SortSense.
Packages SortSense as a standalone Windows One-Folder desktop application.
Excludes extraneous global packages (torch, pandas, scipy, etc.) to keep build fast and lean.
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all CustomTkinter theme JSONs and font assets
ctk_datas = collect_data_files('customtkinter')

# Additional project assets
extra_datas = [
    ('assets', 'assets'),
    ('LICENSE', '.'),
    ('README.md', '.'),
] + ctk_datas

# Hidden imports to ensure dynamic modules are discovered
hidden_imports = (
    collect_submodules('customtkinter')
    + collect_submodules('watchdog')
    + collect_submodules('app.intent')
    + collect_submodules('ollama')
    + [
        'ollama',
        'httpx',
        'httpcore',
        'pypdf',
        'pymupdf',
        'fitz',
        'PIL',
        'pydantic',
        'pydantic_core',
        'watchdog.observers.read_directory_changes',
    ]
)

# Exclude unnecessary dev/server/ML dependencies from global environment
excludes = [
    'pytest',
    '_pytest',
    'unittest',
    'fastapi',
    'uvicorn',
    'starlette',
    'torch',
    'torchvision',
    'torchaudio',
    'scipy',
    'pandas',
    'matplotlib',
    'IPython',
    'ipykernel',
    'jupyter',
    'notebook',
    'sklearn',
    'cv2',
    'tensorboard',
    'lxml',
]

a = Analysis(
    ['sortsense.py'],
    pathex=['.'],
    binaries=[],
    datas=extra_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SortSense',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed GUI application (no black terminal popup)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SortSense',
)
