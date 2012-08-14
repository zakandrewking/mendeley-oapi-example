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

Example usage:

>>> from pprint import pprint
>>> from mendeley_client import MendeleyClient
>>> mendeley = MendeleyClient('<consumer_key>', '<secret_key>')
>>> try:
>>> 	mendeley.load_keys()
>>> except IOError:
>>> 	mendeley.get_required_keys()
>>> 	mendeley.save_keys()
>>> results = mendeley.search('science')
>>> pprint(results['documents'][0])
{u'authors': None,
 u'doi': None,
 u'id': u'8c18bd50-6f07-11df-b8f0-001e688e2dcb',
 u'mendeley_url': u'http://localhost/research//',
 u'publication_outlet': None,
 u'title': None,
 u'year': None}
>>> documents = mendeley.library()
>>> pprint(documents)
{u'current_page': 0,
 u'document_ids': [u'86175', u'86176', u'86174', u'86177'],
 u'items_per_page': 20,
 u'total_pages': 1,
 u'total_results': 4}
>>> details = mendeley.document_details(documents['document_ids'][0])
>>> pprint(details)
{u'authors': [u'Ben Dowling'],
 u'discipline': {u'discipline': u'Computer and Information Science',
                 u'subdiscipline': None},
 u'tags': ['nosql'],
 u'title': u'NoSQL(EU) Write Up',
 u'year': 2010}
"""
import oauth2 as oauth
import pickle
import httplib
import json
import urllib

import apidefinitions

class OAuthClient(object):
    """General purpose OAuth client"""
    def __init__(self, consumer_key, consumer_secret, options=None):
        if options == None: options = {}
        # Set values based on provided options, or revert to defaults
        self.host = options.get('host', 'api.mendeley.com')
        self.port = options.get('port', 80)
        self.access_token_url = options.get('access_token_url', '/oauth/access_token/')
        self.request_token_url = options.get('access_token_url', '/oauth/request_token/')
        self.authorize_url = options.get('access_token_url', '/oauth/authorize/')

        if self.port == 80: 
            self.authority = self.host
        else: 
            self.authority = "%s:%d" % (self.host, self.port)

        self.consumer = oauth.Consumer(consumer_key, consumer_secret)

    def get(self, path, token=None):
        url = "http://%s%s" % (self.host, path)
        request = oauth.Request.from_consumer_and_token(
            self.consumer,
            token,
            http_method='GET',
            http_url=url,
        )
        return self._send_request(request, token)

    def post(self, path, post_params, token=None):
        url = "http://%s%s" % (self.host, path)
        request = oauth.Request.from_consumer_and_token(
            self.consumer,
            token,
            http_method='POST',
            http_url=url,
            parameters=post_params
        )
        return self._send_request(request, token)
    
    def delete(self, path, token=None):
        url = "http://%s%s" % (self.host, path)
        request = oauth.Request.from_consumer_and_token(
            self.consumer, 
            token, 
            http_method='DELETE', 
            http_url=url, 
        )
        return self._send_request(request, token)

    def put(self, path, token=None, body=None, body_hash=None, headers=None):
        url = "http://%s%s" % (self.host, path)
        request = oauth.Request.from_consumer_and_token(
            self.consumer,
            token,
            http_method='PUT',
            http_url=url,
            parameters={'oauth_body_hash': body_hash}
        )
        return self._send_request(request, token, body, headers)

    def request_token(self):
        response = self.get(self.request_token_url).read()
        token = oauth.Token.from_string(response)
        return token 
    
    def authorize(self, token, callback_url = "oob"):
        url = 'http://%s%s' % (self.authority, self.authorize_url)
        request = oauth.Request.from_token_and_callback(token=token, callback=callback_url, http_url=url)
        return request.to_url()

    def access_token(self, request_token):
        response = self.get(self.access_token_url, request_token).read()
        return oauth.Token.from_string(response)

    def _send_request(self, request, token=None, body=None, extra_headers=None):
        request.sign_request(oauth.SignatureMethod_HMAC_SHA1(), self.consumer, token)
        conn = self._get_conn()
        
        if request.method == 'POST':
            conn.request('POST', request.url, body=request.to_postdata(), headers={"Content-type": "application/x-www-form-urlencoded"})
        elif request.method == 'PUT':
            final_headers = request.to_header()
            if extra_headers is not None:
                final_headers.update(extra_headers)
            conn.request('PUT', request.url, body, headers=final_headers)                 
        elif request.method == 'DELETE':
            conn.request('DELETE', request.url, headers=request.to_header())
        else:
            conn.request('GET', request.url, headers=request.to_header())
        return conn.getresponse()

    def _get_conn(self):
        return httplib.HTTPConnection("%s:%d" % (self.host, self.port))

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
        response = self.callback(url, self.details.get('access_token_required', False), self.details.get('method', 'get'), optional_args)
        status = response.status
        body = response.read()
        content_type = response.getheader("Content-Type")
        ct = content_type.split("; ")
        mime = ct[0]
        attached = None
        try:
            content_disposition = response.getheader("Content-Disposition")
            cd = content_disposition.split("; ")
            attached = cd[0]
            filename = cd[1].split("=")
            filename = filename[1].strip('"')
        except:
            pass

        if mime == 'application/json':
	    # HTTP Status 204 means 'No Content' which json.loads cannot deal with
            if status == 204:
                data = ''
            else:
                data = json.loads(body)
            return data
        elif attached == 'attachment':
            return {'filename': filename, 'data': body}
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
        if not hasattr(self,"api_key") or not hasattr(self, "api_secret"):
            return False

        if self.api_key == "<change me>" or self.api_secret == "<change me>":
            return False

        return True

    def load(self):
        loaded = json.loads(open(self.filename,'r').read())
        for key, value in loaded.items():
            setattr(self, key, value)

class MendeleyClient(object):

    def __init__(self, consumer_key, consumer_secret, options=None):
        self.oauth_client = OAuthClient(consumer_key, consumer_secret, options)

        # Create methods for all of the API calls    
        for method, details in apidefinitions.methods.items():
            setattr(self, method, MendeleyRemoteMethod(details, self._api_request))

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
            headers = {'Content-disposition': 'attachment; filename="%s"' % params.get('file_name')}
            response = self.oauth_client.put(url, access_token, params.get('data'), params.get('oauth_body_hash'), headers)
        elif method == 'post':
            response = self.oauth_client.post(url, params, access_token)
        else:
            raise Exception("Unsupported method: %s"%method)
        return response

    def set_access_token(self, access_token):
        self.access_token = access_token

    def get_access_token(self):
        return self.access_token

    def get_auth_url(self,callback_url='oob'):
        """Returns an auth url"""
        request_token = self.oauth_client.request_token()
        auth_url = self.oauth_client.authorize(request_token,callback_url)
        return (request_token,auth_url)

    def verify_auth(self, request_token, verifier):
        """Generate an access_token from a request_token generated by
           get_auth_url and the verifier received from the server"""
        request_token.set_verifier(verifier)
        access_token = self.oauth_client.access_token(request_token)
        return access_token    

    def interactive_auth(self):
        request_token, auth_url = self.get_auth_url()
        print 'Go to the following url to auth the token:\n%s' % (auth_url,)
        verifier = raw_input('Enter verification code: ')
        self.set_access_token(self.verify_auth(request_token, verifier))

