import datetime
import re
import os
import pdfplumber
from tabulate import tabulate
from flask import Flask, render_template, request, redirect
from flask import url_for
import sqlite3
from werkzeug.utils import secure_filename
import requests

app = Flask(__name__)

def match_company_street_city(text):
    pattern = r'^(.*)\n(\w.*\s\d+)\n(.*?)$'
    match = re.search(pattern, text, re.MULTILINE)
    if match:
        line1, line2, line3 = match.groups()
        return line1, line2, line3
    else:
        return None

def extract_data(text):
    lines = text.split('\n')
    items = []
    current_item = None
    company_name = None
    street = None
    zip_code = ''
    city = None

    # Match company name, street, and city using match_company_street_city function
    company_match = match_company_street_city(text)
    date_match = re.search(r'\b(?:0[1-9]|[12]\d|3[01])\.(?:0[1-9]|1[0-2])\.\d{4}\b', text)

    if date_match:
        date = date_match.group()
    if company_match:
        company_name, street, city = company_match

    # Split city into zip_code and city components
    if city:
        city_parts = city.split(' ', 1)
        if len(city_parts) == 2:
            zip_code, city = city_parts

    for line in lines:
        if re.match(r'^-{3,}$', line.strip()) or re.search(r'\bTotal\b', line, re.IGNORECASE):
            break
        if current_item:
            quantity_match = re.search(r'(\d+(?:,\d+)? (?:kg|Stk)) x (\d+,\d+)', line)
            if quantity_match:
                quantity_data = quantity_match.group(1).split()
                current_item['quantity'] = quantity_data[0]
                current_item['unit'] = quantity_data[1]
                current_item['unit_price'] = quantity_match.group(2)
                continue
        item_match = re.match(r'(.*) (\d+,\d+)', line)
        if item_match:
            current_item = {'name': re.sub(r'\s+x.*', '', item_match.group(1).strip()), 'total_price': item_match.group(2)}
            items.append(current_item)
        quantity_match = re.search(r'x(\d+)\s+(\d+)', line)
        if quantity_match:
            current_item['quantity'] = quantity_match.group(1)
            current_item['unit_price'] = str(round(float(current_item['total_price'].replace(',', '.')) / float(quantity_match.group(1).replace(',', '.')) , 2)).replace('.', ',')
            current_item['unit'] = 'Stk'



    # API Request
    try:
        api_url = f"https://www.rewe.de/api/marketsearch?searchTerm={street} {zip_code}"
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an exception for non-successful status codes
        json_data = response.json()
        
        # Extracting data from the API response
        if json_data:
            company_name = json_data[0].get('companyName', company_name)
            city = json_data[0].get('contactCity', city)
            street = json_data[0].get('contactStreet', street)
            zip_code = json_data[0].get('contactZipCode', zip_code)
        else:
            company_name = company_name
            city = city
    
    except requests.exceptions.RequestException:
        company_name = company_name
        city = city

    except Exception as e:
        # Handle any other exceptions here
        company_name = company_name
        city = city
    
    return {'CompanyName': company_name, 'street': street, 'zip_code': zip_code, 'city': city}, items, date

