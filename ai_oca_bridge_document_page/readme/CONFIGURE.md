## Configuration Guide

To use this module as intended, two components must be configured:

1. **Bridge configuration on the Odoo side**
2. **An endpoint capable of handling bridge requests**

For an agent to have updated RAG (Retrieval-Augmented Generation) capabilities, you must create at least **three bridges** for each active knowledge database:

- **Bridge with `Usage = "AI Thread Create"`**  
    Adds document pages to the external database used by agents.

- **Bridge with `Usage = "AI Thread Write"`**  
    Updates document pages already on the external database used by agents.

- **Bridge with `Usage = "AI Thread Unlink"`**  
    Removes document pages from the external database when those pages are deleted from Odoo.

For creating those bridges, apart from the usage of the bridge, the user must define:
- Payload Type: it depends on the endpoint configuration, normally "Record" would work.
- Result Type: for this case "No processing" is OK.
- Model: select the "Document Page" model
- Field: add at least the fields the endpoint is expecting on the other side.
- Filter: add a domain for using the bridge only with the documents intended to trigger bridge

For context, you can download an [example n8n workflow JSON file](../static/description/RagCapabilitiesWithOdooKnowledge.json) capable of handling the bridge with `Usage = "AI Thread Create"`. This workflow includes a manual trigger for testing purposes. Remember to update the models and database knowledge as needed.
