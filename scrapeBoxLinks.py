import requests
import re
import json
import os
from bs4 import BeautifulSoup
from utils import sanitize, write, writeJson
from consts import USERNAME, PASSWORD
API_URL = 'https://cornell.app.box.com'

def getFileName(itemID, postStreamData):
    if '/app-api/enduserapp/shared-folder' in postStreamData:
        items = postStreamData['/app-api/enduserapp/shared-folder']['items']
    else:
        items = postStreamData[f"/app-api/enduserapp/item/f_{itemID}"]['items']
    item = [item for item in items if item['id'] == itemID][0]
    return f"{sanitize(item['name'])}.{item['extension']}"

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

def requestItemUrl(s, itemID, readToken, shared_link):
    r = s.get(f'https://api.box.com/2.0/files/{itemID}',
                headers = {
                    'Authorization': f'Bearer {readToken}',
                    'Boxapi': f'shared_link={shared_link}',
                    'X-Box-Client-Name': 'box-content-preview',
                    'X-Rep-Hints': '[3d][pdf]'
                    },
                params={
                    'fields': 'id,permissions,shared_link,sha1,file_version,name,size,extension,representations,watermark_info,authenticated_download_url,is_download_available'
                }                    
    )
    pdfURL = r.json()['representations']['entries'][0]['content']["url_template"]
    return pdfURL.split('{+asset_path}?watermark_content=')

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

def scrapeBoxFile(s, folder, postStreamData, itemID, sharedName, requestToken, shared_link):
    file = f"file_{itemID}"
    readToken, writeToken = requestTokens(s, file, requestToken, sharedName)

    previewURL, watermark_content = requestItemUrl(s, itemID, readToken, shared_link)

    content = requestPreviewContent(s, previewURL, watermark_content, readToken, shared_link)

    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, getFileName(itemID, postStreamData)), 'wb') as f:
        f.write(content)

    print(f'Wrote: {getFileName(itemID, postStreamData)}')

def scrapeBoxFolder(s, folder, postStreamData, items, sharedName, requestToken, shared_link):
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
            print('Type: ', item['type'])
            print(item)




def scrapeBoxLink(s, url):
    r1 = s.get(url)
    # https://cornell.app.box.com/s/hr6o4f9c6j2cl2exj31o7u8jz6wy8lr5
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
            folder = '.' ,
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
            folder = os.path.join('.', postStreamData['/app-api/enduserapp/shared-folder']['currentFolderName']),
            postStreamData = postStreamData,
            items = postStreamData['/app-api/enduserapp/shared-folder']['items'],
            sharedName = sharedName,
            requestToken = requestToken,
            shared_link = r1.url
        )
    else:
        print(f'itemType {itemType} not recognized')



s = boxLogin()
url = 'https://cornell.box.com/s/hr6o4f9c6j2cl2exj31o7u8jz6wy8lr5' # prelim 2
# url = 'https://cornell.box.com/s/z4bts0jiufhcnx21rdmu7wopmyx003x7' # assignment 1 folder

scrapeBoxLink(s, url)


    
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