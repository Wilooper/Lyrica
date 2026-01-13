from src.app import create_app
import os

app = create_app()

app.run(port=9999)



