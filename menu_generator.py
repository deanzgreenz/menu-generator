# menu_generator.py
"""
This file contains all the core logic for fetching menu data from the POSaBIT API
and generating PDF menus. It is designed to be used by a web server
and does not contain any user interface code.
"""

import requests
import os
import re
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph,
    Spacer, Table, TableStyle, PageBreak, KeepTogether, SimpleDocTemplate
)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.colors import HexColor

# ------------------------------------------------------------------
# Configuration for Different Stores/Menus
# ------------------------------------------------------------------

STORE_CONFIG = {
    "foster": {
        "api_token": "sGPrAXqxjrIzamFGrjAxyg",
        "feeds": {
            "flower": "04c0a074-8bbb-4948-89d3-1e8f54556d44",
            "preroll": "c3f32dc0-f575-48fe-a83d-3c28bdf00841",
            "cart": "538176e0-39fd-42c5-9b81-d9dd6d2f0591",
            "dab": "4d688b26-d0bd-481e-89ec-68ce0c72d0f6",
            "prepack": "ea944211-7cb0-4f3b-8298-6a95147a8f6e",
        }
    },
    "sandy": {
        "api_token": "J6ClfqCh_p2GtPPLCjdNyA",
        "feeds": {
            "flower": "6a6d3676-a3c5-48a9-9059-d3b00bee0f19",
            "preroll": "2d033094-e091-4d0c-ba41-a8b1029b79df",
            "cart": "c672599d-9d75-47b6-a194-eabc1bd45528",
            "dab": "321e5e61-af9b-4278-b0a5-e81dab357867",
            "prepack": "dd19ec03-6f94-4a70-984d-9c2c2586b2ee",
        }
    },
    "division": {
        "api_token": "RVYH-8ZRB_oLjkHSIGf-Vw",
        "feeds": {
            "flower": "78185309-c2c7-4359-ba8b-4a0ba70e0ebb",
            "preroll": "5a833c30-e184-4b07-a191-bcd71d6c2ac9",
            "cart": "f8c597e1-8d83-49d3-99e5-45c8f4b7e061",
            "dab": "2b1d9103-2b5a-42bb-9fcb-1c4b179ebd98",
            "prepack": "7403c681-bdae-4ab5-bf9d-5feacc7b9184",
        }
    }
}

# ------------------------------------------------------------------
# Constants (Shared across different menu types)
# ------------------------------------------------------------------

DEFAULT_LINEAGE_MAP = {
    "sativa": "S", "sativa_hybrid": "SH", "hybrid": "H",
    "indica": "I", "indica_hybrid": "IH", "cbd": "CBD"
}

LINEAGE_COLORS = {
    "S": colors.red, "SH": colors.red, "H": colors.green,
    "I": colors.purple, "IH": colors.purple, "CBD": HexColor("#292cf0")
}

LINEAGE_ORDER = {"S": 0, "SH": 0.5, "H": 1, "I": 2, "IH": 2.5, "CBD": 3}

# ------------------------------------------------------------------
# Data Fetching Logic
# ------------------------------------------------------------------

