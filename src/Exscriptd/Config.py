# Copyright (C) 2007-2010 Samuel Abels.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
import os
import base64
import shutil
from sqlalchemy              import create_engine
from Order                   import Order
from OrderDB                 import OrderDB
from lxml                    import etree
from Exscript                import Account, Queue
from HTTPDaemon              import HTTPDaemon
from PythonService           import PythonService
from ConfigReader            import ConfigReader
from Exscript.AccountManager import AccountManager

default_config_dir = os.path.join('/etc', 'exscriptd')

class Config(ConfigReader):
    def __init__(self, cfg_dir = default_config_dir):
        ConfigReader.__init__(self, os.path.join(cfg_dir, 'main.xml'))
        self.daemons          = {}
        self.account_managers = {}
        self.queues           = {}
        self.cfg_dir          = cfg_dir
        self.service_dir      = os.path.join(cfg_dir, 'services')

    def init_account_pool_from_name(self, name):
        accounts = []
        element  = self.cfgtree.find('account-pool[@name="%s"]' % name)
        for child in element.iterfind('account'):
            user     = child.find('user').text
            password = child.find('password').text
            accounts.append(Account(user, base64.decodestring(password)))
        return accounts

    def init_account_manager_from_name(self, name):
        if self.account_managers.has_key(name):
            return self.account_managers[name]
        accounts = self.init_account_pool_from_name(name)
        manager  = AccountManager(accounts)
        self.account_managers[name] = manager
        return manager

    def init_queue_from_name(self, name, logdir):
        if self.queues.has_key(name):
            return self.queues[name]

        # Create the queue first.
        element     = self.cfgtree.find('queue[@name="%s"]' % name)
        max_threads = element.find('max-threads').text
        delete_logs = element.find('delete-logs') is not None
        queue       = Queue(verbose     = 0,
                            max_threads = max_threads,
                            logdir      = logdir,
                            delete_logs = delete_logs)

        # Add some accounts, if any.
        account_pool = element.find('account-pool')
        if account_pool is not None:
            manager = self.init_account_manager_from_name(account_pool.text)
            queue.account_manager = manager

        self.queues[name] = queue
        return queue

    def init_database_from_name(self, name):
        element = self.cfgtree.find('database[@name="%s"]' % name)
        dbn     = element.find('dbn').text
        #print 'Creating database connection for', dbn
        engine  = create_engine(dbn)
        db      = OrderDB(engine)
        #print 'Initializing database tables...'
        db.install()
        return db

    def load_service(self, filename):
        service_dir = os.path.dirname(filename)
        cfgtree     = ConfigReader(filename).cfgtree
        for element in cfgtree.iterfind('service'):
            name = element.get('name')
            print 'Loading service "%s"...' % name,

            module      = element.find('module').text
            daemon_name = element.find('daemon').text
            daemon      = self.init_daemon_from_name(daemon_name)
            queue_elem  = element.find('queue')
            queue_name  = queue_elem is not None and queue_elem.text
            logdir      = daemon.get_logdir()
            queue       = self.init_queue_from_name(queue_name, logdir)
            service     = PythonService(daemon,
                                        name,
                                        module,
                                        service_dir,
                                        queue = queue)
            daemon.add_service(name, service)
            print 'done.'

    def get_service_files(self):
        files = []
        for file in os.listdir(self.service_dir):
            config_dir = os.path.join(self.service_dir, file)
            if not os.path.isdir(config_dir):
                continue
            config_file = os.path.join(config_dir, 'config.xml')
            if not os.path.isfile(config_file):
                continue
            files.append(config_file)
        return files

    def get_service_file_from_name(self, name):
        for file in self.get_service_files():
            xml     = etree.parse(file)
            element = xml.find('service[@name="%s"]' % name)
            if element is not None:
                return file
        return None

    def load_services(self):
        for file in self.get_service_files():
            service = self.load_service(file)

    def init_rest_daemon(self, element):
        # Init the database for the daemon first, then
        # create the daemon (this does not start it).
        name    = element.get('name')
        address = element.find('address').text or ''
        port    = int(element.find('port').text)
        db_name = element.find('database').text
        logdir  = element.find('logdir').text
        db      = self.init_database_from_name(db_name)
        if not os.path.isdir(logdir):
            os.makedirs(logdir)
        daemon  = HTTPDaemon(name,
                             address,
                             port,
                             database = db,
                             logdir   = logdir)

        # Add some accounts, if any.
        account_pool = element.find('account-pool')
        for account in self.init_account_pool_from_name(account_pool.text):
            daemon.add_account(account)

        return daemon

    def init_daemon_from_name(self, name):
        if self.daemons.has_key(name):
            return self.daemons[name]

        # Create the daemon.
        element = self.cfgtree.find('daemon[@name="%s"]' % name)
        type    = element.get('type')
        if type == 'rest':
            daemon = self.init_rest_daemon(element)
        else:
            raise Exception('No such daemon type: %s' % type)

        self.daemons[name] = daemon
        return daemon

    def init_daemons(self):
        self.load_services()
        return self.daemons.values()
