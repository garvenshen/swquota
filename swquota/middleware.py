# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Quota middleware for Openstack Swift Proxy """

try:
    from swift.common.swob import HTTPForbidden, HTTPRequestEntityTooLarge,\
        HTTPUnauthorized, HTTPBadRequest, Request
except ImportError:
    from webob.exc import HTTPForbidden, HTTPRequestEntityTooLarge,\
        HTTPUnauthorized, HTTPBadRequest, Request

from swift.common.utils import cache_from_env, get_logger
from swift.common.wsgi import make_pre_authed_request


class Swquota(object):
    """
    swquota is a WSGI middleware for Openstack Swift Proxy. It blocks write
    requests (PUT, POST) if a given quota is exceeded while DELETE requests
    are still allowed.

    swquota uses the x-account-meta-bytes-limit metadata to store the quota.
    Write requests to this metadata setting are only allowed for resellers.
    There is no quota limit if x-account-meta-bytes-limit is not set.

    memcache is used to lower the number of subsequent HTTP requests.

    The following shows an example proxy-server.conf:

    [filter:swquota]
    paste.filter_factory = swquota:filter_factory
    #cache_timeout = 300

    """

    def __init__(self, app, conf):
        self.app = app
        self.conf = conf

        self.logger = get_logger(self.conf, log_route='swquota')

    def _get_quota(self, account, env):
        """ Get quota und currently used storage from account """

        request = make_pre_authed_request(env, 'HEAD', '/v1/' + account)
        response = request.get_response(self.app)
        quota = -1
        for (key, value) in response.headers.items():
            if key == 'x-account-bytes-used':
                bytes_used = int(value)
            if key == 'x-account-meta-bytes-limit':
                quota = int(value)
        return (bytes_used, quota)

    def __call__(self, env, start_response):
        request = Request(env)

        reseller = False

        #used by tempauth and swauth
        user = env.get('REMOTE_USER', '')
        if isinstance(user, basestring):
            if ".reseller_admin" in user.split(','):
                reseller = True

        #used by keystone
        roles = env.get('HTTP_X_ROLES', '')
        if "reseller" in roles.split(','):
            reseller = True

        #Check if quota set is valid
        if request.method in ("POST"):
            for (key, value) in request.headers.items():
                if key.lower() == 'x-account-meta-bytes-limit':
                    if not reseller:
                        return HTTPForbidden()(env, start_response)
                    if value:
                        try:
                            int(value)
                        except ValueError:
                            return HTTPBadRequest()(env, start_response)

        #Pass early if request is from reseller
        if reseller:
            return self.app(env, start_response)

        if request.method in ("POST", "PUT"):
            path_info = env.get('PATH_INFO', None)
            if path_info:
                accountname = path_info.split('/')[2]
                memcache_client = cache_from_env(env)
                quota_exceeded = None

                if memcache_client:
                    memcache_key = "quota_exceeded_%s" % (accountname, )
                    quota_exceeded = memcache_client.get(memcache_key)

                if quota_exceeded is None:
                    quota_exceeded = False

                    (used_bytes, quota) = self._get_quota(accountname, env)

                    if quota >= 0 and quota < used_bytes:
                        quota_exceeded = True
                        self.logger.info("Quota exceeded: %s %s > %s",
                                         accountname, used_bytes, quota)
                    if memcache_client:
                        memcache_client.set(
                            memcache_key,
                            quota_exceeded,
                            timeout=float(self.conf.get('cache_timeout', 300)))

                if quota_exceeded:
                    #A different return code is needed for Swift S3
                    if 'HTTP_AUTHORIZATION' in env:
                        if env['HTTP_AUTHORIZATION'][0:3] == "AWS":
                            return HTTPUnauthorized()(env, start_response)
                    return HTTPRequestEntityTooLarge()(env, start_response)
        return self.app(env, start_response)


def filter_factory(global_conf, **local_conf):
    """Returns a WSGI filter app for use with paste.deploy."""
    conf = global_conf.copy()
    conf.update(local_conf)

    def auth_filter(app):
        return Swquota(app, conf)
    return auth_filter
