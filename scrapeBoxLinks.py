import requests
import re
import json
from bs4 import BeautifulSoup
from utils import write, writeJson
from consts import USERNAME, PASSWORD
API_URL = 'https://cornell.app.box.com'

s = requests.Session()
s.headers.update({'User-Agent': 'Mozilla/5.0'})
url = 'https://cornell.box.com/s/hr6o4f9c6j2cl2exj31o7u8jz6wy8lr5'
r1 = s.get(url)
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
r3 = s.post(
    soup.find('form', {'method': 'post'})['action'],
    data = {
        'SAMLRequest': soup.find('input', {'name': 'SAMLRequest'})['value'],
    }
)
cred = {'j_username': USERNAME,
            'j_password': PASSWORD,
            '_eventId_proceed' : 'Login'}
# 'https://shibidp.cit.cornell.edu/idp/profile/SAML2/POST/SSO?execution=e1s1'
r4 = s.post(
    r3.url,
    data = cred
)
soup = BeautifulSoup(r4.text, 'html.parser')
#'https://sso.services.box.net/sp/ACS.saml2'
r5 = s.post(
    soup.find('form', {'method': 'post'})['action'],
    data = {
        'SAMLResponse': soup.find('input', {'name': 'SAMLResponse'})['value'],
        'RelayState': RelayState,
    }
)

#https://cornell.app.box.com/s/hr6o4f9c6j2cl2exj31o7u8jz6wy8lr5
r6 = s.get(r5.url)
soup = BeautifulSoup(r6.text, 'html.parser')
#  <script>
#    window.Box = window.Box || {};   Box.prefetchedData =
# get the script with Box.prefetchedData
script = soup.find('script', text=re.compile('Box.prefetchedData'))
prefetchedData = re.search(r'Box.prefetchedData = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
prefetchedData = json.loads(prefetchedData)
postStreamURLs = re.search(r'Box\.postStreamURLs = (\[.*?\]);', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
postStreamURLs = json.loads(postStreamURLs)
webpackPublicPath = re.search(r'Box\.webpackPublicPath = (.*?);', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
webpackRemotes = re.search(r'Box.webpackRemotes = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
webpackRemotes = json.loads(webpackRemotes)
config = re.search(r'Box\.config = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
config = json.loads(config)

script = soup.find('script', text=re.compile('Box.postStreamData'))
postStreamData = re.search(r'Box.postStreamData = (\{.*?\});', script.string, flags=re.DOTALL | re.MULTILINE).group(1)
postStreamData = json.loads(postStreamData)

itemID = postStreamData['/app-api/enduserapp/shared-item']['itemID']
file = f"file_{itemID}"

r7 = s.post('https://cornell.app.box.com/app-api/enduserapp/elements/tokens',
            json={
                'fileIDs': [file]
            },
            headers = {
                'Content-Type': 'application/json',
                'Request-Token': config['requestToken'],
                'Referer': r5.url,
                'Origin': 'https://cornell.app.box.com',
                'X-Box-Client-Name': 'enduserapp',
                'X-Box-Client-Version': '20.1091.0',
                'X-Box-Enduser-Api':postStreamData['/app-api/enduserapp/shared-item']['sharedName'],
                'X-Request-Token': config['requestToken'],
            }
)

# r8 = s.get(f'https://api.box.com/2.0/files/{itemID}',
#            headers = {
#                 'Authorization': f'Bearer {r7.json()[file]["write"]}',
#                 'Boxapi': f'shared_link={r5.url}',
#                 'Origin': 'https://cornell.app.box.com',
#                 'Referer': 'https://cornell.app.box.com/',
#                 'X-Box-Client-Name': 'enduserapp',
#                 'X-Box-Client-Version': '20.1091.0',
#                 'X-Box-Client-Name': 'ContentPreview',
#                 'X-Rep-Hints': '[3d][pdf][text][mp3][json][jpg?dimensions=1024x1024&paged=false][jpg?dimensions=2048x2048,png?dimensions=2048x2048][dash,mp4][filmstrip]'
#             },
#             params={
#                 'fields': 'permissions,shared_link,sha1,file_version,name,size,extension,representations,watermark_info,authenticated_download_url,is_download_available'
#             }
# )

r9 = s.get(f'https://api.box.com/2.0/files/{itemID}',
              headers = {
                  'Authorization': f'Bearer {r7.json()[file]["read"]}',
                  'Boxapi': f'shared_link={r5.url}',
                  'Origin': 'https://cornell.app.box.com',
                  'Referer': 'https://cornell.app.box.com/',
                  'X-Box-Client-Name': 'box-content-preview',
                  'X-Box-Client-Version': '2.93.0',
                  'X-Rep-Hints': '[3d][pdf]'
                },
                params={
                    'fields': 'id,permissions,shared_link,sha1,file_version,name,size,extension,representations,watermark_info,authenticated_download_url,is_download_available'
                }
)

pdfURL = r9.json()['representations']['entries'][0]['content']["url_template"]
# 'https://dl.boxcloud.com/api/2.0/internal_files/807151451016/versions/863717564616/representations/pdf/content/{+asset_path}?watermark_content=1686532769'
url, watermark_content = pdfURL.split('{+asset_path}?watermark_content=')
r10 = s.get(url,
            params = {
                'watermark_content': watermark_content,
                'access_token': r7.json()[file]["read"],
                'shared_link': r5.url,
                'box_client_name': 'box-content-preview',
                'box_client_version': '2.93.0', 
                'encoding': 'gzip',
            }
)

with open('test.pdf', 'wb') as f:
    f.write(r10.content)

print('Success!')
           
           

# writeJson(prefetchedData)
# writeJson(postStreamData)

# write(r8.text, overwrite=True)

