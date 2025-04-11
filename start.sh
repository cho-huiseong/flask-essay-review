#!/bin/sh
exec gunicorn app:app --timeout 120
