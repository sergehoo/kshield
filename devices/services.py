"""KAYDAN SHIELD — Services badges + casques.

Fournit la génération de PDF de badge (3 designs) et l'attribution /
réassignation d'un badge à un porteur.

Designs :
- employee_rfid → fond clair, logo filiale en haut, photo dans cercle orange,
                  nom + rôle + matricule, QR code en bas.  (1 page)
- worker_rfid   → fond navy, logo KAYDAN, gros QR central, "OUVRIER" en bas,
                  + verso avec QR + description groupe.   (2 pages recto-verso)
- visitor_qr    → fond jaune KAYDAN, gros QR central, code visite, "VISITEUR"
                  en bas, + verso identique au worker.    (2 pages recto-verso)

Format : portrait 60 × 95 mm — taille d'impression standard pour badge tour
de cou (compatible holders 64 × 100 mm).

Dépendances : reportlab + qrcode + Pillow.
"""
from __future__ import annotations

import io
import logging
import secrets
from typing import TYPE_CHECKING, Optional

from django.core.files.base import ContentFile
from django.utils import timezone

if TYPE_CHECKING:
    from .models import Badge

log = logging.getLogger(__name__)


# ===========================================================================
# Génération PDF
# ===========================================================================
class BadgePDFService:
    """Génère un PDF imprimable au format badge portrait avec QR code."""

    CARD_WIDTH_MM = 60.0
    CARD_HEIGHT_MM = 95.0

    # Palette KAYDAN
    NAVY = "#0B1B33"
    NAVY_DEEP = "#06122A"
    ORANGE = "#F26B1F"
    ORANGE_DARK = "#C4541A"
    YELLOW = "#FFC72C"
    YELLOW_DARK = "#E8A800"
    DARK = "#1A1A1A"
    LIGHT_GREY = "#F5F5F5"
    MID_GREY = "#9AAACB"

    @classmethod
    def generate(cls, badge) -> bytes:
        """Retourne les bytes du PDF (1 ou 2 pages selon la catégorie)."""
        try:
            from reportlab.lib.units import mm
            from reportlab.pdfgen import canvas
        except ImportError:
            raise RuntimeError("reportlab non installé — pip install reportlab")

        page_w = cls.CARD_WIDTH_MM * mm
        page_h = cls.CARD_HEIGHT_MM * mm

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_w, page_h))

        if badge.category == "employee_rfid":
            cls._render_employee_front(c, badge, page_w, page_h, mm)
        elif badge.category == "worker_rfid":
            cls._render_worker_front(c, badge, page_w, page_h, mm)
            c.showPage()
            cls._render_kaydan_back(c, badge, page_w, page_h, mm,
                                     bg_color=cls.NAVY)
        elif badge.category == "visitor_qr":
            cls._render_visitor_front(c, badge, page_w, page_h, mm)
            c.showPage()
            cls._render_kaydan_back(c, badge, page_w, page_h, mm,
                                     bg_color=cls.YELLOW)
        else:
            cls._render_employee_front(c, badge, page_w, page_h, mm)

        c.showPage()
        c.save()
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _make_qr_bytes(payload: str, box_size: int = 4):
        import qrcode
        from qrcode.image.pil import PilImage
        qr = qrcode.QRCode(
            version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size, border=1,
        )
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(image_factory=PilImage,
                            fill_color="#000000", back_color="#FFFFFF")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    @staticmethod
    def _draw_qr_card(c, x, y, size_mm, payload, mm,
                      bg_color="#FFFFFF", padding=1.5):
        from reportlab.lib.colors import HexColor
        from reportlab.lib.utils import ImageReader

        size = size_mm * mm
        pad = padding * mm
        c.setFillColor(HexColor(bg_color))
        c.roundRect(x, y, size, size, 1.5 * mm, fill=1, stroke=0)
        qr_buf = BadgePDFService._make_qr_bytes(payload, box_size=8)
        c.drawImage(ImageReader(qr_buf),
                    x + pad, y + pad,
                    size - 2 * pad, size - 2 * pad,
                    mask="auto")

    @staticmethod
    def _draw_circular_photo(c, photo, cx, cy, radius, mm,
                              ring_color="#F26B1F", ring_width=1.2):
        from reportlab.lib.colors import HexColor
        from reportlab.lib.utils import ImageReader

        if not photo or not getattr(photo, "name", ""):
            return False
        try:
            c.saveState()
            p = c.beginPath()
            p.circle(cx, cy, radius)
            c.clipPath(p, stroke=0, fill=0)
            c.drawImage(ImageReader(photo.path),
                        cx - radius * 1.1, cy - radius * 1.1,
                        radius * 2.2, radius * 2.2,
                        mask="auto", preserveAspectRatio=True, anchor="c")
            c.restoreState()
            c.setStrokeColor(HexColor(ring_color))
            c.setLineWidth(ring_width * mm)
            c.circle(cx, cy, radius, stroke=1, fill=0)
            return True
        except Exception as e:
            log.warning("Photo draw failed: %s", e)
            return False

    @staticmethod
    def _draw_kaydan_logo_text(c, cx_mm, cy_mm, mm, color="#1A1A1A",
                                 width_mm=22, sub=True):
        from reportlab.lib.colors import HexColor

        c.setFillColor(HexColor(color))
        c.setFont("Helvetica-Bold", 13)
        text = "KAYDAN"
        text_w = c.stringWidth(text, "Helvetica-Bold", 13)
        c.drawString(cx_mm * mm - text_w / 2, cy_mm * mm, text)

        c.setStrokeColor(HexColor("#F26B1F"))
        c.setLineWidth(0.5 * mm)
        bx = cx_mm * mm + text_w / 2 + 0.5 * mm
        by = cy_mm * mm + 4.5 * mm
        c.line(bx, by, bx + 1.5 * mm, by)
        c.line(bx + 1.5 * mm, by, bx + 1.5 * mm, by - 1.5 * mm)

        if sub:
            c.setFillColor(HexColor("#666666"))
            c.setFont("Helvetica", 5.5)
            sub_w = c.stringWidth("GROUPE", "Helvetica", 5.5)
            c.drawString(cx_mm * mm - sub_w / 2, cy_mm * mm - 3 * mm, "GROUPE")

    # ------------------------------------------------------------------
    # Design 1 — Employé / Filiale
    # ------------------------------------------------------------------
    @classmethod
    def _render_employee_front(cls, c, badge, page_w, page_h, mm):
        from reportlab.lib.colors import HexColor
        from reportlab.lib.utils import ImageReader

        c.setFillColor(HexColor(cls.LIGHT_GREY))
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        logo_y = page_h - 18 * mm
        holder = badge.holder
        company = getattr(holder, "company", None)
        company_logo = getattr(company, "logo", None) if company else None

        if company_logo and company_logo.name:
            try:
                c.drawImage(ImageReader(company_logo.path),
                            (page_w - 30 * mm) / 2, logo_y - 5 * mm,
                            30 * mm, 14 * mm,
                            mask="auto", preserveAspectRatio=True)
            except Exception:
                cls._draw_kaydan_logo_text(c, cls.CARD_WIDTH_MM / 2,
                                             cls.CARD_HEIGHT_MM - 14, mm)
        elif company:
            c.setFillColor(HexColor(cls.DARK))
            c.setFont("Helvetica-Bold", 14)
            name = company.name.upper()
            name_w = c.stringWidth(name, "Helvetica-Bold", 14)
            c.drawString((page_w - name_w) / 2, logo_y - 1 * mm, name)
            if company.sector:
                c.setFillColor(HexColor("#666666"))
                c.setFont("Helvetica", 6)
                sec = dict(company.SECTOR_CHOICES).get(company.sector, "").upper()
                sw = c.stringWidth(sec, "Helvetica", 6)
                c.drawString((page_w - sw) / 2, logo_y - 5 * mm, sec)
        else:
            cls._draw_kaydan_logo_text(c, cls.CARD_WIDTH_MM / 2,
                                         cls.CARD_HEIGHT_MM - 14, mm)

        # Bandeau orange double derrière la photo
        band_y = page_h * 0.55
        c.setFillColor(HexColor(cls.ORANGE))
        c.rect(0, band_y - 0.6 * mm, page_w, 1.2 * mm, fill=1, stroke=0)
        c.rect(0, band_y + 5 * mm, page_w, 1.2 * mm, fill=1, stroke=0)

        # Photo dans cercle orange
        photo_radius = 13 * mm
        photo_cx = page_w / 2
        photo_cy = band_y + 2 * mm
        photo_drawn = False
        if holder:
            photo = getattr(holder, "photo", None)
            photo_drawn = cls._draw_circular_photo(
                c, photo, photo_cx, photo_cy, photo_radius, mm,
                ring_color=cls.ORANGE, ring_width=1.4,
            )
        if not photo_drawn:
            c.setFillColor(HexColor("#E5E7EB"))
            c.circle(photo_cx, photo_cy, photo_radius, fill=1, stroke=0)
            c.setStrokeColor(HexColor(cls.ORANGE))
            c.setLineWidth(1.4 * mm)
            c.circle(photo_cx, photo_cy, photo_radius, fill=0, stroke=1)
            initials = ""
            if holder:
                initials = ((getattr(holder, 'first_name', '') or ' ')[0]
                            + (getattr(holder, 'last_name', '') or ' ')[0]).upper()
            c.setFillColor(HexColor("#9CA3AF"))
            c.setFont("Helvetica-Bold", 14)
            iw = c.stringWidth(initials, "Helvetica-Bold", 14)
            c.drawString(photo_cx - iw / 2, photo_cy - 5, initials)

        first_name = getattr(holder, "first_name", "") if holder else ""
        last_name = getattr(holder, "last_name", "") if holder else ""

        name_y = band_y - 13 * mm
        c.setFont("Helvetica-Bold", 11)
        first_w = c.stringWidth(first_name, "Helvetica-Bold", 11)
        last_w = c.stringWidth(last_name.upper(), "Helvetica-Bold", 11)
        total_w = first_w + 2 * mm + last_w
        x_start = (page_w - total_w) / 2
        c.setFillColor(HexColor(cls.DARK))
        c.drawString(x_start, name_y, first_name)
        c.setFillColor(HexColor(cls.ORANGE))
        c.drawString(x_start + first_w + 2 * mm, name_y, last_name.upper())

        position = ""
        if holder:
            pos_obj = getattr(holder, "position", None)
            position = getattr(pos_obj, "title", "") if pos_obj else ""
            if not position:
                trade = getattr(holder, "trade", None)
                position = getattr(trade, "name", "") if trade else ""
        position = position or "Employé"

        role_y = name_y - 5 * mm
        c.setFillColor(HexColor("#444444"))
        c.setFont("Helvetica", 7.5)
        role_w = c.stringWidth(position, "Helvetica", 7.5)
        c.drawString((page_w - role_w) / 2, role_y, position)
        c.setStrokeColor(HexColor("#9CA3AF"))
        c.setLineWidth(0.3)
        line_pad = 2 * mm
        c.line(8 * mm, role_y + 1 * mm,
               (page_w - role_w) / 2 - line_pad, role_y + 1 * mm)
        c.line((page_w + role_w) / 2 + line_pad, role_y + 1 * mm,
               page_w - 8 * mm, role_y + 1 * mm)

        matricule = getattr(holder, "matricule", "") if holder else ""

        mat_label_y = role_y - 8 * mm
        c.setFillColor(HexColor(cls.ORANGE))
        c.setFont("Helvetica-Bold", 6)
        c.drawString(8 * mm, mat_label_y, "Matricule")

        box_y = mat_label_y - 5 * mm
        c.setFillColor(HexColor(cls.ORANGE))
        c.roundRect(8 * mm, box_y - 1 * mm, page_w - 16 * mm, 5 * mm,
                    1 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 9)
        m_w = c.stringWidth(matricule or "—", "Helvetica-Bold", 9)
        c.drawString((page_w - m_w) / 2, box_y + 0.5 * mm, matricule or "—")

        info_y = box_y - 7 * mm
        hired = getattr(holder, "hired_at", None) if holder else None
        phone = getattr(holder, "phone", "") if holder else ""

        c.setFillColor(HexColor(cls.DARK))
        c.setFont("Helvetica-Bold", 7)
        if hired:
            txt = f"Date début : {hired.strftime('%d/%m/%Y')}"
            tw = c.stringWidth(txt, "Helvetica-Bold", 7)
            c.drawString((page_w - tw) / 2, info_y, txt)
        if phone:
            txt2 = f"Tél : {phone}"
            tw2 = c.stringWidth(txt2, "Helvetica-Bold", 7)
            c.drawString((page_w - tw2) / 2, info_y - 4 * mm, txt2)

        qr_size_mm = 18
        qr_x = (page_w - qr_size_mm * mm) / 2
        qr_y = 5 * mm
        cls._draw_qr_card(c, qr_x, qr_y, qr_size_mm,
                           badge.qr_payload or badge.uid, mm)

    # ------------------------------------------------------------------
    # Design 2 — Ouvrier (KAYDAN navy, 2 pages)
    # ------------------------------------------------------------------
    @classmethod
    def _render_worker_front(cls, c, badge, page_w, page_h, mm):
        from reportlab.lib.colors import HexColor

        c.setFillColor(HexColor(cls.NAVY))
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        c.setFillColor(HexColor("#FFFFFF"))
        c.rect(0, page_h - 22 * mm, page_w, 22 * mm, fill=1, stroke=0)
        cls._draw_kaydan_logo_text(c, cls.CARD_WIDTH_MM / 2,
                                     cls.CARD_HEIGHT_MM - 13, mm,
                                     color=cls.DARK)

        qr_band_y = page_h - 50 * mm
        c.setFillColor(HexColor(cls.ORANGE))
        c.rect(0, qr_band_y + 3 * mm, page_w, 1 * mm, fill=1, stroke=0)
        c.rect(0, qr_band_y - 4 * mm, page_w, 1 * mm, fill=1, stroke=0)

        qr_size_mm = 28
        qr_x = (page_w - qr_size_mm * mm) / 2
        qr_y = page_h - 22 * mm - qr_size_mm * mm
        cls._draw_qr_card(c, qr_x, qr_y, qr_size_mm,
                           badge.qr_payload or badge.uid, mm)

        holder = badge.holder
        first = getattr(holder, "first_name", "") if holder else ""
        last = getattr(holder, "last_name", "") if holder else ""

        name_y = page_h - 60 * mm
        c.setFont("Helvetica-Bold", 11)
        first_w = c.stringWidth(first, "Helvetica-Bold", 11)
        last_w = c.stringWidth(last.upper(), "Helvetica-Bold", 11)
        total_w = first_w + 2 * mm + last_w
        x = (page_w - total_w) / 2
        c.setFillColor(HexColor("#FFFFFF"))
        c.drawString(x, name_y, first)
        c.drawString(x + first_w + 2 * mm, name_y, last.upper())

        trade = getattr(holder, "trade", None) if holder else None
        position = getattr(trade, "name", "") if trade else "Ouvrier"

        role_y = name_y - 5 * mm
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 7.5)
        role_w = c.stringWidth(position, "Helvetica-Bold", 7.5)
        c.drawString((page_w - role_w) / 2, role_y, position)
        c.setStrokeColor(HexColor("#FFFFFF"))
        c.setLineWidth(0.3)
        c.line(8 * mm, role_y + 1 * mm,
               (page_w - role_w) / 2 - 2 * mm, role_y + 1 * mm)
        c.line((page_w + role_w) / 2 + 2 * mm, role_y + 1 * mm,
               page_w - 8 * mm, role_y + 1 * mm)

        matricule = getattr(holder, "matricule", "") if holder else ""
        mat_label_y = role_y - 8 * mm
        c.setFillColor(HexColor(cls.ORANGE))
        c.setFont("Helvetica-Bold", 6)
        c.drawString(8 * mm, mat_label_y, "Matricule")
        box_y = mat_label_y - 5 * mm
        c.setFillColor(HexColor(cls.ORANGE))
        c.roundRect(8 * mm, box_y - 1 * mm, page_w - 16 * mm, 5 * mm,
                    1 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 9)
        m_w = c.stringWidth(matricule or "—", "Helvetica-Bold", 9)
        c.drawString((page_w - m_w) / 2, box_y + 0.5 * mm, matricule or "—")

        info_y = box_y - 7 * mm
        hired = (getattr(holder, "hired_at", None)
                 or getattr(holder, "created_at", None)) if holder else None
        phone = getattr(holder, "phone", "") if holder else ""
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 7)
        if hired:
            txt = f"Date début : {hired.strftime('%d/%m/%Y')}"
            tw = c.stringWidth(txt, "Helvetica-Bold", 7)
            c.drawString((page_w - tw) / 2, info_y, txt)
        if phone:
            txt2 = f"Tél : {phone}"
            tw2 = c.stringWidth(txt2, "Helvetica-Bold", 7)
            c.drawString((page_w - tw2) / 2, info_y - 4 * mm, txt2)

        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(page_w - 5 * mm, 4 * mm, "OUVRIER")

    # ------------------------------------------------------------------
    # Design 3 — Visiteur (jaune)
    # ------------------------------------------------------------------
    @classmethod
    def _render_visitor_front(cls, c, badge, page_w, page_h, mm):
        from reportlab.lib.colors import HexColor

        c.setFillColor(HexColor(cls.YELLOW))
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        cls._draw_kaydan_logo_text(c, cls.CARD_WIDTH_MM / 2,
                                     cls.CARD_HEIGHT_MM - 13, mm,
                                     color=cls.DARK)

        qr_band_y = page_h - 50 * mm
        c.setFillColor(HexColor("#000000"))
        c.rect(0, qr_band_y + 3 * mm, page_w, 1 * mm, fill=1, stroke=0)
        c.rect(0, qr_band_y - 4 * mm, page_w, 1 * mm, fill=1, stroke=0)

        qr_size_mm = 28
        qr_x = (page_w - qr_size_mm * mm) / 2
        qr_y = page_h - 22 * mm - qr_size_mm * mm
        cls._draw_qr_card(c, qr_x, qr_y, qr_size_mm,
                           badge.qr_payload or badge.uid, mm)

        holder = badge.holder
        first = getattr(holder, "first_name", "") if holder else ""
        last = getattr(holder, "last_name", "") if holder else ""

        name_y = page_h - 60 * mm
        if first or last:
            c.setFillColor(HexColor(cls.DARK))
            c.setFont("Helvetica-Bold", 11)
            full_name = f"{first} {last.upper()}".strip()
            n_w = c.stringWidth(full_name, "Helvetica-Bold", 11)
            c.drawString((page_w - n_w) / 2, name_y, full_name)
        else:
            c.setFillColor(HexColor(cls.DARK))
            c.setFont("Helvetica-Bold", 11)
            label = "VISITEUR"
            n_w = c.stringWidth(label, "Helvetica-Bold", 11)
            c.drawString((page_w - n_w) / 2, name_y, label)

        visit_kind = "PARTENAIRE"
        role_y = name_y - 5 * mm
        c.setFillColor(HexColor(cls.DARK))
        c.setFont("Helvetica-Bold", 7.5)
        role_w = c.stringWidth(visit_kind, "Helvetica-Bold", 7.5)
        c.drawString((page_w - role_w) / 2, role_y, visit_kind)
        c.setStrokeColor(HexColor(cls.DARK))
        c.setLineWidth(0.3)
        c.line(8 * mm, role_y + 1 * mm,
               (page_w - role_w) / 2 - 2 * mm, role_y + 1 * mm)
        c.line((page_w + role_w) / 2 + 2 * mm, role_y + 1 * mm,
               page_w - 8 * mm, role_y + 1 * mm)

        code = badge.uid or "—"
        if badge.qr_payload and badge.qr_payload.startswith("VISIT-"):
            code = badge.qr_payload[6:][:14]
            code = f"KG-{code[:3]}-{code[3:8]}" if len(code) >= 8 else code

        code_label_y = role_y - 8 * mm
        c.setFillColor(HexColor(cls.DARK))
        c.setFont("Helvetica-Bold", 6)
        c.drawString(8 * mm, code_label_y, "Code visite")
        box_y = code_label_y - 5 * mm
        c.setFillColor(HexColor("#000000"))
        c.roundRect(8 * mm, box_y - 1 * mm, page_w - 16 * mm, 5 * mm,
                    1 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 9)
        c_w = c.stringWidth(code, "Helvetica-Bold", 9)
        c.drawString((page_w - c_w) / 2, box_y + 0.5 * mm, code)

        info_y = box_y - 7 * mm
        phone = getattr(holder, "phone", "") if holder else ""
        if phone:
            c.setFillColor(HexColor(cls.DARK))
            c.setFont("Helvetica-Bold", 7)
            txt = f"Tél : {phone}"
            tw = c.stringWidth(txt, "Helvetica-Bold", 7)
            c.drawString((page_w - tw) / 2, info_y, txt)

        c.setFillColor(HexColor("#000000"))
        c.rect(0, 0, page_w, 8 * mm, fill=1, stroke=0)
        c.setFillColor(HexColor("#FFFFFF"))
        c.setFont("Helvetica-Bold", 12)
        label = "VISITEUR"
        lw = c.stringWidth(label, "Helvetica-Bold", 12)
        c.drawString((page_w - lw) / 2, 2.5 * mm, label)

    # ------------------------------------------------------------------
    # Verso commun
    # ------------------------------------------------------------------
    @classmethod
    def _render_kaydan_back(cls, c, badge, page_w, page_h, mm,
                              bg_color="#0B1B33"):
        from reportlab.lib.colors import HexColor

        is_yellow = bg_color.upper() in ("#FFC72C", "#FFC72D", "#FFC700")
        text_color = "#1A1A1A" if is_yellow else "#FFFFFF"

        c.setFillColor(HexColor(bg_color))
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        qr_size_mm = 28
        qr_x = (page_w - qr_size_mm * mm) / 2
        qr_y = page_h - 5 * mm - qr_size_mm * mm
        cls._draw_qr_card(c, qr_x, qr_y, qr_size_mm,
                           f"https://kaydan.example.com/verify/{badge.uid}",
                           mm)

        desc_y = qr_y - 8 * mm
        c.setFillColor(HexColor(text_color))
        c.setFont("Helvetica-Bold", 9)

        lines = [
            "KAYDAN GROUPE est une",
            "entreprise ivoirienne",
            "spécialisée dans le BTP",
            "(Bâtiments et Travaux",
            "Publics).",
        ]
        for i, line in enumerate(lines):
            lw = c.stringWidth(line, "Helvetica-Bold", 9)
            c.drawString((page_w - lw) / 2, desc_y - i * 4.5 * mm, line)

        contact_y = desc_y - 5 * 4.5 * mm - 5 * mm
        c.setFont("Helvetica-Bold", 7)
        contacts = [
            "infos@kaydangroupe.com",
            "08 BP 2553 Abj 08",
            "+225 27 22 46 90 37",
        ]
        for i, line in enumerate(contacts):
            lw = c.stringWidth(line, "Helvetica-Bold", 7)
            c.drawString((page_w - lw) / 2, contact_y - i * 3.5 * mm, line)

    @classmethod
    def generate_and_save(cls, badge) -> str:
        """Génère le PDF + la miniature PNG, persiste les 2 fichiers."""
        pdf_bytes = cls.generate(badge)
        filename = f"badge_{badge.category}_{badge.uid}.pdf"
        badge.pdf_file.save(filename, ContentFile(pdf_bytes), save=False)
        try:
            png_bytes = BadgeThumbnailService.generate(badge)
            badge.thumbnail.save(
                f"badge_{badge.category}_{badge.uid}.png",
                ContentFile(png_bytes), save=False,
            )
            badge.save(update_fields=["pdf_file", "thumbnail"])
        except Exception:
            log.exception("Thumbnail generation failed for badge %s", badge.uid)
            badge.save(update_fields=["pdf_file"])
        return badge.pdf_file.name


