from docx import Document
from io import BytesIO

from jobfinder.resume_parser import parse_resume


def make_docx():
    doc = Document()
    doc.add_paragraph("Marina da Silva")
    doc.add_paragraph("marina@example.com | (11) 91234-5678")
    doc.add_paragraph("FORMAÇÃO ACADÊMICA")
    doc.add_paragraph("Análise e Desenvolvimento de Sistemas")
    doc.add_paragraph("HABILIDADES TÉCNICAS")
    doc.add_paragraph("Python, JavaScript, React e SQL")
    doc.add_paragraph("EXPERIÊNCIA PROFISSIONAL")
    doc.add_paragraph("Estágio de suporte técnico - Empresa Exemplo")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


def test_parse_docx_extracts_profile_suggestions():
    parsed = parse_resume(make_docx(), "curriculo.docx")
    assert parsed["name"] == "Marina da Silva"
    assert "Python" in parsed["technologies"]
    assert "Análise e Desenvolvimento" in parsed["course"]
    assert "Estágio de suporte" in parsed["experience"]


def test_rejects_unsupported_format():
    try:
        parse_resume(b"texto qualquer", "curriculo.txt")
    except ValueError as exc:
        assert "PDF ou DOCX" in str(exc)
    else:
        raise AssertionError("Formato não suportado deveria ser rejeitado")