def fetch_menu_data(store, menu_type):
    """
    Fetches menu data for a specific store and menu type.
    """
    store_info = STORE_CONFIG.get(store)
    if not store_info:
        print(f"Error: Configuration for store '{store}' not found.")
        return None

    feed_key = store_info["feeds"].get(menu_type)
    api_token = store_info.get("api_token")

    if not feed_key or not api_token:
        print(f"Error: Incomplete configuration for store '{store}' and menu '{menu_type}'")
        return None

    api_url = f"https://app.posabit.com/api/v1/menu_feeds/{feed_key}"
    headers = {"Authorization": f"Bearer {api_token}", "Accept": "application/json"}
    try:
        resp = requests.get(api_url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        print(f"Error fetching {store} {menu_type} menu data: {exc}")
        return None

def extract_all_items(menu_feed):
    """Extracts all items from a menu feed without any special filtering."""
    items = []
    if not menu_feed: return items
    menu_groups = menu_feed.get("menu_feed", {}).get("menu_groups", [])
    for group in menu_groups:
        items.extend(group.get("menu_items", []))
    return items

# ------------------------------------------------------------------
# Generic Helper Functions (Can be used by multiple menu types)
# ------------------------------------------------------------------

def get_price_info(item):
    """Return (unit, price_dollars) from the first price entry."""
    prices = item.get("prices", [])
    if prices:
        unit_raw = prices[0].get("unit", "").strip()
        if unit_raw and not re.search(r"[a-zA-Z]", unit_raw):
            unit_raw += "g"
        cents = prices[0].get("price_cents", 0)
        return unit_raw, (cents / 100.0 if cents else 0.0)
    return "", 0.0

def get_lineage_abbr(item):
    """Return 'S','SH','H','I','IH','CBD' from flower_type."""
    ftype = (item.get("flower_type") or "").lower()
    return DEFAULT_LINEAGE_MAP.get(ftype, "")

def get_lineage_order(abbr):
    """Lineage sort weight from LINEAGE_ORDER."""
    return LINEAGE_ORDER.get(abbr, 99)

def determine_lineage_color(item):
    """Return the color for the strain name based on its lineage."""
    abbr = get_lineage_abbr(item)
    return LINEAGE_COLORS.get(abbr, colors.black)

def format_cbd_value(raw_str):
    """Show <LOQ if 0 or empty, else the original string."""
    if not raw_str: return "<LOQ"
    try:
        return "<LOQ" if float(raw_str) == 0.0 else raw_str
    except (ValueError, TypeError):
        return raw_str

def truncate_text(text, max_width, font_name, font_size):
    """Truncate text so it doesn't exceed max_width in PDF."""
    if not text: return ""
    width = pdfmetrics.stringWidth(text, font_name, font_size)
    if width <= max_width: return text
    ell, ell_w = "…", pdfmetrics.stringWidth("…", font_name, font_size)
    while text and pdfmetrics.stringWidth(text, font_name, font_size) + ell_w > max_width:
        text = text[:-1]
    return text + ell

# ------------------------------------------------------------------
# PREROLL SPECIFIC LOGIC
# ------------------------------------------------------------------

def process_flavored_title(title: str):
    """For 'Flavored' items, remove any leading brand/price by splitting on the first hyphen."""
    if not title: return ""
    return title.split("-", 1)[1].strip() if "-" in title else title.strip()

def extract_pack_size(title: str):
    """Return a numeric string (e.g. "2" for "2pk" or "2 pack") if found."""
    if not title: return None
    match = re.search(r"(\d+)\s*(?:pk|pack)\b", title, re.IGNORECASE)
    return match.group(1) if match else None

def determine_preroll_category(item):
    """Classify preroll item into Plain/Infused/Flavored/Blunts/Packs."""
    title = (item.get("name") or item.get("strain") or "").lower()
    product_type = (item.get("product_type") or "").lower()
    brand = (item.get("brand") or "").lower()
    weight = 0
    prices = item.get("prices", [])
    if prices:
        m = re.search(r"([\d.]+)", prices[0].get("unit", "").lower())
        if m: weight = float(m.group(1))
    if "flavored" in product_type or "combined" in product_type: return "Flavored"
    if "hellavated" in brand:
        if "flavored" in title or "combined" in product_type: return "Flavored"
        if weight >= 1.5: return "Preroll Packs"
        if "blunt" in title: return "Infused Blunts"
        return "Infused Prerolls"
    if weight > 2.9: return "Preroll Packs"
    is_infused = ("infused" in product_type) or (brand == "portland heights")
    is_blunt = ("blunt" in title or "blunts" in title)
    return "Infused Blunts" if is_infused and is_blunt else "Infused Prerolls" if is_infused else "Plain Blunts" if is_blunt else "Plain Prerolls"

def group_preroll_items(menu_feed):
    """Collect preroll items into category-labeled lists."""
    cats = {"Plain Prerolls": [], "Plain Blunts": [], "Infused Prerolls": [], "Infused Blunts": [], "Flavored": [], "Preroll Packs": []}
    for item in extract_all_items(menu_feed):
        cat = determine_preroll_category(item)
        cats[cat].append(item)
    return cats

def generate_preroll_pdf(grouped_data, font_size=12):
    """Generates the full-size preroll menu PDF and returns it as bytes."""
    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter, leftMargin=24, rightMargin=24, topMargin=36, bottomMargin=36)
    gap = 12
    fw, fh = (doc.width - gap) / 2, doc.height
    frames = [Frame(doc.leftMargin, doc.bottomMargin, fw, fh), Frame(doc.leftMargin + fw + gap, doc.bottomMargin, fw, fh)]
    doc.addPageTemplates([PageTemplate(id='TwoCol', frames=frames)])
    styles = getSampleStyleSheet()
    cat_header_style = ParagraphStyle("CatHeader", parent=styles["Heading1"], alignment=1, fontSize=font_size + 4)
    sub_header_style = ParagraphStyle("SubHeader", parent=styles["Heading2"], alignment=0, fontSize=font_size + 2)
    normal_style = ParagraphStyle("Normal", parent=styles["Normal"], fontSize=font_size)
    elements = []
    order = ["Plain Prerolls","Plain Blunts","Infused Prerolls","Infused Blunts","Flavored","Preroll Packs"]
    for cat in [c for c in order if grouped_data.get(c)]:
        flow = [Paragraph(cat, cat_header_style), Spacer(1, 12)]
        gmap = {k: sorted(v, key=lambda i: (get_price_info(i)[1], get_lineage_order(get_lineage_abbr(i)), (i.get("strain") or "").lower())) for k, v in group_by_brand_unit(grouped_data[cat]).items()}
        sorted_keys = sorted(gmap.keys(), key=lambda k: (min((get_price_info(i)[1] for i in gmap[k]), default=9e9), k[0].lower(), k[1].lower()))
        for brand, unit in sorted_keys:
            subitems = gmap[(brand, unit)]
            if not subitems: continue
            min_price = get_price_info(subitems[0])[1]
            pack_sz = extract_pack_size(subitems[0].get("name") or "")
            heading = f"{brand} {unit} ${min_price:.2f}" + (f" {pack_sz} pack" if pack_sz else "")
            hdr = ["Product Name", "THC MG", "CBD MG"] if "infused" in cat.lower() or cat == "Flavored" else ["Product Name", "THC %", "CBD %"]
            col_w = [fw * 0.5, fw * 0.25, fw * 0.25]
            data = [hdr]
            for it in subitems:
                name = process_flavored_title(it.get("name") or "") if cat == "Flavored" else (it.get("strain") or "")
                t_name = truncate_text(name, col_w[0], "Helvetica", font_size)
                p_style = ParagraphStyle("Prod", parent=normal_style, textColor=determine_lineage_color(it))
                p_par = Paragraph(t_name, p_style)
                thc, cbd = it.get("thc", {}).get("current", ""), format_cbd_value(it.get("cbd", {}).get("current", ""))
                data.append([p_par, thc, cbd])
            sub_flow = [Paragraph(heading, sub_header_style), Spacer(1, 6)]
            tbl = Table(data, colWidths=col_w)
            tbl.setStyle(TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), font_size), ('BACKGROUND', (0,0), (-1,0), colors.grey), ('ALIGN', (1,0), (-1,-1), 'CENTER'), ('GRID', (0,0), (-1,-1), 0.25, colors.black), ('FONTNAME', (0,1), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,1), (-1,-1), font_size)]))
            sub_flow.extend([tbl, Spacer(1, 12)])
            flow.append(KeepTogether(sub_flow))
        elements.extend([KeepTogether(flow), Spacer(1, 24)])
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

