import os
import requests
import json
import pandas as pd
import csv

from bs4 import BeautifulSoup
from canvasapi import Canvas
from canvasapi.exceptions import ResourceDoesNotExist, Forbidden
from utils import (sanitize, cprint, extract_files, 
                   write, ThrowsLambdaError, 
                   getModules, getAssignments, getCourse,
                   getFiles, getPages, getQuizzes, getDiscussionTopics, getReplies)

from consts import API_KEY, API_URL, HEADERS

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

def scrapeHTMLContent(course, folder, files_downloaded, html_file_name, html):
    """
    writes html and accompanying files to folder
    """
    os.makedirs(folder, exist_ok=True)
    write(html, os.path.join(folder, html_file_name))
    file_ids = extract_files(html)
    scrapeFiles(course, folder, files_downloaded, file_ids)
    

def scrapeExternalUrl(folder, item):
    os.makedirs(folder, exist_ok=True)
    cprint(f'Downloading External URL: {item.external_url}')
    with open(os.path.join(folder, sanitize(item.title) + '.txt'), 'w') as f:
        f.write(item.external_url)
    

def scrapeQuiz(course, folder, files_downloaded, quiz_id):
    """
    Appends the folder path and quiz.html_url to a csv file in misc/quizzes.csv
    We can only see quizzes for ones that we've taken before.
    Further, the api does not allow us to download the quiz itself, so we
    must login to canvas and download the quiz.html_url
    We will handle this later using canvasDuoLogin
    """
    quiz = course.get_quiz(quiz_id)
    cprint(f'Preparing Quiz: {quiz.title}')
    os.makedirs('misc', exist_ok=True)
    with open('misc/quizzes.csv', 'a') as f:
        if os.stat('misc/quizzes.csv').st_size == 0:
            writer = csv.writer(f)
            writer.writerow(['folder', 'url'])
        writer = csv.writer(f)
        writer.writerow([os.path.join(folder, sanitize(quiz.title)), quiz.html_url])

def scrapeQuizzes(course, folder, files_downloaded):
    quizzes = getQuizzes(course)
    if not quizzes:
        return
    folder = os.path.join(folder, 'Quizzes')
    for quiz in quizzes:
        scrapeQuiz(course, folder, files_downloaded, quiz.id)

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
            pass
            # TODO: see if modules ever have pages
            # scrapePage(course, folder, files_downloaded, item.page_url)
        elif item.type == 'Assignment':
            scrapeAssignment(course, folder, files_downloaded, item.content_id)
        elif item.type == 'ExternalUrl':
            scrapeExternalUrl(folder, item)
        elif item.type == 'Quiz':
            # scrapeQuiz(course, folder, files_downloaded, item.content_id)
            cprint(f'Quiz: {item.title}')
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
    
def scrapeAssignment(course, folder, files_downloaded, assignment_id):
    """
    Modules may only have the assignment id, not the class instance of the assignment,
    hence we pass in assignment_id instead of assignment
    """
    assignment = course.get_assignment(assignment_id)
    cprint(f'Downloading Assignment: {assignment.name}')
    scrapeHTMLContent(course, folder, files_downloaded, 
                      sanitize(assignment.name) + '.html', assignment.description)

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
    """
    canvasapi doesn't support this call yet
    """
    url = f'{API_URL}/api/v1/courses/{course.id}'
    r = requests.get(url, headers=HEADERS, params={'include[]': 'syllabus_body'})
    if 'syllabus_body' in r.json() and r.json()['syllabus_body']:
        syllabus = r.json()['syllabus_body']
        folder = os.path.join(folder, 'Syllabus')
        scrapeHTMLContent(course, folder, files_downloaded, 
                        'Syllabus.html', syllabus)

def recursiveReplies(html, replies):
    """
    I hate canvas
    """
    if not replies:
        return html
    for reply in replies:
        html += (f'<h4>Date: {reply.created_at} </h4>'
                f"<h4>Author: {reply.user['display_name'] if 'display_name' in reply.user else ''}"
                f" id:({reply.user['id'] if 'id' in reply.user else ''}) </h4>"
                f'{reply.message if reply.message else ""}'
        )
        html = recursiveReplies(html, getReplies(reply))
    return html

