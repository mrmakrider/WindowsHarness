# WindowsHarness PyInstaller Spec File
# Build on Windows: pyinstaller windows-harness.spec
#
# Requirements:
#   pip install pyinstaller
#   pip install -r requirements.txt
#   pip install PyQt6-WebEngine PyQt6-Qscintilla

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# -----------------------------------------------------------------------------
# Collect PyQt6 WebEngine data files (critical for browser widget)
# -----------------------------------------------------------------------------
webengine_data = []

# QtWebEngineProcess executable
webengine_data += collect_data_files('PyQt6', subdir='QtWebEngineProcess', include_py_files=False)

# QtWebEngineCore resources
webengine_data += collect_data_files('PyQt6', subdir='QtWebEngineCore', include_py_files=False)

# QtWebEngineWidgets
webengine_data += collect_data_files('PyQt6', subdir='QtWebEngineWidgets', include_py_files=False)

# Translations
webengine_data += collect_data_files('PyQt6', subdir='translations', include_py_files=False)

# Resources (icudtl.dat, etc.)
webengine_data += collect_data_files('PyQt6', subdir='resources', include_py_files=False)

# -----------------------------------------------------------------------------
# Collect QScintilla plugin
# -----------------------------------------------------------------------------
qsci_data = collect_data_files('PyQt6', subdir='Qsci', include_py_files=False)

# -----------------------------------------------------------------------------
# Project source files
# -----------------------------------------------------------------------------
project_modules = [
    'config',
    'core',
    'llm',
    'tools',
    'workspace',
    'skills',
    'shell',
    'ui',
]

project_data = [(mod, mod) for mod in project_modules]

# -----------------------------------------------------------------------------
# Hidden imports (modules not detected by static analysis)
# -----------------------------------------------------------------------------
hiddenimports = [
    # Qt async integration
    'qasync',
    
    # Keyring Windows backend
    'keyring.backends.Windows',
    'keyring.util.platform_',
    
    # Pydantic v2
    'pydantic',
    'pydantic_core',
    'pydantic._internal',
    'pydantic.fields',
    'pydantic.main',
    'pydantic.types',
    'pydantic.networks',
    'pydantic.json_schema',
    
    # PyQt6 WebEngine (critical)
    'PyQt6.QtWebEngineCore',
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineQuick',
    'PyQt6.QtWebChannel',
    
    # QScintilla
    'PyQt6.Qsci',
    
    # Git/GitHub
    'git',
    'git.cmd',
    'git.repo',
    'git.index',
    'git.diff',
    'github',
    'github.Github',
    'github.Repository',
    'github.PaginatedList',
    
    # LLM providers (optional - loaded dynamically)
    'openai',
    'anthropic',
    'google.generativeai',
    'google.ai.generativelanguage',
    
    # YAML
    'yaml',
    
    # Standard library modules sometimes missed
    'asyncio',
    'json',
    'pathlib',
    'dataclasses',
    'typing',
    'enum',
    'datetime',
    'uuid',
    'hashlib',
    'base64',
    'hmac',
    'secrets',
    'subprocess',
    'shlex',
    'signal',
    'platform',
    'importlib',
    'importlib.util',
    'importlib.machinery',
    'inspect',
    'textwrap',
    'difflib',
    're',
    'fnmatch',
    'shutil',
    'tempfile',
    'mimetypes',
    'urllib.parse',
    'urllib.request',
    'http.client',
    'ssl',
    'socket',
    'threading',
    'queue',
    'concurrent.futures',
    'collections',
    'collections.abc',
    'functools',
    'itertools',
    'operator',
    'contextlib',
    'abc',
    'numbers',
    'decimal',
    'fractions',
    'statistics',
    'math',
    'random',
    'string',
    'time',
    'calendar',
    'zoneinfo',
    'email',
    'html',
    'xml',
    'csv',
    'sqlite3',
    'logging',
    'logging.config',
    'logging.handlers',
    'argparse',
    'getopt',
    'optparse',
    'cmd',
    'shlex',
    'configparser',
    'tomllib',
    'plistlib',
    'pickle',
    'shelve',
    'dbm',
    'zlib',
    'gzip',
    'bz2',
    'lzma',
    'tarfile',
    'zipfile',
    'hashlib',
    'hmac',
    'secrets',
    'bisect',
    'heapq',
    'array',
    'weakref',
    'types',
    'copy',
    'pprint',
    'reprlib',
    'enum',
    'graphlib',
    'dataclasses',
    'typing',
    'typing_extensions',
]

