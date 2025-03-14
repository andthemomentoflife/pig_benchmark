'''OAuth support functionality
'''

import BaseHTTPServer
import logging
import random
import urlparse
import time
import os.path
import sys
import webbrowser

import requests
from requests.auth import OAuth1


from flickrapi import sockutil, exceptions
import six
from flickrapi.exceptions import FlickrError

class OAuthTokenHTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):
    def do_GET(self):
        # /?oauth_token=72157630789362986-5405f8542b549e95&oauth_verifier=fe4eac402339100e

        qs = urlparse.urlsplit(self.path).query
        url_vars = urlparse.parse_qs(qs)

        self.server.oauth_token = url_vars['oauth_token'][0].decode('utf-8')
        self.server.oauth_verifier = url_vars['oauth_verifier'][0].decode('utf-8')

        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

        self.wfile.write('OK')

class OAuthTokenHTTPServer(BaseHTTPServer.HTTPServer):
    '''HTTP server on a random port, which will receive the OAuth verifier.'''
    
    def __init__(self):
        
        self.log = logging.getLogger('{}.{}'.format(__name__, self.__class__.__name__))
        
        self.local_addr = self.listen_port()
        self.log.info('Creating HTTP server at %s', self.local_addr)
       
        BaseHTTPServer.HTTPServer.__init__(self, self.local_addr, OAuthTokenHTTPHandler)

        self.oauth_verifier = None
    
    def listen_port(self):
        '''Returns the hostname and TCP/IP port number to listen on.
        
        By default finds a random free port between 1100 and 20000.
        '''

        # Find a random free port
        local_addr = ('localhost', int(random.uniform(1100, 20000)))
        self.log.debug('Finding free port starting at %s', local_addr)
        return sockutil.find_free_port(local_addr)
        
        return local_addr
    
    def wait_for_oauth_verifier(self):
        '''Starts the HTTP server, waits for the OAuth verifier.'''
            
        while self.oauth_verifier is None:
            self.handle_request()
    
        self.log.info('OAuth verifier: %s' % self.oauth_verifier)
        return self.oauth_verifier

    @property
    def oauth_callback_url(self):
        return 'http://localhost:%i/' % self.local_addr[1]

class FlickrAccessToken(object):
    '''Flickr access token.
    
    Contains the token, token secret, and the user's full name, username and NSID.
    '''
    
    def __init__(self, token, token_secret, fullname, username, user_nsid):
        self.token = token
        self.token_secret = token_secret
        self.fullname = fullname
        self.username = username
        self.user_nsid = user_nsid
    
    def __str__(self):
        return unicode(self).encode('utf-8')
    
    def __unicode__(self):
        return u'FlickrAccessToken(token=%s, fullname=%s, username=%s, user_nsid=%s)' % (
                   self.token, self.fullname, self.username, self.user_nsid) 

    def __repr__(self):
        return str(self)


