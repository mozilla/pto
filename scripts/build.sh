# Jenkins build script for running tests
#
# peterbe@mozilla.com
#
# Inspired by Zamboni
# https://github.com/mozilla/zamboni/blob/master/scripts/build.sh


find . -name '*.pyc' -delete;

rm -fr env
virtualenv --no-site-packages env
source env/bin/activate

git submodule update --init --recursive
echo "
from base import *
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'pto',
        'USER': 'hudson',
        'PASSWORD': '',
        'HOST': 'localhost',
        'PORT': '',
        'OPTIONS': {
            'init_command': 'SET storage_engine=InnoDB',
            'charset' : 'utf8',
            'use_unicode' : True,
        },
        'TEST_CHARSET': 'utf8',
        'TEST_COLLATION': 'utf8_general_ci',
    },
}
SECRET_KEY = 'somethingaslongasitsnotblank'

HMAC_KEYS = {
    '2012-06-06': 'anything',
}
from django_sha2 import get_password_hashers
hashers = (#'django_sha2.hashers.BcryptHMACCombinedPasswordVerifier',
 #'django_sha2.hashers.SHA512PasswordHasher',
 #'django_sha2.hashers.SHA256PasswordHasher',
 'django.contrib.auth.hashers.SHA1PasswordHasher',
 'django.contrib.auth.hashers.MD5PasswordHasher',
 'django.contrib.auth.hashers.UnsaltedMD5PasswordHasher'
)
PASSWORD_HASHERS = get_password_hashers(hashers, HMAC_KEYS)
AUTH_LDAP_BIND_PASSWORD = 'Anything'
AUTH_LDAP_BIND_DN = 'Something'
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'pto'
    }
}
" > pto/settings/local.py

## install dependencies
# prod.txt is covered by vendor-local

# compiled modules
pip install -r requirements/compiled.txt

# dependencies for running the tests
pip install -r requirements/dev.txt

FORCE_DB=true python manage.py test --noinput