def generate_preroll_pdf_condensed(grouped_data):
    """Generates the condensed preroll menu PDF and returns it as bytes."""
    BASE_FONT, PAD_LR, PAD_TB, SPACER_S, SPACER_M, SPACER_L, MARGINS = 9, 1, 0.5, 2, 4, 8, 18
    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter, leftMargin=MARGINS, rightMargin=MARGINS, topMargin=24, bottomMargin=24)
    gap = 10
    fw, fh = (doc.width - gap) / 2, doc.height
    frames = [Frame(doc.leftMargin, doc.bottomMargin, fw, fh), Frame(doc.leftMargin + fw + gap, doc.bottomMargin, fw, fh)]
    doc.addPageTemplates([PageTemplate(id="TwoCol", frames=frames)])
    styles = getSampleStyleSheet()
    cat_h = ParagraphStyle("CatH", parent=styles["Heading3"], alignment=1, fontSize=BASE_FONT+3, leading=BASE_FONT+4)
    sub_h = ParagraphStyle("SubH", parent=styles["Heading4"], alignment=0, fontSize=BASE_FONT+1, leading=BASE_FONT+2)
    normal = ParagraphStyle("Norm", parent=styles["Normal"], fontSize=BASE_FONT, leading=BASE_FONT+1)
    elements = []
    order = ["Plain Prerolls", "Plain Blunts", "Infused Prerolls", "Infused Blunts", "Flavored", "Preroll Packs"]
    for cat in [c for c in order if grouped_data.get(c)]:
        if cat in ("Infused Prerolls", "Preroll Packs") and elements: elements.append(PageBreak())
        elements.extend([Paragraph(cat, cat_h), Spacer(1, SPACER_S)])
        gmap = {k: sorted(v, key=lambda i: (get_price_info(i)[1], get_lineage_order(get_lineage_abbr(i)), (i.get("strain") or "").lower())) for k, v in group_by_brand_unit(grouped_data[cat]).items()}
        sorted_keys = sorted(gmap.keys(), key=lambda k: (min((get_price_info(i)[1] for i in gmap[k]), default=9e9), k[0].lower(), k[1].lower()))
        for brand, unit in sorted_keys:
            subitems = gmap[(brand, unit)]
            if not subitems: continue
            min_price = get_price_info(subitems[0])[1]
            pack_sz = extract_pack_size(subitems[0].get("name") or "")
            head = f"{brand} {unit} ${min_price:.2f}" + (f" {pack_sz} pack" if pack_sz else "")
            flow = [Paragraph(head, sub_h), Spacer(1, SPACER_S)]
            hdr = ["Product Name", "THC MG", "CBD MG"] if "infused" in cat.lower() or cat == "Flavored" else ["Product Name", "THC %", "CBD %"]
            col_w = [fw*0.5, fw*0.25, fw*0.25]
            data = [hdr]
            for it in subitems:
                name = process_flavored_title(it.get("name") or "") if cat == "Flavored" else (it.get("strain") or "")
                t_name = truncate_text(name, col_w[0], "Helvetica", BASE_FONT)
                p_par = Paragraph(t_name, ParagraphStyle("P", parent=normal, textColor=determine_lineage_color(it)))
                thc, cbd = it.get("thc", {}).get("current", ""), format_cbd_value(it.get("cbd", {}).get("current", ""))
                data.append([p_par, thc, cbd])
            tbl = Table(data, colWidths=col_w)
            tbl.setStyle(TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), BASE_FONT), ('BACKGROUND', (0,0), (-1,0), colors.grey), ('ALIGN', (1,0), (-1,-1), 'CENTER'), ('GRID', (0,0), (-1,-1), 0.25, colors.black), ('FONTNAME', (0,1), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,1), (-1,-1), BASE_FONT), ('LEFTPADDING', (0,0), (-1,-1), PAD_LR), ('RIGHTPADDING', (0,0), (-1,-1), PAD_LR), ('TOPPADDING', (0,0), (-1,-1), PAD_TB), ('BOTTOMPADDING', (0,0), (-1,-1), PAD_TB)]))
            flow.extend([tbl, Spacer(1, SPACER_M)])
            elements.append(KeepTogether(flow))
        elements.append(Spacer(1, SPACER_L))
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ------------------------------------------------------------------
# CART & DAB SPECIFIC LOGIC
# ------------------------------------------------------------------

