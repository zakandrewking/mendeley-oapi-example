"""
Mendeley Open API Example Client

Copyright (c) 2010, Mendeley Ltd. <copyright@mendeley.com>

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

For details of the Mendeley Open API see http://dev.mendeley.com/

See test.py and the tests in unit-tests/

"""

import hashlib
import json
from rauth import OAuth2Service
import os
import pickle
import requests
import sys
import urllib
import mimetypes

import apidefinitions


def resolve_http_redirect(url):
    # this function is needed to make sure oauth headers are not sent
    # when following redirections. requests only removes the cookies
    # as of 4889adce4e7ea6b9e89fd6059cda2dc7cdf53be8

    # see https://github.com/kennethreitz/requests/blob/develop/requests/models.py#L228
    # for a smarter implementation

    # same as chrome and firefox
    max_redirects = 20

    redirections = 0
    while True:
        redirections += 1
        if redirections > max_redirects:
            raise Exception("Too many redirects (%d)"%redirections)

        response = requests.head(url)
        if "location" in response.headers:
            new_url = response.headers["location"]
            if new_url != url:
                continue
        break
    return url

class OAuthClient(object):
    """General purpose OAuth client"""
    def __init__(self, client_id, client_secret, options=None):
        if options == None: options = {}
        # Set values based on provided options, or revert to defaults
        self.access_token_url = options.get('access_token_url', 'https://api-oauth2.mendeley.com/oauth/token')
        self.authorize_url = options.get('access_token_url', 'https://api-oauth2.mendeley.com/oauth/authorize')
        self.name = options.get('name', 'Example app')
        self.base_url = options.get('base_url', 'https://api-oauth2.mendeley.com')

        self.consumer = OAuth2Service(client_id=client_id,
                client_secret=client_secret,
                name=self.name,
                authorize_url=self.authorize_url,
                access_token_url=self.access_token_url,
                base_url=self.base_url)

    def get_authorize_url(self, redirect_uri="http://localhost"):
        params = {'redirect_uri': redirect_uri,
                'response_type': 'code',
                'scope':'all'}
        return self.consumer.get_authorize_url(**params)

    def get_access_token(self, code, redirect_uri):
        data = {'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri}

        return self.consumer.get_access_token(data=data, decoder=json.loads)

    def get_session(self, access_token):
        return self.consumer.get_session(token=access_token)

    def get(self, path, token=None):
        request = { "method": "GET", "url": path}
        return self._send_request(request, token)

    def post(self, path, post_params, token=None):
        request = { "method": "POST", "url": path}
        return self._send_request(request, token, post_params)

    def delete(self, path, token=None):
        request = { "method": "DELETE", "url": path}
        return self._send_request(request, token)

    def put(self, path, token=None, body=None, headers=None):
        request = { "method": "PUT", "url": path}
        return self._send_request(request, token, body, headers)

    def _send_request(self, request, token=None, body=None, extra_headers=None):
        session = self.get_session(token)

        # common arguments for the requests call
        # disables automatic redirections following as requests
        # to use resolve_http_redirect(..) above
        requests_args = {"allow_redirects":False}
        method = request.get("method")
        url = request.get("url")

        if method == 'GET':
            return session.get(url, **requests_args)

        if method == 'POST':
            return session.post(url, data=body, headers={"Content-type": "application/x-www-form-urlencoded"},**requests_args )

        elif method == 'DELETE':
            return session.delete(url, **requests_args)

        elif method == 'PUT':
            return session.put(url, data=body, headers=extra_headers, **requests_args)

        assert False

class MendeleyRemoteMethod(object):
    """Call a Mendeley OpenAPI method and parse and handle the response"""
    def __init__(self, details, callback):
        self.details = details # Argument, URL and additional details.
        self.callback = callback # Callback to actually do the remote call

    def serialize(self, obj):
        if isinstance(obj,dict):
            return json.dumps(obj)
        return obj

    def __call__(self, *args, **kwargs):
        url = self.details['url']
        # Get the required arguments
        if self.details.get('required'):
            required_args = dict(zip(self.details.get('required'), args))
            if len(required_args) < len(self.details.get('required')):
                raise ValueError('Missing required args')

            for (key, value) in required_args.items():
                required_args[key] = urllib.quote_plus(str(value))

            url = url % required_args

        # Optional arguments must be provided as keyword args
        optional_args = {}
        for optional in self.details.get('optional', []):
            if kwargs.has_key(optional):
                optional_args[optional] = self.serialize(kwargs[optional])

        # Do the callback - will return a HTTPResponse object
        response = self.callback(url, self.details.get('access_token_required', True), self.details.get('method', 'get'), optional_args)

        # basic redirection following
        if response.status_code in [301, 302, 303]:
            url = resolve_http_redirect(response.headers["location"])
            response = requests.get(url)

        # if we expect something else than 200 with no content, just check
        # that the status code is as expected
        status = response.status_code
        expected_status = self.details.get("expected_status",200)
        if expected_status != 200:
            return status == expected_status

        # if the request failed, return all the request instead of just the body
        if status == 401:
            print 'Access token expired, please remove the .pkl file and try again.'
            print response.content
            return response

        if status in [400, 403, 404, 405]:
            return response

        content_type = response.headers["Content-Type"]
        ct = content_type.split("; ")
        mime = ct[0]
        attached = None
        try:
            content_disposition = response.headers["Content-Disposition"]
            cd = content_disposition.split("; ")
            attached = cd[0]
            filename = cd[1].split("=")
            filename = filename[1].strip('"')
        except:
            pass

        if mime == 'application/json':
            return json.loads(response.text)
        elif attached == 'attachment':
            return {'filename': filename, 'data': response.content}
        else:
            return response

class MendeleyAccount:

    def __init__(self, access_token):
        self.access_token = access_token

class MendeleyTokensStore:

    def __init__(self, filename='mendeley_api_keys.pkl'):
        self.filename = filename
        self.accounts = {}

        if self.filename:
            self.load()

    def __del__(self):
        if self.filename:
            self.save()

    def add_account(self, key, access_token):
        self.accounts[key] = MendeleyAccount(access_token)

    def get_account(self, key):
        return self.accounts.get(key, None)

    def get_access_token(self, key):
        if not key in self.accounts:
            return None
        return self.accounts[key].access_token

    def remove_account(self, key):
        if not key in self.accounts:
            return
        del self.accounts[key]

    def save(self):
        if not self.filename:
            raise Exception("Need to specify a filename for this store")
        pickle.dump(self.accounts, open(self.filename, 'w'))

    def load(self):
        if not self.filename:
            raise Exception("Need to specify a filename for this store")
        try:
            self.accounts = pickle.load(open(self.filename, 'r'))
        except IOError:
            print "Can't load tokens from %s"%self.filename

class MendeleyClientConfig:

    def __init__(self, filename='config.json'):
        self.filename = filename
        self.load()

    def is_valid(self):
        if not hasattr(self,"client_id") or not hasattr(self, "client_secret"):
            return False

        if self.client_id == "<change me>" or self.client_secret == "<change me>":
            return False

        return True

    def load(self):
        loaded = json.loads(open(self.filename,'r').read())
        for key, value in loaded.items():
            setattr(self, key, value.encode("ascii"))

class MendeleyClient(object):

    def __init__(self, client_id, client_secret, options=None):
        self.oauth_client = OAuthClient(client_id, client_secret, options)

        # Create methods for all of the API calls
        for method, details in apidefinitions.methods.items():
            setattr(self, method, MendeleyRemoteMethod(details, self._api_request))

    # replace the upload_pdf with a more user friendly method
    def upload_pdf(self,document_id, filename):

        fp = open(filename, 'rb')
        data = fp.read()

        hasher = hashlib.sha1()
        hasher.update(data)
        sha1_hash = hasher.hexdigest()

        return self._upload_pdf(document_id,
                            file_name=os.path.basename(filename),
                            sha1_hash=sha1_hash,
                            data=data)

    def _api_request(self, url, access_token_required = False, method='get', params=None):
        if params == None:
            params = {}

        access_token = None
        if access_token_required:
            access_token = self.get_access_token()

        if method == 'get':
            if len(params) > 0:
                url += "?%s" % urllib.urlencode(params)
            response = self.oauth_client.get(url, access_token)
        elif method == 'delete':
            response = self.oauth_client.delete(url, access_token)
        elif method == 'put':
            [content_type, encoding] = mimetypes.guess_type(params.get('file_name'))
            headers = {'Content-disposition': 'attachment; filename="%s"' % params.get('file_name'), 'Content-Type': content_type}
            response = self.oauth_client.put(url, access_token, params.get('data'), headers)
        elif method == 'post':
            response = self.oauth_client.post(url, params, access_token)
        else:
            raise Exception("Unsupported method: %s"%method)
        return response

    def set_access_token(self, access_token):
        self.access_token = access_token

    def get_access_token(self):
        return self.access_token

    def get_auth_url(self,callback_url="http://localhost"):
        """Returns an auth url"""
        return self.oauth_client.get_authorize_url(callback_url)

    def exchange_access_token(self, code):
        """Generate an access_token from a request_token generated by
           get_auth_url and the verifier received from the server"""
        try :
            access_token = self.oauth_client.get_access_token(code, "http://localhost")
            print access_token
        except Exception as e:
            print "exchange_access_token"
            print e
        return access_token

    def interactive_auth(self):
        auth_url = self.get_auth_url()
        print 'Go to the following url to auth the token:\n%s' % (auth_url,)
        code = raw_input('Enter code: ')
        self.set_access_token(self.exchange_access_token(code))

def create_client(config_file="config.json", keys_file=None, account_name="test_account"):
    # Load the configuration file
    config = MendeleyClientConfig(config_file)
    if not config.is_valid():
        print "Please edit config.json before running this script"
        sys.exit(1)

    # create a client and load tokens from the pkl file
    host = "api-oauth2.mendeley.com"
    if hasattr(config, "host"):
        host = config.host

    if not keys_file:
        keys_file = "keys_%s.pkl"%host

    client = MendeleyClient(config.client_id, config.client_secret, {"host":host})
    tokens_store = MendeleyTokensStore(keys_file)

    # configure the client to use a specific token
    # if no tokens are available, prompt the user to authenticate
    access_token = tokens_store.get_access_token(account_name)
    if not access_token:
        try:
            client.interactive_auth()
            tokens_store.add_account(account_name,client.get_access_token())
        except Exception as e:
            print e
            sys.exit(1)
    else:
        client.set_access_token(access_token)
    return client
