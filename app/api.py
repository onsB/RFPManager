import json
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.agent import extract_requirements
from app.documents import load_document
from app.sections import split_sections

STATIC_DIR = Path(__file__).parent / "static"
SUPPORTED = {".pdf", ".docx", ".txt", ".md"}

app = FastAPI(title="RFP Manager")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/extract")
def extract(file: UploadFile) -> StreamingResponse:
    """Extracts requirements section by section, streaming one JSON line per event.

    Events: {"type": "sections", ...} first, then one {"type": "section", ...} per
    section as it finishes, so the page shows progress instead of waiting minutes.
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(400, f"Unsupported file type: {suffix or 'none'}")

    # load_document reads from a path and picks the parser by extension.
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
    try:
        sections = split_sections(load_document(tmp.name))
    finally:
        Path(tmp.name).unlink(missing_ok=True)

    def events():
        yield json.dumps({
            "type": "sections",
            "sections": [{"id": s.id, "title": s.breadcrumb, "chars": s.char_count} for s in sections],
        }) + "\n"

        for section in sections:
            start = time.perf_counter()
            try:
                requirements = [r.model_dump() for r in extract_requirements(section)]
                error = None
            except Exception as exc:  # one failing section should not stop the run
                requirements, error = [], str(exc)
            yield json.dumps({
                "type": "section",
                "id": section.id,
                "title": section.breadcrumb,
                "seconds": round(time.perf_counter() - start, 1),
                "requirements": requirements,
                "error": error,
            }) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


if __name__ == "__main__":
    # Lets VS Code's Run button start the server: then open http://127.0.0.1:8000
    import uvicorn

    uvicorn.run("app.api:app", host="127.0.0.1", port=8000, reload=True)
