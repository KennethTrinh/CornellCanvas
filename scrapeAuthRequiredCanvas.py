import os
import requests
from bs4 import BeautifulSoup
import json

from canvasDuoLogin import login
from utils import (sanitize, cprint, extract_files, 
                   ThrowsLambdaError, getModules, getAssignments, getQuizzes)
from canvasapi import Canvas

API_KEY = os.environ['CANVAS_TOKEN']
API_URL = 'https://canvas.cornell.edu'

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


canvas  = Canvas(API_URL, API_KEY)
courses = list(canvas.get_courses()) # --> lists all courses you've taken

# >>> a.is_quiz_assignment
# True
# >>> a.quiz_id
# 47945
