'''
    prefix_listener - listen voor BGP updates and mail to support

    with the RabbitMQ message broker BGP updates are on a queue.
    Listen for these updates and mail these to support.

    @author: Pim van Stam <pim@svsnet.nl>
    Updates:
    10-01-2020 - 0.2 - Added as-path and community from mqbgp message classs in output
    11-01-2020 - 0.2.1 - Fix: as_path and community are dicts. In output msg make string of them
'''
__version__="0.2.1"

import os
import daemon
import argparse
import configparser
import logging
import logging.handlers
import pika
import smtplib
import email.mime.text
import mqbgp

logger = None

config = {'configfile' : 'bgpmonitor.conf',
          'logfile'    : '/var/log/prefixlistener.log',
          'errorfile'  : '/var/log/prefixlistener.err',
          'loglevel'   : 'info',
          'mailfrom'   : 'bgpmonitor@mailserver.com',
          'mailto'     : 'support@mailserver.com',
          'mailserver' : 'smtp.mailserver.com'
         }


def set_logging(logfile, level):
    '''
        set logging handler for logging output to logfile
    '''
    if level == 'debug':
        loglevel = logging.DEBUG
    elif level == 'warning':
        loglevel = logging.WARNING
    elif level == 'error':
        loglevel = logging.ERROR
    else:
        loglevel = logging.INFO
    
    log = logging.getLogger() # get root logger
    log.setLevel(loglevel)
    loghandler = logging.handlers.WatchedFileHandler(filename=logfile)
    frm = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")
    loghandler.setFormatter(frm)
    log.addHandler(loghandler)

    return log


def read_config(confg, cfgfile, context):
    '''
        read config file
    '''
    if os.path.isfile(cfgfile):
        configs = configparser.RawConfigParser()
        configs.read(cfgfile)

        for option in configs.options(context):
            confg[option]=configs.get(context,option)

    return confg


def send_message(subject, msg):
    '''
        Send message to recipients
    '''
    #TODO: sendmail in separate thread and retry if connection error occurred (like No route to host)

    emsg = email.mime.text.MIMEText(msg)

    emsg['Subject'] = subject
    emsg['From'] = config['mailfrom']
    emsg['To'] = config['mailto']

    try:
        s = smtplib.SMTP(config['mailserver'])
    except:
        exctype, excvalue = sys.exc_info()[:2]
        logger.error("send_message: Send mail message failed; exception occurred:  %s - %s" % (exctype, excvalue))
    else:
        try:
            s.sendmail(config['mailfrom'], [config['mailto']], emsg.as_string())
        except:
            exctype, excvalue = sys.exc_info()[:2]
            logger.error("send_message: Send mail message failed; exception occurred:  %s - %s" % (exctype, excvalue))

        s.quit()


def callback_prefix_updates(message:mqbgp.PrefixMessage):
    msg = message.get_message()

    subject = "NaWas prefix change: " + msg['type'] + " of " + msg['prefix'] + " by AS" + msg['asn']

    body = "Prefix change at NaWas\n"
    body += "\nType: " + msg['type']
    body += "\nPrefix: " + msg['prefix']
    body += "\nAS number: " + msg['asn']
    body += "\nNexthop: " + msg['nexthop']
    body += "\nAS Path: " + str(msg['as_path'])
    body += "\nCommunity: " + str(msg['community'])
    body += "\n\nKind regards,\n\nThe BGP Monitor Daemon\n\n"

    send_message(subject, body)
    logger.info("bgpmonitor: " + subject)


def mainroutine():
    global logger
    
    logger = set_logging(cfg['logfile'], cfg['loglevel'])
    logger.info("bgpmonitor: Starting BGP Monitoring Daemon")
    while True:
        try:
            li = mqbgp.Listener("/etc/exabgp/config.yml")
            li.listen(mqbgp.PrefixMessage, callback_prefix_updates)
        except pika.exceptions.ConnectionClosed:
            logger.info("bgpmonitor: Connection to RabbitMQ server was closed, trying to reconnect.")
        except KeyboardInterrupt:
            logger.info("bgpmonitor: Bye, bye")
            break



if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description="BGP Monitor Daemon")
    parser.add_argument("-c", "--configfile", help="Configuration file")
    parser.add_argument("-d", "--nodaemon", default=False,
                        action='store_true', help="Do not enter daemon mode")

    options = parser.parse_args()
    if options.configfile != None:
        config['configfile'] = options.configfile
    cfg = read_config(config, config['configfile'], 'common')

    fileout = open(cfg['errorfile'], "w")

    if not options.nodaemon:
        with daemon.DaemonContext(stderr=fileout, stdout=fileout):
            mainroutine()
    else:
        mainroutine()

    fileout.close()

