import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "1234567"))
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
MONGO_DB = os.getenv("MONGO_DB", "YOUR_MONGO_URI")

# Admin IDs comma separated string se parse hongi (e.g. "12345,67890")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

JOIN_REWARD = 2
DAILY_JOIN_LIMIT = 100
MIN_ORDER_CREDITS = 50
VERIFY_DELAY = 1
