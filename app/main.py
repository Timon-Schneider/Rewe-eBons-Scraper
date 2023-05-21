import datetime
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
    c.execute("PRAGMA foreign_keys = ON")
    c.execute('''CREATE TABLE IF NOT EXISTS items
                 (name text PRIMARY KEY, total_price text, quantity text, unit text, unit_price text)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS changes
             (ChangeID INTEGER PRIMARY KEY AUTOINCREMENT, ItemName text,
             ChangeDate text, ChangeQuantity text, NewQuantity text,
             Oldtotal_price text, Newtotal_price text, Oldunit_price text, 
             Newunit_price text, unit text, pdf_file text,
             FOREIGN KEY (ItemName) REFERENCES items(name))''')



    conn.commit()
    conn.close()


def write_to_database(data, pdf_file):
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

            merged_quantity = round(float(existing_quantity.replace(',', '.')) + float(new_quantity.replace(',', '.')), 3)
            merged_total_price = round(float(existing_total_price.replace(',', '.')) + float(new_total_price.replace(',', '.')), 3)

            merged_quantity_str = str(round(merged_quantity, 3)).replace('.', ',') if merged_quantity % 1 != 0 else str(int(merged_quantity))
            merged_total_price_str = str(merged_total_price).replace('.', ',') if merged_total_price % 1 != 0 else str(int(merged_total_price))

            Oldtotal_price = existing_total_price
            Newtotal_price = new_total_price
            Oldunit_price = existing_unit_price
            Newunit_price = new_unit_price
            unit = item['unit']

            c.execute('UPDATE items SET total_price=?, quantity=?, unit_price=? WHERE name=?',
                  (merged_total_price_str, merged_quantity_str, new_unit_price, item['name']))
            c.execute('INSERT INTO changes (ItemName, ChangeDate, ChangeQuantity, NewQuantity, Oldtotal_price, Newtotal_price, Oldunit_price, Newunit_price, unit, pdf_file) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)',
                  (item['name'], new_quantity, merged_quantity_str, Oldtotal_price, Newtotal_price, Oldunit_price, Newunit_price, unit, pdf_file))
        else:
            quantity = item['quantity'].replace('.', ',')
            c.execute('INSERT INTO items VALUES (?, ?, ?, ?, ?)',
                      (item['name'], item['total_price'], quantity, item['unit'], item['unit_price']))

            # Log the change in the "changes" table
            c.execute('INSERT INTO changes (ItemName, ChangeDate, ChangeQuantity, NewQuantity, Newtotal_price, Newunit_price, unit, pdf_file) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)',
                    (item['name'], quantity, quantity, item['total_price'], item['unit_price'], item['unit'], pdf_file))

    conn.commit()
    conn.close()



@app.route('/')
def index():
    return redirect('/items')

@app.route('/items')
def display_items():
    conn = sqlite3.connect('receipts.db')
    c = conn.cursor()
    c.execute('SELECT * FROM items')
    data = c.fetchall()
    conn.close()
    headers = ['name', 'total_price', 'quantity', 'unit', 'unit_price']
    return render_template('index.html', view='items', headers=headers, data=data)

@app.route('/changes')
def display_changes():
    conn = sqlite3.connect('receipts.db')
    c = conn.cursor()

    c.execute('SELECT DISTINCT pdf_file FROM changes')
    pdf_files = [row[0] for row in c.fetchall()]

    filter_value = request.args.get('filter')

    if filter_value:
        c.execute('SELECT * FROM changes WHERE pdf_file=?', (filter_value,))
    else:
        c.execute('SELECT * FROM changes')

    data = c.fetchall()
    conn.close()

    headers = ['ChangeID', 'ItemName', 'ChangeDate', 'ChangeQuantity', 'NewQuantity', 'Oldtotal_price', 'Newtotal_price', 'Oldunit_price', 'Newunit_price', 'unit', 'pdf_file']


    return render_template('index.html', view='changes', headers=headers, data=data, pdf_files=pdf_files, filter_value=filter_value)


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
    c.execute('SELECT quantity, unit_price, total_price, unit FROM items WHERE name=?', (name,))
    result = c.fetchone()
    quantity = result[0]
    unit_price = float(result[1].replace(',', '.'))
    total_price = float(result[2].replace(',', '.'))

    Oldtotal_price = str(total_price).replace('.', ',') if total_price % 1 != 0 else str(int(total_price))
    Oldunit_price = str(unit_price).replace('.', ',') if unit_price % 1 != 0 else str(int(unit_price))

    new_quantity = round(float(quantity.replace(',', '.')) - reduce_amount, 3)

    if new_quantity <= 0:
        c.execute('DELETE FROM items WHERE name=?', (name,))
        c.execute('INSERT INTO changes (ItemName, ChangeDate, ChangeQuantity, NewQuantity, Oldtotal_price, Oldunit_price, Newtotal_price, Newunit_price, unit, pdf_file) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)',
                  (name, -abs(reduce_amount), "0", Oldtotal_price, Oldunit_price, "0", "0", "", "user"))
    else:
        new_total_price = round(total_price - (reduce_amount * unit_price), 3)
        new_total_price_str = str(new_total_price).replace('.', ',') if new_total_price % 1 != 0 else str(int(new_total_price))
        new_quantity_str = str(round(new_quantity, 3)).replace('.', ',') if new_quantity % 1 != 0 else str(int(new_quantity))
        Newtotal_price = new_total_price_str
        Newunit_price = Oldunit_price
        unit = result[3]

        c.execute('UPDATE items SET quantity=?, total_price=? WHERE name=?', (new_quantity_str, new_total_price_str, name))

        # Log the change in the "changes" table
        c.execute('INSERT INTO changes (ItemName, ChangeDate, ChangeQuantity, NewQuantity, Oldtotal_price, Oldunit_price, Newtotal_price, Newunit_price, unit, pdf_file) VALUES (?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?)',
                  (name, -abs(reduce_amount), new_quantity_str, Oldtotal_price, Oldunit_price, Newtotal_price, Newunit_price, unit, "user"))

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
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filename = os.path.basename(file_path)
        pdf_file = f"{filename} ({timestamp})"
        write_to_database(data, pdf_file)



UPLOAD_FOLDER = './upload_folder'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
create_table()

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=80)
