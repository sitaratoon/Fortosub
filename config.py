import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "18946488"))
API_HASH = os.getenv("API_HASH", "c163d4e28e63196c3806cf3b9b2885de")
BOT_TOKEN = os.getenv("BOT_TOKEN", "7611196343:AAHRN3D-GsAZDROzcsiye7vT1HJI8AjkD5E")
MONGO_DB = os.getenv("MONGO_DB", "mongodb+srv://stoons:stoons@ajay.v5uug.mongodb.net/?retryWrites=true&w=majority")

# Admin IDs comma separated string se parse hongi (e.g. "12345,67890")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

JOIN_REWARD = 2
DAILY_JOIN_LIMIT = 100
MIN_ORDER_CREDITS = 50
VERIFY_DELAY = 1
