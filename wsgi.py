import sys
import os

# Ensure the project directory is in sys.path
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from app import app as application

if __name__ == "__main__":
    application.run()
