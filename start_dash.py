"""Quick dashboard starter."""
import db
db.init_db()
print("DB initialized, starting dashboard...")
from dashboard import start_dashboard
start_dashboard()