swquota
------

swquota is a WSGI middleware for Openstack Swift Proxy. It blocks write
requests (PUT, POST) if a given quota is exceeded while DELETE requests
are still allowed.

swquota request an URL with the name of the account appended and uses the
returned body data as quota size in bytes. The easiest way is to put
objects with the reseller prefix and account name as key and size in bytes as 
content into a public readable container.

swquota reads the x-account-bytes-used from the accounts, thus a
reseller account is needed (because users without admin rights can't
HEAD the account).

memcache is used to lower the number of subsequent HTTP requests.


Quick Install
-------------

1) Install swquota:
    
    sudo python setup.py install

2) Create a new account in swift to store the quotas. For example using swauth:

    swauth-add-user -A http://127.0.0.1:8080/auth/ -K swauthkey -a -s swquota swquota swquota swquota

3) Create a public-readable container in this account:

    swift -A https://127.0.0.1/auth/v1.0 -U swquota:swquota -K swquota post -r ".r:*" quotas

4) Put an object with the name of the reseller prefix + account as key and quota as content into this container:

    echo 1000000 > auth_accountname
    swift -A https://127.0.0.1/auth/v1.0 -U swquota:swquota -K swquota upload quotas auth_accountname
    rm auth_accountname

5) Alter your proxy-server.conf pipeline to use swquota:

    [pipeline:main]
    pipeline = catch_errors healthcheck cache swauth swquota proxy-server
 
6) Configure swquota in proxy-server.conf:

    [filter:swquota]
    paste.filter_factory = swquota:filter_factory
    quota_account = auth_swquota
    quota_container = quotas
    reseller_account = .super_admin:.super_admin
    reseller_key = swauthkey
    auth_url = http://127.0.0.1/auth/v1.0
    #cache_timeout = 300
    #request_timeout = 15

7) Make sure that the proxy uses memcache:

    [filter:cache]
    use = egg:swift#memcache
    memcache_servers = 127.0.0.1:11211
 
8) Restart your proxy server: 

    swift-init proxy reload

Please keep in mind that the quota comes into effect after an object was put into swift.  If you have already 999 bytes in your account and your quota is 1000 bytes you can still 
upload a single object with 5GB. Due to swifts eventual consistency the calculated usage might be a little bit higher or lower than the actual usage. 
