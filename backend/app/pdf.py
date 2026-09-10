"""Fatura PDF uretimi (Phase 7).

Turkce karakter notu: reportlab'in varsayilan Helvetica fontu Latin-1 oldugu
icin c/s/g/i gibi harfleri bozar. Bu yuzden reportlab ile birlikte gelen
Vera (Bitstream Vera Sans) TTF fontu gomuluyor - tum Turkce karakterleri
icerdigi dogrulandi ve ekstra bir dosyaya ihtiyac duymuyor.
"""
from decimal import Decimal
import os
from datetime import timedelta
from io import BytesIO

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

COMPANY_NAME = 'ERP Demo Sirketi'
COMPANY_INFO = 'Ornek Mah. Demo Cad. No:1, Istanbul  |  info@erpdemo.com  |  0212 000 00 00'

FONT_REGULAR = 'DejaVuLike'
FONT_BOLD = 'DejaVuLike-Bold'

INDIGO = colors.HexColor('#4f46e5')
GRAY_TEXT = colors.HexColor('#4b5563')
GRAY_LINE = colors.HexColor('#e5e7eb')
GRAY_BG = colors.HexColor('#f9fafb')

STATUS_LABELS = {'draft': 'Taslak', 'issued': 'Kesildi', 'paid': 'Odendi'}

_fonts_ready = False


def _ensure_fonts():
    """Turkce karakterleri destekleyen fontu bir kez kaydeder."""
    global _fonts_ready
    if _fonts_ready:
        return
    fonts_dir = os.path.join(os.path.dirname(reportlab.__file__), 'fonts')
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, os.path.join(fonts_dir, 'Vera.ttf')))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, os.path.join(fonts_dir, 'VeraBd.ttf')))
    _fonts_ready = True


def _money(value) -> str:
    """1234.5 -> '1.234,50 TL' (Turkce bicim)"""
    n = Decimal(str(value or 0)).quantize(Decimal('0.01'))
    whole, frac = f'{n:,.2f}'.split('.')
    return f"{whole.replace(',', '.')},{frac} TL"


def _date(value) -> str:
    return value.strftime('%d.%m.%Y') if value else '-'


