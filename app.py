from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import urllib.parse
import json
import os
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask import request, redirect, url_for, flash
from flask_login import login_user
from functools import wraps
from sqlalchemy import func
import os
from dotenv import load_dotenv # Add this

load_dotenv()

app = Flask(__name__)

# Get the directory where app.py is located
basedir = os.path.abspath(os.path.dirname(__file__))
# --- CONFIGURATION ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'shop.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# --- ADMIN CONFIGURATION ---
ADMIN_USERNAME = os.environ.get('ADMIN_USER')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASS')

# Initialize Extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # Redirects here if user tries to access restricted page

# --- DATABASE MODELS ---

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)     # Total stock ever purchased
    purchase_price = db.Column(db.Float, nullable=False) # Buying price
    sale_price = db.Column(db.Float, nullable=False)     # Selling price
    date_added = db.Column(db.Date, default=date.today)
    
    # Link to User (Owner)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # Link to Sales
    sales = db.relationship('Sale', backref='product', lazy=True, cascade="all, delete-orphan")

    @property
    def items_sold(self):
        return sum(sale.quantity_sold for sale in self.sales)

    @property
    def remaining(self):
        return self.quantity - self.items_sold

    @property
    def profit_per_item(self):
        return self.sale_price - self.purchase_price
    
    @property
    def total_profit_generated(self):
        return self.profit_per_item * self.items_sold

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity_sold = db.Column(db.Integer, nullable=False)
    sale_date = db.Column(db.Date, default=date.today)

class Loan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    product_taken = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.now)
    # 0 = Unpaid, 1 = Paid
    status = db.Column(db.Integer, default=0)
    
    # Link to User (Owner)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# --- LOAD USER ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Initialize Database
with app.app_context():
    db.create_all()

# --- ROUTES ---



from functools import wraps
from sqlalchemy import func

# --- ADMIN DECORATOR ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash("Admin access required.", "danger")
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ADMIN ROUTES ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and \
           request.form.get('password') == ADMIN_PASSWORD:
            session['is_admin'] = True
            flash("Welcome to the Master Admin Panel", "success")
            return redirect(url_for('admin_dashboard'))
        flash("Invalid Admin Credentials", "danger")
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    stats = {
        'users_count': User.query.count(),
        'products_count': Product.query.count(),
        'total_sales_count': Sale.query.count(),
        'total_loans_count': Loan.query.count(),
        # Calculate Global Revenue and Profit
        'total_revenue': db.session.query(func.sum(Sale.quantity_sold * Product.sale_price)).join(Product).scalar() or 0,
        'total_profit': db.session.query(func.sum(Sale.quantity_sold * (Product.sale_price - Product.purchase_price))).join(Product).scalar() or 0
    }
    return render_template('admin_dashboard.html', stats=stats)

@app.route('/admin/users')
@admin_required
def admin_users():
    # Query users and count their related items
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/user/<int:user_id>')
@admin_required
def admin_user_detail(user_id):
    user = User.query.get_or_404(user_id)
    user_products = Product.query.filter_by(user_id=user.id).all()
    user_loans = Loan.query.filter_by(user_id=user.id).all()
    return render_template('admin_user_detail.html', user=user, products=user_products, loans=user_loans)