def create_table():
    # Connect to the database or create a new one if it doesn't exist
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()

    # Create the Invoices table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Invoices (
            invoice_id INTEGER PRIMARY KEY,
            date TEXT DEFAULT (datetime('now','localtime')),
            supplier_id INTEGER,
            total_amount REAL,
            due_date TEXT,
            currency TEXT,
            payment_status TEXT DEFAULT 'Paid',
            FOREIGN KEY (supplier_id) REFERENCES Suppliers (supplier_id)
        )
    ''')

    # Create the Products table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Products (
            product_id INTEGER PRIMARY KEY,
            name TEXT UNIQUE,
            description TEXT,
            price REAL,
            category_id INTEGER,
            manufacturer TEXT,
            weight REAL,
            dimensions TEXT,
            SKU TEXT,
            unit_id INTEGER,
            FOREIGN KEY (category_id) REFERENCES Categories (category_id),
            FOREIGN KEY (unit_id) REFERENCES Units (unit_id)
        )
    ''')

    # Create the InvoiceItems table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS InvoiceItems (
            invoice_item_id INTEGER PRIMARY KEY,
            invoice_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            unit_price REAL,
            discount_percentage REAL,
            tax_rate REAL,
            FOREIGN KEY (invoice_id) REFERENCES Invoices (invoice_id),
            FOREIGN KEY (product_id) REFERENCES Products (product_id)
        )
    ''')

    # Create the Categories table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Categories (
            category_id INTEGER PRIMARY KEY,
            name TEXT,
            description TEXT
        )
    ''')

    # Create the Suppliers table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Suppliers (
            supplier_id INTEGER PRIMARY KEY,
            name TEXT,
            address TEXT,
            contact_number TEXT,
            email TEXT,
            preferred_payment_terms TEXT,
            lead_time INTEGER,
            CHECK (lead_time >= 0)
        )
    ''')

    # Create the Units table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS Units (
            unit_id INTEGER PRIMARY KEY,
            name TEXT,
            abbreviation TEXT
        )
    ''')

    # Check if Kilogramm exists in the Units table
    cursor.execute("SELECT * FROM Units WHERE name='Kilogramm'")
    result = cursor.fetchone()

    # If Kilogramm doesn't exist, insert it into the Units table
    if not result:
        cursor.execute("INSERT INTO Units (name, abbreviation) VALUES ('Kilogramm', 'kg')")

    # Check if Stück exists in the Units table
    cursor.execute("SELECT * FROM Units WHERE name='Stück'")
    result = cursor.fetchone()

    # If Stück doesn't exist, insert it into the Units table
    if not result:
        cursor.execute("INSERT INTO Units (name, abbreviation) VALUES ('Stück', 'Stk')")

    # Create the InventoryLevels table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS InventoryLevels (
            inventory_id INTEGER PRIMARY KEY,
            product_id INTEGER,
            quantity REAL,
            reorder_point INTEGER,
            FOREIGN KEY (product_id) REFERENCES Products (product_id),
            CHECK (quantity >= 0 AND reorder_point >= 0)
        )
    ''')

    # Create the ProductAttributes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ProductAttributes (
            attribute_id INTEGER PRIMARY KEY,
            product_id INTEGER,
            attribute_name TEXT,
            attribute_value TEXT,
            FOREIGN KEY (product_id) REFERENCES Products (product_id)
        )
    ''')

    # Create the PriceHistory table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS PriceHistory (
            price_id INTEGER PRIMARY KEY,
            product_id INTEGER,
            price REAL,
            date_changed TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (product_id) REFERENCES Products (product_id)
        )
    ''')


    #views ###############################################################################################################################

    # View_InvoiceList
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_InvoiceList AS
        SELECT invoice_id, date, supplier_id, total_amount, due_date, payment_status
        FROM Invoices
    ''')

    # View_ProductList
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ProductList AS
        SELECT product_id, name, description, price, category_id, manufacturer, weight, dimensions, SKU, unit_id
        FROM Products
    ''')

    # View_SupplierList
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_SupplierList AS
        SELECT supplier_id, name, address, contact_number, email, preferred_payment_terms, lead_time
        FROM Suppliers
    ''')

    # View_CategoryList
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_CategoryList AS
        SELECT category_id, name, description
        FROM Categories
    ''')

    # View_UnitList
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_UnitList AS
        SELECT unit_id, name, abbreviation
        FROM Units
    ''')

    # View_InventoryLevels
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_InventoryLevels AS
        SELECT inventory_id, product_id, quantity, reorder_point
        FROM InventoryLevels
    ''')

    # View_InvoiceDetails
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_InvoiceDetails AS
        SELECT i.invoice_id, i.date, i.supplier_id, i.total_amount, i.due_date, i.currency, i.payment_status,
            ii.invoice_item_id, ii.product_id, ii.quantity, ii.unit_price, ii.discount_percentage, ii.tax_rate, ii.total_amount
        FROM Invoices AS i
        INNER JOIN InvoiceItems AS ii ON i.invoice_id = ii.invoice_id
    ''')

    # View_ProductDetails
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ProductDetails AS
        SELECT p.product_id, p.name, p.description, p.price, p.category_id, p.manufacturer, p.weight, p.dimensions, p.SKU, p.unit_id,
            pa.attribute_name, pa.attribute_value
        FROM Products AS p
        LEFT JOIN ProductAttributes AS pa ON p.product_id = pa.product_id
    ''')

    # View_SupplierDetails
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_SupplierDetails AS
        SELECT s.supplier_id, s.name, s.address, s.contact_number, s.email, s.preferred_payment_terms, s.lead_time,
            i.invoice_id, i.date, i.total_amount, i.due_date, i.currency, i.payment_status
        FROM Suppliers AS s
        LEFT JOIN Invoices AS i ON s.supplier_id = i.supplier_id
    ''')

    # View_CategoryDetails
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_CategoryDetails AS
        SELECT c.category_id, c.name, c.description, p.product_id, p.name, p.description, p.price
        FROM Categories AS c
        LEFT JOIN Products AS p ON c.category_id = p.category_id
    ''')

    # View_UnitDetails
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_UnitDetails AS
        SELECT u.unit_id, u.name, u.abbreviation, p.product_id, p.name, p.description, p.price
        FROM Units AS u
        LEFT JOIN Products AS p ON u.unit_id = p.unit_id
    ''')

    # View_PendingInvoices
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_PendingInvoices AS
        SELECT invoice_id, date, supplier_id, total_amount, due_date, payment_status
        FROM Invoices
        WHERE payment_status = 'Pending'
    ''')

    # View_ExpensiveProducts
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ExpensiveProducts AS
        SELECT product_id, name, price
        FROM Products
        WHERE price > 1000
    ''')

    # View_LowInventoryProducts
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_LowInventoryProducts AS
        SELECT p.product_id, p.name, p.price, il.quantity
        FROM Products AS p
        INNER JOIN InventoryLevels AS il ON p.product_id = il.product_id
        WHERE il.quantity < 10
    ''')

    # View_RevenueBySupplier
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_RevenueBySupplier AS
        SELECT s.supplier_id, s.name, SUM(i.total_amount) AS total_revenue
        FROM Suppliers AS s
        LEFT JOIN Invoices AS i ON s.supplier_id = i.supplier_id
        GROUP BY s.supplier_id
    ''')

    # View_ExpiredInvoices
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ExpiredInvoices AS
        SELECT invoice_id, date, supplier_id, total_amount, due_date, payment_status
        FROM Invoices
        WHERE payment_status = 'Pending' AND due_date < DATE('now')
    ''')

    # View_BestSellingProducts
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_BestSellingProducts AS
        SELECT p.product_id, p.name, SUM(ii.quantity) AS total_quantity_sold
        FROM Products AS p
        INNER JOIN InvoiceItems AS ii ON p.product_id = ii.product_id
        GROUP BY p.product_id
        ORDER BY total_quantity_sold DESC
    ''')

    # View_OverdueInvoices
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_OverdueInvoices AS
        SELECT invoice_id, date, supplier_id, total_amount, due_date, payment_status
        FROM Invoices
        WHERE payment_status = 'Pending' AND due_date < DATE('now')
    ''')

    # View_TotalInventoryValue
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_TotalInventoryValue AS
        SELECT p.product_id, p.name, SUM(il.quantity * ii.unit_price) AS total_value
        FROM Products AS p
        INNER JOIN InventoryLevels AS il ON p.product_id = il.product_id
        INNER JOIN InvoiceItems AS ii ON p.product_id = ii.product_id
        GROUP BY p.product_id
    ''')

    # View_SuppliersWithMostInvoices
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_SuppliersWithMostInvoices AS
        SELECT s.supplier_id, s.name, COUNT(i.invoice_id) AS invoice_count
        FROM Suppliers AS s
        LEFT JOIN Invoices AS i ON s.supplier_id = i.supplier_id
        GROUP BY s.supplier_id
        ORDER BY invoice_count DESC
    ''')

    # View_OutOfStockProducts
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_OutOfStockProducts AS
        SELECT p.product_id, p.name, p.price
        FROM Products AS p
        LEFT JOIN InventoryLevels AS il ON p.product_id = il.product_id
        WHERE il.quantity = 0
    ''')

    # View_TopSuppliersByRevenue
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_TopSuppliersByRevenue AS
        SELECT s.supplier_id, s.name, SUM(i.total_amount) AS total_revenue
        FROM Suppliers AS s
        LEFT JOIN Invoices AS i ON s.supplier_id = i.supplier_id
        GROUP BY s.supplier_id
        ORDER BY total_revenue DESC
    ''')

    # View_ProductsWithDiscounts
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ProductsWithDiscounts AS
        SELECT p.product_id, p.name, ii.discount_percentage
        FROM Products AS p
        INNER JOIN InvoiceItems AS ii ON p.product_id = ii.product_id
        WHERE ii.discount_percentage > 0
    ''')

    # View_ActiveSuppliers
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ActiveSuppliers AS
        SELECT s.supplier_id, s.name, s.address, s.contact_number, s.email, s.preferred_payment_terms, s.lead_time
        FROM Suppliers AS s
        INNER JOIN Invoices AS i ON s.supplier_id = i.supplier_id
    ''')

    # View_TotalSalesByCategory
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_TotalSalesByCategory AS
        SELECT c.category_id, c.name, SUM(ii.quantity * ii.unit_price) AS total_sales
        FROM Categories AS c
        INNER JOIN Products AS p ON c.category_id = p.category_id
        INNER JOIN InvoiceItems AS ii ON p.product_id = ii.product_id
        GROUP BY c.category_id
    ''')

    # View_ExpiredProducts
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ExpiredProducts AS
        SELECT p.product_id, p.name, ii.due_date
        FROM Products AS p
        INNER JOIN InvoiceItems AS ii ON p.product_id = ii.product_id
        WHERE ii.due_date < DATE('now')
    ''')

    # Create the ProductPriceHistory view
    cursor.execute('''
        CREATE VIEW IF NOT EXISTS View_ProductPriceHistory AS
        SELECT p.product_id, p.name, ph.price, ph.date_changed
        FROM Products AS p
        INNER JOIN PriceHistory AS ph ON p.product_id = ph.product_id
    ''')

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS ProductInventoryView AS
        SELECT p.product_id, p.name, p.price, il.quantity, u.abbreviation, ROUND(p.price * il.quantity, 2) AS total_price
        FROM Products p
        JOIN InventoryLevels il ON p.product_id = il.product_id
        JOIN Units u ON p.unit_id = u.unit_id
        WHERE il.quantity > 0
    ''')

    cursor.execute('''
        CREATE VIEW IF NOT EXISTS InvoiceView AS
        SELECT i.invoice_id, i.date, s.name AS supplier_name, s.address AS supplier_address, i.total_amount, i.due_date, i.currency, i.payment_status
        FROM Invoices i
        JOIN Suppliers s ON i.supplier_id = s.supplier_id
    ''')

    # Commit the changes and close the connection
    conn.commit()
    conn.close()


