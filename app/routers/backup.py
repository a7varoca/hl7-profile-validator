import zipfile
from datetime import date
from io import BytesIO

from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.services import db as profile_db
from app.services.profile_service import import_profile_yaml

router = APIRouter()


@router.get("/")
def download_backup():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for profile_id, yaml_str in profile_db.all_as_yaml():
            zf.writestr(f"profiles/{profile_id}.yaml", yaml_str.encode("utf-8"))
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
            try:
                yaml_content = zf.read(name).decode("utf-8")
                import_profile_yaml(yaml_content)
                profiles_restored += 1
            except Exception:
                continue

    return {"profiles_restored": profiles_restored}
