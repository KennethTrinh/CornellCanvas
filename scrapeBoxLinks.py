import requests
import re
import json
import os
from bs4 import BeautifulSoup
from utils import sanitize, write, writeJson, getModules, getCourse, getAllCourses, retry
from canvasapi import Canvas
from consts import USERNAME, PASSWORD, API_KEY, API_URL


def getFileName(itemID, postStreamData):
    if '/app-api/enduserapp/shared-folder' in postStreamData:
        items = postStreamData['/app-api/enduserapp/shared-folder']['items']
    else:
        items = postStreamData[f"/app-api/enduserapp/item/f_{itemID}"]['items']
    item = [item for item in items if item['id'] == itemID][0]
    # return f"{sanitize(item['name'])}.{item['extension']}" # extension embedded in name
    return f"{sanitize(item['name'])}"

def boxLogin():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0'})
    r1 = s.get('https://cornell.account.box.com/login')
    soup = BeautifulSoup(r1.text, 'html.parser')

    r2 = s.post('https://cornell.account.box.com/login',
                    data = {
                        'redirect_url': soup.find('input', {'name': 'redirect_url'})['value'],
                        'request_token': soup.find('input', {'name': 'request_token'})['value'],
                        'login_page_source': soup.find('input', {'name': 'login_page_source'})['value'],
                    }
    )
    soup = BeautifulSoup(r2.text, 'html.parser')
    RelayState = soup.find('input', {'name': 'RelayState'})['value']

    r3 = s.post( soup.find('form', {'method': 'post'})['action'],
                    data = {
                        'SAMLRequest': soup.find('input', {'name': 'SAMLRequest'})['value'],
                    }
    )

    # 'https://shibidp.cit.cornell.edu/idp/profile/SAML2/POST/SSO?execution=e1s1'
    r4 = s.post(r3.url,
                data = {
                    'j_username': USERNAME,
                    'j_password': PASSWORD,
                    '_eventId_proceed' : 'Login'
                }
    )
    soup = BeautifulSoup(r4.text, 'html.parser')

    #'https://sso.services.box.net/sp/ACS.saml2'
    r5 = s.post(soup.find('form', {'method': 'post'})['action'],
                data = {
                    'SAMLResponse': soup.find('input', {'name': 'SAMLResponse'})['value'],
                    'RelayState': RelayState,
                }
    )
    return s

@retry(retry_num=3)
def requestTokens(s, file, requestToken, sharedName):
    r = s.post('https://cornell.app.box.com/app-api/enduserapp/elements/tokens',
                json={
                    'fileIDs': [file]
                },
                headers = {
                    'Content-Type': 'application/json',
                    'Request-Token': requestToken,
                    # 'X-Box-Client-Name': 'enduserapp',
                    'X-Box-Enduser-Api':sharedName,
                    'X-Request-Token': requestToken,
                }
    )
    return r.json()[file]['read'], r.json()[file]['write']

@retry(retry_num=3)
def requestItemUrl(s, itemID, readToken, shared_link):
    r = s.get(f'https://api.box.com/2.0/files/{itemID}',
                headers = {
                    'Authorization': f'Bearer {readToken}',
                    'Boxapi': f'shared_link={shared_link}',
                    'X-Box-Client-Name': 'box-content-preview',
                    'X-Rep-Hints': '[3d][pdf][text][mp3][json][jpg?dimensions=1024x1024&paged=false][jpg?dimensions=2048x2048,png?dimensions=2048x2048][dash,mp4][filmstrip]'
                    },
                params={
                    'fields': 'id,permissions,shared_link,sha1,file_version,name,size,extension,representations,watermark_info,authenticated_download_url,is_download_available'
                }                    
    )
    return r.json()

@retry(retry_num=3)
def requestPreviewContent(s, previewURL, watermark_content, readToken, shared_link):
    r = s.get(previewURL,
                params = {
                    'watermark_content': watermark_content,
                    'access_token': readToken,
                    'shared_link': shared_link,
                    'box_client_name': 'box-content-preview',
                    'encoding': 'gzip',
                }
    )
    return r.content