def write_to_database(data, pdf_file, company_info, date):
    print (data, pdf_file, company_info)
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    company_address_str = f"{company_info['street']}, {company_info['zip_code']} {company_info['city']}"  # Concatenate the company information
    c.execute('SELECT * FROM Suppliers WHERE address=?', (company_address_str,))
    existing_Supplier = c.fetchone()
    if not existing_Supplier:
        c.execute('INSERT INTO Suppliers (name, address) VALUES (?, ?)',
                  (company_info['CompanyName'], company_address_str))
    
    c.execute('SELECT * FROM Suppliers WHERE address=?', (company_address_str,))
    existing_Supplier = c.fetchone()
    supplier_id = existing_Supplier[0]
    c.execute('INSERT INTO Invoices (date, supplier_id) VALUES (?, ?)',
                      (date, supplier_id))
    invoice_id = c.lastrowid

    total_amount = 0
    for item in data:
        total_amount += float(item['total_price'].replace(',', '.'))
        c.execute('SELECT * FROM Products WHERE name=?', (item['name'],))
        existing_item = c.fetchone()
        c.execute('SELECT unit_id FROM Units WHERE abbreviation=?', (item['unit'],))
        unit_id = c.fetchone()
        unit_id = unit_id[0]

        if existing_item:

            product_id = existing_item[0]
            c.execute('SELECT * FROM InventoryLevels WHERE product_id=?', (product_id,))
            existing_quantity = c.fetchone()
            existing_quantity = existing_quantity[2]

            new_quantity = float(item['quantity'].replace(',', '.'))
            new_unit_price = float(item['unit_price'].replace(',', '.'))

            merged_quantity = round(float(existing_quantity) + float(new_quantity), 3)


            c.execute('UPDATE Products SET price=? WHERE product_id=?',
                      (new_unit_price, product_id))
            c.execute('INSERT INTO PriceHistory (product_id, price) VALUES (?, ?)',
                      (product_id, new_unit_price))
            c.execute('UPDATE InventoryLevels SET quantity=? WHERE product_id=?',
                      (merged_quantity, product_id))

        else:
            quantity = float(item['quantity'].replace(',', '.'))
            price = float(item['unit_price'].replace(',', '.'))
            c.execute('INSERT INTO Products (name, price, unit_id) VALUES (?, ?, ?)',
                      (item['name'], price, unit_id))
            c.execute('SELECT product_id FROM Products WHERE name=?', (item['name'],))
            product_id = c.fetchone()
            product_id = product_id[0]
            c.execute('INSERT INTO PriceHistory (product_id, price) VALUES (?, ?)',
                      (product_id, price))
            c.execute('INSERT INTO InventoryLevels (product_id, quantity) VALUES (?, ?)',
                      (product_id, quantity))

        quantity = float(item['quantity'].replace(',', '.'))
        price = float(item['unit_price'].replace(',', '.'))
        c.execute('INSERT INTO InvoiceItems (invoice_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)',
                    (invoice_id, product_id, quantity, price))

    c.execute('UPDATE Invoices SET total_amount=? WHERE invoice_id=?',
                      (round(total_amount, 2), invoice_id))
    conn.commit()
    conn.close()