@app.route('/admin/toggle_user/<int:user_id>')
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    # Prevent admin from deactivating themselves if they are in the User table
    user.is_active = not user.is_active
    db.session.commit()
    status = "activated" if user.is_active else "deactivated"
    flash(f"User {user.username} has been {status}.", "info")
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # This will also delete their products/loans if you have cascade="all, delete-orphan"
    db.session.delete(user)
    db.session.commit()
    
    flash(f"User {user.username} and all their data have been permanently deleted.", "warning")
    return redirect(url_for('admin_users'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if user already exists
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        
        if existing_user:
            flash('Username or Email already registered!', 'error')
            return redirect(url_for('register'))

        # Create new user and hash the password
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        # request.form.get('remember') returns 'on' if checked, else None
        remember_me = True if request.form.get('remember') else False

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, send them to dashboard
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        # Get data from the form
        identity = request.form.get('login_identity')  # Matches the 'name' in your HTML
        password = request.form.get('password')
        
        # Check if "Remember Me" was checked (returns 'on' if checked, else None)
        remember_me = True if request.form.get('remember') else False

        # 1. Look for user by Username OR Email
        user = User.query.filter((User.username == identity) | (User.email == identity)).first()

        # 2. Verify password
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash("Your account has been deactivated by the admin.", "danger")
                return redirect(url_for('login'))
            # The 'remember' parameter creates a long-term cookie in the browser
            login_user(user, remember=remember_me)
            
            flash("Welcome back to TuckShop Pro!", "success")
            
            # Redirect to the page they were trying to access, or dashboard
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash("Login failed. Please check your username/email and password.", "danger")

    return render_template('login.html')
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/add_rate', methods=['POST'])
@login_required
def add_rate():
    # 1. Get data from form - ADDED 'category' HERE
    new_entry = {
        "name": request.form.get('name'),
        "price": float(request.form.get('price')), # Convert to float/int
        "unit": request.form.get('unit'),
        "category": request.form.get('category'), # <--- THIS WAS MISSING
        "trend": request.form.get('trend'),
        "date": date.today().strftime('%Y-%m-%d')
    }

    json_path = os.path.join(app.root_path, 'static', 'rates.json')

    try:
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                rates_list = json.load(f)
        else:
            rates_list = []

        rates_list.insert(0, new_entry) 
        with open(json_path, 'w') as f:
            json.dump(rates_list, f, indent=4)
        
        flash("Rate added successfully!", "success")
    except Exception as e:
        flash(f"Error saving rate: {e}", "error")

    return redirect(url_for('rates'))


@app.route('/delete_rate/<int:index>')
@login_required
def delete_rate(index):
    # Path to your JSON file
    json_path = os.path.join(app.root_path, 'static', 'rates.json')
    
    try:
        if os.path.exists(json_path):
            # 1. Read the current rates
            with open(json_path, 'r') as f:
                rates_list = json.load(f)
            
            # 2. Remove the item using the index passed from HTML
            if 0 <= index < len(rates_list):
                rates_list.pop(index)
                
                # 3. Save the updated list back to the file
                with open(json_path, 'w') as f:
                    json.dump(rates_list, f, indent=4)
                flash("Rate deleted successfully!", "info")
            else:
                flash("Error: Item index not found.", "error")
        else:
            flash("Error: rates.json file is missing.", "error")
            
    except Exception as e:
        flash(f"An error occurred: {e}", "error")

    # 4. Go back to the rates page
    return redirect(url_for('rates'))

@app.route('/')
@login_required
def dashboard():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    analytics_data = None
    
    # FILTER: Only get products for the current logged-in user
    products = Product.query.filter_by(user_id=current_user.id).order_by(Product.date_added.desc()).all()

    if start_date and end_date:
        try:
            s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            
            # Find IDs of products owned by this user
            my_product_ids = [p.id for p in products]

            # Filter sales that belong to those products AND are within date range
            filtered_sales = Sale.query.filter(
                Sale.sale_date.between(s_date, e_date),
                Sale.product_id.in_(my_product_ids)
            ).all()
            
            if filtered_sales:
                stats = {}
                for s in filtered_sales:
                    if s.product_id not in stats:
                        stats[s.product_id] = {'sold': 0, 'profit': 0, 'obj': s.product}
                    stats[s.product_id]['sold'] += s.quantity_sold
                    stats[s.product_id]['profit'] += (s.quantity_sold * s.product.profit_per_item)

                best_seller_id = max(stats, key=lambda x: stats[x]['sold'])
                best_profit_id = max(stats, key=lambda x: stats[x]['profit'])

                analytics_data = {
                    'total_sold': sum(s.quantity_sold for s in filtered_sales),
                    'total_revenue': sum(s.quantity_sold * s.product.sale_price for s in filtered_sales),
                    'net_profit': sum(s.quantity_sold * s.product.profit_per_item for s in filtered_sales),
                    'most_profitable': stats[best_profit_id]['obj'],
                    'highest_margin': max(products, key=lambda p: p.profit_per_item) if products else None
                }
            else:
                analytics_data = 'empty'
        except ValueError:
            analytics_data = 'empty'

    return render_template('dashboard.html', products=products, analytics=analytics_data, s_date=start_date, e_date=end_date)

@app.route('/products')
@login_required
def products():
    # FILTER: Only show my products
    all_products = Product.query.filter_by(user_id=current_user.id).order_by(Product.date_added.desc()).all()
    return render_template('products.html', products=all_products)

@app.route('/add_product', methods=['POST'])
@login_required
def add_product():
    # 1. Get data from the form
    name = request.form.get('name')
    p_price = request.form.get('purchase_price')
    s_price = request.form.get('sale_price')
    qty = request.form.get('quantity')

    # 2. VALIDATION: Check if any field is empty
    if not name or not p_price or not s_price or not qty:
        flash("All fields are required.", "error")
        return redirect(url_for('products'))

    try:
        # 3. INTEGER CONVERSION (Fixes the "float" issue)
        # We assume the HTML regex worked, but we double-check here safely.
        # We strip non-numeric characters just in case.
        import re
        clean_p_price = int(re.sub(r'[^0-9]', '', str(p_price)))
        clean_s_price = int(re.sub(r'[^0-9]', '', str(s_price)))
        clean_qty = int(re.sub(r'[^0-9]', '', str(qty)))

        # 4. Create the new Product
        # NOTE: Make sure 'quantity' matches your database column name (it might be 'stock' or 'initial_stock')
        new_product = Product(
            name=name,
            purchase_price=clean_p_price,
            sale_price=clean_s_price,
            quantity=clean_qty,  # This sets the initial stock
            user_id=current_user.id
        )

        db.session.add(new_product)
        db.session.commit()
        
        flash("Product added successfully!", "success")

    except ValueError:
        flash("Invalid number format. Please enter whole numbers only.", "error")
    except Exception as e:
        db.session.rollback()
        print(f"Error adding product: {e}")
        flash("An error occurred while adding the product.", "error")

    # 5. Refresh the page
    return redirect(url_for('products'))

@app.route('/update_sales/<int:id>', methods=['POST'])
@login_required
def update_sales(id):
    # 1. SECURITY: Ensure the product belongs to the logged-in user
    product = Product.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        # 2. SAFE CONVERSION: Handle "4" or "4.00" string formats
        raw_val = request.form.get('items_sold', '0')
        qty_sold_now = int(float(raw_val))
        
        # 3. VALIDATION: Check for empty or negative input
        if qty_sold_now <= 0:
            return jsonify({'success': False, 'error': 'Please enter a valid quantity.'}), 400
        
        # 4. STOCK CHECK: Compare against the calculated property
        if qty_sold_now > product.remaining:
            return jsonify({
                'success': False, 
                'error': f'Not enough stock! Only {int(product.remaining)} left.'
            }), 400
        
        
        # updates itself automatically based on the sales in the DB.
        new_sale = Sale(product_id=product.id, quantity_sold=qty_sold_now)
        db.session.add(new_sale)
        db.session.commit()

        # 6. RESPONSE: Handle AJAX (for your JS) or standard form redirect
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'new_remaining': int(product.remaining), # Send back the new calculated stock
                'product_id': id
            })

        return redirect(request.referrer or url_for('products'))

    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid number format.'}), 400
    except Exception as e:
        db.session.rollback()
        # Log the error for yourself and send a clean message to the user
        print(f"Error in update_sales: {str(e)}")
        return jsonify({'success': False, 'error': 'Server error. Please try again.'}), 500

