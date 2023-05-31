import os
import requests
import json
import re
import pandas as pd

from bs4 import BeautifulSoup
from canvasapi import Canvas
from canvasapi.exceptions import Unauthorized, ResourceDoesNotExist, Forbidden


API_KEY = os.environ['CANVAS_TOKEN']
API_URL = 'https://canvas.cornell.edu'

sanitize = lambda text: text.replace('/', '-')

def extract_files(text):
    """
    Serches for url ending in /files/<id> and returns a set of ids
    """
    text_search = re.findall("/files/(\\d+)", text, re.IGNORECASE)
    groups = set(text_search)
    return groups

def write(text, filename='test.html'):
    """
    For debugging purposes, write the text to a file
    """
    with open(filename, 'w') as f:
        soup = BeautifulSoup(text, 'html.parser')
        f.write(soup.prettify())


def writeCoursesToCSV(canvas):
    """
    Write all courses to a file. Outputs courses.csv
    """
    df = pd.DataFrame(columns=['name', 'id'])
    for page in range(1, 5):
        allCourses = canvas.search_all_courses(per_page=100, page=page)
        for c in allCourses:
            df = df.append({'name': c["course"]["name"], 'id': c["course"]["id"]}, 
                          ignore_index=True)
        print(f'Finished page {page}')
    df.to_csv('courses/courses.csv', index=False)






def scrapeHomePage(course):
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

def scrapeHTMLContent(course, folder, files_downloaded, file_ids):
    """
    For pages or assignments with html content.
    file_ids is a list of ids obtained from extract_files
    """
    for file_id in file_ids:
        if file_id in files_downloaded:
            continue
        try: 
            file = course.get_file(file_id)
            files_downloaded.add(file_id)
            file.download(
                os.path.join(folder, sanitize(file.display_name))
            )
            print(f'Downloaded File: {file.display_name}')
        except ResourceDoesNotExist:
            print(f'File {file_id} does not exist')


def scrapeModule(course, module, files_downloaded):
    """
    Course/Module ID will always exist
    """
    
    course_name = sanitize(course.name) if hasattr(course, 'name') else f'MISC_{course.id}'
    module_name = sanitize(module.name) if hasattr(module, 'name') else f'MISC_{module.id}'
    folder = os.path.join('data', course_name, module_name)
    os.makedirs(folder, exist_ok=True)
    print(f'Created directory {folder}')
    print(f'Module: {module.name} , ID: {module.id}')
    for item in module.get_module_items():
        if item.type == 'File':
            file = course.get_file(item.content_id)
            files_downloaded.add(item.content_id)
            # file.download(os.path.join(folder, sanitize(file.display_name)))
            print(f'Downloaded File: {file.display_name}')
        elif item.type == 'Page':
            page = course.get_page(item.page_url)
            write(page.body or '', 
                  os.path.join(folder, sanitize(page.title) + '.html'))
            file_ids = extract_files(page.body or '')
            # scrapeHTMLContent(course, folder, files_downloaded, file_ids)
            print(f'Downloaded Page: {page.title}')
        elif item.type == 'ExternalUrl':
            print(f'External URL: {item.external_url}')
        elif item.type == 'Assignment':
            assignment = course.get_assignment(item.content_id)
            print(f'Assignment: {assignment.id}')
        elif item.type == 'Quiz':
            quiz = course.get_quiz(item.content_id)
            print(f'Quiz: {quiz.id}')
        else:
            print(f'Unknown type: {item.type}')




def scrapeModules(course):
    files_downloaded = set()
    modules = list(course.get_modules())
    for module in modules:
        scrapeModule(course, module, files_downloaded)
    
    return files_downloaded

    

# ECE 4130 COMBINED-XLIST Introduction to Nuclear Science and Engineering (2021FA) 33592
# MAE 2030 Dynamics (Spring 2019):         Prof. Andy Ruina 1402


# courses = list(canvas.get_courses()) --> lists all courses you've taken
# for course in courses:
#     name = course.name if  hasattr(course, 'name') else 'MISC'
#     print(f'{name} {course.id}')
# courses = list(map(lambda c: (c.name, c.id), courses)) --> not every course has name!
def main():
    canvas = Canvas(API_URL, API_KEY)
    courses = pd.read_csv('courses/courses.csv')
    # course = canvas.get_course(6607)
    try:
        # course = canvas.get_course(1402) # dynamics, 
        # course = canvas.get_course(6607) # data driven, forbidden
        # course = canvas.get_course(41544) # data driven, no name
        # course = canvas.get_course(340) # chem assignments and quizzes
        course = canvas.get_course(24870) # phys 2214, everything in modules
        files_downloaded = scrapeModules(course)
    except Forbidden:
        print('Forbidden')
    
main()

# canvas = Canvas(API_URL, API_KEY)
# course = canvas.get_course(24870) # phys 2214
# module = course.get_module(128436)


# assignments = list(course.get_assignments())
# assignment = assignments[0]



