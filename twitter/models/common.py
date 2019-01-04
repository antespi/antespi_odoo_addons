import uuid
import hmac
import hashlib
import binascii
import urllib
import cgi
import time
import tweepy
from base64 import b64encode

twitter_api = 'https://api.twitter.com'
request_token_url = twitter_api + '/oauth/request_token'
authorize_url = twitter_api + '/oauth/authorize'
access_token_url = twitter_api + '/oauth/access_token'

tapi = {}


def twitter_client(consumer_key, consumer_secret, access_token, access_secret):
    if not tapi.get(access_token):
        auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_secret)
        tapi[access_token] = tweepy.API(auth)
    return tapi.get(access_token)


def escape(s):
    return urllib.parse.quote(s, safe='~')


def oauth_timestamp():
    return int(time.time())


def oauth_nonce():
    return uuid.uuid4().hex


def oauth_response_keys(response):
    params = cgi.parse_qs(response, keep_blank_values=False)
    return {k: v[0] for k, v in params.items()}


def oauth_signature(method, url, consumer_secret, token_secret=None, params=None):
    if params is None:
        params = {}
    params_quote = {escape(str(k)): escape(str(v)) for k, v in params.items()}
    params_keys = list(params_quote.keys())
    params_keys.sort()
    params_string = '&'.join([k + '=' + params_quote[k] for k in params_keys])
    print("params_string: %s" % params_string)
    base_string = '&'.join([
        method.upper(),
        escape(str(url)),
        escape(params_string),
    ])
    print("base_string: %s" % base_string)
    key = escape(str(consumer_secret)) + '&'
    if token_secret:
        key += escape(str(token_secret))
    print("key: %s" % key)
    encoded_string = base_string.encode('utf-8')
    encoded_key = key.encode('utf-8')
    signature_hex = hmac.new(encoded_key, encoded_string, hashlib.sha1).hexdigest()
    signature_string = b64encode(binascii.unhexlify(signature_hex))
    return signature_string
