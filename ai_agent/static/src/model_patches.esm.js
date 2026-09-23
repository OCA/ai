import {ChatWindow} from "@mail/core/common/chat_window_model";
import {Store} from "@mail/core/common/store_service";
import {Thread} from "@mail/core/common/thread_model";
import {DiscussApp} from "@mail/core/public_web/discuss_app_model";
import {DiscussAppCategory} from "@mail/core/public_web/discuss_app_category_model";
import {Record} from "@mail/core/common/record";

import {_t} from "@web/core/l10n/translation";
import {patch} from "@web/core/utils/patch";

export const AI_AGENTS_CATEGORY_ID = "ai_agent.agents";

patch(DiscussApp.prototype, {
    setup() {
        super.setup(...arguments);
        this.aiAgentsCategory = Record.one("DiscussAppCategory", {
            compute() {
                return {
                    extraClass: "o-ai_agent-DiscussSidebarCategory",
                    icon: "fa fa-magic",
                    id: AI_AGENTS_CATEGORY_ID,
                    name: _t("Agents"),
                    // Right after "Direct messages" (30)
                    sequence: 35,
                };
            },
            // No thread belongs to this category: nothing else would ever
            // create it and compute its (lazy) app, which lists it.
            eager: true,
            onUpdate() {
                return this.aiAgentsCategory?.app;
            },
        });
    },
});

patch(DiscussAppCategory.prototype, {
    get isVisible() {
        if (this.id === AI_AGENTS_CATEGORY_ID) {
            return this.store.env.services.ai_agent.state.agents.length > 0;
        }
        return super.isVisible;
    },
});

patch(Thread.prototype, {
    _computeDiscussAppCategory() {
        // AI agent conversations are listed under their agent, by the
        // "Agents" category itself, not as threads of a category.
        if (this.channel_type === "ai_agent") {
            return undefined;
        }
        return super._computeDiscussAppCategory();
    },
    get aiAgent() {
        if (this.channel_type !== "ai_agent") {
            return undefined;
        }
        return this.store.env.services.ai_agent.getAgent(this.ai_agent_id);
    },
    get avatarUrl() {
        const agent = this.aiAgent;
        if (agent) {
            return `/web/image/res.partner/${agent.partner_id}/avatar_128`;
        }
        return super.avatarUrl;
    },
    setAsDiscussThread() {
        this.store.env.services.ai_agent.state.draft = null;
        return super.setAsDiscussThread(...arguments);
    },
});

patch(ChatWindow.prototype, {
    get displayName() {
        if (!this.thread && this.aiDraft) {
            const agent = this.store.env.services.ai_agent.getAgent(
                this.aiDraft.agentId
            );
            return agent?.name ?? _t("New conversation");
        }
        return super.displayName;
    },
});

patch(Store.prototype, {
    /** Agents never get direct messages: open a new conversation instead. */
    async openChat(person) {
        const aiAgent = this.env.services.ai_agent;
        if (!aiAgent.state.loaded) {
            await aiAgent.load();
        }
        const agent = person && aiAgent.getAgentOfPerson(person);
        if (agent) {
            return aiAgent.openDraft({agentId: agent.id});
        }
        return super.openChat(...arguments);
    },
    openNewMessage() {
        const chatWindow = this.ChatWindow.get({thread: undefined});
        if (chatWindow) {
            chatWindow.aiDraft = undefined;
        }
        return super.openNewMessage(...arguments);
    },
});
