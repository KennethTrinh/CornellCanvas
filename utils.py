import json
import re
import pandas as pd
import os
import time
import functools
from bs4 import BeautifulSoup
from canvasapi.exceptions import Unauthorized, ResourceDoesNotExist, Forbidden
from consts import LOG, FILES_REGEX
from pathvalidate import sanitize_filename

sanitize = lambda text: sanitize_filename(text)

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

def writeJson(jsonDict, filename='test.json'):
    """
    dumps json to a file.
    json is a dict
    """
    with open(filename, 'w') as f:
        json.dump(jsonDict, f, indent=4)

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

class NoQuizFound(Exception):
    """Exception raised when no quiz found"""
    pass

class MaxRetriesExceeded(Exception):
    """Exception raised when max retries exceeded"""
    pass


def retry(retry_num, retry_sleep_sec=10):
    """
    retry decorator.
    :param retry_num: the retry num; retry sleep sec
    :return: decorator
    usage: @retry(3)
    """
    def decorator(func):
        """decorator"""
        # preserve information about the original function, or the func name will be "wrapper" not "func"
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            """wrapper"""
            for attempt in range(retry_num):
                try:
                    return func(*args, **kwargs)  # should return the raw function's return value
                except Exception as err:   
                    time.sleep(retry_sleep_sec)
                print(f"Retry Attempt {attempt+1} / {retry_num}.")
            raise MaxRetriesExceeded(f'Exceed max retry num: {retry_num} failed')
        return wrapper
    return decorator

def xmlToHtml(xml):
    replacements = {
        '<paragraph>': '<p>',
        '</paragraph>': '</p>',
        '<paragraph/>': '',
        '<italic>': '<i>',
        '</italic>': '</i>',
        '<bold>': '<b>',
        '</bold>': '</b>',
        '<list-item>': '<li>',
        '</list-item>': '</li>',
        '<document version="2.0">': '',
        '<document version="1.0">': '',
        '</document>': '',
    }
    # find the <file url=(1) filename=(2)> and replace with <a href=(1)>(2)</a>
    xml = re.sub(r'<file url="(.*)" filename="(.*)"/>', r'<a href="\1">\2</a>', xml)
    # replace <link href="https://classes.cornell.edu/browse/roster/SP23/class/SYSEN/5420">here</link> with <a href="https://classes.cornell.edu/browse/roster/SP23/class/SYSEN/5420">here</a>
    xml = re.sub(r'<link href="(.*)">(.*)</link>', r'<a href="\1">\2</a>', xml)
    for k, v in replacements.items():
        xml = xml.replace(k, v)
    return xml