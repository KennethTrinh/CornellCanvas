import os
import requests
from bs4 import BeautifulSoup
import json

from utils import (sanitize, cprint, extract_files, 
                   write, ThrowsLambdaError, getCourse, 
                   getModules, getAssignments, getQuizzes)
from canvasapi import Canvas
from consts import API_KEY, API_URL
from canvasDuoEdLogin import canvasDuoLogin

def scrapeHTML(course):
    """
    TODO: adapt this for courses such as homepage, quizzes... etc, where 
    html is not directly accessisble through the API.  Thus, this function
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

def scrapeQuiz(course, folder, quizzes_downloaded, session, quiz_id):
    """
    We get the html by using a session with the correct cookies, since the
    html is not directly accessible through the API.
    Thus, quiz.html_url has a url like: 
    https://canvas.cornell.edu/courses/<course-id>/quizzes/<quiz-id>
    """
    if quiz_id in quizzes_downloaded:
        print('Quiz {quiz_id} already downloaded')
        return
    os.makedirs(folder, exist_ok=True)
    quiz = course.get_quiz(quiz_id)
    r = session.get(quiz.html_url)
    write(r.text, os.path.join(folder, sanitize(quiz.title)) + '.html')
    quizzes_downloaded.add(quiz_id)

def scrapeQuizzes(course, folder, quizzes_downloaded, session):
    quizzes = getQuizzes(course)
    if not quizzes:
        return
    folder = os.path.join(folder, 'Quizzes')
    for quiz in quizzes:
        scrapeQuiz(course, folder, quizzes_downloaded, session, quiz.id)

def scrapeModuleQuiz(course, folder, quizzes_downloaded, session, module):
    """
    Course/Module ID will always exist
    """
    module_name = sanitize(module.name) if hasattr(module, 'name') else f'MISC_{module.id}'
    folder = os.path.join(folder, module_name)
    for item in module.get_module_items():
        if item.type == 'Quiz':
            print('Module Quiz: ', item.title)
            scrapeQuiz(course, folder, quizzes_downloaded, session, item.content_id)

def scrapeModuleQuizzes(course, folder, quizzes_downloaded, session):
    modules = getModules(course)
    folder = os.path.join(folder, 'Modules')
    for module in modules:
        scrapeModuleQuiz(course, folder, quizzes_downloaded, session, module)

def scrapeAssignmentQuiz(course, folder, quizzes_downloaded, session, assignment):
    """
    Modules may only have the assignment id, not the class instance of the assignment,
    hence we pass in assignment_id instead of assignment
    """
    folder = os.path.join(folder, sanitize(assignment.name))
    scrapeQuiz(course, folder, quizzes_downloaded, session, assignment.quiz_id)

def scrapeAssignmentQuizzes(course, folder, quizzes_downloaded, session):
    assignments = getAssignments(course)
    folder = os.path.join(folder, 'Assignments')
    for assignment in assignments:
        if assignment.is_quiz_assignment:
            print('Assignment Quiz: ', assignment.name)
            scrapeAssignmentQuiz(course, folder, quizzes_downloaded, session, assignment)

def scrapeQuizzesForCourse(canvas, course_id):
    quizzes_downloaded = set()
    course = getCourse(canvas, course_id)
    course_name = sanitize(course.name) if hasattr(course, 'name') else f'MISC_{course.id}'
    folder = os.path.join('data', course_name)
    session = canvasDuoLogin()
    scrapeQuizzes(course, folder, quizzes_downloaded, session)
    scrapeModuleQuizzes(course, folder, quizzes_downloaded, session)
    scrapeAssignmentQuizzes(course, folder, quizzes_downloaded, session)



canvas  = Canvas(API_URL, API_KEY)
courses = list(canvas.get_courses()) # --> lists all courses you've taken
scrapeQuizzesForCourse(canvas, 24870)
