import os
import requests
import json
import pandas as pd

from bs4 import BeautifulSoup
from canvasapi import Canvas
from canvasapi.exceptions import Unauthorized, ResourceDoesNotExist, Forbidden
from canvasDuoLogin import login
from utils import (sanitize, cprint, extract_files, 
                   write, ThrowsLambdaError)
                   
API_KEY = os.environ['CANVAS_TOKEN']
API_URL = 'https://canvas.cornell.edu'
HEADERS = {
    'Authorization': f'Bearer {API_KEY}'
}
#TODO: switch to True when ready finished
DUO_LOGIN = True

def getModules(course):
    """
    Always works, returns empty list if no modules
    """
    return list(course.get_modules())

def getAssignments(course):
    """
    Always works, returns empty list if no assignments
    """
    return list(course.get_assignments())

@ThrowsLambdaError(Forbidden)
def getCourse(canvas, course_id):
    return canvas.get_course(course_id)

@ThrowsLambdaError(Forbidden)
def getFiles(course):
    return list(course.get_files())

@ThrowsLambdaError(ResourceDoesNotExist)
def getPages(course):
    return list(course.get_pages())

@ThrowsLambdaError(ResourceDoesNotExist)
def getQuizzes(course):
    return list(course.get_quizzes())

@ThrowsLambdaError(Forbidden)
def getDiscussionTopics(course, only_announcements):
    """
    passing in only_announcements weirdly enables announcements regardless of True/False
    """
    return list(course.get_discussion_topics(
                only_announcements=only_announcements)) if only_announcements else \
            list(course.get_discussion_topics())




def scrapeHTML(course):
    """
    TODO: adapt this for courses such as homepage, quizzes... etc, where 
    html is not directly accessible through the API.  Thus, this function
    will have to take in the request session outputted by the login function.
    """
    #Home page
    r = requests.get('https://canvas.cornell.edu/courses/1402')
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

@ThrowsLambdaError(ResourceDoesNotExist)
def scrapeFile(course, folder, files_downloaded, file_id):
    if file_id in files_downloaded:
        cprint(f'File {file_id} already downloaded')
        return
    os.makedirs(folder, exist_ok=True)
    file = course.get_file(file_id)
    cprint(f'Downloading File: {file.display_name}')
    # TODO: enable eventually, disabled for testing purposes
    # file.download(os.path.join(folder, sanitize(file.display_name)))
    files_downloaded.add(file_id)

def scrapeFiles(course, folder, files_downloaded, file_ids):
    """
    For pages or assignments with several fles
    file_ids is a list of ids obtained from extract_files
    """
    for file_id in file_ids:
        if file_id in files_downloaded:
            cprint(f'File {file_id} already downloaded')
            continue
        scrapeFile(course, folder, files_downloaded, file_id)

def scrapePage(course, folder, files_downloaded, page_url):
    os.makedirs(folder, exist_ok=True)
    page = course.get_page(page_url)
    cprint(f'Downloading Page: {page.title}')
    write(page.body, os.path.join(folder, sanitize(page.title) + '.html'))
    file_ids = extract_files(page.body)
    scrapeFiles(course, folder, files_downloaded, file_ids)


def scrapeExternalUrl(folder, external_url):
    os.makedirs(folder, exist_ok=True)
    cprint(f'Downloading External URL: {external_url}')
    with open(os.path.join(folder, sanitize(external_url) + '.txt'), 'w') as f:
        f.write(external_url)
    

def scrapeQuiz(course, folder, files_downloaded, quiz_id):
    quiz = course.get_quiz(quiz_id)
    cprint(f'Downloading Quiz: {quiz.title}')
    ## TODO: use s = login() from canvasDuoLogin.py to download quiz

def scrapeModule(course, folder, files_downloaded, module):
    """
    Course/Module ID will always exist
    """
    module_name = sanitize(module.name) if hasattr(module, 'name') else f'MISC_{module.id}'
    folder = os.path.join(folder, module_name)
    for item in module.get_module_items():
        print(f'Item: {item.title}   ID: {item.id}  Type: {item.type}')
        if item.type == 'File':
            scrapeFile(course, folder, files_downloaded, item.content_id)
        elif item.type == 'Page':
            scrapePage(course, folder, files_downloaded, item.page_url)
        elif item.type == 'Assignment':
            scrapeAssignment(course, folder, files_downloaded, item.content_id)
        elif item.type == 'ExternalUrl':
            scrapeExternalUrl(folder, item.external_url)
        elif item.type == 'Quiz':
            scrapeQuiz(course, folder, files_downloaded, item.content_id)
        elif item.type == 'SubHeader':
            cprint(f'SubHeader: {item.title}')
        else:
            cprint(f'Unknown type: {item.type}')

