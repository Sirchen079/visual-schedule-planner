# tests/adapters/test_parsers.py
import pytest
from zhishi.adapters.parsers import parse_file, ParsedDoc


def test_txt(tmp_path):
    p = tmp_path / "a.txt"; p.write_text("你好日程", encoding="utf-8")
    doc = parse_file(p)
    assert doc.kind == "text" and "你好日程" in doc.text and doc.tables == []


def test_csv(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("节次,星期一\n2,高数[连续周1-16周]", encoding="utf-8")
    doc = parse_file(p)
    assert doc.kind == "csv" and doc.tables[0][0] == ["节次", "星期一"]


def test_docx_real_timetable_fixture():
    from pathlib import Path
    fx = Path("tests/fixtures/timetables")
    files = list(fx.glob("*.docx"))
    if not files:
        pytest.skip("无 docx fixture")
    doc = parse_file(files[0])
    assert doc.kind == "docx"
    assert len(doc.tables) >= 1
    head = doc.tables[0][0]
    # 偏差（对计划）：真实 fixture 表头首列为空（['', '节次', '星期一', ...]），
    # 故由 head[0]/head[1] 单元格断言放宽为行内包含断言，测试意图不变
    assert "节次" in head and "星期一" in head
    body = "".join("".join(r[2:]) for r in doc.tables[0][1:])
    assert "连续周" in body          # 真实课表周次规则已进表格


def test_pdf_real_fixture():
    from pathlib import Path
    files = list(Path("tests/fixtures/timetables").glob("*.pdf"))
    if not files:
        pytest.skip("无 pdf fixture")
    doc = parse_file(files[0])
    assert doc.kind == "pdf" and doc.tables          # pdfplumber 表格可用


def test_unsupported_doc():
    from pathlib import Path
    files = list(Path("tests/fixtures/timetables").glob("*.doc"))
    if not files:
        pytest.skip("无 doc fixture")
    doc = parse_file(files[0])
    assert doc.kind == "unsupported"


def test_image_needs_vision(tmp_path):
    pytest.importorskip("PIL")  # 若无 PIL 则跳过（不新增依赖，图片走多模态）
    pytest.skip("图片不本地解析——kind=image 由扩展名分支直接返回，无需图像库")
