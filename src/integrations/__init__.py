import logging

# httpx logs full request URLs at INFO; Shop token endpoints carry app_secret/auth_code in the
# query string, so keep httpx at WARNING for any process importing an integration.
logging.getLogger("httpx").setLevel(logging.WARNING)
