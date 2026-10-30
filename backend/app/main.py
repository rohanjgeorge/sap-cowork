from dotenv import load_dotenv
from .api import create_app

load_dotenv()
app = create_app()
