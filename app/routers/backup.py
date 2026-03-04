import zipfile
from datetime import date
from io import BytesIO

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.config import settings

router = APIRouter()


@router.get("/")
def download_backup():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if settings.profiles_dir.exists():
            for yaml_file in sorted(settings.profiles_dir.glob("*.yaml")):
                zf.write(yaml_file, f"profiles/{yaml_file.name}")
    buf.seek(0)
    filename = f"hl7-backup-{date.today()}.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...)):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Expected a .zip file")

    content = await file.read()
    try:
        zf = zipfile.ZipFile(BytesIO(content))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    profiles_restored = 0
    for name in zf.namelist():
        if name.startswith("profiles/") and name.endswith(".yaml"):
            fname = name[len("profiles/"):]
            if not fname:
                continue
            # Sanitize: reject any path traversal attempts
            if "/" in fname or "\\" in fname:
                continue
            settings.profiles_dir.mkdir(exist_ok=True)
            (settings.profiles_dir / fname).write_bytes(zf.read(name))
            profiles_restored += 1

    return {"profiles_restored": profiles_restored}
