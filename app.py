from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
import urllib.parse
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'tuckshop_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


app.secret_key = 'your_very_secret_key' # Change this!

# Initialize Login Manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Redirects here if @login_required fails


db = SQLAlchemy(app)

# --- DATABASE MODELS ---


# Simple User Class for Demo
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)     # Total stock ever purchased
    purchase_price = db.Column(db.Float, nullable=False) # Buying price
    sale_price = db.Column(db.Float, nullable=False)     # Selling price
    date_added = db.Column(db.Date, default=date.today)

    # Link to Sales
    sales = db.relationship('Sale', backref='product', lazy=True, cascade="all, delete-orphan")

    @property
    def items_sold(self):
        return sum(sale.quantity_sold for sale in self.sales)

    @property
    def remaining(self):
        # Automatically calculates: No setter needed!
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
    # New Column: 0 = Unpaid, 1 = Paid
    status = db.Column(db.Integer, default=0)


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
        user = User.query.filter_by(username=request.form.get('username')).first()
        
        if user and user.check_password(request.form.get('password')):
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
    
    products = Product.query.order_by(Product.date_added.desc()).all()

    if start_date and end_date:
        s_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        e_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        filtered_sales = Sale.query.filter(Sale.sale_date.between(s_date, e_date)).all()
        
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
                'highest_margin': max(products, key=lambda p: p.profit_per_item)
            }
        else:
            analytics_data = 'empty'

    return render_template('dashboard.html', products=products, analytics=analytics_data, s_date=start_date, e_date=end_date)

@app.route('/loans')
@login_required
def loans():
    # Filter by status: 0 for pending, 1 for paid
    unpaid = Loan.query.filter_by(status=0).order_by(Loan.date_added.desc()).all()
    history = Loan.query.filter_by(status=1).order_by(Loan.date_added.desc()).limit(10).all()
    return render_template('loans.html', unpaid=unpaid, history=history)

@app.route('/add_loan', methods=['POST'])
def add_loan():
    try:
        # We take the list of products and the total combined price
        new_loan = Loan(
            customer_name=request.form['customer_name'],
            product_taken=request.form['product_taken'], # Can now hold "Juice, Cake, etc"
            amount=float(request.form['amount']),
            phone_number=request.form['phone_number']
        )
        db.session.add(new_loan)
        db.session.commit()
        return redirect(url_for('loans'))
    except Exception as e:
        db.session.rollback()
        return f"Error: {e}"


@app.route('/send_whatsapp/<int:id>')
def send_whatsapp(id):
    loan = Loan.query.get_or_404(id)
    
    # Format the message
    message = (
        f"Hello {loan.customer_name},\n\n"
        f"This is a receipt from Tuck Shop.\n"
        f"Items: {loan.product_taken}\n"
        f"Total Amount: PKR {loan.amount}\n"
        f"Date: {loan.date_added.strftime('%d %b, %I:%M %p')}\n\n"
        f"Please clear your dues at your earliest convenience. Thank you!"
    )
    
    # Encode for URL (converts spaces to %20, etc.)
    encoded_msg = urllib.parse.quote(message)
    
    # Create the WhatsApp link
    # We clean the phone number to ensure it only has digits
    clean_phone = ''.join(filter(str.isdigit, loan.phone_number))
    
    # Ensure it has the country code (92 for Pakistan)
    if clean_phone.startswith('0'):
        clean_phone = '92' + clean_phone[1:]
    
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_msg}"
    
    return redirect(whatsapp_url)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/rates')
def rates():
    return render_template('rates.html')

@app.route('/mark_paid/<int:id>')
def mark_paid(id):
    loan = Loan.query.get_or_404(id)
    loan.status = 1  # Change status to Paid
    db.session.commit()
    return redirect(url_for('loans'))

@app.route('/delete_loan/<int:id>')
def delete_loan(id):
    # Keep this route for permanently removing mistakes
    loan = Loan.query.get_or_404(id)
    db.session.delete(loan)
    db.session.commit()
    return redirect(url_for('loans'))
@app.route('/products')
@login_required
def products():
    all_products = Product.query.order_by(Product.date_added.desc()).all()
    return render_template('products.html', products=all_products)

@app.route('/add_product', methods=['POST'])
def add_product():
    try:
        name = request.form['name']
        quantity = int(request.form['quantity'])
        p_price = float(request.form['purchase_price'])
        s_price = float(request.form['sale_price'])
        
        # FIX: Removed 'remaining=quantity' because it's a @property
        new_product = Product(
            name=name, 
            quantity=quantity, 
            purchase_price=p_price, 
            sale_price=s_price
        )
        db.session.add(new_product)
        db.session.commit()
        
        if (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 
            'application/json' in request.headers.get('Accept', '')):
            return jsonify({'success': True})

        return redirect(request.referrer or url_for('products'))
        
    except Exception as e:
        db.session.rollback()
        if (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 
            'application/json' in request.headers.get('Accept', '')):
            return jsonify({'success': False, 'error': str(e)}), 500
        return redirect(request.referrer or url_for('products'))

@app.route('/update_sales/<int:id>', methods=['POST'])
def update_sales(id):
    product = Product.query.get_or_404(id)
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
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully.", "info")
    # Redirect back to wherever you came from
    return redirect(request.referrer or url_for('products'))

if __name__ == '__main__':
    app.run(debug=True)