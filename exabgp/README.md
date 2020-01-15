Setup for an exabgp implementation

The ExaBGP application can be run from repository, pip or Docker hub. 

Like:
$ pip install exabgp

In the 'etc' directory (like /etc/exabgp), you need the following:
- exabgp.env - environmental values for the ExaBGP daemon (supplied with exabgp)
- exabgp.conf - configuration of the BGP and application to run
- bgp-monitor4.py - script to receive updates and send to RabbitMQ
- mqbgp.py - MQBGP library
- config.yml - configuration for mqbgp

The exabgp.conf is just an example for setting up a BGP sessions. Adapt it for your situation.