@app.route('/delete/<int:id>')
@login_required
def delete_product(id):
    # SECURITY: Ensure product belongs to current user
    product = Product.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully.", "info")
    return redirect(request.referrer or url_for('products'))

@app.route('/loans')
@login_required
def loans():
    # FILTER: Only show my loans
    unpaid = Loan.query.filter_by(status=0, user_id=current_user.id).order_by(Loan.date_added.desc()).all()
    history = Loan.query.filter_by(status=1, user_id=current_user.id).order_by(Loan.date_added.desc()).limit(10).all()
    return render_template('loans.html', unpaid=unpaid, history=history)

@app.route('/add_loan', methods=['POST'])
@login_required
def add_loan():
    try:
        # SAVE: Add user_id
        new_loan = Loan(
            customer_name=request.form['customer_name'],
            product_taken=request.form['product_taken'],
            amount=float(request.form['amount']),
            phone_number=request.form['phone_number'],
            user_id=current_user.id
        )
        db.session.add(new_loan)
        db.session.commit()
        return redirect(url_for('loans'))
    except Exception as e:
        db.session.rollback()
        return f"Error: {e}"

@app.route('/send_whatsapp/<int:id>')
@login_required
def send_whatsapp(id):
    # SECURITY: Ensure loan belongs to current user
    loan = Loan.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    message = (
        f"Hello {loan.customer_name},\n\n"
        f"This is a receipt from Tuck Shop.\n"
        f"Items: {loan.product_taken}\n"
        f"Total Amount: PKR {loan.amount}\n"
        f"Date: {loan.date_added.strftime('%d %b, %I:%M %p')}\n\n"
        f"Please clear your dues at your earliest convenience. Thank you!"
    )
    
    encoded_msg = urllib.parse.quote(message)
    clean_phone = ''.join(filter(str.isdigit, loan.phone_number))
    
    if clean_phone.startswith('0'):
        clean_phone = '92' + clean_phone[1:]
    
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_msg}"
    return redirect(whatsapp_url)

@app.route('/mark_paid/<int:id>')
@login_required
def mark_paid(id):
    # SECURITY: Ensure loan belongs to current user
    loan = Loan.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    loan.status = 1
    db.session.commit()
    return redirect(url_for('loans'))

@app.route('/delete_loan/<int:id>')
@login_required
def delete_loan(id):
    # SECURITY: Ensure loan belongs to current user
    loan = Loan.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(loan)
    db.session.commit()
    return redirect(url_for('loans'))

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/rates')
def rates():
    return render_template('rates.html')

if __name__ == '__main__':
    app.run(host= '0.0.0.0', debug=True)