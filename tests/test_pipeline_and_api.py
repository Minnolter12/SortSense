"""
Tests for multi-format ingestion extensions, watcher debounce/temp-file filtering,
end-to-end FileMindPipeline, SQLite database, and FastAPI endpoints.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.database import FileMindDatabase
from app.ingestion import ingest_file
from app.pipeline import FileMindPipeline
from app.watcher import _should_ignore, wait_for_file_ready


# ---------------------------------------------------------------------------
# 1. Watcher edge cases (.crdownload, .part, debounce)
# ---------------------------------------------------------------------------

class TestWatcherDownloadEdgeCases:
    def test_ignores_browser_partial_downloads(self, tmp_path: Path):
        assert _should_ignore(tmp_path / "video.mp4.crdownload") is True
        assert _should_ignore(tmp_path / "archive.zip.part") is True
        assert _should_ignore(tmp_path / "report.pdf.tmp") is True
        assert _should_ignore(tmp_path / "report.pdf") is False

    def test_wait_for_file_ready_succeeds_for_stable_file(self, tmp_path: Path):
        f = tmp_path / "complete.txt"
        f.write_text("download finished")
        assert wait_for_file_ready(f, interval=0.01, max_wait=1.0) is True

    def test_wait_for_file_ready_returns_false_for_missing_file(self, tmp_path: Path):
        assert wait_for_file_ready(tmp_path / "missing.txt", interval=0.01, max_wait=0.1) is False


# ---------------------------------------------------------------------------
# 2. Multi-format Ingestion (CSV, JSON, Code, DOCX, XLSX, PPTX, Images)
# ---------------------------------------------------------------------------

def _create_minimal_docx(path: Path, text: str) -> Path:
    xml_content = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", xml_content)
    return path


def _create_minimal_xlsx(path: Path, cell_text: str) -> Path:
    shared_strings = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<si><t>{cell_text}</t></si></sst>"
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData><row><c t=\"s\"><v>0</v></c></row></sheetData></worksheet>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", shared_strings)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return path


def _create_minimal_pptx(path: Path, slide_text: str) -> Path:
    slide_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
        'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
        f"<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>{slide_text}</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld>"
        "</p:sld>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", slide_xml)
    return path


class TestExtendedIngestion:
    def test_csv_and_json_ingestion(self, tmp_path: Path):
        csv_p = tmp_path / "sales_q3.csv"
        csv_p.write_text("region,revenue\nNorth,50000\n", encoding="utf-8")
        doc_csv = ingest_file(csv_p)
        assert doc_csv.extraction_status == "ok"
        assert "revenue" in doc_csv.text

        json_p = tmp_path / "config.json"
        json_p.write_text('{"project": "FileMind"}', encoding="utf-8")
        doc_json = ingest_file(json_p)
        assert doc_json.extraction_status == "ok"
        assert "FileMind" in doc_json.text

    def test_docx_ingestion(self, tmp_path: Path):
        docx_p = _create_minimal_docx(tmp_path / "offer.docx", "Employment Offer Letter Northwind")
        doc = ingest_file(docx_p)
        assert doc.extraction_status == "ok"
        assert "Employment Offer Letter" in doc.text

    def test_xlsx_ingestion(self, tmp_path: Path):
        xlsx_p = _create_minimal_xlsx(tmp_path / "q3_report.xlsx", "Quarterly Sales Revenue")
        doc = ingest_file(xlsx_p)
        assert doc.extraction_status == "ok"
        assert "Quarterly Sales Revenue" in doc.text

    def test_pptx_ingestion(self, tmp_path: Path):
        pptx_p = _create_minimal_pptx(tmp_path / "pitch.pptx", "Gemma 4 Local Privacy Agent")
        doc = ingest_file(pptx_p)
        assert doc.extraction_status == "ok"
        assert "Gemma 4 Local Privacy Agent" in doc.text


# ---------------------------------------------------------------------------
# 3. End-to-End Pipeline & FastAPI Endpoints
# ---------------------------------------------------------------------------

class TestPipelineAndApi:
    @pytest.fixture()
    def pipeline_env(self, tmp_path: Path):
        watched = tmp_path / "Downloads"
        organized = tmp_path / "FileMind"
        db_file = tmp_path / "test_filemind.db"
        watched.mkdir()
        organized.mkdir()

        db = FileMindDatabase(db_path=db_file)
        pipeline = FileMindPipeline(db=db, watched_dir=watched, organized_dir=organized)
        app = create_app(pipeline=pipeline, enable_watcher=False)
        client = TestClient(app)
        return watched, organized, pipeline, client

    def test_full_pipeline_and_rest_api_flow(self, pipeline_env):
        watched, organized, pipeline, client = pipeline_env

        # 1. Health & status
        res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

        # 2. Drop a high-confidence file (fouriertransforms.pdf)
        f1 = watched / "fouriertransforms.pdf"
        import pymupdf
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Lecture Notes: Fourier Transforms and Frequency Domain Mathematics")
        doc.save(str(f1))
        doc.close()

        scan_res = client.post("/api/scan", json={"path": str(f1)})
        assert scan_res.status_code == 200
        processed = scan_res.json()["processed"]
        assert len(processed) == 1
        rec1 = processed[0]
        assert rec1["status"] == "organized"
        assert rec1["category"] == ["Academic", "Mathematics"]
        assert not f1.exists()
        assert Path(rec1["currentPath"]).exists()

        # 3. Search endpoint finds the file by semantic topic / text
        search_res = client.get("/api/search", params={"q": "Fourier"})
        assert search_res.status_code == 200
        results = search_res.json()["results"]
        assert len(results) == 1
        assert "Academic" in results[0]["category"]

        # 4. Undo endpoint restores the file to watched directory
        undo_res = client.post(f"/api/undo/{rec1['id']}")
        assert undo_res.status_code == 200
        assert f1.exists()

        # 5. Accept review item with custom category & filename edit
        accept_res = client.post(
            f"/api/review/{rec1['id']}/accept",
            json={
                "category": "Academic",
                "subcategory": "Signal Processing",
                "suggested_filename": "Fourier_Signal_Notes.pdf",
            },
        )
        assert accept_res.status_code == 200
        updated = accept_res.json()["file"]
        assert updated["status"] == "organized"
        assert updated["category"] == ["Academic", "Signal Processing"]
        assert updated["suggested"] == "Fourier_Signal_Notes.pdf"
        assert (organized / "Academic" / "Signal Processing" / "Fourier_Signal_Notes.pdf").exists()

        # 6. Dashboard & Activity endpoints
        dash_res = client.get("/api/dashboard")
        assert dash_res.status_code == 200
        assert dash_res.json()["organizedCount"] >= 1

        act_res = client.get("/api/activity")
        assert act_res.status_code == 200
        assert len(act_res.json()["auditLog"]) >= 1
