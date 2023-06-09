# Follow along as I scrape my canvas for one last hurrah!
Programming doesn't stop after graduation! I'm gonna scrape all the contents of my canvas to personify Cornell's Any Person, Any Study motto.  I'm going to download everything from every course without opening my browser.

# Background
- Instructure / Canvas LMS has a valuation of $2.9 Billion (https://iblnews.org/instructure-canvas-details-its-ipo-a-valuation-of-2-9-billion-expected/)

- Edstem Technologies's estimated annual revenue is currently $8M per year (https://growjo.com/company/Edstem_Technologies)

This is concerning because some little boy (like myself) shouldn't be able to deconstruct their system and download all the course content that he's ever had access to.  Yet here we are!

## Setup
```
python -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Then log onto canvas and go to Account >> Settings >> + New Access Token 

Careful! This token can only be viewed once.
Make this an environment variable called CANVAS_TOKEN like so:
```
export CANVAS_TOKEN=<your token here>
```
You can just paste this into your env/bin/activate file if you want!

## Authorizaton Required Setup (Optional)
It turns out that Quizzes and Ed Posts require username/password authentication with two factor login - 
quel cauchemar! Luckily, I went throught the http requests and reverse-engineered the login process so you don't have to.  Feel free to look at `misc/CanvasRequests.png` and `misc/EdRequests.png` for the chain of requests that happen (I just use chrome dev tools, no postman needed), and check my implementation in `canvasDuoEdLogin.py` for each one.  Follow the steps below to get your username and password set up.

```
export USERNAME=<your username here>
export PASSWORD=<your password here>
```

Test that you can run `canvasDuoLogin.py` - before running script, make sure you have duo mobile installed and ready to go. Then run the script:
```
python canvasDuoEdLogin.py
```

You'll be prompted with this message:
```
Evaluate Push
```
Go to your phone and accept the push notification. Successful authentication will result in this message:
```
Login Successful https://canvas.cornell.edu/?login_success=1
```

## TODO:
Describe `scrapeCanvas.py` , `scrapeEdPosts.py`, and `scrapeExistingQuizzes.py`