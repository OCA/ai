1. Create an AI connection in *Settings > Technical > AI > AI Connection*
   (administrators only), for example with `ai_connection_openai`. Its model
   must read PDF and images. The connection keeps the key of the provider.
2. In *Message Import > Configuration > Settings*, choose the *AI connection*
   of the company and review the other settings:
   - the days of previous documents sent to the AI to recognise corrections;
   - the maximum size of the files of a message and of a conversation;
   - the transport product, used for the transport charges of the documents;
   - whether the AI chooses the products no rule identifies, and the minimum
     confidence of its choice;
   - the difference allowed between the totals of a document and of its order.
3. In *Message Import > Configuration > AI prompts* (administrators only),
   write the prompts the installed modules need: the reading of the
   conversations, the choice of the products and one description per document
   type. They are created without text: until they are written, the settings
   warn which ones are missing and the conversations are left in error.
4. Give the users that review the documents the group *Message Import Manager*
   and the rights of the orders of each type.
