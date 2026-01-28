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