def scrapeDiscussion(folder, discussion):
    os.makedirs(folder, exist_ok=True)
    cprint(f'Discussion: {discussion.title}')
    html = (f'<h1>Title: {discussion.title} </h1>'
            f'<h2>Date: {discussion.posted_at} </h2>'
            f"<h2>Author: {discussion.author['display_name'] if 'display_name' in discussion.author else ''}"
            f" id:({discussion.author['id'] if 'id' in discussion.author else ''}) </h2>"
            f'{discussion.message}'
    )
    replies = list(discussion.get_topic_entries())
    html += f'<h2>Replies: </h2>' if replies else ''
    html = recursiveReplies(html, replies)
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
    url = f'{API_URL}/api/v1/courses/{course.id}/pages/{page_id}'
    r = requests.get(url, headers=HEADERS)
    if 'body' in r.json() and r.json()['body']:
        body = r.json()['body']
        scrapeHTMLContent(course, folder, files_downloaded,
                            sanitize(r.json()['title']) + '.html', body)
        
def scrapePages(course, folder, files_downloaded):
    pages = getPages(course)
    if not pages:
        print(f'Pages not enabled for course: {course.id}')
        return
    folder = os.path.join(folder, 'Pages')
    for page in pages:
        print(f'******* Page: {page.title} , ID: {page.url} *******')
        scrapePage(course, folder, files_downloaded, page.page_id)

@ThrowsLambdaError(ResourceDoesNotExist)
def scrapeHomePage(course, folder, files_downloaded):
    front_page = course.show_front_page()
    folder = os.path.join(folder, 'Home_page')
    scrapeHTMLContent(course, folder, files_downloaded,
                        'Home_page.html', front_page.body)


def scrapeCourse(canvas, course_id):
    files_downloaded = set()
    course = getCourse(canvas, course_id)
    if not course:
        print(f'Course not accessible for course: {course_id}')
        return
    course_name = sanitize(course.name) if hasattr(course, 'name') else f'MISC_{course.id}'
    folder = os.path.join('data', course_name)

    scrapeModules(course, folder, files_downloaded)
    scrapeAssignments(course, folder, files_downloaded)
    scrapeRemainingFiles(course, folder, files_downloaded)
    scrapeSyllabus(course, folder, files_downloaded)
    scrapeDiscussions(course, folder, isAnnouncement=True)
    scrapeDiscussions(course, folder, isAnnouncement=False)
    scrapePages(course, folder, files_downloaded)
    scrapeHomePage(course, folder, files_downloaded)




    
    
canvas = Canvas(API_URL, API_KEY)
courses = pd.read_csv('misc/courses.csv')
# courses = list(canvas.get_courses()) # --> lists all courses you've taken
scrapeCourse(canvas, 51429)
scrapeCourse(canvas, 24870)
# course = getCourse(canvas, 51429)
# module = course.get_module(128448)
# items = list(module.get_module_items())
# item = items[1]
# discussions = getDiscussionTopics(course, only_announcements=True)
# d = discussions[0]
# dis = course.get_discussion_topic(543124)
# scrapeDiscussion('test', dis)
# replies = list(dis.get_topic_entries())
# reply = replies[0]
# r = list(reply.get_replies())[0]



# course = getCourse(canvas, 51189)
# announcements = getDiscussionTopics(course, only_announcements=False)
# d = announcements[0]

# for a in announcements:
#     print(f'********* {a.title} *********')
#     print(a.message)
# s = login() if DUO_LOGIN else requests.Session()
# r = s.get(f'{API_URL}/courses/{course.id}/announcements')
# write(r.text, 'test.html')

    
# course = getCourse(canvas, 1060) # syllabus homepage
# course = canvas.get_course(1402) # dynamics, homepage
# course = canvas.get_course(6607) # data driven, forbidden
# course = canvas.get_course(41544) # data driven, no name
# course = canvas.get_course(340) # chem assignments and quizzes
# course = canvas.get_course(24870) # phys 2214, everything in modules
# course = getCourse(canvas, 51429) # HD 2930, files enabled, discussion topics
# course = getCourse(canvas, 14264) # HIST 1200 no modules, homepage is syllabus
# course = getCourse(canvas, 51189) # PAM 3301, pages enabled
# course = getCourse(canvas, 23439) # CS 2110, quizzes enabled


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


# for i, row in courses.iterrows():
#     course = getCourse(canvas, row['id'])
#     if not course:
#         continue
#     quizzes = getQuizzes(course)
#     if quizzes:
#         quizzes = getQuizzes(course)
#         try:
#             q = quizzes[0]
#             questions = list(q.get_questions())
#             print(f'Course: {course.name} ({course.id}): {len(questions)} questions')
#         except Forbidden:
#             continue