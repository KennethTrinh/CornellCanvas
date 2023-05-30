from canvasapi import Canvas
import os
import requests
from bs4 import BeautifulSoup
import json
import re

API_KEY = os.environ['CANVAS_TOKEN']
API_URL = 'https://canvas.cornell.edu'

sanitize = lambda text: text.replace('/', '-')

def write(text):
    """
    For debugging purposes, write the text to a file
    """
    with open('test.html', 'w') as f:
        soup = BeautifulSoup(text, 'html.parser')
        f.write(soup.prettify())

def printCourses(per_page=100, page=2):
    """
    Print all courses, page ranges from 1 to 4 --> range(1,5)
    """
    allCourses = canvas.search_all_courses(per_page=per_page, page=page)
    for c in allCourses:
        print(c['course']['name'], c['course']['id'])


canvas = Canvas(API_URL, API_KEY)
courses = list(canvas.get_courses())
# ECE 4130 COMBINED-XLIST Introduction to Nuclear Science and Engineering (2021FA) 33592
# MAE 2030 Dynamics (Spring 2019):         Prof. Andy Ruina 1402 False
course = canvas.get_course(1402)

#Home page
r = requests.get('https://canvas.cornell.edu/courses/1402',
                 headers={'Authorization': 'Bearer ' + API_KEY})
soup = BeautifulSoup(r.text, 'html.parser')
# get all script tags
scripts = soup.find_all('script')
# get the script with ENV = in it
script = [s for s in scripts if 'ENV = {' in str(s)][0]
# get everything after ENV = and before the BRANDABLE_CSS_HANDLEBARS_INDEX
text = script.string.split('ENV = ')[1].split('BRANDABLE_CSS_HANDLEBARS_INDEX')[0]
# remove the trailing semicolon
text = text[:text.rfind(';')]
text = json.loads(text)
# print(json.dumps(text, indent=4, sort_keys=True))
soup = BeautifulSoup(text['WIKI_PAGE']['body'], 'html.parser')
# get all a tags with data-api-endpoint=
links = soup.find_all('a', {'data-api-endpoint': True})
links = [l for l in links if 'files' in l['data-api-endpoint']]
# download all files
id = links[0]['data-api-endpoint'].split('/')[-1]
file = course.get_file(id)
file.download(sanitize(file.display_name))





# assignments = list(course.get_assignments())
# assignment = assignments[0]


# modules = list(course.get_modules())
# module = modules[0]
# os.makedirs(os.path.join(course.name, module.name), exist_ok=True)
# moduleItems = list(module.get_module_items())
# moduleItem = moduleItems[0]
# course.get_file(moduleItem.content_id)\
#       .download(os.path.join(course.name, module.name, moduleItem.title))

