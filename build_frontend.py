from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "frontend"
DST = ROOT / "app" / "static"
if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST)
(DST / "config.js").write_text('window.APP_CONFIG = {buildTarget:"docker",version:"9.1.3",defaultApiUrl:"",allowLocalMode:false};\n', encoding="utf-8")
print(f"Built Docker frontend into {DST}")