def build_invoice_pdf(invoice, sale, customer, items, tax_days=30) -> bytes:
    """Fatura PDF'ini olusturur ve bytes olarak doner.

    items: [{'name', 'sku', 'quantity', 'unit_price', 'total_price'}, ...]
    """
    _ensure_fonts()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=f'Fatura {invoice.invoice_number}',
        author=COMPANY_NAME,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
    )

    base = getSampleStyleSheet()['Normal']
    normal = ParagraphStyle('n', parent=base, fontName=FONT_REGULAR, fontSize=9, leading=12)
    small = ParagraphStyle('s', parent=normal, fontSize=7.5, textColor=GRAY_TEXT)
    # SKU'lar tire iceren uzun kodlar olabiliyor; wordWrap='CJK' karakter bazinda
    # sardigi icin kod kesilmeden alt satira iniyor.
    sku_style = ParagraphStyle('sku', parent=normal, fontSize=7.5, leading=9, wordWrap='CJK')
    title = ParagraphStyle('t', parent=normal, fontName=FONT_BOLD, fontSize=18,
                           textColor=INDIGO, leading=22)
    heading = ParagraphStyle('h', parent=normal, fontName=FONT_BOLD, fontSize=9.5)
    right = ParagraphStyle('r', parent=normal, alignment=TA_RIGHT)

    story = []

    # --- Baslik: sirket solda, FATURA sagda ---
    due_date = invoice.issued_date + timedelta(days=tax_days) if invoice.issued_date else None
    header = Table(
        [[
            Paragraph(f'<b>{COMPANY_NAME}</b><br/><font size="7.5" color="#4b5563">'
                      f'{COMPANY_INFO}</font>', normal),
            Paragraph('FATURA', ParagraphStyle('tr', parent=title, alignment=TA_RIGHT)),
        ]],
        colWidths=[110 * mm, 64 * mm],
    )
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 4 * mm))

    # --- Fatura bilgisi + musteri, yan yana ---
    invoice_rows = [
        ['Fatura No', invoice.invoice_number or '-'],
        ['Kesim Tarihi', _date(invoice.issued_date)],
        ['Vade Tarihi', _date(due_date)],
        ['Satis No', f'#{invoice.sale_id}' if invoice.sale_id else '-'],
        ['Durum', STATUS_LABELS.get(invoice.status, invoice.status or '-')],
    ]
    info_table = Table(invoice_rows, colWidths=[24 * mm, 50 * mm])
    info_table.setStyle(TableStyle([
        ('FONT', (0, 0), (0, -1), FONT_REGULAR, 8),
        ('FONT', (1, 0), (1, -1), FONT_BOLD, 8),
        ('TEXTCOLOR', (0, 0), (0, -1), GRAY_TEXT),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))

    customer_lines = [f'<b>{customer.name}</b>' if customer else '<b>-</b>']
    if customer and customer.email:
        customer_lines.append(customer.email)
    if customer and customer.phone:
        customer_lines.append(customer.phone)
    customer_block = [
        Paragraph('SAYIN', small),
        Spacer(1, 1.5 * mm),
        Paragraph('<br/>'.join(customer_lines), normal),
    ]

    two_col = Table([[info_table, customer_block]], colWidths=[86 * mm, 88 * mm])
    two_col.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (0, 0), 0),
        ('BOX', (1, 0), (1, 0), 0.5, GRAY_LINE),
        ('BACKGROUND', (1, 0), (1, 0), GRAY_BG),
        ('LEFTPADDING', (1, 0), (1, 0), 6),
        ('RIGHTPADDING', (1, 0), (1, 0), 6),
        ('TOPPADDING', (1, 0), (1, 0), 6),
        ('BOTTOMPADDING', (1, 0), (1, 0), 6),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 6 * mm))

    # --- Urun tablosu (uzun listede otomatik sayfa boler) ---
    table_data = [['#', 'Urun', 'SKU', 'Miktar', 'Birim Fiyat', 'Tutar']]
    for i, item in enumerate(items, start=1):
        table_data.append([
            str(i),
            Paragraph(str(item['name']), normal),
            Paragraph(str(item['sku'] or '-'), sku_style),
            str(item['quantity']),
            _money(item['unit_price']),
            _money(item['total_price']),
        ])

    products = Table(
        table_data,
        colWidths=[8 * mm, 54 * mm, 40 * mm, 16 * mm, 28 * mm, 28 * mm],
        repeatRows=1,
    )
    products.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), INDIGO),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONT', (0, 0), (-1, 0), FONT_BOLD, 8.5),
        ('FONT', (0, 1), (-1, -1), FONT_REGULAR, 8.5),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, GRAY_LINE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, GRAY_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(products)
    story.append(Spacer(1, 4 * mm))

    # --- Toplamlar ---
    subtotal = Decimal(str(sale.total_amount or 0))
    grand_total = Decimal(str(invoice.total_amount or 0))
    tax_amount = (grand_total - subtotal).quantize(Decimal('0.01'))
    tax_rate = int((tax_amount / subtotal * 100).to_integral_value()) if subtotal else 0

    totals = Table(
        [
            ['Ara Toplam', _money(subtotal)],
            [f'KDV (%{tax_rate})', _money(tax_amount)],
            ['GENEL TOPLAM', _money(grand_total)],
        ],
        colWidths=[38 * mm, 36 * mm],
        hAlign='RIGHT',
    )
    totals.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 1), FONT_REGULAR, 9),
        ('FONT', (0, 2), (-1, 2), FONT_BOLD, 10),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 2), (-1, 2), 0.8, INDIGO),
        ('TEXTCOLOR', (0, 2), (-1, 2), INDIGO),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(totals)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(
        'Bu belge ERP Demo sistemi tarafindan olusturulmustur. '
        f'Odeme durumu: <b>{STATUS_LABELS.get(invoice.status, invoice.status)}</b>.',
        small))

    doc.build(story)
    return buffer.getvalue()
