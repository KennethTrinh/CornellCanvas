import os
from bs4 import BeautifulSoup

from utils import (sanitize, NoQuizFound, 
                   write, ThrowsLambdaError, getCourse, 
                   getModules, getAssignments, getQuizzes)
from canvasapi import Canvas
from consts import API_KEY, API_URL
from canvasDuoEdLogin import canvasDuoLogin

@ThrowsLambdaError(NoQuizFound)
def getBestSubmissionEndpoint(session, quiz_submission_versions_html_url):
    r = session.get(quiz_submission_versions_html_url)
    if not r.text:
        raise NoQuizFound(f'No quiz found at {quiz_submission_versions_html_url}')
    soup = BeautifulSoup(r.text, 'html.parser')
    tr = soup.find('tr', class_='kept')
    if not tr: # then only one submission
        return soup.find('a')['href']
    return tr.find('a')['href']

def scrapeQuiz(course, folder, quizzes_downloaded, session, quiz_id):
    """
    We get the html by using a session with the correct cookies, since the
    html is not directly accessible through the API.
    Thus, quiz.html_url has a url like: 
    https://canvas.cornell.edu/courses/<course-id>/quizzes/<quiz-id>
    """
    if quiz_id in quizzes_downloaded:
        print(f'Quiz {quiz_id} already downloaded')
        return
    quiz = course.get_quiz(quiz_id)
    bestQuizSubmissionEndpoint = getBestSubmissionEndpoint(session, quiz.quiz_submission_versions_html_url)
    if not bestQuizSubmissionEndpoint:
        return
    os.makedirs(folder, exist_ok=True)
    r = session.get(f'{API_URL}{bestQuizSubmissionEndpoint}')
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

def scrapeQuizzesForCourse(session, canvas, course_id):
    """
    TODO: take folder out of here and make param
    """
    quizzes_downloaded = set()
    course = getCourse(canvas, course_id)
    if not course:
        print(f'Course not accessible for course: {course_id}')
        return
    print(f'***** Course: {course.name} *****')
    course_name = sanitize(course.name) if hasattr(course, 'name') else f'MISC_{course.id}'
    folder = os.path.join('data', course_name)
    scrapeQuizzes(course, folder, quizzes_downloaded, session)
    scrapeModuleQuizzes(course, folder, quizzes_downloaded, session)
    scrapeAssignmentQuizzes(course, folder, quizzes_downloaded, session)

def scrapeExistingQuizzes():
    canvas = Canvas(API_URL, API_KEY)
    # only want personal courses, since we cant see quizzes for other courses
    courses = list(canvas.get_courses())
    s = canvasDuoLogin()
    for course in courses:
        scrapeQuizzesForCourse(s, canvas, course.id)

if __name__ == '__main__':
    scrapeExistingQuizzes()

# canvas  = Canvas(API_URL, API_KEY)
# courses = list(canvas.get_courses()) # --> lists all courses you've taken
# scrapeQuizzesForCourse(canvas, 24870)
# course = getCourse(canvas, 24870)
# quiz = course.get_quiz(47949)
# quiz = course.get_quiz(47997)
# s = canvasDuoLogin()
# r = s.get(quiz.quiz_submission_versions_html_url)
# soup = BeautifulSoup(r.text, 'html.parser')
# # get the tr with class='kept'
# href = soup.find('tr', class_='kept').find('a')['href']
# r = s.get(f'{API_URL}{href}')
