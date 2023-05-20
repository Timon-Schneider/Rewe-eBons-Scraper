import re
import os
import pdfplumber
from tabulate import tabulate
from flask import Flask, render_template, request, redirect
from flask import url_for
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)

def extract_data(text):
    lines = text.split('\n')
    items = []
    current_item = None
    for line in lines:
        if re.match(r'^-+$', line.strip()):
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
            current_item = {'name': item_match.group(1).strip(), 'total_price': item_match.group(2)}
            items.append(current_item)
    return items

def create_table():
    conn = sqlite3.connect('receipts.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS items
                 (name text, total_price text, quantity text, unit text, unit_price text)''')
    conn.commit()
    conn.close()

def write_to_database(data):
    conn = sqlite3.connect('receipts.db')
    c = conn.cursor()

    for item in data:
        c.execute('SELECT * FROM items WHERE name=?', (item['name'],))
        existing_item = c.fetchone()

        if existing_item:
            existing_quantity = existing_item[2].replace('.', ',')
            existing_total_price = existing_item[1].replace('.', ',')
            existing_unit_price = existing_item[4].replace('.', ',')

            new_quantity = item['quantity'].replace('.', ',')
            new_total_price = item['total_price'].replace('.', ',')
            new_unit_price = item['unit_price'].replace('.', ',')

            merged_quantity = float(existing_quantity.replace(',', '.')) + float(new_quantity.replace(',', '.'))
            merged_total_price = float(existing_total_price.replace(',', '.')) + float(new_total_price.replace(',', '.'))

            merged_quantity_str = str(round(merged_quantity, 3)).replace('.', ',') if merged_quantity % 1 != 0 else str(int(merged_quantity))
            merged_total_price_str = str(merged_total_price).replace('.', ',') if merged_total_price % 1 != 0 else str(int(merged_total_price))

            c.execute('UPDATE items SET total_price=?, quantity=?, unit_price=? WHERE name=?',
                      (merged_total_price_str, merged_quantity_str, new_unit_price, item['name']))
        else:
            quantity = item['quantity'].replace('.', ',')
            c.execute('INSERT INTO items VALUES (?, ?, ?, ?, ?)',
                      (item['name'], item['total_price'], quantity, item['unit'], item['unit_price']))

    conn.commit()
    conn.close()


@app.route('/')
def display_items():
    conn = sqlite3.connect('receipts.db')
    c = conn.cursor()
    c.execute('SELECT * FROM items')
    data = c.fetchall()
    conn.close()
    headers = ['name', 'total_price', 'quantity', 'unit', 'unit_price']
    return render_template('index.html', headers=headers, data=data)

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

@app.route('/reduce', methods=['POST'])
def reduce_quantity():
    name = request.form['name']
    reduce_amount = request.form['reduce_amount'].replace('.', ',')

    try:
        reduce_amount = float(reduce_amount.replace(',', '.'))
    except ValueError:
        # Handle invalid input, such as non-numeric characters
        return "Invalid reduce amount"

    conn = sqlite3.connect('receipts.db')
    c = conn.cursor()
    c.execute('SELECT quantity, unit_price, total_price FROM items WHERE name=?', (name,))
    result = c.fetchone()
    quantity = result[0]
    unit_price = float(result[1].replace(',', '.'))
    total_price = float(result[2].replace(',', '.'))

    new_quantity = round(float(quantity.replace(',', '.')) - reduce_amount, 3)

    if new_quantity <= 0:
        c.execute('DELETE FROM items WHERE name=?', (name,))
    else:
        new_total_price = round(total_price - (reduce_amount * unit_price), 3)
        new_total_price_str = str(new_total_price).replace('.', ',') if new_total_price % 1 != 0 else str(int(new_total_price))
        new_quantity_str = str(round(new_quantity, 3)).replace('.', ',') if new_quantity % 1 != 0 else str(int(new_quantity))
        c.execute('UPDATE items SET quantity=?, total_price=? WHERE name=?', (new_quantity_str, new_total_price_str, name))

    conn.commit()
    conn.close()
    return redirect('/')


@app.route('/delete', methods=['POST'])
def delete_item():
    name = request.form['name']

    conn = sqlite3.connect('receipts.db')
    c = conn.cursor()
    c.execute('DELETE FROM items WHERE name=?', (name,))
    conn.commit()
    conn.close()
    return redirect('/')



def process_pdf_file(file_path):
    with pdfplumber.open(file_path) as pdf:
        text = ""
        for page in pdf.pages:
            text += page.extract_text()
        items = extract_data(text)
        for item in items:
            if 'quantity' not in item:
                item['quantity'] = '1'
                item['unit'] = 'Stk'
                item['unit_price'] = item['total_price']
        data = items
        write_to_database(data)


UPLOAD_FOLDER = './upload_folder'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
create_table()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80)
