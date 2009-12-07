import sys, unittest, re, os.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from Exscript            import Queue, Account
from Exscript.Connection import Connection
from Exscript.util       import template
from Exscript.protocols  import Dummy

test_dir = '../templates'

def count_calls(conn, data, **kwargs):
    # Warning: Assertions raised in this function happen in a subprocess!
    assert kwargs.has_key('testarg')
    assert isinstance(conn, Connection)
    data['n_calls'] += 1

class Log(object):
    data = ''
    def collect(self, data):
        self.data += data
        return data

def ios_dummy_cb(conn, **kwargs):
    # Warning: Assertions raised in this function happen in a subprocess!
    log       = Log()
    test_name = conn.get_host().get_name()
    tmpl      = os.path.join(test_dir, test_name, 'test.exscript')
    expected  = os.path.join(test_dir, test_name, 'expected')
    conn.set_on_data_received_cb(log.collect)
    conn.open()
    conn.authenticate(wait = True)
    template.eval_file(conn, tmpl, slot = 10)
    #open(expected, 'w').write(log.data)
    if log.data != open(expected).read():
        print
        print "Expected:", log.data
        print "---------------------------------------------"
        print "Got:", open(expected).read()
    assert log.data == open(expected).read()

class IOSDummy(Dummy):
    def __init__(self, *args, **kwargs):
        #kwargs['echo'] = True
        Dummy.__init__(self, *args, **kwargs)

    def connect(self, test_name, *args, **kwargs):
        filename = os.path.join(test_dir, test_name, 'pseudodev.py')
        self.load_command_handler_from_file(filename)
        return Dummy.connect(self, test_name, *args, **kwargs)

class QueueTest(unittest.TestCase):
    def setUp(self):
        account       = Account('sab', '')
        self.exscript = Queue(verbose = 0, max_threads = 1)
        self.exscript.add_account(account)
        self.exscript.add_protocol('ios', IOSDummy)

    def testStart(self):
        data  = {'n_calls': 0}
        hosts = ['dummy1', 'dummy2']
        self.exscript.run(hosts,    count_calls, data, testarg = 1)
        self.exscript.run('dummy3', count_calls, data, testarg = 1)
        self.exscript.shutdown()
        self.assert_(data['n_calls'] == 3)

        self.exscript.run('dummy4', count_calls, data, testarg = 1)
        self.exscript.shutdown()
        self.assert_(data['n_calls'] == 4)

    def testIOSDummy(self):
        for test in os.listdir(test_dir):
            self.exscript.run('ios:' + test, ios_dummy_cb)

def suite():
    return unittest.TestLoader().loadTestsFromTestCase(QueueTest)
if __name__ == '__main__':
    unittest.TextTestRunner(verbosity = 2).run(suite())