# ===========================================================================
# Génération miniature PNG (rendu PIL — portrait haute résolution)
# ===========================================================================
class BadgeThumbnailService:
    """Génère un PNG portrait reproduisant le badge (380 × 600 px)."""

    WIDTH = 380
    HEIGHT = 600

    NAVY = (11, 27, 51)
    ORANGE = (242, 107, 31)
    YELLOW = (255, 199, 44)
    DARK = (26, 26, 26)
    LIGHT_GREY = (245, 245, 245)
    MID_GREY = (102, 102, 102)
    WHITE = (255, 255, 255)
    BLACK = (0, 0, 0)

    @classmethod
    def generate(cls, badge) -> bytes:
        if badge.category == "worker_rfid":
            return cls._render_worker(badge)
        if badge.category == "visitor_qr":
            return cls._render_visitor(badge)
        return cls._render_employee(badge)

    @classmethod
    def _render_employee(cls, badge) -> bytes:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (cls.WIDTH, cls.HEIGHT), cls.LIGHT_GREY)
        draw = ImageDraw.Draw(img)

        holder = badge.holder
        company = getattr(holder, "company", None)

        cls._draw_company_logo(img, draw, company,
                                cls.WIDTH // 2, 60, max_w=240, max_h=80)

        band_y = int(cls.HEIGHT * 0.36)
        draw.rectangle([(0, band_y), (cls.WIDTH, band_y + 7)], fill=cls.ORANGE)
        draw.rectangle([(0, band_y + 38), (cls.WIDTH, band_y + 45)], fill=cls.ORANGE)

        photo_radius = 80
        photo_cx = cls.WIDTH // 2
        photo_cy = band_y + 22
        cls._draw_circular_photo(img, draw, holder,
                                   photo_cx, photo_cy, photo_radius,
                                   ring_color=cls.ORANGE, ring_width=8)

        first = getattr(holder, "first_name", "") if holder else ""
        last = getattr(holder, "last_name", "") if holder else ""

        font_name = cls._font(22, bold=True)
        first_w = cls._textwidth(draw, first, font_name)
        last_w = cls._textwidth(draw, last.upper(), font_name)
        gap = 8
        total_w = first_w + gap + last_w
        x_start = (cls.WIDTH - total_w) // 2
        name_y = band_y + 130
        draw.text((x_start, name_y), first, fill=cls.DARK, font=font_name)
        draw.text((x_start + first_w + gap, name_y),
                  last.upper(), fill=cls.ORANGE, font=font_name)

        position = ""
        if holder:
            pos_obj = getattr(holder, "position", None)
            position = getattr(pos_obj, "title", "") if pos_obj else ""
            if not position:
                trade = getattr(holder, "trade", None)
                position = getattr(trade, "name", "") if trade else ""
        position = position or "Employé"
        font_role = cls._font(14)
        role_w = cls._textwidth(draw, position, font_role)
        role_y = name_y + 32
        draw.text(((cls.WIDTH - role_w) // 2, role_y),
                  position, fill=cls.MID_GREY, font=font_role)
        line_y = role_y + 9
        draw.line([(30, line_y), ((cls.WIDTH - role_w) // 2 - 10, line_y)],
                  fill=(180, 180, 180), width=1)
        draw.line([((cls.WIDTH + role_w) // 2 + 10, line_y),
                   (cls.WIDTH - 30, line_y)], fill=(180, 180, 180), width=1)

        matricule = getattr(holder, "matricule", "") if holder else ""

        font_label = cls._font(11, bold=True)
        mat_label_y = role_y + 30
        draw.text((30, mat_label_y), "Matricule",
                  fill=cls.ORANGE, font=font_label)
        box_y = mat_label_y + 18
        cls._rounded_rect(draw, (30, box_y, cls.WIDTH - 30, box_y + 36),
                          radius=6, fill=cls.ORANGE)
        font_mat = cls._font(18, bold=True)
        m_w = cls._textwidth(draw, matricule or "—", font_mat)
        draw.text(((cls.WIDTH - m_w) // 2, box_y + 7),
                  matricule or "—", fill=cls.WHITE, font=font_mat)

        info_y = box_y + 60
        font_info = cls._font(13, bold=True)
        hired = getattr(holder, "hired_at", None) if holder else None
        phone = getattr(holder, "phone", "") if holder else ""
        if hired:
            txt = f"Date début : {hired.strftime('%d/%m/%Y')}"
            tw = cls._textwidth(draw, txt, font_info)
            draw.text(((cls.WIDTH - tw) // 2, info_y),
                      txt, fill=cls.DARK, font=font_info)
        if phone:
            txt2 = f"Tél : {phone}"
            tw2 = cls._textwidth(draw, txt2, font_info)
            draw.text(((cls.WIDTH - tw2) // 2, info_y + 24),
                      txt2, fill=cls.DARK, font=font_info)

        cls._paste_qr(img, badge.qr_payload or badge.uid,
                       cls.WIDTH // 2 - 60, cls.HEIGHT - 130, 120)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    @classmethod
    def _render_worker(cls, badge) -> bytes:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (cls.WIDTH, cls.HEIGHT), cls.NAVY)
        draw = ImageDraw.Draw(img)

        draw.rectangle([(0, 0), (cls.WIDTH, 110)], fill=cls.WHITE)
        cls._draw_kaydan_text_logo(draw, cls.WIDTH // 2, 50, color=cls.DARK)

        qr_y_top = 145
        qr_y_bot = qr_y_top + 200
        draw.rectangle([(0, qr_y_top - 8), (cls.WIDTH, qr_y_top - 4)], fill=cls.ORANGE)
        draw.rectangle([(0, qr_y_bot + 4), (cls.WIDTH, qr_y_bot + 8)], fill=cls.ORANGE)

        qr_size = 175
        qr_x = (cls.WIDTH - qr_size) // 2
        qr_inner_y = qr_y_top + 13
        cls._rounded_rect(draw,
                          (qr_x - 8, qr_inner_y - 8,
                           qr_x + qr_size + 8, qr_inner_y + qr_size + 8),
                          radius=10, fill=cls.WHITE)
        cls._paste_qr(img, badge.qr_payload or badge.uid,
                       qr_x, qr_inner_y, qr_size)

        holder = badge.holder
        first = getattr(holder, "first_name", "") if holder else ""
        last = getattr(holder, "last_name", "") if holder else ""

        font_name = cls._font(22, bold=True)
        full = f"{first} {last.upper()}".strip()
        full_w = cls._textwidth(draw, full, font_name)
        name_y = qr_y_bot + 25
        draw.text(((cls.WIDTH - full_w) // 2, name_y),
                  full, fill=cls.WHITE, font=font_name)

        trade = getattr(holder, "trade", None) if holder else None
        position = getattr(trade, "name", "") if trade else "Ouvrier"
        font_role = cls._font(13, bold=True)
        role_w = cls._textwidth(draw, position, font_role)
        role_y = name_y + 28
        draw.text(((cls.WIDTH - role_w) // 2, role_y),
                  position, fill=cls.WHITE, font=font_role)
        line_y = role_y + 8
        draw.line([(30, line_y), ((cls.WIDTH - role_w) // 2 - 8, line_y)],
                  fill=cls.WHITE, width=1)
        draw.line([((cls.WIDTH + role_w) // 2 + 8, line_y),
                   (cls.WIDTH - 30, line_y)], fill=cls.WHITE, width=1)

        matricule = getattr(holder, "matricule", "") if holder else ""
        font_label = cls._font(11, bold=True)
        mat_label_y = role_y + 28
        draw.text((30, mat_label_y), "Matricule",
                  fill=cls.ORANGE, font=font_label)
        box_y = mat_label_y + 16
        cls._rounded_rect(draw, (30, box_y, cls.WIDTH - 30, box_y + 32),
                          radius=6, fill=cls.ORANGE)
        font_mat = cls._font(16, bold=True)
        m_w = cls._textwidth(draw, matricule or "—", font_mat)
        draw.text(((cls.WIDTH - m_w) // 2, box_y + 6),
                  matricule or "—", fill=cls.WHITE, font=font_mat)

        info_y = box_y + 50
        font_info = cls._font(12, bold=True)
        hired = getattr(holder, "hired_at", None) if holder else None
        if not hired and holder:
            hired = getattr(holder, "created_at", None)
            if hired and hasattr(hired, 'date'):
                hired = hired.date()
        phone = getattr(holder, "phone", "") if holder else ""
        if hired:
            try:
                txt = f"Date début : {hired.strftime('%d/%m/%Y')}"
                tw = cls._textwidth(draw, txt, font_info)
                draw.text(((cls.WIDTH - tw) // 2, info_y),
                          txt, fill=cls.WHITE, font=font_info)
            except Exception:
                pass
        if phone:
            txt2 = f"Tél : {phone}"
            tw2 = cls._textwidth(draw, txt2, font_info)
            draw.text(((cls.WIDTH - tw2) // 2, info_y + 22),
                      txt2, fill=cls.WHITE, font=font_info)

        font_tag = cls._font(16, bold=True)
        label = "OUVRIER"
        lw = cls._textwidth(draw, label, font_tag)
        draw.text((cls.WIDTH - lw - 22, cls.HEIGHT - 28),
                  label, fill=cls.WHITE, font=font_tag)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    @classmethod
    def _render_visitor(cls, badge) -> bytes:
        from PIL import Image, ImageDraw

        img = Image.new("RGB", (cls.WIDTH, cls.HEIGHT), cls.YELLOW)
        draw = ImageDraw.Draw(img)

        cls._draw_kaydan_text_logo(draw, cls.WIDTH // 2, 50, color=cls.DARK)

        qr_y_top = 110
        qr_y_bot = qr_y_top + 200
        draw.rectangle([(0, qr_y_top - 8), (cls.WIDTH, qr_y_top - 4)], fill=cls.BLACK)
        draw.rectangle([(0, qr_y_bot + 4), (cls.WIDTH, qr_y_bot + 8)], fill=cls.BLACK)

        qr_size = 175
        qr_x = (cls.WIDTH - qr_size) // 2
        qr_inner_y = qr_y_top + 13
        cls._rounded_rect(draw,
                          (qr_x - 8, qr_inner_y - 8,
                           qr_x + qr_size + 8, qr_inner_y + qr_size + 8),
                          radius=10, fill=cls.WHITE)
        cls._paste_qr(img, badge.qr_payload or badge.uid,
                       qr_x, qr_inner_y, qr_size)

        holder = badge.holder
        first = getattr(holder, "first_name", "") if holder else ""
        last = getattr(holder, "last_name", "") if holder else ""
        full = f"{first} {last.upper()}".strip() or "VISITEUR"

        font_name = cls._font(22, bold=True)
        n_w = cls._textwidth(draw, full, font_name)
        name_y = qr_y_bot + 25
        draw.text(((cls.WIDTH - n_w) // 2, name_y),
                  full, fill=cls.DARK, font=font_name)

        font_role = cls._font(13, bold=True)
        role_label = "PARTENAIRE"
        role_w = cls._textwidth(draw, role_label, font_role)
        role_y = name_y + 28
        draw.text(((cls.WIDTH - role_w) // 2, role_y),
                  role_label, fill=cls.DARK, font=font_role)
        line_y = role_y + 8
        draw.line([(30, line_y), ((cls.WIDTH - role_w) // 2 - 8, line_y)],
                  fill=cls.DARK, width=1)
        draw.line([((cls.WIDTH + role_w) // 2 + 8, line_y),
                   (cls.WIDTH - 30, line_y)], fill=cls.DARK, width=1)

        code = badge.uid or "—"
        if badge.qr_payload and badge.qr_payload.startswith("VISIT-"):
            short = badge.qr_payload[6:][:14]
            code = f"KG-{short[:3]}-{short[3:8]}" if len(short) >= 8 else short

        font_label = cls._font(11, bold=True)
        cl_y = role_y + 28
        draw.text((30, cl_y), "Code visite",
                  fill=cls.DARK, font=font_label)
        box_y = cl_y + 16
        cls._rounded_rect(draw, (30, box_y, cls.WIDTH - 30, box_y + 32),
                          radius=6, fill=cls.BLACK)
        font_code = cls._font(15, bold=True)
        c_w = cls._textwidth(draw, code, font_code)
        draw.text(((cls.WIDTH - c_w) // 2, box_y + 7),
                  code, fill=cls.WHITE, font=font_code)

        phone = getattr(holder, "phone", "") if holder else ""
        if phone:
            font_info = cls._font(12, bold=True)
            txt = f"Tél : {phone}"
            tw = cls._textwidth(draw, txt, font_info)
            draw.text(((cls.WIDTH - tw) // 2, box_y + 50),
                      txt, fill=cls.DARK, font=font_info)

        draw.rectangle([(0, cls.HEIGHT - 50), (cls.WIDTH, cls.HEIGHT)],
                       fill=cls.BLACK)
        font_v = cls._font(22, bold=True)
        v_label = "VISITEUR"
        vw = cls._textwidth(draw, v_label, font_v)
        draw.text(((cls.WIDTH - vw) // 2, cls.HEIGHT - 38),
                  v_label, fill=cls.WHITE, font=font_v)

        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    @staticmethod
    def _paste_qr(img, payload, x, y, size):
        import qrcode
        qr = qrcode.QRCode(box_size=10, border=1)
        qr.add_data(payload)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="#000000",
                                back_color="#FFFFFF").convert("RGB")
        from PIL import Image as PILImage
        qr_img = qr_img.resize((size, size), PILImage.NEAREST)
        img.paste(qr_img, (x, y))

    @staticmethod
    def _rounded_rect(draw, box, radius=10, fill=(0, 0, 0)):
        try:
            draw.rounded_rectangle(box, radius=radius, fill=fill)
        except (AttributeError, TypeError):
            draw.rectangle(box, fill=fill)

    @classmethod
    def _draw_kaydan_text_logo(cls, draw, cx, cy, color=(26, 26, 26)):
        font_name = cls._font(28, bold=True)
        text = "KAYDAN"
        tw = cls._textwidth(draw, text, font_name)
        draw.text((cx - tw // 2, cy - 22), text, fill=color, font=font_name)

        bx = cx + tw // 2 + 4
        by = cy - 12
        draw.line([(bx, by), (bx + 16, by)], fill=cls.ORANGE, width=4)
        draw.line([(bx + 16, by), (bx + 16, by + 18)], fill=cls.ORANGE, width=4)

        font_sub = cls._font(11)
        sub = "GROUPE"
        sw = cls._textwidth(draw, sub, font_sub)
        draw.text((cx - sw // 2, cy + 16),
                  sub, fill=(102, 102, 102), font=font_sub)

    @classmethod
    def _draw_company_logo(cls, img, draw, company, cx, cy, max_w=240, max_h=80):
        from PIL import Image
        if company:
            logo = getattr(company, "logo", None)
            if logo and getattr(logo, "name", ""):
                try:
                    src = Image.open(logo.path).convert("RGBA")
                    src.thumbnail((max_w, max_h))
                    img.paste(src, (cx - src.width // 2, cy - src.height // 2),
                              src if src.mode == "RGBA" else None)
                    return
                except Exception:
                    pass
        if company:
            font_name = cls._font(22, bold=True)
            text = (company.name or "").upper()
            tw = cls._textwidth(draw, text, font_name)
            draw.text((cx - tw // 2, cy - 18), text,
                      fill=cls.DARK, font=font_name)
            sector = dict(getattr(company, "SECTOR_CHOICES", []) or {}).get(
                getattr(company, "sector", ""), "")
            if sector:
                font_sec = cls._font(10)
                sw = cls._textwidth(draw, sector.upper(), font_sec)
                draw.text((cx - sw // 2, cy + 12),
                          sector.upper(), fill=cls.MID_GREY, font=font_sec)
        else:
            cls._draw_kaydan_text_logo(draw, cx, cy)

    @classmethod
    def _draw_circular_photo(cls, img, draw, holder, cx, cy, radius,
                              ring_color=(242, 107, 31), ring_width=8):
        from PIL import Image, ImageDraw

        photo = getattr(holder, "photo", None) if holder else None
        if photo and getattr(photo, "name", ""):
            try:
                src = Image.open(photo.path).convert("RGB")
                w, h = src.size
                m = min(w, h)
                src = src.crop(((w - m) // 2, (h - m) // 2,
                                (w + m) // 2, (h + m) // 2))
                src = src.resize((radius * 2, radius * 2), Image.LANCZOS)
                mask = Image.new("L", (radius * 2, radius * 2), 0)
                ImageDraw.Draw(mask).ellipse(
                    (0, 0, radius * 2, radius * 2), fill=255)
                img.paste(src, (cx - radius, cy - radius), mask)
                draw.ellipse((cx - radius, cy - radius,
                              cx + radius, cy + radius),
                             outline=ring_color, width=ring_width)
                return True
            except Exception as e:
                log.warning("circular photo failed: %s", e)
        draw.ellipse((cx - radius, cy - radius,
                      cx + radius, cy + radius),
                     fill=(220, 220, 220), outline=ring_color,
                     width=ring_width)
        if holder:
            initials = ((getattr(holder, 'first_name', '') or ' ')[0]
                        + (getattr(holder, 'last_name', '') or ' ')[0]).upper()
            font = cls._font(int(radius * 0.55), bold=True)
            iw = cls._textwidth(draw, initials, font)
            draw.text((cx - iw // 2, cy - int(radius * 0.4)),
                      initials, fill=(150, 150, 150), font=font)
        return False

    @staticmethod
    def _font(size, bold=False):
        from PIL import ImageFont
        candidates = []
        if bold:
            candidates += [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            ]
        candidates += [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size=size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    @staticmethod
    def _textwidth(draw, text, font):
        try:
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0]
        except AttributeError:
            return draw.textsize(text, font=font)[0]


# ===========================================================================
# Création des badges par workflow + lifecycle
# ===========================================================================
class BadgeWorkflowService:
    """Logique métier des 3 workflows de création de badges + lifecycle."""

    # ---------------- 1. Visitor QR ----------------
    @classmethod
    def create_visitor_qr_pool(cls, count: int = 10, prefix: str = "QRV"):
        """Crée N badges QR visiteurs disponibles (sans porteur)."""
        from core.services import get_kaydan_tenant

        from .models import Badge
        tenant = get_kaydan_tenant()
        created = []
        for _ in range(count):
            uid = f"{prefix}-{secrets.token_urlsafe(6).replace('_','').replace('-','')[:10].upper()}"
            badge = Badge.objects.create(
                tenant=tenant,
                uid=uid,
                type="qr",
                category="visitor_qr",
                status="available",
                holder_kind="",
                qr_payload="",
            )
            BadgePDFService.generate_and_save(badge)
            created.append(badge)
        return created

    @classmethod
    def assign_qr_to_visit(cls, badge, visit_request, holder_label: str = ""):
        """Attribue un badge QR libre à une visite spécifique."""
        from .models import BadgeAssignment
        if badge.category != "visitor_qr":
            raise ValueError("Seul un badge visitor_qr peut être attribué à une visite.")
        if badge.status not in ("available", "active"):
            raise ValueError(f"Badge non disponible (statut={badge.status}).")
        cls.release(badge)

        badge.qr_payload = f"VISIT-{visit_request.uuid}"
        badge.status = "active"
        badge.holder_kind = "visitor"
        badge.holder_object_id = visit_request.visitor_id
        from django.contrib.contenttypes.models import ContentType

        from visitors.models import Visitor
        badge.holder_content_type = ContentType.objects.get_for_model(Visitor)
        badge.save()

        BadgeAssignment.objects.create(
            badge=badge,
            holder_kind="visitor",
            holder_object_id=visit_request.visitor_id,
            holder_label=holder_label or f"Visite {visit_request.uuid}",
            visit_request=visit_request,
        )
        BadgePDFService.generate_and_save(badge)
        return badge

    @classmethod
    def release(cls, badge, by_user=None):
        """Libère un badge (fin de visite, restitution employé/ouvrier)."""
        from .models import BadgeAssignment
        active_assignment = BadgeAssignment.objects.filter(
            badge=badge, released_at__isnull=True,
        ).first()
        if active_assignment:
            active_assignment.released_at = timezone.now()
            if by_user is not None:
                active_assignment.released_by = by_user
                active_assignment.save(update_fields=["released_at", "released_by"])
            else:
                active_assignment.save(update_fields=["released_at"])

        if badge.category == "visitor_qr":
            badge.status = "available"
            badge.holder_kind = ""
            badge.holder_object_id = None
            badge.holder_content_type = None
            badge.qr_payload = ""
            badge.save()
        else:
            badge.status = "disabled"
            badge.save(update_fields=["status"])
        return badge

    # ---------------- Lifecycle (suspend / reactivate / revoke / lost) ----
    @classmethod
    def suspend(cls, badge, reason: str = "", by_user=None):
        if badge.status in ("revoked", "expired"):
            raise ValueError(
                f"Le badge est déjà en statut terminal ({badge.get_status_display()}) — "
                "il ne peut être suspendu."
            )
        badge.status = "suspended"
        badge.suspended_at = timezone.now()
        badge.suspended_reason = (reason or "")[:240]
        badge.save(update_fields=["status", "suspended_at", "suspended_reason"])
        log.info("Badge %s suspended (by=%s, reason=%s)", badge.uid,
                 getattr(by_user, "username", None), reason)
        return badge

    @classmethod
    def reactivate(cls, badge, by_user=None):
        if badge.status not in ("suspended", "disabled"):
            raise ValueError(
                f"Seul un badge suspendu ou désactivé peut être réactivé "
                f"(statut courant : {badge.get_status_display()})."
            )
        from datetime import date
        if badge.valid_until and date.today() > badge.valid_until:
            badge.status = "expired"
            badge.save(update_fields=["status"])
            raise ValueError("Validité dépassée — badge passé en expiré.")
        badge.status = "active"
        badge.suspended_at = None
        badge.suspended_reason = ""
        badge.save(update_fields=["status", "suspended_at", "suspended_reason"])
        log.info("Badge %s reactivated (by=%s)", badge.uid,
                 getattr(by_user, "username", None))
        return badge

    @classmethod
    def revoke(cls, badge, reason: str = "", by_user=None):
        from .models import BadgeAssignment
        if badge.status == "revoked":
            return badge
        active_assignment = BadgeAssignment.objects.filter(
            badge=badge, released_at__isnull=True,
        ).first()
        if active_assignment:
            active_assignment.released_at = timezone.now()
            if by_user is not None:
                active_assignment.released_by = by_user
                active_assignment.save(update_fields=["released_at", "released_by"])
            else:
                active_assignment.save(update_fields=["released_at"])

        badge.status = "revoked"
        badge.revoked_at = timezone.now()
        badge.revoked_reason = (reason or "")[:240]
        badge.save(update_fields=["status", "revoked_at", "revoked_reason"])
        log.info("Badge %s REVOKED (by=%s, reason=%s)", badge.uid,
                 getattr(by_user, "username", None), reason)
        return badge

    @classmethod
    def mark_lost(cls, badge, reason: str = "", by_user=None):
        from .models import BadgeAssignment
        active_assignment = BadgeAssignment.objects.filter(
            badge=badge, released_at__isnull=True,
        ).first()
        if active_assignment:
            active_assignment.released_at = timezone.now()
            if by_user is not None:
                active_assignment.released_by = by_user
                active_assignment.save(update_fields=["released_at", "released_by"])
            else:
                active_assignment.save(update_fields=["released_at"])

        badge.status = "lost"
        badge.suspended_reason = (reason or "Déclaré perdu")[:240]
        badge.suspended_at = timezone.now()
        badge.save(update_fields=["status", "suspended_at", "suspended_reason"])
        log.info("Badge %s LOST (by=%s, reason=%s)", badge.uid,
                 getattr(by_user, "username", None), reason)
        return badge

    # ---------------- 2. Employee RFID ----------------
    @classmethod
    def issue_employee_badge(cls, employee, helmet=None):
        """Émet un badge RFID pour un employé (casque obligatoire si chantier)."""
        from django.contrib.contenttypes.models import ContentType

        from employees.models import Employee

        from .models import Badge, BadgeAssignment

        requires_helmet = employee.work_location in ("field", "both")
        if requires_helmet and helmet is None:
            raise ValueError(
                f"L'employé {employee.matricule} travaille en chantier "
                "({}) → un casque RFID est obligatoire.".format(employee.work_location)
            )
        if not requires_helmet and helmet is not None:
            helmet = None

        from core.services import get_kaydan_tenant
        tenant = get_kaydan_tenant()

        uid = f"EMP-{employee.matricule}"
        badge, created = Badge.objects.get_or_create(
            tenant=tenant, uid=uid,
            defaults={
                "type": "nfc",
                "category": "employee_rfid",
                "status": "active",
                "holder_kind": "employee",
                "holder_content_type": ContentType.objects.get_for_model(Employee),
                "holder_object_id": employee.id,
                "qr_payload": uid,
                "paired_helmet": helmet,
            },
        )
        if not created:
            badge.paired_helmet = helmet
            badge.qr_payload = uid
            badge.status = "active"
            badge.save()

        BadgeAssignment.objects.create(
            badge=badge,
            holder_kind="employee",
            holder_object_id=employee.id,
            holder_label=f"{employee.first_name} {employee.last_name} ({employee.matricule})",
        )
        BadgePDFService.generate_and_save(badge)
        return badge

    # ---------------- 3. Worker RFID ----------------
    @classmethod
    def issue_worker_badge(cls, worker, helmet):
        """Émet un badge RFID pour un ouvrier — casque OBLIGATOIRE."""
        from django.contrib.contenttypes.models import ContentType

        from ouvriers.models import Worker

        from .models import Badge, BadgeAssignment

        if helmet is None:
            raise ValueError(
                f"L'ouvrier {worker.matricule} doit avoir un casque RFID — "
                "le couplage badge + casque est obligatoire pour tous les ouvriers."
            )

        from core.services import get_kaydan_tenant
        tenant = get_kaydan_tenant()

        uid = f"OV-{worker.matricule}"
        helmet_uid = helmet.uhf_tag_uid or helmet.serial_number
        qr_payload = f"BADGE:{uid}|CASQUE:{helmet_uid}"

        badge, created = Badge.objects.get_or_create(
            tenant=tenant, uid=uid,
            defaults={
                "type": "uhf",
                "category": "worker_rfid",
                "status": "active",
                "holder_kind": "worker",
                "holder_content_type": ContentType.objects.get_for_model(Worker),
                "holder_object_id": worker.id,
                "paired_helmet": helmet,
                "qr_payload": qr_payload,
            },
        )
        if not created:
            badge.paired_helmet = helmet
            badge.qr_payload = qr_payload
            badge.status = "active"
            badge.save()

        helmet.current_worker = worker
        helmet.save(update_fields=["current_worker"])

        BadgeAssignment.objects.create(
            badge=badge,
            holder_kind="worker",
            holder_object_id=worker.id,
            holder_label=f"{worker.first_name} {worker.last_name} ({worker.matricule})",
        )
        BadgePDFService.generate_and_save(badge)
        return badge