# -----------------------------------------------------------------------------
# Exclude unnecessary packages to reduce size
# -----------------------------------------------------------------------------
excludes = [
    'tkinter', 'tkinter.*',
    'matplotlib', 'matplotlib.*',
    'numpy', 'numpy.*',
    'pandas', 'pandas.*',
    'scipy', 'scipy.*',
    'PIL', 'PIL.*',
    'cv2', 'cv2.*',
    'torch', 'torch.*',
    'tensorflow', 'tensorflow.*',
    'jupyter', 'jupyter.*',
    'IPython', 'IPython.*',
    'notebook', 'notebook.*',
    'pytest', 'pytest.*',
    'setuptools', 'setuptools.*',
    'pip', 'pip.*',
    'wheel', 'wheel.*',
    'virtualenv', 'virtualenv.*',
    'conda', 'conda.*',
    'sphinx', 'sphinx.*',
    'docutils', 'docutils.*',
    'pygments', 'pygments.*',
    'sphinxcontrib', 'sphinxcontrib.*',
    'mypy', 'mypy.*',
    'pylint', 'pylint.*',
    'flake8', 'flake8.*',
    'black', 'black.*',
    'isort', 'isort.*',
    'ruff', 'ruff.*',
    'bandit', 'bandit.*',
    'safety', 'safety.*',
]

# -----------------------------------------------------------------------------
# Analysis
# -----------------------------------------------------------------------------
a = Analysis(
    ['main.py'],
    pathex=[os.path.dirname(os.path.abspath(__file__))],
    binaries=[],
    datas=webengine_data + qsci_data + project_data,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

# -----------------------------------------------------------------------------
# PYZ archive
# -----------------------------------------------------------------------------
pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=None,
)

# -----------------------------------------------------------------------------
# EXE
# -----------------------------------------------------------------------------
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='WindowsHarness',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[
        'vcruntime140.dll',
        'Qt6WebEngineCore.dll',
        'Qt6WebEngine.dll',
        'Qt6WebEngineWidgets.dll',
        'Qt6Qml.dll',
        'Qt6Quick.dll',
    ],
    runtime_tmpdir=None,
    console=False,  # GUI app - no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico' if os.path.exists('assets/icon.ico') else None,
)

# -----------------------------------------------------------------------------
# Optional: Create installer with NSIS (if NSIS installed)
# -----------------------------------------------------------------------------
# from PyInstaller.utils.win32 import versioninfo
# 
# version_info = versioninfo.VSVersionInfo(
#     filevers=(0, 1, 0, 0),
#     prodvers=(0, 1, 0, 0),
#     mask=0x3f,
#     flags=0x0,
#     OS=0x40004,
#     fileType=0x1,
#     subtype=0x0,
#     date=(0, 0),
#     kids=[
#         versioninfo.StringFileInfo([
#             versioninfo.StringTable('040904B0', [
#                 versioninfo.StringStruct('CompanyName', 'WindowsHarness'),
#                 versioninfo.StringStruct('FileDescription', 'AI Coding Agent for Windows'),
#                 versioninfo.StringStruct('FileVersion', '0.1.0'),
#                 versioninfo.StringStruct('InternalName', 'WindowsHarness'),
#                 versioninfo.StringStruct('LegalCopyright', 'MIT License'),
#                 versioninfo.StringStruct('OriginalFilename', 'WindowsHarness.exe'),
#                 versioninfo.StringStruct('ProductName', 'WindowsHarness'),
#                 versioninfo.StringStruct('ProductVersion', '0.1.0'),
#             ])
#         ]),
#         versioninfo.VarFileInfo([
#             versioninfo.VarStruct('Translation', [0x0409, 0x04B0])
#         ])
#     ]
# )
# 
# exe = EXE(..., version=version_info, ...)
