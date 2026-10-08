import sqlite3
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "cache.db"

# Seed default pincodes for Tamil Nadu & major Indian cities
SEED_PINCODES = [
    # Chennai
    ("600001", "Parrys / Fort St George", "Chennai", "Tamil Nadu", 13.0827, 80.2707),
    ("600002", "Anna Road / Mount Road", "Chennai", "Tamil Nadu", 13.0674, 80.2646),
    ("600004", "Mylapore", "Chennai", "Tamil Nadu", 13.0333, 80.2667),
    ("600017", "T. Nagar", "Chennai", "Tamil Nadu", 13.0418, 80.2341),
    ("600020", "Adyar", "Chennai", "Tamil Nadu", 13.0012, 80.2565),
    ("600028", "R.A. Puram", "Chennai", "Tamil Nadu", 13.0247, 80.2560),
    ("600040", "Anna Nagar", "Chennai", "Tamil Nadu", 13.0850, 80.2100),
    ("600042", "Velachery", "Chennai", "Tamil Nadu", 12.9815, 80.2180),
    ("600096", "Perungudi / OMR", "Chennai", "Tamil Nadu", 12.9654, 80.2461),
    ("600100", "Medavakkam", "Chennai", "Tamil Nadu", 12.9175, 80.1923),
    # Coimbatore
    ("641001", "Coimbatore Main / Town Hall", "Coimbatore", "Tamil Nadu", 11.0168, 76.9558),
    ("641002", "RS Puram", "Coimbatore", "Tamil Nadu", 11.0084, 76.9500),
    ("641004", "Peelamedu", "Coimbatore", "Tamil Nadu", 11.0267, 77.0019),
    ("641014", "Gandhipuram", "Coimbatore", "Tamil Nadu", 11.0183, 76.9644),
    ("641035", "Saravanampatti", "Coimbatore", "Tamil Nadu", 11.0797, 76.9997),
    # Madurai
    ("625001", "Madurai Main / Meenakshi Temple", "Madurai", "Tamil Nadu", 9.9252, 78.1198),
    ("625002", "Sellur", "Madurai", "Tamil Nadu", 9.9372, 78.1215),
    ("625020", "KK Nagar", "Madurai", "Tamil Nadu", 9.9320, 78.1480),
    # Tiruchirappalli
    ("620001", "Tiruchirappalli Head Post Office", "Tiruchirappalli", "Tamil Nadu", 10.7905, 78.7047),
    ("620002", "Fort / Teppakulam", "Tiruchirappalli", "Tamil Nadu", 10.8267, 78.6947),
    ("620015", "Thuvakudi / NIT Trichy", "Tiruchirappalli", "Tamil Nadu", 10.7614, 78.8142),
    # Salem
    ("636001", "Salem Head Office", "Salem", "Tamil Nadu", 11.6643, 78.1460),
    # Tirunelveli
    ("627001", "Tirunelveli Town", "Tirunelveli", "Tamil Nadu", 8.7139, 77.7567),
    # Vellore
    ("632001", "Vellore Fort", "Vellore", "Tamil Nadu", 12.9165, 79.1325),
    # Erode
    ("638001", "Erode Head Office", "Erode", "Tamil Nadu", 11.3410, 77.7172),
    # Puducherry
    ("605001", "Puducherry Main", "Puducherry", "Puducherry", 11.9416, 79.8083),
    # Bengaluru
    ("560001", "Bengaluru GPO / MG Road", "Bengaluru", "Karnataka", 12.9716, 77.5946),
    # Mumbai
    ("400001", "Mumbai GPO / Fort", "Mumbai", "Maharashtra", 18.9388, 72.8353),
    # Delhi
    ("110001", "New Delhi GPO / Connaught Place", "New Delhi", "Delhi", 28.6315, 77.2167)
]

def load_pincodes(custom_csv_or_json_path=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pincodes (
            pincode TEXT PRIMARY KEY,
            place_name TEXT,
            district TEXT,
            state TEXT,
            latitude REAL,
            longitude REAL
        )
    """)

    # Load seed pincodes
    cursor.executemany("""
        INSERT OR REPLACE INTO pincodes (pincode, place_name, district, state, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?)
    """, SEED_PINCODES)

    # If an external JSON/CSV dataset path is provided, load it
    if custom_csv_or_json_path and Path(custom_csv_or_json_path).exists():
        path = Path(custom_csv_or_json_path)
        logger.info(f"Loading custom dataset from {path}")
        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                rows = []
                for item in data:
                    rows.append((
                        str(item.get("pincode")),
                        item.get("place_name", ""),
                        item.get("district", ""),
                        item.get("state", ""),
                        float(item.get("latitude", 0.0)),
                        float(item.get("longitude", 0.0))
                    ))
                cursor.executemany("""
                    INSERT OR REPLACE INTO pincodes (pincode, place_name, district, state, latitude, longitude)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, rows)

    conn.commit()
    count = cursor.execute("SELECT COUNT(*) FROM pincodes").fetchone()[0]
    conn.close()
    print(f"Successfully loaded {count} pincodes into SQLite database at {DB_PATH}")

if __name__ == "__main__":
    import sys
    custom_path = sys.argv[1] if len(sys.argv) > 1 else None
    load_pincodes(custom_path)
