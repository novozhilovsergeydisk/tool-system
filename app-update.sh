#!/bin/bash

python3.12 -m venv venv_mac
source venv_mac/bin/activate
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py runserver 3001
