import sys
import unittest
import os

parent_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),"..")
os.sys.path.insert(0, parent_dir) 
from mendeley_client import *

class TestMendeleyClient(unittest.TestCase):

    def clear_groups(self):
        for group in self.client.groups():
            self.client.delete_group(group["id"])
    
    def clear_folders(self):
        for folder in self.client.folders():
            self.client.delete_folder(folder["id"])

    def clear_library(self):
        for doc in self.client.library()["document_ids"]:
            self.client.delete_library_document(doc)

    def is_folder(self, folder_id):
        ret = [f for f in self.client.folders() if f["id"] == folder_id]
        return len(ret) == 1

    @classmethod
    def setUpClass(self):
        # Load the configuration file
        config = MendeleyClientConfig(filename="config.json")
        if not config.is_valid():
            print "Please edit config.json before running this script"
            sys.exit(1)

        # create a client and load tokens from the pkl file
        self.client = MendeleyClient(config.api_key, config.api_secret)
        tokens_store = MendeleyTokensStore()

        # configure the client to use a specific token
        # if no tokens are available, prompt the user to authenticate
        access_token = tokens_store.get_access_token("test_account")
        if not access_token:
            self.client.interactive_auth()
            tokens_store.add_account("test_account",self.client.get_access_token())
        else:
            self.client.set_access_token(access_token)

    def tearDown(self):
        self.clear_folders()
        self.clear_groups()
        self.clear_library()
        
    ## Test Groups ##

    def test_create_group_valid(self):
        self.client.create_group(group=json.dumps({"name":"teawdst", "type":"open"}))
        self.client.create_group(group=json.dumps({"name":"test", "type":"open"}))
        rep = self.client.create_group(group=json.dumps({"name":"testtt", "type":"open"}))
        self.assertTrue("error" not in rep)

    def test_create_restricted_groups(self):
        types = ["private", "invite"]

        for group_type1 in types:
            first_group = self.client.create_group(group=json.dumps({"name":"test", "type":group_type1}))
            self.assertTrue("group_id" in first_group)

            for group_type2 in types:
                response = self.client.create_group(group=json.dumps({"name":"test", "type":group_type2}))
                self.assertTrue("error" in response and "group" in response["error"])
            self.client.delete_group(first_group["group_id"])
   
    def test_create_group_validI(self):
        self.client.create_group(group=json.dumps({"name":"teawdst", "type":"open"}))
        rep = self.client.create_group(group=json.dumps({"name":"testtt", "type":"invite"}))
        self.assertTrue("error" not in rep)

    def test_create_group_validP(self):
        self.client.create_group(group=json.dumps({"name":"teawdst", "type":"open"}))
        rep = self.client.create_group(group=json.dumps({"name":"testtt", "type":"private"}))
        self.assertTrue("error" not in rep)

    ## Test Folder ##

    def test_create_folder_invalid(self):
        self.clear_folders()
        self.client.create_folder(folder=json.dumps({"name": "test"}))
        rep = self.client.create_folder(folder=json.dumps({"name": "test"}))
        self.assertFalse("error" in rep)

    def test_create_folder_valid(self):
        folder_name = "test"
        rep = self.client.create_folder(folder=json.dumps({"name": folder_name}))
        folder_id = rep["folder_id"]
        folder_ = [folder for folder in self.client.folders() if folder["id"] == folder_id]
        self.assertEquals(folder_name, folder_[0]["name"])
        
    def test_delete_folder_valid(self):
        folder_name = "test"
        rep = self.client.create_folder(folder=json.dumps({"name": folder_name}))
        folder_id = rep["folder_id"]
        resp = self.client.delete_folder(folder_id)
        self.assertTrue("error" not in rep)

    def test_delete_folder_invalid(self):
        folder_name = "test"
        rep = self.client.create_folder(folder=json.dumps({"name": folder_name}))
        folder_id = rep["folder_id"]
        self.assertTrue("error" in self.client.delete_folder(folder_id+"some string"))
        self.assertTrue("error" in self.client.delete_folder("1234567890123"))
        self.assertTrue("error" in self.client.delete_folder("-1234567890123"))
        self.assertTrue("error" in self.client.delete_folder("-1"))
        self.assertTrue("error" in self.client.delete_folder(""))
        self.assertTrue("error" in self.client.delete_folder("some string"))

    def test_parent_folder(self):
        parent_id = None
        folder_ids = []
        
        # create top level folder and 3 children 
        for i in range(4):
            data={"name": "folder_%d"%i}
            if parent_id:
                data["parent"] = parent_id
            folder = self.client.create_folder(folder=json.dumps(data))
            self.assertTrue("folder_id" in folder)
            if parent_id:
                self.assertTrue("parent" in folder and str(folder["parent"]) == parent_id)

            # update the list of folder_ids
            folder_ids.append(folder["folder_id"])
            parent_id = folder_ids[-1]
        
        # delete last folder and check it"s gone and that its parent still exists
        response = self.client.delete_folder(folder_ids[-1]) 
        self.is_folder(folder_ids[-1])
        del folder_ids[-1]
        self.assertTrue("error" not in response)

        # add another folder on the bottom and delete its parent
        # check both are deleted and grandparent still ok
        parent_id = folder_ids[-1]
        grandparent_id = folder_ids[-2]

        #  Create the new folder
        folder = self.client.create_folder(folder=json.dumps({"name":"folder_4", "parent":parent_id}))
        new_folder_id = folder["folder_id"]
        folder_ids.append(new_folder_id)
        self.assertTrue("parent" in folder and str(folder["parent"]) == parent_id)
        
        #  Delete the parent and check the parent and new folder are deleted
        deleted = self.client.delete_folder(parent_id)
        self.assertTrue("error" not in deleted)
        self.assertFalse(self.is_folder(new_folder_id))
        del folder_ids[-1] # new_folder_id
        self.assertFalse(self.is_folder(parent_id))
        del folder_ids[-1] # parent_id
        self.assertTrue(self.is_folder(grandparent_id))
        
        # delete top level folder and check all children are deleted
        top_folder = self.client.delete_folder(folder_ids[0])
        for folder_id in folder_ids:
            self.assertFalse(self.is_folder(folder_id))
        
        self.assertEqual(len(self.client.folders()), 0)

    ## Test Other ##

    def test_add_doc_to_folder_valid(self):
        document = self.client.create_document(document=json.dumps({"type" : "Book","title": "doc_test", "year": 2025}))
        doc_id = document["document_id"]
        folder = self.client.create_folder(folder=json.dumps({"name": "Test"}))
        folder_id = folder["folder_id"]
        response = self.client.add_document_to_folder(folder_id, doc_id)
        self.assertTrue("error" not in response )

    def test_add_doc_to_folder_invalid(self):
        document = self.client.create_document(document=json.dumps({"type" : "Book","title": "doc_test", "year": 2025}))
        document_id = document["document_id"]
        self.assertTrue("error" in self.client.add_document_to_folder("invalid_folder_id", document_id))
        self.assertTrue("error" in self.client.add_document_to_folder("5", document_id))
        self.assertTrue("error" in self.client.add_document_to_folder("-1", document_id))

        folder = self.client.create_folder(folder=json.dumps({"name": "Test"}))
        self.assertTrue("error" not in folder)

        folder_id = folder["folder_id"]
        self.assertTrue("error" in self.client.add_document_to_folder(folder_id, "invalid_document_id"))
        self.assertTrue("error" in self.client.add_document_to_folder(folder_id, "5"))
        self.assertTrue("error" in self.client.add_document_to_folder(folder_id, "-1"))

    def test_download_invalid(self):
        self.assertTrue("error" in self.client.download_file("liawhawdd", "ouaawdawdd"))

    

if __name__ == "__main__":
    unittest.main()
