import requests
import re
import os
import pandas as pd

from bs4 import BeautifulSoup
from utils import (sanitize, xmlToHtml, 
                   write, writeJson, retry,
                   getCourse)
from canvasapi import Canvas
from canvasDuoEdLogin import EdLogin, canvasDuoLogin
from consts import API_KEY, API_URL, ED_URL, MAX_PAGES

oidcEntry = lambda soup, s: soup.find('input', {'id': s})['value']

def getEdUrl(s, course_id):
    """
    HTML content is not directly accessisble through the API.  Thus, this function
    will have to take in the request session outputted by the login function.
    We want to extract this url:
    {API_URL}/courses/<course-id>/external_tools/<ed-course-id>?display=borderless
    """
    #Home page
    r = s.get(f'{API_URL}/courses/{course_id}')
    soup = BeautifulSoup(r.text, 'html.parser')
    # get the href of  the <a> tag with 'Ed Discussion' in it
    #  <a class="context_external_tool_3334" href="/courses/24870/external_tools/3334?display=borderless" target="_blank">
    # Ed Discussion </a>
    ed_url = soup.find('a', text='Ed Discussion')
    if not ed_url:
        return None
    ed_url = ed_url['href']
    return f'{API_URL}{ed_url}'

def EdCourseAuthenticationThroughCanvas(s, canvas_course_id):
    """
    Authenticates through canvas external tool.
    Returns ed_course_id and login_token (not available in canvas html, must go through edstem
    authentication to get it)
    """
    ed_url = getEdUrl(s, canvas_course_id)
    if not ed_url:
        return None, None
    r1 = s.get(ed_url)
    soup = BeautifulSoup(r1.text, 'html.parser')
    r2 = s.post(f'{ED_URL}/api/lti/oidc_login', 
                    data={
                        'iss': oidcEntry(soup, 'iss'),
                        'login_hint': oidcEntry(soup, 'login_hint'),
                        'client_id': oidcEntry(soup, 'client_id'),
                        'deployment_id': oidcEntry(soup, 'deployment_id'),
                        'target_link_uri': oidcEntry(soup, 'target_link_uri'),
                        'lti_message_hint': oidcEntry(soup, 'lti_message_hint'),
                        'canvas_environment': oidcEntry(soup, 'canvas_environment'),
                        'canvas_region': oidcEntry(soup, 'canvas_region'),
                        'lti_storage_target': oidcEntry(soup, 'lti_storage_target')
    })
    soup = BeautifulSoup(r2.text, 'html.parser')
    r3 = s.post(f'{ED_URL}/api/lti/launch',
                    data={
                        'utf8': soup.find('input', {'name': 'utf8'})['value'],
                        'authenticity_token': soup.find('input', {'name': 'authenticity_token'})['value'],
                        'id_token': oidcEntry(soup, 'id_token'),
                        'state': oidcEntry(soup, 'state'),
                        'lti_storage_target': oidcEntry(soup, 'lti_storage_target')
    })
    # 'https://edstem.org/us/courses/4130?_logintoken=H2l5NpZaCHBnuvMgXn2dfy9R'
    # parse url for ed_course_id and login_token
    ed_course_id = re.search(r'courses/(\d+)', r3.url).group(1)
    logintoken = re.search(r'_logintoken=(.+)', r3.url).group(1)
    r4 = s.post('https://us.edstem.org/api/login_token', json = {'login_token': logintoken})
    xtoken = r4.json()['token']
    return ed_course_id, xtoken
                
def requestThread(ed_course_id, xtoken, offset):
    """
    Each page is size MAX_PAGES with a starting point 
    (referring to the total number of threads, starting from newest)
    of offset*MAX_PAGES
    """
    return requests.get(f'{ED_URL}/api/courses/{ed_course_id}/threads',
                 headers = {'x-token': xtoken}, 
                 params = {'sort': 'new', 
                           'limit': MAX_PAGES,
                            'offset': int(MAX_PAGES*offset)}
    )                  

def requestAllThreads(ed_course_id, xtoken):
    threads = []
    r = requestThread(ed_course_id, xtoken, 0)
    i = 1
    while r.json()['threads']:
        print('page: ', i * MAX_PAGES)
        threads += r.json()['threads']
        r = requestThread(ed_course_id, xtoken, i)
        i+=1
    return threads


