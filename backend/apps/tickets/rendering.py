"""QR images and PDF tickets."""

from io import BytesIO

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.utils import timezone
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

BRAND = colors.HexColor("#0F766E")


def format_when(event) -> str:
    """e.g. 'Sat 15 Nov 2026, 7:00 PM'"""
    start = timezone.localtime(event.start_at)
    return start.strftime("%a %d %b %Y, ") + start.strftime("%I:%M %p").lstrip("0")


def format_where(event) -> str:
    if event.venue:
        return f"{event.venue.name}, {event.venue.city}"
    return "Online event"


def qr_svg(payload: str) -> str:
    """Inline SVG (a few KB, crisp at any size; good for slow networks)."""
    img = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    return img.to_string(encoding="unicode")


def qr_png(payload: str) -> bytes:
    buf = BytesIO()
    qrcode.make(payload, box_size=10, border=2).save(buf, format="PNG")
    return buf.getvalue()


PAGE = (100 * mm, 165 * mm)


def tickets_pdf(tickets) -> bytes:
    """One page per ticket, sized to read well on a phone or print."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE)
    w, h = PAGE
    m = 7 * mm
    for t in tickets:
        ev = t.event
        c.setFillColor(BRAND)
        c.rect(0, h - 16 * mm, w, 16 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(m, h - 10.5 * mm, settings.PLATFORM_NAME)
        c.setFont("Helvetica", 9)
        c.drawRightString(w - m, h - 10.5 * mm, f"Order {t.order.reference}")

        y = h - 25 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 15)
        for line in simpleSplit(ev.title, "Helvetica-Bold", 15, w - 2 * m)[:3]:
            c.drawString(m, y, line)
            y -= 6.5 * mm
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.HexColor("#3f3f46"))
        c.drawString(m, y, format_when(ev))
        y -= 5 * mm
        for line in simpleSplit(format_where(ev), "Helvetica", 10, w - 2 * m)[:2]:
            c.drawString(m, y, line)
            y -= 5 * mm

        y -= 2 * mm
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 11)
        admits = f"  (admits {t.ticket_type.admits})" if t.ticket_type.admits > 1 else ""
        c.drawString(m, y, f"{t.ticket_type.name}{admits}")
        y -= 5 * mm
        c.setFont("Helvetica", 10)
        if t.attendee_name:
            c.drawString(m, y, t.attendee_name)

        size = 62 * mm
        qr = QrCodeWidget(t.qr_payload, barLevel="M")
        x1, y1, x2, y2 = qr.getBounds()
        d = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
        d.add(qr)
        renderPDF.draw(d, c, (w - size) / 2, 24 * mm)

        c.setFont("Courier-Bold", 14)
        c.drawCentredString(w / 2, 18 * mm, t.code)
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.HexColor("#71717a"))
        c.drawCentredString(w / 2, 11 * mm, "Show this QR code at the entrance. Don't share it:")
        c.drawCentredString(w / 2, 7.5 * mm, "the first scan gets in.")
        if not t.qr_active:
            c.setFillColor(colors.HexColor("#dc2626"))
            c.setFont("Helvetica-Bold", 28)
            c.saveState()
            c.translate(w / 2, h / 2)
            c.rotate(30)
            c.drawCentredString(0, 0, t.get_status_display().split(" ")[0].upper())
            c.restoreState()
        c.showPage()
    c.save()
    return buf.getvalue()