def process_cart_dab_title(title):
    """Remove any leading branding/price info by splitting on first hyphen."""
    if not title: return ""
    return title.split("-", 1)[1].strip() if "-" in title else title.strip()

def is_thc_mg_item(item):
    """Check if item should display THC in MG instead of %."""
    product_type = (item.get("product_type") or "").lower()
    title = (item.get("name") or "").lower()
    return any(term in product_type or term in title for term in ["flavored", "combined", "concentrate"])

def is_flavored_item(item):
    """
    Checks if an item is flavored. This is often the same logic as is_thc_mg_item
    but is kept separate for clarity.
    """
    product_type = (item.get("product_type") or "").lower()
    name = (item.get("name") or "").lower()
    return "flavored" in product_type or "combined" in product_type or "flavored" in name

def is_disposable_item(item):
    """Check if an item is a disposable based on keywords in its name."""
    name = (item.get("name") or "").lower()
    keywords = ["dispos", "all in one", "all-in-one", "allinone"]
    return any(keyword in name for keyword in keywords)

def group_by_brand_unit_price(items):
    """Group items by (brand, unit, price)."""
    groups = {}
    for item in items:
        brand = (item.get("brand") or "").strip()
        unit, price = get_price_info(item)
        groups.setdefault((brand, unit, price), []).append(item)
    return groups

def sort_cart_dab_groups(items):
    """Groups items by (brand, unit, price) -> sorts groups -> sorts items."""
    group_map = group_by_brand_unit_price(items)
    sorted_keys = sorted(group_map.keys(), key=lambda k: (k[2], k[0].lower(), k[1].lower()))
    return [(k[0], k[1], k[2], sorted(group_map[k], key=lambda i: (get_price_info(i)[1], get_lineage_order(get_lineage_abbr(i)), (i.get("strain") or "").lower()))) for k in sorted_keys]

def generate_cart_dab_pdf(items, menu_title, font_size=12):
    """Generic PDF generator for Cart and Dab menus."""
    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter, leftMargin=24, rightMargin=24, topMargin=36, bottomMargin=36)
    gap = 12
    fw, fh = (doc.width - gap) / 2, doc.height
    frames = [Frame(doc.leftMargin, doc.bottomMargin, fw, fh), Frame(doc.leftMargin + fw + gap, doc.bottomMargin, fw, fh)]
    doc.addPageTemplates([PageTemplate(id='TwoCol', frames=frames)])
    groups = sort_cart_dab_groups(items)
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("Header", parent=styles["Heading1"], alignment=1, fontSize=font_size+4)
    sub_header_style = ParagraphStyle("SubHeader", parent=styles["Heading2"], alignment=0, fontSize=font_size+2)
    normal_style = ParagraphStyle("Normal", parent=styles["Normal"], fontSize=font_size)
    elements = [Paragraph(menu_title, header_style), Spacer(1, 12)]
    for brand, unit, price, subitems in groups:
        sub_header = f"{brand} {unit} ${price:.2f}"
        sub_flow = [Paragraph(sub_header, sub_header_style), Spacer(1, 6)]
        hdr = ["Product Name", "THC MG", "CBD MG"] if any(is_thc_mg_item(it) for it in subitems) else ["Product Name", "THC %", "CBD %"]
        col_w = [fw * 0.5, fw * 0.25, fw * 0.25]
        data = [hdr]
        for it in subitems:
            name = truncate_text(process_cart_dab_title(it.get("name") or ""), col_w[0], "Helvetica", font_size)
            p_par = Paragraph(name, ParagraphStyle("Prod", parent=normal_style, textColor=determine_lineage_color(it)))
            thc, cbd = it.get("thc", {}).get("current", ""), format_cbd_value(it.get("cbd", {}).get("current", ""))
            data.append([p_par, thc, cbd])
        tbl = Table(data, colWidths=col_w)
        tbl.setStyle(TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), font_size), ('BACKGROUND', (0,0), (-1,0), colors.grey), ('ALIGN', (1,0), (-1,-1), 'CENTER'), ('GRID', (0,0), (-1,-1), 0.25, colors.black), ('FONTNAME', (0,1), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,1), (-1,-1), font_size)]))
        sub_flow.extend([tbl, Spacer(1, 12)])
        elements.append(KeepTogether(sub_flow))
    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