class OAuthFlickrInterface(object):
    '''Interface object for handling OAuth-authenticated calls to Flickr.'''

    REQUEST_TOKEN_URL = "http://www.flickr.com/services/oauth/request_token"
    AUTHORIZE_URL = "http://www.flickr.com/services/oauth/authorize"
    ACCESS_TOKEN_URL = "http://www.flickr.com/services/oauth/access_token"

    
    def __init__(self, api_key, api_secret, cache_dir=None):
        self.log = logging.getLogger('{}.{}'.format(__name__, self.__class__.__name__))

        assert isinstance(api_key, six.text_type), 'api_key must be unicode string'
        assert isinstance(api_secret, six.text_type), 'api_secret must be unicode string'

        self.oauth = OAuth1(api_key, api_secret, signature_type='query')
        self.cache_dir = cache_dir
        self.oauth_token = None

    @property
    def key(self):
        '''Returns the OAuth key'''
        return self.oauth.client.client_key

    @property
    def verifier(self):
        '''Returns the OAuth verifier.'''
        return self.oauth.client.verifier
    
    @verifier.setter
    def verifier(self, new_verifier):
        '''Sets the OAuth verifier'''
        
        assert isinstance(new_verifier, six.text_type), 'verifier must be unicode text type'
        self.oauth.client.verifier = new_verifier

    def _find_cache_dir(self):
        '''Returns the appropriate directory for the HTTP cache.'''
        
        if sys.platform.startswith('win'):
            return os.path.expandvars('%APPDATA%/flickrapi/cache')
        
        return os.path.expanduser('~/.flickrapi/cache')

    def do_request(self, url, params=None):
        '''Performs the HTTP request, signed with OAuth.
        
        @return: the response content
        '''
        
        req = requests.get(url, params=params, auth=self.oauth)
        
        # check the response headers / status code.
        if req.status_code != 200:
            self.log.error('do_request: Status code %i received, content:', req.status_code)

            for part in req.content.split('&'):
                self.log.error('    %s', urlparse.unquote(part))
           
            raise exceptions.FlickrError('do_request: Status code %s received' % req.status_code)
        
        return req.content
    
    @staticmethod
    def parse_oauth_response(data):
        '''Parses the data string as OAuth response, returning it as a dict.'''
        
        return {key: value.decode('utf-8') for key, value in urlparse.parse_qsl(data)}

    def get_request_token(self, oauth_callback):
        '''Requests a new request token.
        
        Updates this OAuthFlickrInterface object to use the request token on the following
        authentication calls.
        
        @param oauth_callback: the URL the user is sent to after granting the token access.
        '''
        
        params = {
            'oauth_callback': oauth_callback,
        }
        
        token_data = self.do_request(self.REQUEST_TOKEN_URL, params)
        self.log.debug('Token data: %s', token_data)
        
        # Parse the token data
        request_token = self.parse_oauth_response(token_data)
        
        self.oauth.client.resource_owner_key = request_token['oauth_token']
        self.oauth.client.resource_owner_secret = request_token['oauth_token_secret']

    def auth_url(self, perms='read'):
        '''Returns the URL the user should visit to authenticate the given oauth Token.
        
        Use this method in webapps, where you can redirect the user to the returned URL.
        After authorization by the user, the browser is redirected to the callback URL,
        which will contain the OAuth verifier. Set the 'verifier' property on this object
        in order to use it.
        
        In stand-alone apps, use open_browser_for_authentication instead.
        '''
        
        if self.oauth.client.resource_owner_key is None:
            raise FlickrError('No resource owner key set, you probably forgot to call get_request_token(...)')

        if perms not in {'read', 'write', 'delete'}:
            raise ValueError('Invalid parameter perms=%r' % perms)
        
        return "%s?oauth_token=%s&perms=read" % (self.AUTHORIZE_URL, self.oauth.client.resource_owner_key)

    def open_browser_for_authentication(self, perms='read'):
        '''Opens the webbrowser to authenticate the given request request_token, sets the verifier.
        
        Use this method in stand-alone apps. In webapps, use auth_url(...) instead,
        and redirect the user to the returned URL.
        
        Updates the given request_token by setting the OAuth verifier.
        '''
        
        url = self.auth_url(perms)
        
        auth_http_server = OAuthTokenHTTPServer()
                
        if not webbrowser.open_new_tab(url):
            raise exceptions.FlickrError('Unable to open a browser to visit %s' % url)
        
        self.verifier = auth_http_server.wait_for_oauth_verifier()
        
    def get_access_token(self):
        '''Exchanges the request token for an access token.

        Also stores the access token in 'self' for easy authentication of subsequent calls.
        
        @return: Access token, a FlickrAccessToken object.
        '''
        
        if self.oauth.client.resource_owner_key is None:
            raise FlickrError('No resource owner key set, you probably forgot to call get_request_token(...)')
        if self.oauth.client.verifier is None:
            raise FlickrError('No token verifier set, you probably forgot to set %s.verifier' % self)

        content = self.do_request(self.ACCESS_TOKEN_URL)
        
        #parse the response
        access_token_resp = self.parse_oauth_response(content)
        
        self.oauth_token = FlickrAccessToken(access_token_resp['oauth_token'],
                                             access_token_resp['oauth_token_secret'],
                                             access_token_resp['fullname'],
                                             access_token_resp['username'],
                                             access_token_resp['user_nsid'])
        
        
        self.oauth.client.resource_owner_key = access_token_resp['oauth_token']
        self.oauth.client.resource_owner_secret = access_token_resp['oauth_token_secret']
        self.oauth.client.verifier = None
        
        return self.oauth_token

        
