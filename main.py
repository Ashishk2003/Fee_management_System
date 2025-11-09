
import sys
import os
import sqlite3
from datetime import datetime
import tempfile
import shutil
import webbrowser
import platform

from PyQt5 import QtWidgets, QtGui, QtCore
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

# --- Constants / Setup ---
DB_FILE = "college_fee.db"
PHOTO_DIR = "student_photos"
os.makedirs(PHOTO_DIR, exist_ok=True)

# --- Database helpers ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            student_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            class TEXT,
            total_fee REAL NOT NULL,
            photo_path TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            receipt_no INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            amount_paid REAL,
            payment_date TEXT,
            mode_of_payment TEXT,
            FOREIGN KEY(student_id) REFERENCES students(student_id)
        )
    ''')
    conn.commit()
    conn.close()

def add_student_db(student_id, name, student_class, total_fee, photo_path):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO students (student_id, name, class, total_fee, photo_path) VALUES (?,?,?,?,?)",
              (student_id, name, student_class, total_fee, photo_path))
    conn.commit()
    conn.close()

def get_student(student_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT student_id, name, class, total_fee, photo_path FROM students WHERE student_id=?", (student_id,))
    row = c.fetchone()
    conn.close()
    return row

def add_payment_db(student_id, amount_paid, payment_date, mode):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO payments (student_id, amount_paid, payment_date, mode_of_payment) VALUES (?,?,?,?)",
              (student_id, amount_paid, payment_date, mode))
    conn.commit()
    receipt_no = c.lastrowid
    conn.close()
    return receipt_no

def get_last_payment(student_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT receipt_no, student_id, amount_paid, payment_date, mode_of_payment FROM payments WHERE student_id=? ORDER BY receipt_no DESC LIMIT 1", (student_id,))
    row = c.fetchone()
    conn.close()
    return row

def get_total_paid(student_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT SUM(amount_paid) FROM payments WHERE student_id=?", (student_id,))
    row = c.fetchone()
    conn.close()
    return row[0] or 0.0

def get_total_due(student_id):
    # Get total paid
    total_paid = get_total_paid(student_id) or 0.0

    # Get total fee
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT total_fee FROM students WHERE student_id=?", (student_id,))
        result = c.fetchone()
        if result is None:
            return None  # student not found
        total_fee = result[0]

    total_due = total_fee - total_paid
    return total_due


# --- Utility to open PDF cross-platform ---
def open_file(path):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess_call = ["open", path]
            os.system(" ".join(subprocess_call))
        else:
            # linux/unix
            os.system(f"xdg-open \"{path}\"")
    except Exception:
        # fallback to webbrowser
        webbrowser.open_new(path)

# --- Receipt PDF generator ---
def generate_receipt_pdf(student_id, receipt_no, student, payment):
    """
    student: tuple(student_id, name, class, total_fee, photo_path)
    payment: tuple(receipt_no, student_id, amount_paid, payment_date, mode)
    """
    # Prepare data
    sid, name, sclass, total_fee, photo_path = student
    receipt_no, _, amount_paid, payment_date, mode = payment
    total_paid = get_total_paid(student_id)
    remaining = float(total_fee) - float(total_paid)

    RECEIPT_DIR = "receipts"
    os.makedirs(RECEIPT_DIR, exist_ok=True)
    # File name
    safe_name = "".join(ch for ch in name if ch.isalnum() or ch in (" ", "_")).strip().replace(" ", "_")
    pdf_filename = os.path.join(RECEIPT_DIR, f"Receipt_{sid}_{receipt_no}.pdf")    # Create PDF
    width, height = A4
    c = canvas.Canvas(pdf_filename, pagesize=A4)

    margin_x = 20
    y = height - 35
# Colored header first
    c.setFillColorRGB(0.2, 0.5, 0.9)  # blue
    header_height = 30
    c.rect(0, y - header_height + 10, width, header_height, fill=1)

# Title text in white
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width/2, y - 12, "FEE RECEIPT")

# Reset text color to black
    c.setFillColorRGB(0, 0, 0)

# Now draw student details
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x, y - header_height - 20, f"Student Name: {name}")
    c.drawString(margin_x, y - header_height - 37, f"Student ID: {sid}")
    c.drawString(margin_x, y - header_height - 54, f"Class: {sclass}")

# Reset text color to black for rest
    c.setFillColorRGB(0, 0, 0)

    # Student photo on top-right (resize to fit)
    photo_w = 110
    photo_h = 110
    photo_x = width - margin_x - photo_w
    photo_y = y - photo_h - 25

    if photo_path and os.path.exists(photo_path):
        try:
            # Resize the image to fit nicely (use a temp file)
            im = Image.open(photo_path)
            im.thumbnail((photo_w, photo_h))
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            im.save(tf.name, format="PNG")
            tf.close()
            c.drawImage(tf.name, photo_x, photo_y, width=photo_w, height=photo_h)
            os.unlink(tf.name)
        except Exception:
            pass

   # Table settings
    table_top = y - 160
    row_height = 25
    col_widths = [120, 140, 120, 120]  # widths of columns
    cols = ["Receipt No", "Amount Paid (Rs.)", "Date", "Mode of Payment"]

# Draw table header with black border
    c.setFont("Helvetica-Bold", 12)
    x = margin_x
    for i, col in enumerate(cols):
        w = col_widths[i]
        c.rect(x, table_top - row_height, w, row_height, fill=0)  # draw cell
        c.drawCentredString(x + w/2, table_top - row_height + 7, col)  # centered text
        x += w

# Draw the payment values row
    c.setFont("Helvetica", 12)
    x  = margin_x
    row_values = [str(receipt_no), f"{amount_paid:.2f}", str(payment_date), str(mode)]
    for i, val in enumerate(row_values):
        w = col_widths[i]
        c.rect(x, table_top - 2*row_height, w, row_height, fill=0)  # draw cell
        c.drawCentredString(x + w/2, table_top - 2*row_height + 7, val)
        x += w

    # Bottom summary: total fee, total paid, remaining, printed on
    bottom_y = table_top - 80
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_x, bottom_y, f"Total Fee: Rs. {float(total_fee):.2f}")
    c.drawString(margin_x, bottom_y - 20, f"Total Paid: Rs. {float(total_paid):.2f}")
    c.drawString(margin_x, bottom_y - 40, f"Remaining Fee Due: Rs. {float(remaining):.2f}")
    c.drawString(margin_x, bottom_y - 60, f"Receipt Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Optional signature line
   # c.line(width - 220, bottom_y - 60, width - 40, bottom_y - 60)
    #c.setFont("Helvetica", 10)
    #c.drawString(width - 210, bottom_y - 75, "Authorized Signatory")

    c.showPage()
    c.save()
    return pdf_filename

# --- PyQt5 GUI ---
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("College Fee Management System")
        self.setGeometry(200, 100, 900, 550)
        self.central = QtWidgets.QWidget()
        self.setCentralWidget(self.central)
        self.layout = QtWidgets.QVBoxLayout(self.central)

        # Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.layout.addWidget(self.tabs)

        self.tab_add_student = QtWidgets.QWidget()
        self.tab_record_payment = QtWidgets.QWidget()
        self.tab_view = QtWidgets.QWidget()

        self.tabs.addTab(self.tab_add_student, "Add / Edit Student")
        self.tabs.addTab(self.tab_record_payment, "Record Payment")
        self.tabs.addTab(self.tab_view, "View / Search")

        self.init_add_student_tab()
        self.init_record_payment_tab()
        self.init_view_tab()

    # --- Add student tab ---
    def init_add_student_tab(self):
        layout = QtWidgets.QFormLayout(self.tab_add_student)

        self.input_sid = QtWidgets.QLineEdit()
        self.input_name = QtWidgets.QLineEdit()
        self.input_class = QtWidgets.QLineEdit()
        self.input_total_fee = QtWidgets.QLineEdit()
        self.input_total_fee.setValidator(QtGui.QDoubleValidator(0.0, 99999999.0, 2))
        self.photo_label = QtWidgets.QLabel()
        self.photo_label.setFixedSize(130, 130)
        self.photo_label.setFrameShape(QtWidgets.QFrame.Box)
        self.photo_label.setAlignment(QtCore.Qt.AlignCenter)
        self.photo_path = None

        btn_browse = QtWidgets.QPushButton("Browse Photo")
        btn_browse.clicked.connect(self.browse_photo)
        btn_save = QtWidgets.QPushButton("Save Student")
        btn_save.clicked.connect(self.save_student)

        layout.addRow("Student ID:", self.input_sid)
        layout.addRow("Name:", self.input_name)
        layout.addRow("Class:", self.input_class)
        layout.addRow("Total Fee (₹):", self.input_total_fee)
        h = QtWidgets.QHBoxLayout()
        h.addWidget(self.photo_label)
        col = QtWidgets.QVBoxLayout()
        col.addWidget(btn_browse)
        col.addStretch()
        h.addLayout(col)
        layout.addRow("Photo:", h)
        layout.addRow(btn_save)

    def browse_photo(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select Student Photo", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            # show preview
            pix = QtGui.QPixmap(path)
            pix = pix.scaled(self.photo_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.photo_label.setPixmap(pix)
            # copy file to photo dir with standardized name
            self.photo_path_temp = path
            self.photo_path = path

    def save_student(self):
        sid = self.input_sid.text().strip()
        name = self.input_name.text().strip()
        sclass = self.input_class.text().strip()
        total_fee_text = self.input_total_fee.text().strip()
        if not sid or not name or not total_fee_text:
            QtWidgets.QMessageBox.warning(self, "Validation", "Student ID, Name and Total Fee are required.")
            return
        try:
            total_fee = float(total_fee_text)
        except:
            QtWidgets.QMessageBox.warning(self, "Validation", "Provide a valid numeric Total Fee.")
            return

        # Save/copy photo into PHOTO_DIR named by student id
        photo_dest = None
        if getattr(self, "photo_path", None):
            ext = os.path.splitext(self.photo_path)[1]
            photo_dest = os.path.join(PHOTO_DIR, f"{sid}{ext}")
            try:
                shutil.copy2(self.photo_path, photo_dest)
            except Exception as e:
                QtWidgets.QMessageBox.warning(self, "Photo Error", f"Could not copy photo: {e}")
                photo_dest = None

        add_student_db(sid, name, sclass, total_fee, photo_dest)
        QtWidgets.QMessageBox.information(self, "Saved", f"Student {name} ({sid}) saved.")
        # clear inputs
        self.input_sid.clear()
        self.input_name.clear()
        self.input_class.clear()
        self.input_total_fee.clear()
        self.photo_label.clear()
        self.photo_path = None

    # --- Record payment tab ---
    def init_record_payment_tab(self):
        layout = QtWidgets.QFormLayout(self.tab_record_payment)

        self.p_sid = QtWidgets.QLineEdit()
        self.p_amount = QtWidgets.QLineEdit()
        self.p_mode = QtWidgets.QComboBox()
        self.p_mode.addItems(["Cash", "Cheque", "UPI", "Online", "Bank Transfer", "Other"])
        btn_fetch = QtWidgets.QPushButton("Fetch Student")
        btn_fetch.clicked.connect(self.fetch_student_for_payment)
        btn_pay = QtWidgets.QPushButton("Record Payment & Generate Receipt")
        btn_pay.clicked.connect(self.record_payment_and_receipt)

        self.p_student_info = QtWidgets.QLabel("Student info will appear here.")
        self.p_student_info.setWordWrap(True)

        layout.addRow("Student ID:", self.p_sid)
        layout.addRow(btn_fetch)
        layout.addRow(self.p_student_info)
        layout.addRow("Amount Paid (₹):", self.p_amount)
        layout.addRow("Mode of Payment:", self.p_mode)
        layout.addRow(btn_pay)

    def fetch_student_for_payment(self):
        sid = self.p_sid.text().strip()
        if not sid:
            QtWidgets.QMessageBox.warning(self, "Input", "Enter Student ID.")
            return
        student = get_student(sid)
        if not student:
            QtWidgets.QMessageBox.warning(self, "Not found", "Student not found in database.")
            return
        sid, name, sclass, total_fee, photo_path = student
        total_paid = get_total_paid(sid)
        remain = float(total_fee) - float(total_paid)
        self.current_student = student
        self.p_student_info.setText(f"Name: {name}\nClass: {sclass}\nTotal Fee: ₹{total_fee:.2f}\nTotal Paid: ₹{total_paid:.2f}\nRemaining: ₹{remain:.2f}")

    def record_payment_and_receipt(self):
        if not getattr(self, "current_student", None):
            QtWidgets.QMessageBox.warning(self, "No student", "Fetch the student first.")
            return
        sid = self.current_student[0]
        amt_text = self.p_amount.text().strip()
        if not amt_text:
            QtWidgets.QMessageBox.warning(self, "Input", "Enter payment amount.")
            return
        try:
            amt = float(amt_text)
        except:
            QtWidgets.QMessageBox.warning(self, "Input", "Enter numeric amount.")
            return
        remaining_fee = get_total_due(sid)
        if amt > remaining_fee:
            QtWidgets.QMessageBox.warning(
            self, 
            "Invalid Payment", 
            f"Payment exceeds remaining fee of ₹{remaining_fee:.2f}."
            )
            return
        mode = self.p_mode.currentText()
        payment_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # insert payment
        receipt_no = add_payment_db(sid, amt, payment_date, mode)
        payment = get_last_payment(sid)
        pdf_file = generate_receipt_pdf(sid, receipt_no, self.current_student, payment)
        QtWidgets.QMessageBox.information(self, "Success", f"Payment recorded. Receipt: {pdf_file}")
        # auto-open pdf
        open_file(os.path.abspath(pdf_file))
        # clear payment inputs
        self.p_amount.clear()
        self.p_student_info.setText("Student info will appear here.")
        self.p_sid.clear()
        self.current_student = None

    # --- View / Search tab ---
    def init_view_tab(self):
        layout = QtWidgets.QVBoxLayout(self.tab_view)
        h = QtWidgets.QHBoxLayout()
        self.search_sid = QtWidgets.QLineEdit()
        self.search_sid.setPlaceholderText("Enter Student ID")
        btn_search = QtWidgets.QPushButton("Search")
        btn_search.clicked.connect(self.search_student)
        h.addWidget(self.search_sid)
        h.addWidget(btn_search)
        layout.addLayout(h)

        self.search_result = QtWidgets.QTextBrowser()
        layout.addWidget(self.search_result)

        # Table of payments
        self.payments_table = QtWidgets.QTableWidget()
        self.payments_table.setColumnCount(5)
        self.payments_table.setHorizontalHeaderLabels(["Receipt No", "Student ID", "Amount", "Date", "Mode"])
        self.payments_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.payments_table)

    def search_student(self):
        sid = self.search_sid.text().strip()
        if not sid:
            QtWidgets.QMessageBox.warning(self, "Input", "Enter Student ID to search.")
            return
        student = get_student(sid)
        if not student:
            QtWidgets.QMessageBox.information(self, "Not Found", "No student found.")
            return
        sid, name, sclass, total_fee, photo_path = student
        total_paid = get_total_paid(sid)
        remain = float(total_fee) - float(total_paid)
        info = f"Name: {name}\nStudent ID: {sid}\nClass: {sclass}\nTotal Fee: ₹{total_fee:.2f}\nTotal Paid: ₹{total_paid:.2f}\nRemaining: ₹{remain:.2f}\nPhoto Path: {photo_path}\n"
        self.search_result.setPlainText(info)

        # populate payments table
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT receipt_no, student_id, amount_paid, payment_date, mode_of_payment FROM payments WHERE student_id=? ORDER BY receipt_no DESC", (sid,))
        rows = c.fetchall()
        conn.close()
        self.payments_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for col, val in enumerate(row):
                item = QtWidgets.QTableWidgetItem(str(val))
                self.payments_table.setItem(r, col, item)

# --- main ---
def main():
    init_db()
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
