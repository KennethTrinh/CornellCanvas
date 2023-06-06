import os

API_KEY = os.environ['CANVAS_TOKEN']
API_URL = 'https://canvas.cornell.edu'
HEADERS = {
    'Authorization': f'Bearer {API_KEY}'
}

ED_URL = 'https://us.edstem.org'
MAX_PAGES = 100
LOG = False
FILES_REGEX = r"canvas\.cornell\.edu/courses/\d+/files/(\d+)"
USERNAME = os.environ['USERNAME']
PASSWORD = os.environ['PASSWORD']