def generate_cart_dab_pdf_condensed(items, menu_title):
    """
    Generic condensed PDF generator for Cart and Dab menus.
    Separates disposables for cart menus.
    """
    BASE_FONT, PAD_LR, PAD_TB, SPACER_S, SPACER_M, MARGINS = 9, 1, 0.5, 2, 4, 18
    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter, leftMargin=MARGINS, rightMargin=MARGINS, topMargin=24, bottomMargin=24)
    gap = 10
    fw, fh = (doc.width - gap) / 2, doc.height
    frames = [Frame(doc.leftMargin, doc.bottomMargin, fw, fh), Frame(doc.leftMargin + fw + gap, doc.bottomMargin, fw, fh)]
    doc.addPageTemplates([PageTemplate(id="TwoCol", frames=frames)])
    
    styles = getSampleStyleSheet()
    head_style = ParagraphStyle("Head", parent=styles["Heading1"], alignment=1, fontSize=BASE_FONT+4, leading=BASE_FONT+5)
    section_style = ParagraphStyle("Sub", parent=styles["Heading2"], alignment=0, fontSize=BASE_FONT+2, leading=BASE_FONT+3)
    body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=BASE_FONT, leading=BASE_FONT+1)
    
    elements = []

    # Helper function to render a list of groups under a specific heading
    def render_section(title, items_list, page_break=False, is_main_header=False):
        if not items_list:
            return
        
        if page_break and elements:
            elements.append(PageBreak())
        
        header_style = head_style if is_main_header else section_style
        elements.append(Paragraph(title, header_style))
        elements.append(Spacer(1, SPACER_M))

        groups_to_render = sort_cart_dab_groups(items_list)

        for brand, unit, price, subitems in groups_to_render:
            hdr_txt = f"{brand} {unit} ${price:.2f}"
            flow = [Paragraph(hdr_txt, section_style), Spacer(1, SPACER_S)]
            hdr = ["Product Name", "THC MG", "CBD MG"] if any(is_thc_mg_item(it) for it in subitems) else ["Product Name", "THC %", "CBD %"]
            col_w = [fw * 0.5, fw * 0.25, fw * 0.25]
            data = [hdr]
            for it in subitems:
                name = truncate_text(process_cart_dab_title(it.get("name") or ""), col_w[0], "Helvetica", BASE_FONT)
                prod = Paragraph(name, ParagraphStyle("P", parent=body_style, textColor=determine_lineage_color(it)))
                thc, cbd = it.get("thc", {}).get("current", ""), format_cbd_value(it.get("cbd", {}).get("current", ""))
                data.append([prod, thc, cbd])
            tbl = Table(data, colWidths=col_w)
            tbl.setStyle(TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), BASE_FONT), ('BACKGROUND', (0,0), (-1,0), colors.grey), ('ALIGN', (1,0), (-1,-1), 'CENTER'), ('GRID', (0,0), (-1,-1), 0.25, colors.black), ('FONTNAME', (0,1), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,1), (-1,-1), BASE_FONT), ('LEFTPADDING', (0,0), (-1,-1), PAD_LR), ('RIGHTPADDING', (0,0), (-1,-1), PAD_LR), ('TOPPADDING', (0,0), (-1,-1), PAD_TB), ('BOTTOMPADDING', (0,0), (-1,-1), PAD_TB)]))
            flow.extend([tbl, Spacer(1, SPACER_M)])
            elements.append(KeepTogether(flow))

    # --- Main Logic for PDF Generation ---
    if "CART" in menu_title.upper():
        # Categorize items into four groups
        carts, flavored_carts, disposables, flavored_disposables = [], [], [], []
        for item in items:
            is_disp = is_disposable_item(item)
            is_flav = is_flavored_item(item)
            if is_disp and is_flav:
                flavored_disposables.append(item)
            elif is_disp:
                disposables.append(item)
            elif is_flav:
                flavored_carts.append(item)
            else:
                carts.append(item)
        
        # Render sections in order
        render_section("CARTS", carts, is_main_header=True)
        render_section("FLAVORED CARTS", flavored_carts)
        render_section("DISPOSABLES", disposables, page_break=True, is_main_header=True)
        render_section("FLAVORED DISPOSABLES", flavored_disposables)
    else:
        # For Dab menus, use the original simpler logic
        render_section(menu_title, items, is_main_header=True)

    doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ------------------------------------------------------------------
