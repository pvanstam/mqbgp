#!/usr/bin/env python3
'''
    Created on 25 jun. 2017
    
    @author: pim
    
    Modifications:
    0.2.1 - 18-09-2018: connect/disconnect in main loop and not in send_message for speed improvement
                        in mqbgp a reconnect if necessary
    0.3.0 - 09-01-2020: fix: give right ASN in withdraw message
                        added as-path and communities with messages and updates mqbgp library
                        reconnect when connecion is lost

'''

__VERSION__ = "0.3.0"
import os
import sys
import time
import syslog
import json
import mqbgp
import pika
from exabgp.bgp.neighbor import Neighbor

mq = None # declaration of message queueing variable


def _prefixed (level, message):
    now = time.strftime('%a, %d %b %Y %H:%M:%S',time.localtime())
    return "%s %-8s %-6d %s" % (now,level,os.getpid(),message)


class exabgp_message():
    ''' class for the highest level message of ExaBGP '''

    def init(self):
        self.counter  = 0            # message counter
        self.exabgp   = "1.0"        # version
        self.host     = "localhost"  # server hostname
        self.pid      = ""           # process id
        self.ppid     = ""           # parent process id
        self.time     = 0            # time in Julian time + usec
        self.type     = None         # type of message; like "update", "state"
        self.neighbor = {}           # message from neighbor as of class neighbor 

    def decode_json(self, msg):
        ''' decode the json msg to the class values '''
        self.counter = msg["counter"]
        self.exabgp = msg["exabgp"]
        self.host = msg["host"]
        self.pid = msg["pid"]
        self.ppid = msg["ppid"]
        self.time = msg["time"]
        self.type = msg["type"]
        self.neighbor = msg["neighbor"]


class neighbor():
    ''' BGP neighbor message
        json like:
            "neighbor": {
                "address": { "local": "192.168.1.2", "peer": "192.168.1.1" },
                "asn": { "local": "65521", "peer": "65520" },
                "direction": "receive",
                "message" : {...}
            }
    '''

    def init(self):
#        self.ip            = ""
        self.address_peer  = ""
        self.address_local = ""
        self.asn_peer      = ""
        self.asn_local     = ""
        self.direction     = ""
        self.message       = {}

    def decode_json(self, msg):
        """ decode the neighbor part of the json into the class values """
#        self.ip            = msg["ip"]
        self.asn_peer      = msg["asn"]["peer"]
        self.asn_local     = msg["asn"]["local"]
        self.address_peer  = msg["address"]["peer"]
        self.address_local = msg["address"]["local"]
        self.direction     = msg["direction"]
        self.message       = msg["message"]

'''
message:
    "message": {
        "update": {
            "attribute": {
                "origin": "igp",
                "as-path": [ 200020, 3333 ],
                "confederation-path": [],
                "med": 0,
                "community": [ [ 65432, 3000 ] ]
            },
            "announce": {
                "ipv4 unicast": {
                    "172.30.4.1": [
                        { "nlri": "193.0.20.0/23" },
                        { "nlri": "193.0.12.0/23" },
                        { "nlri": "193.0.0.0/21" },
                        { "nlri": "193.0.10.0/23" },
                        { "nlri": "193.0.18.0/23" },
                        { "nlri": "193.0.22.0/23" }
                    ] } } } } } }
'''

def get_asn(msg):
    ''' retrieve asn from update message
    '''
    try:
        as_path = msg["attribute"]["as-path"]
    except:
        return("", "")

    if (len(as_path)) > 1:
        return (str(as_path[1]), as_path)
    else:
        return ("I", as_path)


def get_community(msg):
    ''' retrieve community from update message
    '''
    try:
        return msg["attribute"]["community"]
    except:
        return []



def get_prefixes(msg):
    '''
        get prefixes from announce update message
        "announce" message like:
        "ipv4 unicast": {
            "192.168.1.1": [
              { "nlri": "1.2.3.0/24" },
              { "nlri": "2.3.4.0/24" }
            ]
    '''
    prefixes = []
    ann = msg["announce"]
    for proto in ann.keys():
        for host in ann[proto].keys():
            for prfx in ann[proto][host]:
                prefixes.append((host,prfx['nlri']))
                
    return prefixes


'''
withdraw message:
    "message": { 
        "update": {  } } } }
''' 

def del_prefixes(msg):
    ''' bgp withdraws (a) prefix(es)
        msg has attributes "attributes" and "withdraw"

        "withdraw": { 
            "ipv4 unicast": [ { "nlri": "212.114.112.196/32" } ]
        }
    '''
    prefixes=[]
    ann = msg["withdraw"]
    for proto in ann.keys():
        for prfx in ann[proto]:
            prefixes.append(prfx['nlri'])

    return prefixes


def send_bgp_message(msg_time, asn, ip_prefix, nexthop, announce=True, as_path="", community=""):
    '''
        send message to MQ server about announce or withdraw of an IP prefix
    '''
    global mq
    
    if announce:
        ann_str = "announce"
    else:
        ann_str = "withdraw"

#    syslog.syslog(syslog.LOG_ALERT, _prefixed('INFO', str(msg_time) + " - "
#                                              + ann_str
#                                              + " asn: " + asn
#                                              + "; prefix: " + ip_prefix
#                                              + "; nexthop: " + nexthop))
    pm = mqbgp.PrefixMessage(asn, ip_prefix, nexthop, announce, as_path, community)
    try:
        pm.send(mq)
    except (pika.exceptions.StreamLostError, pika.exceptions.ChannelWrongStateError) as err:
        mq = mqbgp.Queue()
        mq.connect()
        pm.send(mq)


if __name__ == '__main__':

    syslog.openlog("ExaBGP")

    # When the parent dies we are seeing continual newlines, so we only access so many before stopping
    counter = 0
    syslog.syslog(syslog.LOG_ALERT, _prefixed('INFO', "Start exaBGP monitoring"))
    examsg = exabgp_message()
    

    mq = mqbgp.Queue()
    mq.connect()


    while True:
        try:
            line = sys.stdin.readline().strip()
            if line == "":
                counter += 1
                if counter > 100:
                    break
                continue

            counter = 0

#            syslog.syslog(syslog.LOG_ALERT, _prefixed('INFO',line))

            jdata = json.loads(line)
            examsg.decode_json(jdata)
            if examsg.type == "update":
                nb = neighbor()
                nb.decode_json(examsg.neighbor)

                try:
                    msg_update = nb.message["update"]
                except:
                    continue

                asn = get_asn(msg_update)
                comm = get_community(msg_update)
                if "announce" in msg_update.keys():
                    for nexthop,pr in get_prefixes(msg_update):
                        send_bgp_message(examsg.time, asn[0], pr, nexthop, True, asn[1], comm)
                elif "withdraw" in msg_update.keys():
                    for pr in del_prefixes(msg_update):
                        send_bgp_message(examsg.time, asn[0], pr, "", False, asn[1], comm)


        except KeyboardInterrupt:
            break
        except IOError:
            # most likely a signal during readline
            syslog.syslog(syslog.LOG_WARNING, _prefixed('WARNING', "ExaBGP got an IOError"))
            break
        except:
            exctype, excvalue = sys.exc_info()[:2]
            syslog.syslog(syslog.LOG_ERR, _prefixed('ERROR', "ExaBGP monitoring, unknown exception: %s - %s" % (exctype, excvalue)))

    mq.disconnect()