@app.route('/')
def index():
    return redirect('/items')

@app.route('/items')
def display_items():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('SELECT * FROM ProductInventoryView')
    data = c.fetchall()
    conn.close()
    headers = ['product_id', 'name', 'unit_price', 'quantity', 'unit', 'total_price']
    return render_template('index.html', view='items', headers=headers, data=data)

@app.route('/invoices')
def display_invoices():
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()

    c.execute('SELECT * FROM InvoiceView')

    data = c.fetchall()
    conn.close()

    headers = ['InvoiceID', 'Date', 'Supplier Name', 'Supplier Address', 'TotalAmount', 'DueDate', 'Currency', 'PaymentStatus']

    return render_template('index.html', view='invoices', headers=headers, data=data)


@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['pdf_file']
    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        process_pdf_file(file_path)
        os.remove(file_path)  # Delete the uploaded file after processing
    return redirect('/')

@app.route('/add_receipt', methods=['GET', 'POST'])
def add_receipt():
    if request.method == 'POST':
        items = []
        item_names = request.form.getlist('item_name[]')
        quantities = request.form.getlist('quantity[]')
        units = request.form.getlist('unit[]')
        unit_prices = request.form.getlist('unit_price[]')

        for i in range(len(item_names)):
            item_name = item_names[i]
            quantity = quantities[i]
            unit = units[i]
            unit_price = unit_prices[i]

            item = {
                'name': item_name,
                'quantity': quantity,
                'unit': unit,
                'unit_price': unit_price,
                'total_price': str(float(quantity.replace(',', '.')) * float(unit_price.replace(',', '.')))
            }
            items.append(item)

        company_info = {
            'CompanyName': request.form.get('company_name'),
            'street': request.form.get('street'),
            'zip_code': request.form.get('zip_code'),
            'city': request.form.get('city')
        }
        date = datetime.datetime.now().strftime("%d.%m.%Y")

        write_to_database(items, '', company_info, date)

        return redirect('/items')
    else:
        return render_template('index.html', view='add_receipt')



