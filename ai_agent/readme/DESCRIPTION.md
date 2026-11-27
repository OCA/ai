AI agents backed by a user, chatting through Discuss and `mail.message`.

Each conversation with an agent is its own Discuss channel, private to the
user and the agent, like the chats of ChatGPT or Gemini:

- the *Agents* category of the Discuss sidebar lists the agents: a click on
  one starts a new conversation, its last conversations unfold below it and
  *Search more…* finds any older one;
- the robot menu of the top bar does the same from any screen, in chat
  windows, and the new conversations get the view being looked at as
  context: model, view type, record of a form view, domain, groupings and
  filters;
- the agent also answers when mentioned on the chatter of any record;
- conversations are created with their first message and get a title
  summarized by the AI after the first answer.

Agents never get direct messages: they are hidden from the searches to
start a conversation, and *Send message* on an agent opens a new
conversation instead.

The answer is computed in the background: posting a message never waits
for the AI. While working, the agent shows what it is doing, live and kept
out of what is sent back to the AI: *Thinking...* while the AI answers,
becoming its collapsible reasoning, and a note per tool while it runs,
ticked when done. Answers written in Markdown are rendered in the chat.

Skills (`ai.skill`) can be preloaded in the system prompt of an agent.