def scrapeModules(course, folder, files_downloaded):
    modules = getModules(course)
    folder = os.path.join(folder, 'Modules')
    for module in modules:
        print(f'******* Module: {module.name} , ID: {module.id} *******')
        scrapeModule(course, folder, files_downloaded, module)
        # TODO: test this
    
def scrapeAssignment(course, folder, files_downloaded, assignment_id):
    """
    Modules may only have the assignment id, not the class instance of the assignment,
    hence we pass in assignment_id instead of assignment
    """
    os.makedirs(folder, exist_ok=True)
    assignment = course.get_assignment(assignment_id)
    cprint(f'Downloading Assignment: {assignment.name}')
    write(assignment.description, os.path.join(folder, sanitize(assignment.name) + '.html'))
    file_ids = extract_files(assignment.description)
    scrapeFiles(course, folder, files_downloaded, file_ids)

def scrapeAssignments(course, folder, files_downloaded):
    assignments = getAssignments(course)
    folder = os.path.join(folder, 'Assignments')
    for assignment in assignments:
        print(f'******* Assignment: {assignment.name} , ID: {assignment.id} *******')
        scrapeAssignment(course, folder, files_downloaded, assignment.id)

def scrapeRemainingFiles(course, folder, files_downloaded):
    files = getFiles(course)
    if not files:
        print(f'Files not enabled for course: {course.id}')
        return
    folder = os.path.join(folder, 'Remaining_files')
    file_ids = list(map(lambda f: f.id, files))
    scrapeFiles(course, folder, files_downloaded, file_ids)
    
def scrapeSyllabus(course, folder, files_downloaded):
    global s
    r = s.get(f'{API_URL}/courses/{course.id}/assignments/syllabus')
    folder = os.path.join(folder, 'syllabus')
    os.makedirs(folder, exist_ok=True)
    write(r.text, os.path.join(folder, 'Syllabus.html'))
    file_ids = extract_files(r.text)
    scrapeFiles(course, folder, files_downloaded, file_ids)
    # TODO: test this

def scrapeDiscussion(folder, discussion):
    os.makedirs(folder, exist_ok=True)
    cprint(f'Discussion: {discussion.title}')
    html = (f'<h1>Title: {discussion.title} </h1>'
            f'<h2>Date: {discussion.posted_at} </h2>'
            f'<h2>Author: {discussion.author["display_name"]} id:({discussion.author["id"]}) </h2>'
            f'{discussion.message}'
    )
    replies = list(discussion.get_topic_entries())
    html += f'<h2>Replies: </h2>' if replies else ''
    for reply in replies:
        html += (f'<h4>Date: {reply.created_at} </h4>'
                 f'<h4>Author: {reply.user["display_name"]} id:({reply.user["id"]}) </h4>'
                 f'{reply.message}' if reply.message else ''
        )
    write(html, os.path.join(folder, sanitize(discussion.title) + '.html'))
        
def scrapeDiscussions(course, folder, isAnnouncement):
    discussions = getDiscussionTopics(course, only_announcements=isAnnouncement)
    typeOfDiscussion = 'Announcement' if isAnnouncement else 'Discussion'
    if not discussions:
        print(f'{typeOfDiscussion} not enabled for course: {course.id}')
        return
    folder = os.path.join(folder, typeOfDiscussion + 's')
    for discussion in discussions:
        print(f'******* {typeOfDiscussion}: {discussion.title} , ID: {discussion.id} *******')
        scrapeDiscussion(folder, discussion)

def scrapePage(course, folder, files_downloaded, page_id):
    """
    canvasapi doesn't support this call yet
    """
    os.makedirs(folder, exist_ok=True)
    url = f'{API_URL}/api/v1/courses/{course.id}/pages/{page_id}'
    r = requests.get(url, headers=HEADERS)
    if 'body' in r.json() and r.json()['body']:
        body = r.json()['body']
        write(r.json()['body'], os.path.join(folder, sanitize(r.json()['title']) + '.html'))
        file_ids = extract_files(r.json()['body'])
        scrapeFiles(course, folder, files_downloaded, file_ids)
        
def scrapePages(course, folder, files_downloaded):
    pages = getPages(course)
    if not pages:
        print(f'Pages not enabled for course: {course.id}')
        return
    folder = os.path.join(folder, 'Pages')
    for page in pages:
        print(f'******* Page: {page.title} , ID: {page.url} *******')
        scrapePage(course, folder, files_downloaded, page.page_id)



