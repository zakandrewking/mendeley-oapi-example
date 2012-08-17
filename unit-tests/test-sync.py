import os
import sys
import unittest

from utils import *
parent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
os.sys.path.insert(0, parent_dir) 
from synced_client import *

debug = True 

class TestDocumentsSyncing(unittest.TestCase):

    def log(self, message):
        if debug:
            self.log_file.write("\n#%s\n"%message)
            self.log_file.write("#"+"-"*len(message)+"\n\n")
            self.sclient.dump_status(self.log_file)

    def clear_library(self):
        for doc in self.sclient.client.library()["document_ids"]:
            self.sclient.client.delete_library_document(doc)

    def seed_library(self, count):
        ids = []
        for i in range(count):
            response = self.sclient.client.create_document(document={"type":"Book", "title":"Title %d"%i})
            ids.append(response["document_id"])
        self.assertEqual(len(ids), count)
        return ids

    def document_exists(self, document_id):
        return "error" not in self.sclient.client.document_details(document_id)
      
    def setUp(self):
        self.sclient = DummySyncedClient("../config_sync.json")
        self.clear_library()
        self.log_file = open("/tmp/log.txt","w")
        
    def tearDown(self):
        pass

    @skip
    def test_fetch(self):
        count = 5
        ids = self.seed_library(count)
        
        # sync, should have count documents with matching ids
        self.sclient.sync()
        self.assertEqual(len(self.sclient.documents), count)
        self.assertEqual(sorted(ids), sorted(self.sclient.documents.keys()))

        # the status of all documents should be synced
        for document in self.sclient.documents.values():
            self.assertTrue(document.is_synced())

    @skip
    def test_local_delete(self):
        count = 5
        ids = self.seed_library(count)
        self.sclient.sync()

        # locally delete 1 document
        deletion_id = ids[count/2]
        local_document = self.sclient.documents[deletion_id]
        local_document.delete()
        # the status of the document should be deleted, the count
        # should stay the same until synced
        self.assertTrue(local_document.is_deleted())
        self.assertEqual(len(self.sclient.documents), count)
        
        # check that the status of the documents are correct
        for docid, document in self.sclient.documents.items():
            if docid == deletion_id:
                self.assertTrue(document.is_deleted())
            else:
                self.assertTrue(document.is_synced())
        self.log("After local delete")

        # sync the deletion
        self.sclient.sync()
        self.log("After sync")
        
        # make sure the document doesn't exist anymore 
        self.assertEqual(len(self.sclient.documents), count-1)
        self.assertTrue(deletion_id not in self.sclient.documents.keys())

        # make sure the other documents are unaffected
        for document in self.sclient.documents.values():
            self.assertTrue(document.is_synced())
            self.assertTrue(document.id() in ids)
            self.assertTrue(document.id() != deletion_id)
        
        # check on the server that the deletion was done
        for doc_id in ids:
            if doc_id == deletion_id:
                self.assertFalse(self.document_exists(doc_id))
            else:
                self.assertTrue(self.document_exists(doc_id))
        
    @skip
    def test_server_delete(self):
        count = 5 
        ids = self.seed_library(count)
        self.sclient.sync()

        # delete one doc on the server
        self.sclient.client.delete_library_document(ids[0])
        self.assertFalse(self.document_exists(ids[0]))

        self.sclient.sync()
        self.log("After sync")
        self.assertEqual(len(self.sclient.documents), count-1)
        self.assertTrue(ids[0] not in self.sclient.documents.keys())

        for doc_id in ids[1:]:
            self.assertTrue(doc_id in self.sclient.documents.keys())
            self.assertTrue(self.sclient.documents[doc_id].is_synced())
        

    # @skip            
    # def test_nop(self):
    #     pass

    # @skip            
    # def test_local_update_remote_delete(self):
    #     pass

    # @skip            
    # def test_local_update_remote_update_conflict(self):
    #     pass

    # @skip            
    def test_local_update_remote_update_no_conflict(self):
        pass

    @skip            
    def test_local_update(self):
        new_title = "updated_title"

        count = 5 
        ids = self.seed_library(count)
        self.sclient.sync()     

        # change the title of one document
        local_document = self.sclient.documents[ids[0]]
        local_document.update({"title":new_title})

        original_version = local_document.version()
        
        # the document should be marked as modified
        self.assertTrue(local_document.is_modified())
        for doc_id in ids[1:]:
            self.assertTrue(self.sclient.documents[doc_id].is_synced())
        
        self.log("Before sync")
        self.sclient.sync()
        self.log("After sync")

        # all documents should be synced now
        for doc_id in ids:
            self.assertTrue(self.sclient.documents[doc_id].is_synced())
            self.assertTrue(self.document_exists(doc_id))

        self.assertEqual(local_document.object.title, new_title)
        self.assertTrue(local_document.version() > original_version)
        
        details = self.sclient.client.document_details(ids[0])
        self.assertEqual(details["title"], new_title)
        self.assertEqual(details["version"], local_document.version())
        

    @skip            
    def test_remote_update(self):
        new_title = "updated_title"

        count = 5 
        ids = self.seed_library(count)
        self.sclient.sync()        
        
        local_document = self.sclient.documents[ids[0]]
        original_version = self.sclient.documents[ids[0]].version()

        # update the title of a document on the server
        response = self.sclient.client.update_document(ids[0], document={"title":new_title})
        self.assertTrue("error" not in response)

        # make sure the title was updated on the server
        details = self.sclient.client.document_details(ids[0])
        self.assertEqual(details["title"], new_title)  
      
        self.sclient.sync()

        # all documents should be synced
        for doc_id in ids:
            self.assertTrue(self.sclient.documents[doc_id].is_synced())
            self.assertTrue(self.document_exists(doc_id))       

        self.assertEqual(local_document.object.title, new_title)
        self.assertTrue(local_document.version() > original_version)            
        
        


if __name__ == "__main__":
    unittest.main()