class Thread:
    def __init__(self, jsonDict):
        for key, value in jsonDict['thread'].items():
            setattr(self, key, value)
        self.users = {
            x['id']: {'name': x['name'], 'course_role': x['course_role']}
                      for x in jsonDict['users']
        }

    def __repr__(self):
        return f'Thread(id={self.id}, title={self.title})'

    def getUser(self, user_id):
        if user_id in self.users:
            return (f'{self.users[user_id]["name"]}'
                    f' ({self.users[user_id]["course_role"]})'
            )
        return 'Anonymous'
    
    def formatReply(self, reply):
        return (
            f"<h3>Author: {self.getUser(reply['user_id']) }</h3>"
            f"<h3> Vote Count: {reply['vote_count']} </h3>"
            f"{'<h3>ENDORSED</h3>' if reply['is_endorsed'] else ''}"
            f"{xmlToHtml(reply['content'])}"
            '<h3> ------------------------------------ </h3>'
        )

    def bfsRepliesStructure(self, replies):
        """
        We want a structure like this:
        REPLY # 1
        |   COMMENT # 1
            |    COMMENT # 11
        |   COMMENT # 2
        REPLY # 2
        |   COMMENT # 1
        """
        getDepth = lambda reply: 1 if 'depth' not in reply else reply['depth']
        ordering  = [] # list of html strings
        prevDepths = [] # stack of depths for enclosing divs
        replies = replies[::-1]
        while replies:
            reply = replies.pop(0)
            ordering.insert(
                len(ordering),
                f'<div style="text-indent: {getDepth(reply)*2}em;">'  + self.formatReply(reply)
                # depth': 0 if 'depth' not in reply else reply['depth'],
            )
            prevDepths.insert(0, getDepth(reply))
            for comment in reply['comments'][::-1]:
                comment['depth'] = reply.get('depth', 1) + 1
                replies.insert(0, comment)
            # add closing divs
            nextDepth = getDepth(replies[0]) if replies else -1
            while prevDepths and prevDepths[0] > nextDepth:
                prevDepths.pop(0)
                ordering.insert(len(ordering), '</div>')
        return ordering
    def bfsReplies(self, html, replies):
        if not replies:
            return html
        for replyHTML in self.bfsRepliesStructure(replies):
            html += replyHTML
        return html
                        
    def format(self):
        html = (f'<h1>Title: {self.title} </h1>'
                f"<h3>Author: {self.getUser(self.user_id)} </h3>" 
                f"<h3>Date: {self.created_at}</h3>"
                f"<h3>Category: {self.category}</h3>"
                f"<h3>Vote Count: {self.vote_count}</h3>"
                f"{'<h3>ENDORSED</h3>' if self.is_endorsed else ''}"
                f'{xmlToHtml(self.content)}'
        )
        html = self.bfsReplies(html, self.comments)
        html += '<h3> ----------- REPLIES ----------- </h3>'
        html = self.bfsReplies(html, self.answers)
        return html

@retry(3)
def getThread(thread_id, xtoken):
    r = requests.get(f'{ED_URL}/api/threads/{thread_id}',
                    headers = {'x-token': xtoken})
    if 'code' in r.json() and r.json()['code'] == 'rate_limit':
        raise Exception('Rate Limit')
    return Thread(r.json())

def scrapeEdPostForCourse(folder, xtoken, thread_id):
    """
    Strangely don't need ed_course_id, just thread_id
    """
    os.makedirs(folder, exist_ok=True)
    thread = getThread(thread_id, xtoken)
    html = thread.format()
    write(html, os.path.join(folder, sanitize(thread.title) + '.html'))

def scrapeEdPostsForCourse(canvasSession, canvas, course_id):
    course = getCourse(canvas, course_id)
    if not course:
        print(f'Course {course_id} not found')
        return
    print(f'***** Course: {course.name} *****')
    course_name = sanitize(course.name) if hasattr(course, 'name') else f'MISC_{course_id}'
    ed_course_id, xtoken = EdCourseAuthenticationThroughCanvas(canvasSession, course_id)
    if not ed_course_id:
        print(f'Edstem login failed for course {course_id}')
        return
    folder = os.path.join('Ed Discussions', course_name, 'Ed_Posts')
    threads = requestAllThreads(ed_course_id, xtoken)
    for i, thread in enumerate(threads):
        if i%50 == 0:
            print(f'*** Thread ({thread["id"]}): {i} / {len(threads)} ***')
        scrapeEdPostForCourse(folder, xtoken, thread['id'])

def scrapeEdPosts(personal_courses=False):
    canvas = Canvas(API_URL, API_KEY)
    # courses = list(canvas.get_courses()) # --> lists all courses you've taken
    courses = list(canvas.get_courses()) if personal_courses else \
                                        pd.read_csv('misc/courses.csv') 
    courses = courses if personal_courses else \
                    courses.id.tolist()
    s = canvasDuoLogin()
    for course in courses:
        scrapeEdPostsForCourse(s, canvas, course.id if personal_courses else course)

if __name__ == '__main__':
    scrapeEdPosts(False)

# canvas  = Canvas(API_URL, API_KEY)
# courses = list(canvas.get_courses()) # --> lists all courses you've taken
# course = getCourse(canvas, 24870)
# course = getCourse(canvas, 51447)
# course = getCourse(canvas, 28427)
# s = canvasDuoLogin()
# scrapeEdPostsForCourse(s, canvas, course.id)

# ed_course_id, xtoken = EdCourseAuthenticationThroughCanvas(s, course.id)

# xtoken = EdLogin()
# thread_id = 2810766
# thread_id = 3032849
# scrapeEdPostForCourse('testing', xtoken, thread_id)
# r = requests.get(f'{ED_URL}/api/threads/{thread_id}',
#                     headers = {'x-token': xtoken})
# writeJson(r.json())

# threads = getThread(1859828, xtoken)

# r = requests.get(f'{ED_URL}/api/threads/{1859828}',
#                     headers = {'x-token': xtoken})

# xml = xmlToHtml(r.json()['thread']['answers'][1]['content'])
# write(xml, 'testing.html', overwrite=True)