# PREPACK SPECIFIC LOGIC
# ------------------------------------------------------------------

def get_special_designation(item):
    """Check for 'Shake' or 'Last of Flower/As Is' in product name."""
    name_lower = (item.get("name") or "").lower()
    if "last of flower" in name_lower and "as is" in name_lower: return "Last of Flower / As Is"
    if "shake" in name_lower: return "Shake"
    return ""

def sort_items_by_price_and_lineage(items):
    """Sort items by price, then lineage, then strain name."""
    def sort_key(item):
        price = item.get("prices", [{}])[0].get("price_cents", 999999)
        lineage_val = get_lineage_order(get_lineage_abbr(item))
        strain = (item.get("strain") or "").strip().lower()
        return (price, lineage_val, strain)
    return sorted(items, key=sort_key)

def get_all_weights(item):
    """Get a formatted string of all available weights, e.g., '1g, 3.5g'."""
    prices = item.get("prices", [])
    if not prices: return ""
    displays = set()
    for p in prices:
        unit, unit_type = p.get("unit"), p.get("unit_type", "g")
        if unit: displays.add(f"{unit}{unit_type[0] if unit_type else ''}")
    return ", ".join(sorted(list(displays)))

def generate_prepack_pdf(items, font_size=9):
    """Generates the full-size prepack menu PDF and returns it as bytes."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    elements = []
    styles = getSampleStyleSheet()
    shake, regular, last_of = [], [], []
    for item in items:
        designation = get_special_designation(item)
        if designation == "Shake": shake.append(item)
        elif designation == "Last of Flower / As Is": last_of.append(item)
        else: regular.append(item)
    
    shake, regular, last_of = sort_items_by_price_and_lineage(shake), sort_items_by_price_and_lineage(regular), sort_items_by_price_and_lineage(last_of)
    
    main_header = ParagraphStyle("MainHeader", parent=styles["Heading1"], alignment=1, fontSize=14, spaceAfter=12)
    section_header = ParagraphStyle("SectionHeader", parent=styles["Heading2"], alignment=0, fontSize=11, spaceBefore=6, spaceAfter=6)
    col_widths = [doc.width * f for f in [0.12, 0.12, 0.18, 0.40, 0.18]]
    
    def create_table(data_items):
        if not data_items: return None
        header = ["Lineage", "Price", "Grams", "Strain Name", "THC"]
        table_data = [header]
        for it in data_items:
            abbr, _ = get_lineage_abbr(it), determine_lineage_color(it)
            price = f"${get_price_info(it)[1]:.2f}" if get_price_info(it)[1] else ""
            grams = get_all_weights(it)
            strain = truncate_text(it.get("strain", ""), col_widths[3], "Helvetica", font_size)
            thc = f"{it.get('thc', {}).get('current', '')}%" if it.get('thc', {}).get('current') else ""
            table_data.append([abbr, price, grams, strain, thc])
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        style = TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), font_size+1), ('BACKGROUND', (0,0), (-1,0), colors.darkgrey), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('GRID', (0,0), (-1,-1), 0.5, colors.black), ('FONTNAME', (0,1), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,1), (-1,-1), font_size), ('ALIGN', (1,1), (1,-1), 'RIGHT'), ('ALIGN', (2,1), (2,-1), 'LEFT'), ('ALIGN', (3,1), (3,-1), 'LEFT')])
        for i, row_item in enumerate(data_items, start=1):
            style.add("TEXTCOLOR", (0, i), (0, i), determine_lineage_color(row_item))
            style.add("FONTNAME", (3, i), (3, i), "Helvetica-Bold")
        tbl.setStyle(style)
        return tbl

    elements.append(Paragraph("Prepack Specials", main_header))
    any_added = False
    if shake:
        elements.extend([Paragraph("Shake", section_header), create_table(shake), Spacer(1, 12)])
        any_added = True
    if regular:
        elements.extend([Paragraph("Regular Prepacks", section_header), create_table(regular)])
        any_added = True
    if last_of:
        if any_added: elements.append(PageBreak())
        elements.extend([Paragraph("Last Of Flower / As Is", section_header), create_table(last_of)])
    
    if any([shake, regular, last_of]):
        doc.build(elements)
    
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

def generate_prepack_pdf_condensed(items):
    """Generates the condensed prepack menu PDF and returns it as bytes."""
    BASE_FONT, PAD_LR, PAD_TB, SPACER_S, SPACER_M, MARGINS, GAP = 9, 1, 0.5, 2, 4, 18, 10
    buffer = BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=letter, leftMargin=MARGINS, rightMargin=MARGINS, topMargin=24, bottomMargin=24)
    fw, fh = (doc.width - GAP) / 2, doc.height
    frames = [Frame(doc.leftMargin, doc.bottomMargin, fw, fh), Frame(doc.leftMargin + fw + GAP, doc.bottomMargin, fw, fh)]
    doc.addPageTemplates([PageTemplate(id="TwoCol", frames=frames)])
    styles = getSampleStyleSheet()
    head_style = ParagraphStyle("Head", parent=styles["Heading1"], alignment=1, fontSize=BASE_FONT+4, leading=BASE_FONT+5)
    section_style = ParagraphStyle("Section", parent=styles["Heading2"], alignment=0, fontSize=BASE_FONT+2, leading=BASE_FONT+3)
    elements = [Paragraph("PREPACK MENU", head_style), Spacer(1, SPACER_M)]
    shake, regular, last_of = [], [], []
    for it in items:
        designation = get_special_designation(it)
        if designation == "Shake": shake.append(it)
        elif designation == "Last of Flower / As Is": last_of.append(it)
        else: regular.append(it)
    
    def make_table(data_items):
        if not data_items: return None
        header = ["Lin.", "Price", "Grams", "Strain", "THC"]
        col_w = [fw * f for f in [0.12, 0.12, 0.18, 0.4, 0.18]]
        rows = [header]
        for it in data_items:
            lin_abbr, _ = get_lineage_abbr(it), determine_lineage_color(it)
            price = f"${get_price_info(it)[1]:.2f}" if get_price_info(it)[1] else ""
            grams = get_all_weights(it)
            strain = truncate_text(it.get("strain", ""), col_w[3], "Helvetica", BASE_FONT)
            thc = f"{it.get('thc', {}).get('current', '')}%" if it.get('thc', {}).get('current') else ""
            rows.append([lin_abbr, price, grams, strain, thc])
        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        style = TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), BASE_FONT), ('BACKGROUND', (0,0), (-1,0), colors.grey), ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke), ('ALIGN', (0,0), (-1,0), 'CENTER'), ('FONTNAME', (0,1), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,1), (-1,-1), BASE_FONT), ('LEFTPADDING', (0,0), (-1,-1), PAD_LR), ('RIGHTPADDING', (0,0), (-1,-1), PAD_LR), ('TOPPADDING', (0,0), (-1,-1), PAD_TB), ('BOTTOMPADDING', (0,0), (-1,-1), PAD_TB), ('GRID', (0,0), (-1,-1), 0.25, colors.black), ('ALIGN', (0,1), (0,-1), 'CENTER'), ('ALIGN', (1,1), (1,-1), 'RIGHT'), ('ALIGN', (2,1), (2,-1), 'LEFT'), ('ALIGN', (4,1), (4,-1), 'CENTER')])
        for idx, row_it in enumerate(data_items, start=1):
            style.add("TEXTCOLOR", (0, idx), (0, idx), determine_lineage_color(row_it))
            style.add("FONTNAME", (3, idx), (3, idx), "Helvetica-Bold")
        tbl.setStyle(style)
        return tbl

    for label, items_list in [("Shake", shake), ("Regular Prepacks", regular), ("Last Of Flower / As Is", last_of)]:
        if not items_list: continue
        flow = [Paragraph(label, section_style), Spacer(1, SPACER_S)]
        tbl = make_table(sort_items_by_price_and_lineage(items_list))
        if tbl: flow.extend([tbl, Spacer(1, SPACER_M)])
        elements.append(KeepTogether(flow))
    
    if len(elements) > 2: doc.build(elements)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data

# ------------------------------------------------------------------
# FLOWER SPECIFIC LOGIC
# ------------------------------------------------------------------

PRICING = {
    "Diamond": {"REC": "Gram - $15, Eighth - $45, Quarter - $80, Half-Oz - $145, Ounce - $270", "MED": "Gram - $12.50, Eighth - $37.50, Quarter - $66.67, Half-Oz - $120.83, Ounce - $225"},
    "Platinum": {"REC": "Gram - $14.00, Eighth - $40.00, Quarter - $72.00, Half-Oz - $135.00, Ounce - $250.00", "MED": "Gram - $11.67, Eighth - $33.33, Quarter - $60.00, Half-Oz - $112.50, Ounce - $208.33"},
    "Gold": {"REC": "Gram - $6, Eighth - $18, Quarter - $34, Half-Oz - $65, Ounce - $125", "MED": "Gram - $5, Eighth - $14.40, Quarter - $28.33, Half-Oz - $54.17, Ounce - $104.17"}
}
ALLOWED_ROOMS = {"Floor Stock", "Floor Stock : Diamond"}

def extract_flower_data(menu_feed):
    """Extracts flower items, filtering by allowed rooms."""
    items = []
    for item in extract_all_items(menu_feed):
        rooms = item.get("rooms", [])
        if not rooms or any(room in ALLOWED_ROOMS for room in rooms):
            items.append(item)
    return items

def is_foster_special(item, special_type):
    """Check for Foster-specific special tags."""
    tags = item.get("tag_list", [])
    return any(special_type in tag and "Foster" in tag for tag in tags)

def filter_by_tier(items, tier):
    """Filter items by tier_name."""
    return [item for item in items if item.get("tier_name", "").strip().lower() == tier.lower()]

def sort_flower_items(items):
    """Sort items by lineage group, then alphabetically by strain name."""
    def sort_key(item):
        group_order = get_lineage_order(get_lineage_abbr(item))
        strain = (item.get("name") or "").strip().lower()
        return (group_order, strain)
    return sorted(items, key=sort_key)

def generate_flower_pdf(items, font_size=12):
    """Generates the multi-page, tiered flower menu PDF."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    all_flowables = []
    styles = getSampleStyleSheet()
    header_style = ParagraphStyle("Header", parent=styles["Heading1"], alignment=1, fontSize=14)
    pricing_style = ParagraphStyle("Pricing", parent=styles["Normal"], fontSize=12)
    
    for idx, tier in enumerate(["Diamond", "Platinum", "Gold"]):
        tier_items = filter_by_tier(items, tier)
        if not tier_items: continue
        
        flowables = []
        flowables.append(Paragraph(f"{tier.upper()} SHELF", header_style))
        flowables.append(Spacer(1, 12))
        flowables.append(Paragraph(f"REC: {PRICING[tier]['REC']}", pricing_style))
        flowables.append(Paragraph(f"MED: {PRICING[tier]['MED']}", pricing_style))
        flowables.append(Spacer(1, 12))

        table_data = [["Lineage", "Strain", "Farm", "THC%", "CBD%"]]
        col_widths = [doc.width * f for f in [0.1, 0.35, 0.25, 0.15, 0.15]]
        
        for item in sort_flower_items(tier_items):
            strain = (item.get("name") or "").replace(" [Gold]", "")
            table_data.append([
                get_lineage_abbr(item),
                truncate_text(strain, col_widths[1] - font_size, "Helvetica", font_size),
                truncate_text(item.get("brand", ""), col_widths[2] - font_size, "Helvetica", font_size),
                item.get("thc", {}).get("current", ""),
                format_cbd_value(item.get("cbd", {}).get("current", ""))
            ])
        
        table = Table(table_data, colWidths=col_widths)
        style = TableStyle([('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), ('FONTSIZE', (0,0), (-1,0), font_size), ('ALIGN', (0,0), (-1,0), 'CENTER'), ('BOTTOMPADDING', (0,0), (-1,0), font_size*0.5+4), ('GRID', (0,0), (-1,-1), 0.25, colors.black), ('FONTNAME', (0,1), (-1,-1), 'Helvetica'), ('FONTSIZE', (0,1), (-1,-1), font_size), ('LEFTPADDING', (0,0), (-1,-1), font_size*0.5), ('RIGHTPADDING', (0,0), (-1,-1), font_size*0.5), ('TOPPADDING', (0,0), (-1,-1), font_size*0.5), ('BOTTOMPADDING', (0,0), (-1,-1), font_size*0.5)])
        for i, item in enumerate(sort_flower_items(tier_items), start=1):
            style.add('TEXTCOLOR', (0, i), (0, i), determine_lineage_color(item))
            if is_foster_special(item, "Last Chance"): style.add('BACKGROUND', (1, i), (1, i), colors.yellow)
            elif is_foster_special(item, "Manager Special"): style.add('BACKGROUND', (1, i), (1, i), colors.lightblue)
        table.setStyle(style)
        flowables.append(table)

        legend_data = [[Paragraph("Last Chance Special 30% OFF", ParagraphStyle(name="LegendYellow", fontSize=8, alignment=1, backColor=colors.yellow)), Paragraph("Manager Special 50% OFF", ParagraphStyle(name="LegendBlue", fontSize=8, alignment=1, backColor=colors.lightblue))]]
        flowables.extend([Spacer(1, 12), Table(legend_data, colWidths=[doc.width/2, doc.width/2])])
        
        all_flowables.extend(flowables)
        if idx < 2: all_flowables.append(PageBreak())

    if all_flowables:
        doc.build(all_flowables)
        
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data