# ECE 4130 COMBINED-XLIST Introduction to Nuclear Science and Engineering (2021FA) 33592
# MAE 2030 Dynamics (Spring 2019):         Prof. Andy Ruina 1402

def scrapeCourse(canvas, course_id):
    files_downloaded = set()
    course = getCourse(canvas, course_id)
    if not course:
        print(f'Course not accessible for course: {course_id}')
        return
    course_name = sanitize(course.name) if hasattr(course, 'name') else f'MISC_{course.id}'
    folder = os.path.join('data', course_name)

    # scrapeModules(course, folder, files_downloaded)
    # scrapeAssignments(course, folder, files_downloaded)
    # scrapeRemainingFiles(course, folder, files_downloaded)
    # scrapeSyllabus(course, folder, files_downloaded)
    # scrapeDiscussions(course, folder, isAnnouncement=True)
    # scrapeDiscussions(course, folder, isAnnouncement=False)
    # scrapePages(course, folder, files_downloaded)
    # if course.default_view in ('modules', 'syllabus', 'assignments'):
    #   # TODO: scrape the homepage



    
    
canvas = Canvas(API_URL, API_KEY)
courses = pd.read_csv('courses/courses.csv')
# courses = list(canvas.get_courses()) # --> lists all courses you've taken
scrapeCourse(canvas, 24870)

# course = getCourse(canvas, 51189)
# announcements = getDiscussionTopics(course, only_announcements=False)
# d = announcements[0]

# for a in announcements:
#     print(f'********* {a.title} *********')
#     print(a.message)
# s = login() if DUO_LOGIN else requests.Session()
# r = s.get(f'{API_URL}/courses/{course.id}/announcements')
# write(r.text, 'test.html')

    

# course = canvas.get_course(1402) # dynamics, homepage
# course = canvas.get_course(6607) # data driven, forbidden
# course = canvas.get_course(41544) # data driven, no name
# course = canvas.get_course(340) # chem assignments and quizzes
# course = canvas.get_course(24870) # phys 2214, everything in modules
# course = getCourse(canvas, 51429) # HD 2930, files enabled, discussion topics
# course = getCourse(canvas, 14264) # HIST 1200 no modules, homepage is syllabus


########## DEBUGGING ##########

# course = canvas.get_course(24870) # phys 2214
# course = getCourse(canvas, 1402)
# module = course.get_module(128436)
# quiz = course.get_quiz(47947)
# item = module.get_module_item(791065)
# ass = list(course.get_assignments())
# assignment = course.get_assignment(assignment_id)
# a = course.get_assignment(197862)


# for course in courses:
#     name = course.name if  hasattr(course, 'name') else 'MISC'
#     print(f'{name} {course.id}')
# courses = list(map(lambda c: (c.name, c.id), courses)) --> not every course has name!


# for i, row in courses.iterrows():
#     print(f'******* Course: {row.name} , ID: {row.id} *******')
#     course = getCourse(canvas, row.id)
#     if not course:
#         print('Course not accessible for course')
#         continue
#     files = getFiles(course)
#     if files:
#         print('Files enabled for course')
#     modules = getModules(course)
#     if modules:
#         print('Modules enabled for course')
#     assignments = getAssignments(course)
#     if assignments:
#         print('Assignments enabled for course')
#     pages = getPages(course)
#     if pages:
#         print('Pages enabled for course')
#     quizzes = getQuizzes(course)
#     if quizzes:
#         print('Quizzes enabled for course')

# for i, row in courses.iterrows():
#     course = getCourse(canvas, row['id'])
#     if not course:
#         # print(f'Course not accessible for course: {row["id"]}')
#         continue
#     print(f'Course: {course.name} ({course.id}): {course.default_view}')


# for course in courses:
#     course = getCourse(canvas, course.id)
#     if not course:
#         continue
#     print(f'******* Course: {course.name} , ID: {course.id} *******')
#     dis = getDiscussionTopics(course, only_announcements=True)
#     if dis:
#         for topic in dis:
#             print(f'Topic: {topic.title}  ID: {topic.id}')
#             print(f'Entries: {len(list(topic.get_topic_entries()))}')


# for i, row in courses.iterrows():
#     course = getCourse(canvas, row['id'])
#     if not course:
#         continue
#     try:
#         pages = list(course.get_pages())
#         print(f'Course: {course.name} ({course.id}): {len(pages)} pages')
#     except ResourceDoesNotExist:
#         continue