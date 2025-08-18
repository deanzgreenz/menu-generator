# app.py
"""
This is the main Flask web server for the menu generator application.
It handles web requests, calls the appropriate PDF generation logic
from menu_generator.py, and sends the generated PDF back to the user.
"""

from flask import Flask, render_template, request, send_file
from io import BytesIO

# Import all the logic we created in the previous step
import menu_generator

# Initialize the Flask application
app = Flask(__name__)

# This dictionary maps the user's dropdown choices to the correct functions
# This makes it very easy to add new menus or stores in the future.
MENU_GENERATOR_MAP = {
    # Flower Menus
    "flower": {
        "data_extractor": menu_generator.extract_flower_data,
        "pdf_generator": menu_generator.generate_flower_pdf,
    },
    # Preroll Menus
    "preroll": {
        "data_extractor": menu_generator.group_preroll_items,
        "pdf_generator": menu_generator.generate_preroll_pdf,
    },
    "preroll_condensed": {
        "data_extractor": menu_generator.group_preroll_items,
        "pdf_generator": menu_generator.generate_preroll_pdf_condensed,
    },
    # Cart Menus
    "cart": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items: menu_generator.generate_cart_dab_pdf(items, "CART MENU"),
    },
    "cart_condensed": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items: menu_generator.generate_cart_dab_pdf_condensed(items, "CART MENU"),
    },
    # Dab Menus
    "dab": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items: menu_generator.generate_cart_dab_pdf(items, "DAB MENU"),
    },
    "dab_condensed": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": lambda items: menu_generator.generate_cart_dab_pdf_condensed(items, "DAB MENU"),
    },
    # Prepack Menus
    "prepack": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": menu_generator.generate_prepack_pdf,
    },
    "prepack_condensed": {
        "data_extractor": menu_generator.extract_all_items,
        "pdf_generator": menu_generator.generate_prepack_pdf_condensed,
    },
}

@app.route('/')
def index():
    """
    This function runs when a user visits the main page.
    It just shows the main HTML form.
    """
    # Flask will automatically look for 'index.html' in a 'templates' folder
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_pdf():
    """
    This function runs when the user clicks the "Generate PDF" button.
    It reads the form, generates the PDF, and sends it for download.
    """
    try:
        # 1. Get the user's selections from the HTML form
        store = request.form.get('store')
        menu_choice = request.form.get('menu_type') # e.g., "preroll_condensed"

        # 2. Look up the correct functions in our map
        generator_info = MENU_GENERATOR_MAP.get(menu_choice)
        if not generator_info:
            return "Error: Invalid menu type selected.", 400

        # 3. Fetch the data from the POSaBIT API
        # The menu_type for the API call is the part before the underscore
        api_menu_type = menu_choice.split('_')[0]
        raw_data = menu_generator.fetch_menu_data(store, api_menu_type)
        if not raw_data:
            return f"Error: Could not fetch data for {store} {api_menu_type}.", 500

        # 4. Process the raw data using the correct extractor function
        data_extractor = generator_info['data_extractor']
        processed_data = data_extractor(raw_data)
        if not processed_data or not any(processed_data.values() if isinstance(processed_data, dict) else processed_data):
            return f"No items found for the selected menu ({menu_choice}). Please check the inventory.", 404

        # 5. Generate the PDF in memory
        pdf_generator = generator_info['pdf_generator']
        pdf_bytes = pdf_generator(processed_data)

        # 6. Send the generated PDF to the user's browser
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'{store}_{menu_choice}_menu.pdf'
        )

    except Exception as e:
        # Basic error handling to catch any unexpected issues
        print(f"An error occurred: {e}")
        return "An unexpected error occurred while generating the PDF.", 500

if __name__ == '__main__':
    # This allows you to run the server locally for testing
    app.run(debug=True)
