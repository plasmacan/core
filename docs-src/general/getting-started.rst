Getting Started with core
======================================

1) Use the template
---------------------

* In Github, there is a "use this template" button on the home page of this repo. Use that to create your own repo
* Pull your repo down with ``git clone``

2) Enable the actions
------------------------

The action are disabled by default when you use a template GitHub. Go to the ``Actions`` tab in your new repo to
enable them

3) Protect the branch
-----------------------

The main branch should be protected. You make changes to the main branch by making pull requests to it from another
branch. In the repo settings, under "Branches" on GitHub, enable branch protection


4) Set up locally
---------------------

Minimum system requirements are:

* Java 8
* Ruby 2.7
* Python 3.7

After installing the prerequisites, enter the repo directory and create a new python virtual environment
using ``python -m venv venv``

Enter the virtual environment using ``./venv/Scripts/activate``
(or ``.\venv\Scripts\activate`` on windows)

From within the virtual environment, install the requirements ``pip install -r requirements.txt``

Now, set up the pre-commit hook using ``pre-commit install``

To confirm all of the hooks work, run ``pre-commit run -a``
