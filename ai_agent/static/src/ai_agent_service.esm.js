import {reactive} from "@odoo/owl";
import {registry} from "@web/core/registry";

/**
 * @typedef {Object} AiAgentDraft
 * @property {Number} agentId
 * @property {String} [resModel] model of the context document
 * @property {Number} [resId] id of the context document
 * @property {String} [resName] name of the context document
 * @property {Object} [viewContext] view the user was looking at, see
 *   getCurrentViewContext
 */

/**
 * AI agents of the user and their conversations for Discuss: sidebar data,
 * drafts of new conversations (created on their first message) and history.
 */
export class AiAgentService {
    constructor(env, services) {
        this.env = env;
        this.orm = services.orm;
        this.store = services["mail.store"];
        this.state = reactive({
            agents: [],
            loaded: false,
            /** @type {AiAgentDraft|null} draft shown in the main panel of Discuss */
            draft: null,
        });
        services.bus_service.subscribe("ai_agent/sessions_changed", () => this.load());
        this.load();
    }

    async load() {
        try {
            this.state.agents = await this.orm.silent.call(
                "ai.agent",
                "get_sidebar_data",
                []
            );
        } catch {
            // No agents for this user (or no ai.agent model, e.g. in the unit
            // tests of other modules): the features of agents stay hidden.
            this.state.agents = [];
        }
        this.state.loaded = true;
    }

    getAgent(agentId) {
        return this.state.agents.find((agent) => agent.id === agentId);
    }

    /** @param {{ partnerId?: number, userId?: number }} person */
    getAgentOfPerson(person) {
        return this.state.agents.find(
            (agent) =>
                (person.partnerId && agent.partner_id === person.partnerId) ||
                (person.userId && agent.user_id === person.userId)
        );
    }

    /**
     * Whether to show conversations in the main panel of Discuss: when it is
     * open, chat windows are hidden.
     */
    get inDiscussPanel() {
        return this.store.discuss.isActive && !this.env.services.ui.isSmall;
    }

    /**
     * Open a new conversation with an agent, without creating anything yet:
     * in the main panel of Discuss when it is open, else in a chat window.
     *
     * @param {AiAgentDraft} draft
     */
    async openDraft(draft) {
        if (draft.resModel && draft.resId && !draft.resName) {
            const [record] = await this.orm.read(
                draft.resModel,
                [draft.resId],
                ["display_name"]
            );
            draft = {...draft, resName: record?.display_name};
        }
        if (this.inDiscussPanel) {
            this.store.discuss.thread = undefined;
            this.state.draft = draft;
            return;
        }
        // As "New message": a single window without thread, which is deleted
        // as soon as it leaves the opened windows of the chat hub.
        let chatWindow = this.store.ChatWindow.get({thread: undefined});
        if (chatWindow) {
            chatWindow.aiDraft = draft;
        } else {
            chatWindow = this.store.ChatWindow.insert({
                thread: undefined,
                aiDraft: draft,
            });
            this.store.chatHub.opened.unshift(chatWindow);
        }
        chatWindow.focus();
    }

    /**
     * Create the conversation of a draft with its first message and open it
     * where the draft was.
     *
     * @param {AiAgentDraft} draft
     * @param {String} body
     * @param {import("models").ChatWindow} [chatWindow] window of the draft
     */
    async startConversation(draft, body, chatWindow) {
        const result = await this.orm.call(
            "ai.agent",
            "action_start_conversation",
            [[draft.agentId], body],
            {
                res_model: draft.resModel || false,
                res_id: draft.resId || false,
                in_chat_window: Boolean(chatWindow),
                view_context: draft.viewContext || false,
            }
        );
        this.store.insert(result.data);
        const thread = this.store.Thread.get({
            model: "discuss.channel",
            id: result.channel_id,
        });
        if (chatWindow) {
            await chatWindow.close();
            thread.openChatWindow();
        } else {
            this.state.draft = null;
            thread.setAsDiscussThread();
        }
        this.load();
        return thread;
    }

    /**
     * Open a session of the sidebar or the history: its conversation (in the
     * main panel of Discuss when it is open, else in a chat window), or the
     * document for the sessions of the chatter.
     */
    async openSession(session) {
        if (session.channel_id) {
            const thread = await this.store.Thread.getOrFetch({
                model: "discuss.channel",
                id: session.channel_id,
            });
            if (!thread) {
                return;
            }
            if (this.inDiscussPanel) {
                thread.setAsDiscussThread();
            } else {
                thread.openChatWindow();
            }
            return;
        }
        this.store.openDocument({model: session.res_model, id: session.res_id});
    }

    async searchSessions(agentId, term, offset, limit) {
        return this.orm.call("ai.agent", "search_sessions", [agentId, term], {
            offset,
            limit,
        });
    }
}

export const aiAgentService = {
    dependencies: ["bus_service", "mail.store", "orm", "ui"],
    start(env, services) {
        return new AiAgentService(env, services);
    },
};

registry.category("services").add("ai_agent", aiAgentService);
