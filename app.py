# app.py
from flask import Flask, render_template, request, send_file
from io import BytesIO
import menu_generator

app = Flask(__name__)

# Map dropdown choices to extractors and generators
MENU_GENERATOR_MAP = {
    # Flower (needs store for highlight scoping)
    "flower": {
        "data_extractor": menu_generator.extract_flower_data,
        "pdf_generator": lambda items, store=None: menu_generator.generate_flower_pdf(items, store=store),
    },
    # Preroll
    "preroll": {
        "data_extractor": menu_generator.group_preroll_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_preroll_pdf(items, store=store),
    },
    "preroll_condensed": {
        "data_extractor": menu_generator.group_preroll_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_preroll_pdf_condensed(items, store=store),
    },
    # Cart
    "cart": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_cart_dab_pdf(items, "CART MENU", store=store),
    },
    "cart_condensed": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_cart_dab_pdf_condensed(items, "CART MENU", store=store),
    },
    # Dab
    "dab": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_cart_dab_pdf(items, "DAB MENU", store=store),
    },
    "dab_condensed": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_cart_dab_pdf_condensed(items, "DAB MENU", store=store),
    },
    # Prepack
    "prepack": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_prepack_pdf(items, store=store),
    },
    "prepack_condensed": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items, store=None: menu_generator.generate_prepack_pdf_condensed(items, store=store),
    },
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_pdf():
    try:
        store = request.form.get('store')             # foster | sandy | division
        menu_choice = request.form.get('menu_type')   # e.g. "preroll_condensed"

        generator_info = MENU_GENERATOR_MAP.get(menu_choice)
        if not generator_info:
            return "Error: Invalid menu type selected.", 400

        api_menu_type = menu_choice.split('_')[0]
        raw_data = menu_generator.fetch_menu_data(store, api_menu_type)
        if not raw_data:
            return f"Error: Could not fetch data for {store} {api_menu_type}.", 500

        data_extractor = generator_info['data_extractor']
        processed_data = data_extractor(raw_data)

        has_items = bool(
            processed_data and (
                any(processed_data.values()) if isinstance(processed_data, dict)
                else len(processed_data) > 0
            )
        )
        if not has_items:
            return f"No items found for the selected menu ({menu_choice}).", 404

        pdf_generator = generator_info['pdf_generator']
        pdf_bytes = pdf_generator(processed_data, store=store)  # pass store to all generators

        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{store}_{menu_choice}_menu.pdf'
        )
    except Exception as e:
        print(f"An error occurred: {e}")
        return "An unexpected error occurred while generating the PDF.", 500

if __name__ == '__main__':
    app.run(debug=True)
