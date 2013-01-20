Openstack Swift Quota Middleware
================================

swquota is a WSGI middleware for Openstack Swift Proxy. It blocks write
requests (PUT, POST) if a given quota is exceeded while DELETE requests
are still allowed.

swquota uses the x-account-meta-bytes-limit metadata to store the quota.
Write requests to this metadata setting are only allowed for resellers.
There is no quota limit if x-account-meta-bytes-limit is not set.

swquota has been tested with tempauth, keystone and swauth.

memcache (if enabled) is used to lower the number of subsequent HTTP requests.

Please keep in mind that the quota comes into effect after an object was put into swift.  If you have already 999 bytes in your account and your quota is 1000 bytes you can still 
upload a single object with 5GB. Due to swifts eventual consistency the calculated usage might be a little bit higher or lower than the actual usage. 


Quick Install
-------------

1) Install swquota:

    git clone git://github.com/cschwede/swquota.git
    cd swquota
    sudo python setup.py install

2) Alter your proxy-server.conf pipeline to use swquota. swquota can be used with tempauth, keystone and swauth; simply add swquota after your authentication middleware.

    [pipeline:main]
    pipeline = catch_errors healthcheck cache swauth swquota proxy-server
 
 
3) Configure swquota in proxy-server.conf:

    [filter:swquota]
    use = egg:swquota#swquota
    #cache_timeout = 60

4) Restart your proxy server: 

    swift-init proxy reload

5) If you want to force a quota on an account you have to set it as reseller.

### tempauth ###
tempauth accounts are configured in /etc/proxy-server.conf. For example:

	[filter:tempauth]
	use = egg:swift#tempauth
	user_account_reseller = secret .reseller_admin
	user_account_admin = secret .admin
	user_account_user = secret

Only the user account:reseller is allowed to change the quota:
	
	swift -U account:reseller -K secret post -m bytes-limit:1000 

### keystone ###
For keystone you need an account with the role "reseller". Let's create this role and assign it to an existing account:
	
	# keystone role-create --name reseller
	# keystone role-list
	+----------------------------------+----------------------+
	|                id                |         name         |
	+----------------------------------+----------------------+
	| 422e2ca73227452999f11997352bb7f7 |       reseller       |
	+----------------------------------+----------------------+
	
	# keystone tenant-list
	+----------------------------------+--------------------+---------+
	|                id                |        name        | enabled |
	+----------------------------------+--------------------+---------+
	| bb27a3b085344d98a46157c6d8e6e948 |       admin        |   True  |
	+----------------------------------+--------------------+---------+
	
	# keystone user-list --tenant-id bb27a3b085344d98a46157c6d8e6e948
	+----------------------------------+-------+---------+-------------------+
	|                id                |  name | enabled |       email       |
	+----------------------------------+-------+---------+-------------------+
	| 52a6eb0f906f42a2b968b2e8bd967e23 | admin |   True  | admin@example.com |
	+----------------------------------+-------+---------+-------------------+
	
	# keystone user-role-add --user-id 52a6eb0f906f42a2b968b2e8bd967e23 --role-id 422e2ca73227452999f11997352bb7f7 --tenant-id bb27a3b085344d98a46157c6d8e6e948

Now you can set the quota for this tenant:

	# swift -V 2 -A http://localhost:5000/v2.0 -U admin:admin -K adminpw post -m bytes-limit:1000

### swauth ###

Using swauth you also need an account with the reseller flag set: 

    swauth-add-user -K swauthkey -r account reseller secret

Now set the quota on this account:
    
    swift -U account:reseller -K secret post -m bytes-limit:10000
   
    