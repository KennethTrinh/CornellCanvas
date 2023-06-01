from bs4 import BeautifulSoup
import requests
import os

# -.css -.js -.woff2 -.ico -font -logo -.svg -.png -.jpg -.gif -analytics? -collect? -googleads
def write(text, filename='test.html'):
    """
    For debugging purposes, write the text to a file
    """
    with open(filename, 'w') as f:
        soup = BeautifulSoup(text, 'html.parser')
        f.write(soup.prettify())

def login():
    """
    After calling this function, press two factor on phone - have to be quick!
    See Requests.png for a visual of the requests made.

    Request 1 - Request the ultimate final URL where I wish to grab data and begin my automation. 
    Request 2 - The session handles a redirection to an IDP SAML based url and is expecting my username and password. 
    Request 3 - After successfully passing credentials, the session is passed off to duo. Duo checks my IDP authentication. 
    Request 4 - After successful IDP authentication, duo prompts my device for 2FA and I do receive this prompt. 
    Request 5 - Ask the duo api for status. Duo answers with 'OK' and that a login request was 'pushed'.
    Request 6 - Ask the duo api again for status. Duo answers with 'Success' and provides the txid needed for last step of duo 2FA. 
    Request 7 - Send the txid to duo to complete the 2FA. 200
    Request 8 - Finally, the session is passed back to the original URL and I am logged in. 

    returns a session object
    """
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.95 Safari/537.36'})
    url1 = 'https://canvas.cornell.edu/login/saml'
    r1 = s.get(url1)
    # r1.url ==  https://shibidp.cit.cornell.edu/idp/profile/SAML2/Redirect/SSO?execution=e1s1
    url2 = r1.url 
    cred = {'j_username': os.environ['USERNAME'],
            'j_password': os.environ['PASSWORD'],
            '_eventId_proceed' : 'Login'}
    # r2.url == https://shibidp.cit.cornell.edu/idp/profile/SAML2/Redirect/SSO?execution=e1s2
    r2 = s.post(url2, data = cred)
    soup = BeautifulSoup(r2.text, 'html.parser')
    tx = soup.find('input', {'name': 'tx'})['value']
    _xsrf = soup.find('input', {'name': '_xsrf'})['value']
    #https://api-68fd2842.duosecurity.com/frame/frameless/v4/auth?sid=frameless-6f09f0f6-25b0-42a4-9121-cd8ac2c7defe&tx=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJkdW9fdW5hbWUiOiJrbHQ0NSIsInNjb3BlIjoib3BlbmlkIiwicmVzcG9uc2VfdHlwZSI6ImNvZGUiLCJyZWRpcmVjdF91cmkiOiJodHRwczpcL1wvc2hpYmlkcC5jaXQuY29ybmVsbC5lZHVcL2lkcFwvcHJvZmlsZVwvQXV0aG5cL0R1b1wvMkZBXC9kdW8tY2FsbGJhY2siLCJzdGF0ZSI6IjE5NDViMWE5ZjUyNmM1NmI0NDUyY2MyNjJhNzQzNThlLjY1MzE3MzMyIiwiZXhwIjoxNjc1NzEzMjI3LCJjbGllbnRfaWQiOiJESUU2UTlNWkVNVlZHOU5HUUY3VSJ9.CGbVmKIzyaQZlW9RF_4taglM8EbxO7_antpgXV20o8Dz1Z9BJ7vp1XL-FgmDksWWA3tnmh70VbW1v5N4mxkOGA
    r3 = s.post( r2.url, data = {'tx': tx, '_xsrf': _xsrf, 'parent': 'None'})
    soup = BeautifulSoup(r3.text, 'html.parser')
    sid = soup.find('input', {'name': 'sid'})['value']
    ukey = soup.find('input', {'name': 'ukey'})['value']
    # r3.url == https://api-68fd2842.duosecurity.com/frame/prompt?sid=frameless-fc6f4392-aa5a-4a41-8f39-ec3b3eaab0cb
    print('Evaluate Push!')
    r4 = s.post('https://api-68fd2842.duosecurity.com/frame/v4/prompt', data = {'device': 'phone1', 'factor': 'Duo Push', 'sid': sid, 'postAuthDestination': 'OIDC_EXIT'} )
    response = r4.json()['response']
    txid = response['txid']
    r5 = s.post('https://api-68fd2842.duosecurity.com/frame/v4/status', data = {'txid': txid, 'sid': sid})
    r6 = s.post('https://api-68fd2842.duosecurity.com/frame/v4/status', data = {'txid': txid, 'sid': sid})
    r7 = s.post('https://api-68fd2842.duosecurity.com/frame/v4/oidc/exit', 
                data = {'sid': sid, 'txid': txid, 'factor': 'Duo Push', 'device_key': ukey, '_xsrf': _xsrf, 'dampen_choice': 'true'})
    soup = BeautifulSoup(r7.text, 'html.parser')
    SAMLResponse = soup.find('input', {'name':'SAMLResponse'})['value']
    r8 = s.post(url1, data = {'SAMLResponse': SAMLResponse})
    print('Login Successful', r8.url) 
    return s

if __name__ == '__main__':
    s = login()
    r = s.get('https://canvas.cornell.edu/courses/24870/quizzes/47980')
    write(r.text, 'test.html')