@retry(retry_num=3)
def requestContent(s, itemID, requestToken, sharedName):
    """
    May eventually need readToken, but the only course 
    I had with public content was to everyone (not just to cornell students)
    """
    r = s.post('https://cornell.app.box.com/index.php',
                params = {
                   'rm': 'box_download_shared_file',
                   'shared_name': sharedName,
                   'file_id': f'f_{itemID}',
                },
                data = {
                    'request_token': requestToken,
                }
    )
    return r.content

def getUrlForExtension(entries, extension):
    """
    We can only have extensions specified in 'X-Rep-Hints' header
    """
    if extension == 'mp4':
        extension = 'dash'
    if extension == 'csv':
        extension = 'pdf'
    entry = [e for e in entries if e['representation'] == extension][0]
    return entry['content']['url_template']

def scrapeBoxFile(s, folder, postStreamData, itemID, sharedName, requestToken, shared_link):
    file = f"file_{itemID}"
    readToken, writeToken = requestTokens(s, file, requestToken, sharedName)

    itemDict = requestItemUrl(s, itemID, readToken, shared_link)
    if itemDict['permissions']['can_download']:
        content = requestContent(s, itemID, requestToken, sharedName)
    elif itemDict['permissions']['can_preview']:
        extensionUrl = getUrlForExtension(itemDict['representations']['entries'], itemDict['extension'])
        previewURL, watermark_content = extensionUrl.split('{+asset_path}?watermark_content=')
        content = requestPreviewContent(s, previewURL, watermark_content, readToken, shared_link)
    
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, getFileName(itemID, postStreamData)), 'wb') as f:
        f.write(content)

    print(f'Success! scraped File: {getFileName(itemID, postStreamData)}')

def scrapeBoxFolder(s, folder, postStreamData, items, sharedName, requestToken, shared_link):
    """
    I'm not exactly sure how to handle nested folders, but I suspect just call
    this function recursively.  Nonetheless, I don't have any links that have 
    given me nested folders, so I wouldn't be able to test this.
    I'm passing the torch to whoever needs this code next.
    """
    print(f'Scraping Folder: {folder}')
    for item in items:
        if item['type'] == 'file':
            scrapeBoxFile(
                s,
                folder = folder,
                postStreamData = postStreamData,
                itemID = item['id'],
                sharedName = sharedName,
                requestToken = requestToken,
                shared_link = shared_link
            )
        else:
            # TODO: Handle nested folders
            print('Type: ', item['type'])
            print(item)


