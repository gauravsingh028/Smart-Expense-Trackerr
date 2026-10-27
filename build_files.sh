#!/bin/bash
# Vercel build script
pip install -r requirements.txt
python manage.py collectstatic --noinput
