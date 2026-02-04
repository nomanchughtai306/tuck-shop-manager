from app import app, db, Product, Sale
from datetime import date

def migrate():
    with app.app_context():
        # 1. Create the new Sale table if it doesn't exist
        db.create_all()
        print("Ensured Sale table exists.")

        # 2. Check every product
        products = Product.query.all()
        for p in products:
            # Check if this product already has sales in the new table
            existing_sales_sum = sum(s.quantity_sold for s in p.sales)
            
            # If the new table is empty but the old record had sales, move them
            # Note: Since we are deleting the old column, we assume you haven't 
            # deleted the db file yet.
            try:
                # We check the actual database column directly
                from sqlalchemy import text
                result = db.session.execute(text(f"SELECT items_sold FROM product WHERE id={p.id}")).fetchone()
                old_sold_value = result[0] if result else 0

                if old_sold_value > 0 and existing_sales_sum == 0:
                    # Create a "Legacy Sale" entry to keep your data safe
                    legacy_sale = Sale(
                        product_id=p.id,
                        quantity_sold=old_sold_value,
                        sale_date=p.date_added # Assign it to the day the product was added
                    )
                    db.session.add(legacy_sale)
                    print(f"Migrated {old_sold_value} sales for {p.name}")
            except Exception as e:
                print(f"Skipping migration for {p.name}: {e}")

        db.session.commit()
        print("Migration Complete! You can now delete this script.")

if __name__ == "__main__":
    migrate()




















    from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import urllib.parse
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# --- CONFIGURATION ---
app.config['SECRET_KEY'] = 'tuckshop_secret_key_change_this_in_production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials.', 'error')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

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
    try:
        name = request.form['name']
        quantity = int(request.form['quantity'])
        p_price = float(request.form['purchase_price'])
        s_price = float(request.form['sale_price'])
        
        # SAVE: Add user_id
        new_product = Product(
            name=name, 
            quantity=quantity, 
            purchase_price=p_price, 
            sale_price=s_price,
            user_id=current_user.id
        )
        db.session.add(new_product)
        db.session.commit()
        
        # Helper for AJAX requests
        if (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 
            'application/json' in request.headers.get('Accept', '')):
            return jsonify({'success': True})

        return redirect(request.referrer or url_for('products'))
        
    except Exception as e:
        db.session.rollback()
        if (request.headers.get('X-Requested-With') == 'XMLHttpRequest'):
            return jsonify({'success': False, 'error': str(e)}), 500
        return redirect(request.referrer or url_for('products'))

@app.route('/update_sales/<int:id>', methods=['POST'])
@login_required
def update_sales(id):
    # SECURITY: Ensure product belongs to current user
    product = Product.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    
    try:
        qty_sold_now = int(request.form['items_sold'])
        
        if qty_sold_now > product.remaining:
            return jsonify({'success': False, 'error': 'Not enough stock!'}), 400
        
        new_sale = Sale(product_id=product.id, quantity_sold=qty_sold_now)
        db.session.add(new_sale)
        db.session.commit()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'new_remaining': product.remaining,
                'product_id': id
            })

        return redirect(request.referrer or url_for('products'))
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

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
    app.run(debug=True)