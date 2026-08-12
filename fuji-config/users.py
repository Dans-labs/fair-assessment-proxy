import os

from dotenv import load_dotenv

load_dotenv()

fuji_users = {os.environ["FUJI_USERNAME"]: os.environ["FUJI_PASSWORD"]}
