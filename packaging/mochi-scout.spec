from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ, COLLECT


ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "app" / "cli.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "app" / "prompts"), "app/prompts"),
        (str(ROOT / "app" / "skills"), "app/skills"),
        (str(ROOT / "pipeline_defs"), "pipeline_defs"),
    ],
    hiddenimports=[
        "app.workflow",
        "app.workflow.graph",
        "app.workflow.langgraph_runner",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "pytest",
        "jupyter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "torch",
        "tensorflow",
        "langchain",
        "langchain_openai",
        "PyQt5",
        "PySide6",
        "tkinter",
        "zmq",
        "pyarrow",
        "xarray",
        "bokeh",
        "sphinx",
        "notebook",
        "jupyterlab",
        "sklearn",
        "torch",
        "torchvision",
        "yt_dlp",
        "Crypto",
        "Cryptodome",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="mochi-scout",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    exclude_binaries=True,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name="mochi-scout")
