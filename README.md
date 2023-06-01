# Follow along as I scrape my canvas for one last hurrah!

Programming doesn't stop after graduation! I'm gonna scrape all the contents of my canvas to personify Cornell's Any Person, Any Study motto.  In this tutorial, you will learn how to download an entire course from canvas without even opening your browser.

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

Do the same thing with your username and password:
```
export USERNAME=<your username here>
export PASSWORD=<your password here>
```

Test that you can run canvasDuoLogin.py - before running script, make sure you have duo mobile installed and ready to go. Then run the script:
```
python canvasDuoLogin.py
```

You'll be prompted with this message:
```
Evaluate Push
```
Go to your phone and accept the push notification. Successful authentication will result in this message:
```
Login Successful https://canvas.cornell.edu/?login_success=1
```