from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
sys.path.insert(0, str(root / "dependencias"))
resources = [
    (str(root / "assets"), "assets"),
    (str(root / "dependencias/PPlay/LICENSE.Power-PPlay.txt"), "PPlay"),
]

analysis = Analysis(
    [str(root / "main.py")],
    pathex=[str(root / "src"), str(root / "dependencias")],
    datas=resources,
    hiddenimports=collect_submodules("PPlay"),
    module_collection_mode={"spawnbound": "pyz+py", "PPlay": "pyz+py"},
)
archive = PYZ(analysis.pure)
game = EXE(archive, analysis.scripts, [], exclude_binaries=True, name="SpawnBound",
           console=False, upx=False)
bundle = COLLECT(game, analysis.binaries, analysis.datas, name="SpawnBound", upx=False)
