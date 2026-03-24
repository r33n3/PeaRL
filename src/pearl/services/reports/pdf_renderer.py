"""PDF renderer for PeaRL reports using Jinja2 + WeasyPrint."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent / "templates"


def render_report_pdf(report_data: dict) -> bytes:
    """Render report dict to PDF bytes using PeaRL HTML template."""
    weasyprint = _get_weasyprint()
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html.jinja2")
    html = template.render(**report_data)
    pdf_bytes = weasyprint.HTML(string=html).write_pdf()
    return pdf_bytes


def _get_weasyprint():
    """Import weasyprint lazily so missing install raises ImportError at call time."""
    try:
        import weasyprint
        return weasyprint
    except ImportError as exc:
        raise ImportError(
            "weasyprint is required for PDF export. "
            "Install it with: pip install 'weasyprint>=60.0'"
        ) from exc