@app.route('/reduce', methods=['POST'])
def reduce_quantity():
    product_id = request.form['product_id']
    reduce_amount = request.form['reduce_amount'].replace('.', ',')

    try:
        reduce_amount = float(reduce_amount.replace(',', '.'))
    except ValueError:
        # Handle invalid input, such as non-numeric characters
        return "Invalid reduce amount"

    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('SELECT quantity FROM InventoryLevels WHERE product_id=?', (product_id,))
    result = c.fetchone()
    quantity = result[0]

    new_quantity = round(float(quantity) - reduce_amount, 3)

    if new_quantity <= 0:
        c.execute('UPDATE InventoryLevels SET quantity=? WHERE product_id=?', (0, product_id))
    else:

        c.execute('UPDATE InventoryLevels SET quantity=? WHERE product_id=?', (new_quantity, product_id))

    conn.commit()
    conn.close()
    return redirect('/')




@app.route('/delete', methods=['POST'])
def delete_item():
    product_id = request.form['product_id']

    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    c.execute('UPDATE InventoryLevels SET quantity=? WHERE product_id=?', (0, product_id))
    conn.commit()
    conn.close()
    return redirect('/')



def process_pdf_file(file_path):
    with pdfplumber.open(file_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
        company_info, items, date = extract_data(text)
        for item in items:
            if 'quantity' not in item:
                item['quantity'] = '1'
                item['unit'] = 'Stk'
                item['unit_price'] = item['total_price']
        data = items
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = os.path.basename(file_path)
        pdf_file = f"{filename} ({timestamp})"
        write_to_database(data, pdf_file, company_info, date)




UPLOAD_FOLDER = './upload_folder'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
create_table()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80)
