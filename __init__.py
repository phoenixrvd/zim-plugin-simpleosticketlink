# coding=utf-8
import gtk


from zim.actions import action
from zim.gui import Dialog, MessageDialog
from zim.gui.widgets import InputForm
from zim.plugins import PluginClass, WindowExtension, extends
from abc import abstractmethod

# Global resources including
#
# If the dependencies can not be resolved, the plugin shall not be installed.
# @see SimpleOSTicketLinkPlugin.check_dependencies()

try:
    import requests
except ImportError:
    requests = None

try:
    import re
except ImportError:
    re = None

try:
    import BeautifulSoup
except ImportError:
    BeautifulSoup = None


class SimpleOSTicketLinkPlugin(PluginClass):
    plugin_info = {
        'name': _('Simple osTicket Link'),  # T: plugin name
        'description': _('Entry link to osTicket, without switching into Browser.'),  # T: plugin description
        'author': 'Viacheslav Wolf',
        'help': 'Plugins:Simple osTicket Link',
    }

    plugin_preferences = (
        ('url', 'string', _('URL'), 'http://'),  # T: Label for plugin preference
        ('user', 'string', _('Login'), ''),  # T: Label for plugin preference
        ('password', 'password', _('Password'), ''),  # T: Label for plugin preference
    )

    @classmethod
    def check_dependencies(klass):
        return bool(requests or BeautifulSoup.BeautifulSoup or re), [
            ('requests', not requests is None, True),
            ('BeautifulSoup', not BeautifulSoup.BeautifulSoup is None, True),
            ('re', not re is None, True)
        ]


@extends('MainWindow')
class MainWindowExtension(WindowExtension):
    uimanager_xml = '''
        <ui>
            <menubar name='menubar'>
                <menu action='insert_menu'>
                    <placeholder name='plugin_items'>
                        <menuitem action='osticket_button_clicked'/>
                    </placeholder>
                </menu>
            </menubar>
        </ui>
    '''

    def __init__(self, plugin, window):
        WindowExtension.__init__(self, plugin, window)

        # Define the bugtracker object as global, for the performance purpose
        plugin.bt = osTicket()

    @action(
            _('osTicket Link'),
            readonly=True,
            accelerator='<Control><Shift>O'
    )  # T: menu item
    def osticket_button_clicked(self):
        '''Run the TicketDialog'''
        TicketDialog(self.window, self.plugin, self.window.pageview).run()


class RequestError(Exception):
    pass

class TicketDialog(Dialog):
    def __init__(self, ui, notebook, pageview):
        self.notebook = notebook
        self.bt = notebook.bt
        self.pageview = pageview
        self.ui = ui

        Dialog.__init__(
                self,
                ui,
                _('Insert Ticket ID'),  # T: Dialog title
                button=(_('_Insert'), 'gtk-ok'),  # T: Button label
                defaultwindowsize=(245, 120)
        )

        self.form = InputForm(notebook=notebook)
        self.vbox.pack_start(self.form, False)
        self.form.add_inputs((
            ('ticket', 'string', _('ID')),  # T: Ticket ID
        ))

        # Register global dielog key-press event, which is called for every input
        self.add_events(gtk.gdk.KEY_PRESS_MASK)
        self.connect('key-press-event', self.on_dialog_key_press)

    def on_dialog_key_press(self, dialog, event):
        # Close dialog on enter click
        if event.keyval == gtk.keysyms.Return:
            dialog.response(gtk.RESPONSE_OK)
            return True

    def do_response_ok(self):
        self.bt.setup_config(self.notebook.preferences)

        # get the ticket ID and prevent changes during http request
        input = self.form.widgets.get('ticket')
        input.set_editable(False)
        ticket = input.get_text()
        self.do_close(self)

        # by empty string do nothing
        if not ticket:
            return True

        try:
            # Do Request to web page an set the response data formatted at cursor position
            ticket_data = self.bt.get_ticket_data(ticket)
            buffer = self.pageview.view.get_buffer()
            buffer.insert_link_at_cursor(ticket_data['ticket'], ticket_data['url'])
            buffer.insert_at_cursor(" " + ticket_data['title'] + "\n")
        except RequestError as e:
            MessageDialog(self, e.message).run()

        return True

class BugTracker:
    def __init__(self):
        pass

    session = None

    # Required-Setting for login
    # can be setted from map
    # @see Tracker.setup_config
    url = "http://www.ostickethacks.com/demo/scp/"
    user = ""
    password = ""

    def setup_config(self, config):
        for (item, value) in config.items():
            setattr(self, item, value)

    def get_ticket_data(self, ticket_id):

        # all requests have a same http - Session
        if not self.session:
            self.session_start()

        ticket_url = self.url + self.get_ticket_path(ticket_id)
        response = self.do_request(ticket_url)

        # if log form response, session timed out. Login again.
        if not self.is_login_valid(response):
            self.session_start()
            response = self.do_request(ticket_url)

        ticket_data = self.parse_ticket_page(response, ticket_url, ticket_id)
        return ticket_data

    def session_start(self):
        login_url = self.url + self.get_login_path()
        login_data = self.get_login_post_data()
        response = self.do_request(login_url, login_data)

        if not self.is_login_valid(response):
            raise RequestError(_('Login name or password is incorrect. Please check the plugin settings.'))

    def do_request(self, url, post_data=None):

        if post_data is None:
            post_data = {}

        if not self.session:
            self.session = requests.session()

        try:
            response = self.session.post(url, data=post_data)
            return BeautifulSoup.BeautifulSoup(response.content)
        except:
            raise RequestError(_('Page is unreachable. Please check the URL in plugin settings.'))

    @abstractmethod
    def is_login_valid(self, content):
        """Check the content after login"""
        pass

    @abstractmethod
    def parse_ticket_page(self, content, url, ticket):
        return {
            'ticket': ticket,
            'title': '',
            'url': url
        }

    @abstractmethod
    def get_login_path(self):
        """Returned the login URL suffix ()"""
        return "login.php"

    @abstractmethod
    def get_ticket_path(self, ticket_id):
        """Returned the ticket URL suffix ()"""
        return "bug.php?bug=" + ticket_id

    def get_login_post_data(self):
        return {
            'password': self.password,
            'username': self.user
        }


class osTicket(BugTracker):
    def get_ticket_path(self, ticket_id):
        return "tickets.php?id=" + ticket_id

    def is_login_valid(self, soup):
        return soup.findAll('input', attrs={'name': 'passwd'}).__len__() == 0

    def get_login_path(self):
        return "login.php"

    def parse_ticket_page(self, soup, url, ticket):
        ticket_title = soup.find("div", { "id" : "content" }).findAll('h2')[1].text
        ticket_title_text = soup.find('title').text

        return {
            'ticket': ticket_title_text.strip(),
            'title': ticket_title,
            'url': url
        }

    def get_login_post_data(self):
        login_url = self.url + self.get_login_path()
        response = self.do_request(login_url)
        crf = response.find('input', attrs={'name': '__CSRFToken__'}).attrMap['value']
        return {
            'passwd': self.password,
            'username': self.user,
            '__CSRFToken__': crf
        }