def scrapeBoxLink(s, folder, url):
    r1 = s.get(url)
    r2 = s.get(r1.url)
    soup = BeautifulSoup(r2.text, 'html.parser')
    script = soup.find('script', text=re.compile('Box.prefetchedData'))
    config = re.search(r'Box.config = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
    config = json.loads(config)

    script = soup.find('script', text=re.compile('Box.postStreamData'))
    postStreamData = re.search(r'Box.postStreamData = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
    postStreamData = json.loads(postStreamData)

    itemType = postStreamData['/app-api/enduserapp/shared-item']['itemType']
    sharedName = postStreamData['/app-api/enduserapp/shared-item']['sharedName']
    requestToken = config['requestToken']
    if itemType == 'file':
        # postStreamData has: 
        # dict_keys(['/app-api/enduserapp/shared-item', '/app-api/enduserapp/item/f_807151451016'])
        scrapeBoxFile(
            s,
            folder = folder,
            postStreamData = postStreamData,
            itemID = postStreamData['/app-api/enduserapp/shared-item']['itemID'],
            sharedName = sharedName, 
            requestToken = requestToken,
            shared_link = r1.url
        )
    elif itemType == 'folder':
        # postStreamData has: 
        # dict_keys(['/app-api/enduserapp/shared-item', '/app-api/enduserapp/shared-folder'])
        scrapeBoxFolder(
            s,
            folder = os.path.join(folder, postStreamData['/app-api/enduserapp/shared-folder']['currentFolderName']),
            postStreamData = postStreamData,
            items = postStreamData['/app-api/enduserapp/shared-folder']['items'],
            sharedName = sharedName,
            requestToken = requestToken,
            shared_link = r1.url
        )
    else:
        print(f'itemType {itemType} not recognized')

def scrapeLink(s, folder, downloaded_IDs, external_url):
    if not external_url.startswith('https://cornell.box.com/s'):
        return
    shared_id = re.search(r'https://cornell.box.com/s/(.*)', external_url).group(1)
    if shared_id in downloaded_IDs:
        print(f'Already downloaded: {external_url}')
        return
    print(f'FOUND BOX LINK: {external_url}')
    scrapeBoxLink(s, folder, external_url)
    downloaded_IDs.add(shared_id)

def scrapeModule(s, folder, module, downloaded_IDs):
    module_name = sanitize(module.name) if hasattr(module, 'name') else f'MISC_{module.id}'
    folder = os.path.join(folder, module_name)
    for item in module.get_module_items():
        if item.type == 'ExternalUrl':
            scrapeLink(s, folder, downloaded_IDs, item.external_url)

def scrapeModules(s, course, folder, downloaded_IDs):
    print(f'*** Modules for course: {course.id} ***')
    modules = getModules(course)
    folder = os.path.join(folder, 'Modules')
    for module in modules:
        # print(f'Module: {module.name} , ID: {module.id}')
        scrapeModule(s, folder, module, downloaded_IDs)

def scrapeCourse(s, canvas, course_id):
    downloaded_IDs = set()
    course = getCourse(canvas, course_id)
    if not course:
        print(f'Course not accessible for course: {course_id}')
        return
    course_name = sanitize(course.name) if hasattr(course, 'name') else f'MISC_{course.id}'
    print(f'********* Course: {course_name} ({course.id}) *********')
    folder = os.path.join('data', course_name)
    scrapeModules(s, course, folder, downloaded_IDs)

# def scrapeBoxLinks():
#     s = boxLogin()
#     canvas = Canvas(API_URL, API_KEY)
#     courses = getAllCourses(canvas)
#     for i, course_id in enumerate(courses):
#         print(f'********* {i+1}/{len(courses)} *********')
#         scrapeCourse(s, canvas, course_id)

if __name__ == '__main__':
    s = boxLogin()
    canvas = Canvas(API_URL, API_KEY)
    scrapeCourse(s, canvas, 27847) # ML
    scrapeCourse(s, canvas, 44979) # MP4s
    scrapeBoxLink(
        s, 
        folder = "data/SYSENMAE 52806280 Adaptive and Learning Systems - Prof Timothy Sands/Modules/Previous Years' Live Lectures/2021 Live Recordings (Helpful !!)",
        url = 'https://cornell.app.box.com/s/gywlk1cz26jgg0sdgpie8ftxn9msm3lo?page=2'
    )
    scrapeBoxLink(
        s, 
        folder = "data/SYSENMAE 52806280 Adaptive and Learning Systems - Prof Timothy Sands/Modules/Previous Years' Live Lectures/2020 Live Recordings (Superfluous?)",
        url = 'https://cornell.app.box.com/s/amks8w832sxm2unwfqzpgoyxvxwxttk1?page=2'
    )



# scrapeCourse(s, Canvas(API_URL, API_KEY), 18565) # 1 PPT
# ********* Course: SYSENMAE 52806280 Adaptive and Learning Systems - Prof Timothy Sands (44979) *********
# *** Modules for course: 44979 ***
# FOUND BOX LINK: https://cornell.box.com/s/gywlk1cz26jgg0sdgpie8ftxn9msm3lo
# FOUND BOX LINK: https://cornell.box.com/s/amks8w832sxm2unwfqzpgoyxvxwxttk1
# scrapeBoxLink(s, 'test', external_url)
# url =  'https://cornell.box.com/s/gywlk1cz26jgg0sdgpie8ftxn9msm3lo' # videos
# r1 = s.get(url)
# r2 = s.get(r1.url)
# soup = BeautifulSoup(r2.text, 'html.parser')
# script = soup.find('script', text=re.compile('Box.prefetchedData'))
# config = re.search(r'Box.config = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
# config = json.loads(config)

# script = soup.find('script', text=re.compile('Box.postStreamData'))
# postStreamData = re.search(r'Box.postStreamData = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
# postStreamData = json.loads(postStreamData)
# # writeJson(postStreamData)

# itemType = postStreamData['/app-api/enduserapp/shared-item']['itemType']
# sharedName = postStreamData['/app-api/enduserapp/shared-item']['sharedName']
# requestToken = config['requestToken']

# items = postStreamData['/app-api/enduserapp/shared-folder']['items']
# item = items[1]
# itemID = item['id']
# file = f"file_{itemID}"
# shared_link = r1.url

# readToken, writeToken = requestTokens(s, file, requestToken, sharedName)
# itemDict = requestItemUrl(s, itemID, readToken, shared_link)
# extensionUrl = getUrlForExtension(itemDict['representations']['entries'], itemDict['extension'])
# r = s.post('https://cornell.app.box.com/index.php',
#                 params = {
#                    'rm': 'box_download_shared_file',
#                    'shared_name': sharedName,
#                    'file_id': f'f_{itemID}',
#                 },
#                 data = {
#                     'request_token': requestToken,
#                 }
#     )



# s = boxLogin()
# url = 'https://cornell.box.com/s/hr6o4f9c6j2cl2exj31o7u8jz6wy8lr5' # prelim 2
# url = 'https://cornell.box.com/s/z4bts0jiufhcnx21rdmu7wopmyx003x7' # assignment 1 folder
# scrapeBoxLink(s, url)
    
# readToken, writeToken = requestTokens(s, file, config['requestToken'], postStreamData['/app-api/enduserapp/shared-item']['sharedName'])





# r3 = s.post('https://cornell.app.box.com/app-api/enduserapp/elements/tokens',
#                 json={
#                     'fileIDs': [file]
#                 },
#                 headers = {
#                     'Content-Type': 'application/json',
#                     'Request-Token': config['requestToken'],
#                     'Referer': r1.url,
#                     'Origin': 'https://cornell.app.box.com',
#                     'X-Box-Client-Name': 'enduserapp',
#                     'X-Box-Client-Version': '20.1091.0',
#                     'X-Box-Enduser-Api':postStreamData['/app-api/enduserapp/shared-item']['sharedName'],
#                     'X-Request-Token': config['requestToken'],
#                 }
# )

# r4 = s.get(f'https://api.box.com/2.0/files/{itemID}',
#                 headers = {
#                     'Authorization': f'Bearer {r3.json()[file]["read"]}',
#                     'Boxapi': f'shared_link={r1.url}',
#                     'Origin': 'https://cornell.app.box.com',
#                     'Referer': 'https://cornell.app.box.com/',
#                     'X-Box-Client-Name': 'box-content-preview',
#                     'X-Box-Client-Version': '2.93.0',
#                     'X-Rep-Hints': '[3d][pdf]'
#                     },
#                     params={
#                         'fields': 'id,permissions,shared_link,sha1,file_version,name,size,extension,representations,watermark_info,authenticated_download_url,is_download_available'
#                     }
# )

# pdfURL = r4.json()['representations']['entries'][0]['content']["url_template"]
# 'https://dl.boxcloud.com/api/2.0/internal_files/807151451016/versions/863717564616/representations/pdf/content/{+asset_path}?watermark_content=1686532769'
# url, watermark_content = pdfURL.split('{+asset_path}?watermark_content=')
# r5 = s.get(url,
#             params = {
#                 'watermark_content': watermark_content,
#                 'access_token': readToken,
#                 'shared_link': r1.url,
#                 'box_client_name': 'box-content-preview',
#                 'box_client_version': '2.93.0', 
#                 'encoding': 'gzip',
#             }
# )

# with open('test.pdf', 'wb') as f:
#     f.write(r5.content)

# print('Done2!')

            
            

# writeJson(prefetchedData)
# writeJson(postStreamData)