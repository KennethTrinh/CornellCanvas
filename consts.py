import os

API_KEY = os.environ['CANVAS_TOKEN']
API_URL = 'https://canvas.cornell.edu'
HEADERS = {
    'Authorization': f'Bearer {API_KEY}'
}

LOG = False
FILES_REGEX = r"canvas\.cornell\.edu/courses/\d+/files/(\d+)"
USERNAME = os.environ['USERNAME']
PASSWORD = os.environ['PASSWORD']
