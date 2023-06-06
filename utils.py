import re
import pandas as pd
from bs4 import BeautifulSoup
from canvasapi.exceptions import Unauthorized, ResourceDoesNotExist, Forbidden
from consts import LOG, FILES_REGEX
import os

sanitize = lambda text: text.replace('/', '-')

def cprint(*args, log=LOG, **kwargs):
    """
    Conditional print. Only prints if LOG is True
    """
    if log:
        print(*args, **kwargs)


def extract_files(text):
    """
    Serches for url ending in /files/<id> and returns a set of ids
    """
    if not text:
        return set()
    text_search = re.findall(FILES_REGEX, text, re.IGNORECASE)
    groups = set(text_search)
    return groups

def write(text, filename='test.html', overwrite=False):
    """
    Write the text to a file.
    """
    if not text:
        return
    indexOfDot = filename.rfind('.')
    while os.path.exists(filename) and not overwrite:
        filename = filename[:indexOfDot] + '_' + filename[indexOfDot:]
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


def ThrowsLambdaError(*errors):
    """
    1. The outermost level is the ThrowsLambdaError function itself. 
    It takes the custom error class as a parameter and returns the inner decorator function.

    2. The second level is the decorator function, which is returned by the outer function. 
    It takes the function to be decorated as an argument and returns the wrapper function.
    
    3. The innermost level is the wrapper function. 
    It is the actual function that replaces the original function and performs the error handling. 
    It wraps the original function and handles any exceptions that occur.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except errors as e:
                error_names = ', '.join([error.__name__ for error in errors])
                cprint(f"One of the following errors occurred: {error_names} " + \
                      f"when calling {func.__name__} with args: {args} and kwargs: {kwargs}")   
                return
        return wrapper
    return decorator

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

@ThrowsLambdaError(ResourceDoesNotExist)
def getReplies(reply):
    return list(reply.get_replies())