import calendar
import sys
import time

def timed(fn):
    def wrapped(*args, **kwargs):
        now = time.time()
        res = fn(*args, **kwargs)
        delta = time.time()-now
        print "\n%s took\t%5.3fs"%(fn.__name__,delta)
        return res
    return wrapped

def skip(fn):
    def wrapped(*args, **kwargs):
        print "Skipping %s"%fn.__name__
        return
    return wrapped

def timestamp():
    n = time.gmtime()
    return calendar.timegm(n)

def get_config_file():
    config_file = "../config.json"
    if len(sys.argv) > 1 and sys.argv[1].endswith("json"):
        config_file = sys.argv[1]
        del sys.argv[1]    
    return config_file

class TemporaryDocument:

    def __init__(self, client):
        self.__client = client
        self.__document = client.create_document(document={'type' : 'Book', 
                                                           'title': 'Document creation test'})
        assert "document_id" in self.__document

    def document(self):
        return self.__document

    def __del__(self):
        response = self.__client.delete_library_document(self.__document["document_id"])
        assert "error" not in response
        
def test_prompt():
    print "\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
    print "!! This test will reset the library of the account used for testing !!"
    print "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n"
    inp = raw_input("If you are okay with this, please type 'yes' to continue: ")
    return inp == "yes"
