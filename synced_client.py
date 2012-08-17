from mendeley_client import *

class SyncStatus:
    Deleted = 0
    Modified = 1
    New = 2
    Synced = 3   

    @staticmethod
    def to_str(status):
        return ["DEL","MOD","NEW","SYN"][status]

class Object:
    pass

class SyncedObject:

    def __init__(self, obj, status=SyncStatus.New):
        self.reset(obj, status)
        
    def reset(self, obj, status):
        self.changes = {}
        self.status = status

        if isinstance(obj, dict):
            self.object = Object()
            for key in obj.keys():
                setattr(self.object, key, obj[key])
        elif isinstance(obj, SyncedObject):
            self.object = obj.object
        else:
            assert False

    def version(self):
        return self.object.version

    def id(self):
        return self.object.id

    def update(self, change):
        if len(change.keys()) == 0:
            return
        # TODO add some checking of the keys etc
        for key, value in change.items():
            self.changes[key] = value
        
        self.status = SyncStatus.Modified

    def apply_changes(self):
        if len(self.changes) == 0:
            return

        for key, value in self.changes.items():
            setattr(self.object, key, value)

    def to_json(self):
        obj = {}

        for key in vars(self.object):
            obj[key] = getattr(self.object,key)

        return obj

    def is_deleted(self):
        return self.status == SyncStatus.Deleted

    def is_modified(self):
        return self.status == SyncStatus.Modified

    def is_new(self):
        return self.status == SyncStatus.New

    def is_synced(self):
        return self.status == SyncStatus.Synced

    def delete(self):
        self.status = SyncStatus.Deleted

    #####
    def local_delete(self):
        self.status = SyncStatus.Deleted
        
    def local_update(self, change):
        self.status = self.Modified
        self.changes.append(obj)
        
        
class SyncedFolder(SyncedObject):
    pass

class SyncedDocument(SyncedObject):

    def __str__(self):
        return self.object.id

from pprint import pprint


class ConflictResolver:

    def resolve_both_updated(self, local_document, server_document):
        raise Exception("Reimplement me")

    def resolve_local_delete_before_update(self, sid, server_document):
        raise Exception("Reimplement me")

class SimpleConflictResolver(ConflictResolver):

    def resolve_local_delete_before_update(self, sid, server_document):
        keep_server_document = True
        return keep_server_document

    def resolve_both_updated(self, local_document, server_document):
        assert isinstance(server_document, SyncedDocument)
        assert isinstance(local_document, SyncedDocument)

        server_changes = {}
        for key in vars(server_document):
            if getattr(server_document, key) != getattr(local_document, key):
                server_changes[key] = getattr(server_document, key)

        local_changes = local_document.changes
        
        for key, server_value in server_changes.items():
            if key not in local_changes:
                # no conflict, just accept the server changes
                setattr(local_document, key, server_value)
            else:
                keep_server_version = self.resolve_conflict(key, local_changes[key], server_value)
                if keep_server_version:
                    setattr(local_document, key, server_value)
                    del local_changes[key]
                else:
                    # the document status will stay modified and will send its
                    # change to the server in sync_documents
                    pass
        
        local_document.object.version = server_document["version"]

        # if no local changes are left, the document isn't modified anymore
        if len(local_changes) == 0:
            local_document.status = SyncStatus.Synced
        else:
            # local changes will be applied in sync_documents
            pass

    def resolve_conflict(self, key, local_version, server_version):
        # dumb "resolution", 
        return False

class DummySyncedClient:

    def __init__(self, config_file="config.json", conflict_resolver=SimpleConflictResolver()):
        self.client = create_client(config_file)
        self.folders = {}
        self.documents = {}
        assert isinstance(conflict_resolver, ConflictResolver)
        self.conflict_resolver = conflict_resolver

    def sync(self):
        success = False
        
        while True:
            # if not self.sync_folders():
            #     continue
            if not self.sync_documents():
                continue
            break

    def fetch_document(self, sid):
        details = self.client.document_details(sid)
        assert "error" not in details
        assert details["id"] == sid  
        return SyncedDocument(details, SyncStatus.Synced)

    def sync_documents(self):
        # TODO fetch the whole library with paging
        # handle new docs in self.documents
        # validate folders before storing, restart sync if unknown folder

        server_documents = self.client.library()
        assert "error" not in server_documents
        server_ids = []
        for server_document in server_documents["documents"]:
            sid = server_document["id"]
            sdoc = SyncedDocument(server_document, SyncStatus.Synced)
            server_ids.append(sid)
            if sid not in self.documents:
                # new document
                self.documents[sid] = self.fetch_document(sid)
                assert self.documents[sid].object.id == sid
                continue
            
            local_document = self.documents[sid]
            assert not local_document.is_new()

            # if server version is more recent
            if local_document.version() != sdoc.version():
                sdoc = self.fetch_document(sid)
                if local_document.is_deleted():
                    keep_server = self.conflict_resolver.resolve_local_delete_remote_update(local_document, sdoc)
                    if keep_server:
                        self.documents[sid].reset(sdoc, SyncStatus.Synced)
                    else:
                        # will be deleted later
                        pass
                    continue

                if local_document.is_synced():
                    # update from server
                    local_document.reset(sdoc, SyncStatus.Synced)
                    continue

                if local_document.is_modified():
                    # both documents are modified, resolve the conflict
                    # by handling the server changes required and leave the local 
                    # changes to be synced later
                    self.conflict_resolver.resolve_both_updated(local_document, sdoc)
                    assert local_document.version() == sdoc.version()
                    continue

                # all cases should have been handled
                assert False

            # both have the same version, so only local changes possible
            else:
                if local_document.is_synced():
                    # nothing to do
                    # assert sdoc == local_document
                    continue

                if local_document.is_deleted():
                    # nothing to do, will be deleted
                    continue

                if local_document.is_modified():
                    # nothing to do, changes will be sent in the update loop
                    continue
                
                # all cases should have been handled
                assert False

        for doc_id in self.documents.keys():
            local_document = self.documents[doc_id]
            assert local_document.object.id == doc_id

            if doc_id not in server_ids:
                if not local_document.is_new():
                    # was deleted on the server
                    del self.documents[doc_id]
                    continue
                else:
                    response = self.client.create_document(document=local_document.to_json())
                    assert "error" not in response

                    local_document.object.version = response["version"]
                    local_document.object.id = response["document_id"]
                    local_document.status = SyncStatus.Synced
                    continue   

            if local_document.is_synced():
                continue                 

            # shouldn't happen, if it's new the server shouldn't know about it
            assert not local_document.is_new()
            assert not local_document.is_synced()

            if local_document.is_deleted():
                response = self.client.delete_library_document(doc_id)
                assert "error" not in response
                del self.documents[doc_id]
                continue

            if local_document.is_modified():
                response = self.client.update_document(doc_id, document=local_document.changes)
                assert "error" not in response
                local_document.status = SyncStatus.Synced
                local_document.object.version = response["version"]
                local_document.apply_changes()
                continue

            assert False

        return True

    def reset(self):
        self.documents = {}
        self.folders = {}

    def dump_status(self,outf):
        outf.write( "\n")
        outf.write( "#Documents (%d)\n"%len(self.documents))
        outf.write( "@sort 0\n")
        outf.write( "@group 0\n")
        outf.write( "--\n")
        outf.write( "status, id, version, title\n")
        if len(self.documents):

            for sid, document in self.documents.items():
                outf.write( "%s,  %s ,  %s , %s\n"%(SyncStatus.to_str(document.status), document.object.id, document.version(), document.object.title))
        
