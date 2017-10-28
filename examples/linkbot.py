from jayk.cli.module import JaykMeta
from urllib.parse import urlparse
from html.parser import HTMLParser
import socket
import re
import fnmatch
import ipaddress
import requests


identity = lambda x: x
url_re = re.compile("\S+://\S+")
local_networks = ['127.0.0.0/8', '10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16']


class LinkbotError(Exception):
    '''
    Basic exception that will cause linkbot to display an error message to the channel.
    '''
    def __init__(self, chan_message):
        super().__init__(chan_message)
        self.chan_message = chan_message


class HTMLTitleParser(HTMLParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title_start = False
        self.title_end = False
        self.title = None

    def handle_starttag(self, tag, attrs):
        if self.title_end: return
        if tag.lower() == "title":
            self.title_start = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.title_end = True

    def handle_data(self, data):
        if not self.title_end and self.title_start:
            self.title = data


class Linkbot(metaclass=JaykMeta):
    def __init__(self, blacklist=[], follow_local_urls=False, max_urls=3, report_errors=True, **kwargs):
        super().__init__(**kwargs)
        # user params
        self.blacklist = blacklist
        self.follow_local_urls = follow_local_urls
        self.max_urls = max_urls
        self.report_errors = report_errors

    def on_update_params(self, params):
        updates = ['blacklist', 'follow_local_urls', 'max_urls', 'report_errors']
        for p in updates:
            if p in params:
                self.debug("Updating parameter %s", p)
                setattr(self, p, params[p])

    def on_message(self, client, room, sender, msg):
        global url_re
        matches = url_re.findall(msg)
        urls = filter(self.is_valid_url, matches)
        count = 0
        for url in urls:
            if count >= self.max_urls:
                break
            try:
                title = self.get_title(url)
            except LinkbotError as ex:
                client.send_message(room, "{}: {}".format(sender.nick, ex.chan_message))
            else:
                if not title:
                    continue
                if len(title) > 512:
                    title = title[0:512]
                client.send_message(room, title)
                count += 1

    def get_title(self, url):
        """
        Given a URL, attempts to get its title. If the URL does not match the content-type of text/*, None is
        returned.
        :returns: either a title, or None if the title couldn't be found.
        """
        # Get the request
        try:
            self.debug("getting title for %s", url)
            r = requests.get(url)
        except Exception as ex:
            self.debug("invalid URL: %s", ex)
            return None
        if r.status_code != 200:
            self.debug("invalid status code: %s", r.status_code)
            raise LinkbotError("{} error".format(r.status_code))
        elif not fnmatch.fnmatch(r.headers['content-type'], 'text/*'):
            self.debug("invalid content-type: %s", r.headers['content-type'])
            return None
        content = r.text
        title_parser = HTMLTitleParser()
        title_parser.feed(content)
        return title_parser.title.strip()

    def is_valid_url(self, url):
        """
        Makes URL request to the given address. If they match the blacklist, or if their hosts resolve to an item in
        the blacklist, they are not followed. Also, if the URL does not parse, it is not followed.
        """
        global local_networks
        self.debug("validating URL %s", url)
        # make sure URL is valid
        try: url_parts = urlparse(url)
        except ValueError: return False # bad URL

        # make sure hostname is valid
        location = url_parts.netloc
        if not location: return False  # not a valid hostname

        # make sure hostname isn't blacklisted
        hostname = location if ':' in location else location.split(':')[0]
        if hostname in self.blacklist: return False  # blacklisted

        # make sure address is valid
        try: addr = socket.gethostbyname(hostname)
        except socket.gaierror: return False  # bad hostname

        # make sure IP is not blacklisted
        if addr in self.blacklist: return False  # blacklisted

        # make sure IP is not in local network if desired
        if not self.follow_local_urls:
            ip = ipaddress.ip_address(addr)
            if not ip.is_global: self.warning("Linkbot tried to resolve non-global IP address: %s", addr)
            return ip.is_global
        else:
            self.debug("%s is a valid URL", url)
            # good URL
            return True

    @staticmethod
    def author(): return 'intercal'

    @staticmethod
    def about(): return 'Every link posted gets its title send to the channel.'

    @staticmethod
    def name(): return 'Linkbot'


# TODO
# * ipv6 support
# * advanced pattern matching for links
# * max title length parameter
