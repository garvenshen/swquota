Openstack Swift Quota Middleware
================================

swquota is a WSGI middleware for Openstack Swift Proxy. It blocks write
requests (PUT, POST) if a given quota is exceeded while DELETE requests
are still allowed.

swquota uses the x-account-meta-bytes-limit metadata to store the quota.
Write requests to this metadata setting are only allowed for resellers.
There is no quota limit if x-account-meta-bytes-limit is not set.

memcache (if enabled) is used to lower the number of subsequent HTTP requests.


Quick Install
-------------

1) Install swquota:
    
    sudo python setup.py install

2) Alter your proxy-server.conf pipeline to use swquota:

    [pipeline:main]
    pipeline = catch_errors healthcheck cache swauth swquota proxy-server
 
3) Configure swquota in proxy-server.conf:

    [filter:swquota]
    use = egg:swquota#swquota
    #cache_timeout = 60

4) Restart your proxy server: 

    swift-init proxy reload

5) If you want to force a quota on an account you have to set it as reseller. For example:

    swift -U reseller:reseller -K reseller --os-storage-url=https://127.0.0.1/v1/AUTH_account-name post -m bytes-limit:10000

Please keep in mind that the quota comes into effect after an object was put into swift.  If you have already 999 bytes in your account and your quota is 1000 bytes you can still 
upload a single object with 5GB. Due to swifts eventual consistency the calculated usage might be a little bit higher or lower than the actual usage. 
